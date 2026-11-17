"""Tests for overlap-free planning, task suggestions, Gemini validation and fallbacks."""
import pytest

import llm_suggester
from pawpal_system import Owner, Pet, Scheduler, Task
from pet_tasks import COMMON_TASKS, SPECIES, SPECIES_TASKS, tasks_for


def make(availability=90, *tasks, species="dog"):
    owner = Owner("Sam", availability)
    pet = Pet("Rex", species)
    owner.pets.append(pet)
    for t in tasks:
        pet.add_task(t)
    scheduler = Scheduler(owner)
    scheduler.generate_plan()
    return owner, pet, scheduler


# ---- pet_tasks source of truth -------------------------------------------------

@pytest.mark.parametrize("species", SPECIES)
def test_each_species_has_five_common_plus_three_unique_low_priority_tasks(species):
    tasks = tasks_for(species)
    assert len(COMMON_TASKS) == 5 and len(SPECIES_TASKS[species]) == 3 and len(tasks) == 8
    assert all(t["priority"] == "low" and t["duration"] > 0 for t in tasks)


# ---- overlap-free generate_plan ------------------------------------------------

def test_generate_plan_skips_lower_priority_task_that_overlaps_a_higher_one():
    _, _, s = make(
        120,
        Task("walk", "x", 30, "high", preference="08:00"),
        Task("feed", "x", 10, "medium", preference="08:15"),   # overlaps walk
        Task("play", "x", 10, "low", preference="08:30"),      # starts exactly when walk ends
    )
    assert [t.name for t in s.scheduled_items] == ["walk", "play"]
    assert [t.name for t in s.conflict_skipped] == ["feed"]
    assert s.detect_conflicts() == []
    assert "overlaps a higher-priority task" in s.explain()


def test_untimed_tasks_never_conflict():
    _, _, s = make(60, Task("a", "x", 10, "high"), Task("b", "x", 10, "high"))
    assert len(s.scheduled_items) == 2 and s.conflict_skipped == []


# ---- find_overlaps ------------------------------------------------------------

@pytest.mark.parametrize("start,duration,expected", [
    ("07:15", 10, ["walk"]),      # inside
    ("06:50", 30, ["walk"]),      # runs into the start
    ("07:30", 10, []),            # back-to-back after walk is fine
    ("06:50", 10, []),            # ends exactly as walk starts
    ("08:00", 90, ["vet"]),       # swallows vet
])
def test_find_overlaps(start, duration, expected):
    _, _, s = make(
        180,
        Task("walk", "x", 30, "high", preference="07:00"),
        Task("vet", "x", 20, "high", preference="09:00"),
    )
    assert [t.name for t in s.find_overlaps(start, duration)] == expected


def test_find_overlaps_rejects_malformed_time():
    _, _, s = make(60)
    with pytest.raises(ValueError):
        s.find_overlaps("noon", 10)


# ---- rule-based suggest_tasks -------------------------------------------------

def test_suggestions_fit_free_minutes_and_never_overlap_the_plan():
    _, _, s = make(90, Task("walk", "x", 30, "high", preference="07:00"),
                   Task("vet", "x", 20, "high", preference="07:40"))
    sugg = s.suggest_tasks()
    assert sugg and sum(t.duration for t in sugg) <= 90 - 50
    assert all(t.suggested and t.source == "rules" and t.priority == "low" and t.reason for t in sugg)
    for t in sugg:
        assert s.find_overlaps(t.preference, t.duration) == []
    # suggestions don't overlap each other either
    spans = sorted((int(t.preference[:2]) * 60 + int(t.preference[3:]),
                    int(t.preference[:2]) * 60 + int(t.preference[3:]) + t.duration) for t in sugg)
    assert all(a_end <= b_start for (_, a_end), (b_start, _) in zip(spans, spans[1:]))


def test_no_suggestions_when_day_is_full():
    _, _, s = make(30, Task("walk", "x", 30, "high", preference="07:00"))
    assert s.suggest_tasks() == []


def test_suggestions_skip_existing_pending_and_declined_tasks():
    _, _, s = make(120, Task("feeding", "x", 10, "high", preference="08:00"))
    names = {t.name for t in s.suggest_tasks(declined={("Rex", "walk")})}
    assert "Feeding" not in names and "Walk" not in names


def test_accepted_suggestion_is_added_to_pet_and_planned_without_conflict():
    owner, pet, s = make(90, Task("walk", "x", 30, "high", preference="07:00"))
    first = s.suggest_tasks()[0]
    pet.add_task(first)
    s.generate_plan()
    assert first in s.scheduled_items and first.suggested
    assert s.detect_conflicts() == []


# ---- Gemini idea validation ---------------------------------------------------

def idea(**kw):
    base = {"pet_name": "Rex", "name": "Sniff walk", "duration": 10, "time": "08:00", "reason": "Fun."}
    return {**base, **kw}


def test_build_suggestions_drops_invalid_ideas():
    _, _, s = make(60, Task("walk", "x", 30, "high", preference="07:00"))
    bad = [
        idea(pet_name="Ghost"),            # unknown pet
        idea(name="   "),                  # blank name
        idea(name="walk"),                 # already pending
        idea(duration=0),                  # non-positive
        idea(duration=500),                # longer than free time
        idea(duration="10"),               # wrong type
        "not a dict",
    ]
    assert s.build_suggestions(bad) == []


def test_build_suggestions_relocates_overlapping_or_bad_times_and_respects_budget():
    _, _, s = make(60, Task("walk", "x", 30, "high", preference="07:00"))  # 30 min free
    out = s.build_suggestions([
        idea(name="A", time="07:10"),      # overlaps walk -> moved
        idea(name="B", time="nonsense"),   # bad time -> moved
        idea(name="C", time="23:55"),      # would run past the window -> moved
        idea(name="D"),                    # 4th would exceed the 30 free minutes
    ])
    assert [t.name for t in out] == ["A", "B", "C"]
    assert all(s.find_overlaps(t.preference, t.duration) == [] for t in out)
    assert all(t.source == "gemini" and t.suggested for t in out)


def test_build_suggestions_removes_declined_and_duplicates():
    _, _, s = make(60)
    out = s.build_suggestions(
        [idea(name="A"), idea(name="a"), idea(name="B")], declined={("Rex", "b")}
    )
    assert [t.name for t in out] == ["A"]


# ---- LLM layer: fallbacks, never a real network call --------------------------

def test_propose_without_api_key_raises_unavailable(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    _, _, s = make(60)
    with pytest.raises(llm_suggester.LLMUnavailable):
        llm_suggester.propose(s)


def test_generate_retries_temporary_errors_then_succeeds(monkeypatch):
    from google.genai import errors
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(llm_suggester.time, "sleep", lambda _: None)
    calls = []

    class Resp:
        text = "hello"

    class Models:
        def generate_content(self, **kw):
            calls.append(1)
            if len(calls) < 3:
                raise errors.ServerError(503, {"error": {"message": "busy"}})
            return Resp()

    class Client:
        def __init__(self, **kw):
            self.models = Models()

    monkeypatch.setattr("google.genai.Client", Client)
    assert llm_suggester._generate("hi", {}) == "hello" and len(calls) == 3


def test_generate_does_not_retry_permanent_errors(monkeypatch):
    from google.genai import errors
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    calls = []

    class Models:
        def generate_content(self, **kw):
            calls.append(1)
            raise errors.ClientError(404, {"error": {"message": "gone"}})

    class Client:
        def __init__(self, **kw):
            self.models = Models()

    monkeypatch.setattr("google.genai.Client", Client)
    with pytest.raises(llm_suggester.LLMUnavailable):
        llm_suggester._generate("hi", {})
    assert len(calls) == 1


def test_explain_plan_is_capped_at_four_sentences(monkeypatch):
    _, _, s = make(60, Task("walk", "x", 30, "high", preference="07:00"))
    monkeypatch.setattr(
        llm_suggester, "_generate",
        lambda *a, **k: "One. Two! Three? Four. Five. Six.",
    )
    assert llm_suggester.explain_plan(s, []) == "One. Two! Three? Four."


# ---- template explanation (the fallback) --------------------------------------

def test_explain_conversational_is_three_or_four_sentences():
    _, _, s = make(90, Task("walk", "x", 30, "high", preference="07:00"),
                   Task("bath", "x", 40, "low", preference="07:10"))
    text = s.explain_conversational(s.suggest_tasks())
    assert 3 <= text.count(". ") + text.endswith(".") <= 4
    assert "bath" in text.lower() and "walk" not in text.lower().split("leave out")[1]


def test_explain_conversational_when_nothing_left_out_or_suggested():
    _, _, s = make(30, Task("walk", "x", 30, "high", preference="07:00"))
    text = s.explain_conversational([])
    assert "without any overlaps" in text and "spare time" in text
