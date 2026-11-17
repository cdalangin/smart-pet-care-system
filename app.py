from datetime import datetime, time

import streamlit as st
import llm_suggester
from pawpal_system import Owner, Pet, Scheduler, Task


def valid_time(text: str) -> bool:
    """Return True if text is a valid 24-hour HH:MM time."""
    try:
        datetime.strptime(text, "%H:%M")
    except ValueError:
        return False
    return True


st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")

st.markdown(
    """
Welcome to PawPal+!

This is a pet care planning assistant. It helps a pet owner plan care tasks for their pet(s) based on constraints like time, priority, and preferences.
"""
)

st.divider()

st.subheader("Input Pet")
owner_name = st.text_input("Owner name", placeholder="Enter your name")
pet_name = st.text_input("Pet name", placeholder="Enter your pet's name")
species = st.selectbox("Species", ["dog", "cat", "fish", "rabbit", "hamster"])
availability = st.number_input("Time available today (minutes)", min_value=1, max_value=1440, placeholder=90)

if "owner" not in st.session_state:
    st.session_state.owner = Owner(name=owner_name, availability=90)
owner = st.session_state.owner
owner.name = owner_name
owner.availability = int(availability)

if st.button("Add pet"):
    if any(p.name == pet_name for p in owner.pets):
        st.warning(f"{pet_name} already exists.")
    else:
        owner.pets.append(Pet(name=pet_name, species=species))
        st.success(f"Added {pet_name} the {species}.")

if owner.pets:
    st.write("Your pets: " + ", ".join(f"{p.name} ({p.species})" for p in owner.pets))


st.subheader("Input Task")
st.caption("Give a task a preferred time (HH:MM) and set whether it repeats.")

task_pet = st.selectbox("Pet for this task", [p.name for p in owner.pets]) if owner.pets else None

col1, col2, col3 = st.columns(3)
with col1:
    task_title = st.text_input("Task title", value="Morning walk")
with col2:
    duration = st.number_input("Duration (minutes)", min_value=1, max_value=240, value=20)
with col3:
    priority = st.selectbox("Priority", ["low", "medium", "high"], index=2)

col4, col5 = st.columns(2)
with col4:
    preferred_time = st.text_input("Preferred time (HH:MM, optional)", value="")
with col5:
    frequency = st.selectbox("Repeats", ["daily", "weekly", "once"])

if st.button("Add task"):
    time_text = preferred_time.strip()
    if task_pet is None:
        st.warning("Add a pet first.")
    elif time_text and not valid_time(time_text):
        st.warning("Preferred time must look like HH:MM, for example 08:30.")
    else:
        pet = next(p for p in owner.pets if p.name == task_pet)
        try:
            pet.add_task(
                Task(task_title, "general", int(duration), priority,
                     preference=time_text, frequency=frequency)
            )
        except ValueError as err:
            st.warning(str(err))
        else:
            st.success(f"Added '{task_title}' to {task_pet}.")

st.markdown("#### Your tasks")
if "flash" in st.session_state:
    st.success(st.session_state.pop("flash"))

all_tasks = owner.get_all_tasks()
if all_tasks:
    fcol1, fcol2 = st.columns(2)
    with fcol1:
        pet_filter = st.selectbox("Show pet", ["All pets"] + [p.name for p in owner.pets])
    with fcol2:
        status_filter = st.selectbox("Show status", ["All", "Pending", "Completed"])

    visible = Scheduler.sort_by_time(
        owner.filter_tasks(
            pet_name=None if pet_filter == "All pets" else pet_filter,
            completed={"All": None, "Pending": False, "Completed": True}[status_filter],
        )
    )
    if visible:
        st.caption(f"Showing {len(visible)} of {len(all_tasks)} task(s), sorted by time.")
        st.table(
            [
                {
                    "Pet": t.pet_name,
                    "Task": ("💡 " if t.suggested else "") + t.name,
                    "Time": t.preference or "—",
                    "Minutes": t.duration,
                    "Priority": t.priority,
                    "Repeats": t.frequency,
                    "Due": str(t.due_date) if t.due_date else "—",
                    "Status": "✅ Done" if t.completed else "Pending",
                }
                for t in visible
            ]
        )
    else:
        st.info("No tasks match these filters.")

    pending = Scheduler.sort_by_time(owner.filter_tasks(completed=False))
    if pending:
        choice = st.selectbox(
            "Mark a task complete",
            range(len(pending)),
            format_func=lambda i: f"{pending[i].pet_name}: {pending[i].name} ({pending[i].preference or 'any time'})",
        )
        if st.button("Complete task"):
            done = pending[choice]
            next_task = Scheduler(owner=owner).complete_task(done)
            msg = f"Completed '{done.name}' for {done.pet_name}."
            if next_task:
                msg += f" Next {next_task.frequency} occurrence is due {next_task.due_date:%b %d}."
            st.session_state.flash = msg
            st.rerun()
else:
    st.info("No tasks yet. Add one above.")

st.divider()

st.subheader("Build Schedule")
st.caption("Picks tasks by priority until time runs out, then lists them in time order.")

if st.button("Generate schedule"):
    st.session_state.show_plan = True

if st.session_state.get("show_plan"):
    scheduler = Scheduler(owner=owner)
    plan = scheduler.generate_plan()
    used = sum(t.duration for t in plan)

    if plan:
        st.success(f"Schedule generated: {len(plan)} task(s) planned.")
    else:
        st.info("Nothing to schedule. Add tasks that are pending and due today.")

    m1, m2, m3 = st.columns(3)
    m1.metric("Tasks planned", len(plan))
    m2.metric("Minutes used", f"{used} / {owner.availability}")
    m3.metric("Tasks skipped", len(scheduler.skipped_tasks))

    if plan:
        st.table(
            [
                {
                    "Time": t.preference or "—",
                    "Pet": t.pet_name,
                    "Task": t.name,
                    "Minutes": t.duration,
                    "Priority": t.priority,
                    "Source": ("✨ Suggested by Gemini" if t.source == "gemini" else "💡 Suggested") if t.suggested else "Your task",
                }
                for t in plan
            ]
        )

    for warning in scheduler.detect_conflicts():
        st.warning(warning)
    if scheduler.skipped_tasks:
        st.warning(
            "Skipped (not enough time or overlapping a higher-priority task): "
            + ", ".join(f"{t.name} ({t.pet_name}, {t.duration} min)" for t in scheduler.skipped_tasks)
        )

    declined = st.session_state.setdefault("declined", set())
    gemini_ready = llm_suggester.is_configured()
    use_gemini = st.toggle(
        "Use Gemini for suggestions",
        value=False,
        disabled=not gemini_ready,
        help="Needs GEMINI_API_KEY in your .env file." if not gemini_ready else None,
    )
    suggestions = []
    gemini_ok = use_gemini
    if use_gemini:
        # Fetch from Gemini only when something the owner entered changes (availability or
        # their own tasks). Accepting/declining a suggestion must NOT trigger a new call:
        # the already-fetched pool is just filtered and re-validated against the new plan.
        base_key = (
            owner.availability,
            tuple((t.pet_name, t.name, t.preference, t.duration) for t in plan if not t.suggested),
        )
        pool_cache = st.session_state.setdefault("gemini_pool", {})
        if base_key not in pool_cache:
            try:
                with st.spinner("Asking Gemini for suggestions (gives up after 10s)..."):
                    ideas = llm_suggester.propose(scheduler, declined)
                pool_cache[base_key] = scheduler.build_suggestions(ideas, declined)
            except llm_suggester.LLMUnavailable as err:
                pool_cache[base_key] = None
                st.session_state.gemini_error = str(err)
        pool = pool_cache[base_key]
        if pool is None:
            gemini_ok = False
            st.warning(f"⚠️ Gemini unavailable, showing built-in suggestions instead. ({st.session_state.get('gemini_error')})")
            if st.button("Retry Gemini"):
                pool_cache.pop(base_key, None)
                st.rerun()
            suggestions = scheduler.suggest_tasks(declined)
        else:
            # Drop declined/accepted ones and re-check fit and overlaps; no API call here.
            suggestions = scheduler.build_suggestions(
                [{"pet_name": t.pet_name, "name": t.name, "duration": t.duration,
                  "time": t.preference, "reason": t.reason} for t in pool],
                declined,
            )
    else:
        suggestions = scheduler.suggest_tasks(declined)

    if suggestions:
        st.markdown("#### 💡 Suggested tasks")
        st.caption(
            f"You have {owner.availability - used} minutes free. Accept a suggestion to add it "
            "to the schedule, change its start time first if you like, or decline it."
        )
        for i, s in enumerate(suggestions):
            c1, c2, c3, c4 = st.columns([4, 2, 1, 1])
            by = "✨ Gemini" if s.source == "gemini" else "built-in rules"
            c1.write(
                f"💡 **{s.name}** for {s.pet_name} ({s.duration} min, {s.priority} priority) · _{by}_"
                f"\n\n{s.reason}"
            )
            hh, mm = (int(x) for x in s.preference.split(":"))
            # The suggested time is part of the key, so a re-placed suggestion resets the field.
            picked = c2.time_input(
                "Start time", value=time(hh, mm), step=300,
                key=f"time_{s.pet_name}_{s.name}_{s.preference}",
            )
            chosen = f"{picked:%H:%M}"
            clashes = scheduler.find_overlaps(chosen, s.duration)
            past_midnight = picked.hour * 60 + picked.minute + s.duration > 24 * 60
            if clashes:
                st.error(
                    f"{s.name} at {chosen} would overlap "
                    + ", ".join(f"{t.name} ({t.pet_name}, {t.preference})" for t in clashes)
                    + ". Pick a different start time."
                )
            elif past_midnight:
                st.error(f"{s.name} would run past midnight. Pick an earlier start time.")
            blocked = bool(clashes) or past_midnight
            c3.write("")  # line the buttons up with the time field
            if c3.button("Accept", key=f"accept_{i}_{s.pet_name}_{s.name}", disabled=blocked):
                # Re-check on click so a conflicting time can never go through.
                if scheduler.find_overlaps(chosen, s.duration):
                    st.error("That time now conflicts with the schedule.")
                else:
                    s.preference = chosen
                    pet = next(p for p in owner.pets if p.name == s.pet_name)
                    pet.add_task(s)
                    st.session_state.flash = f"Added suggested task '{s.name}' for {s.pet_name} at {s.preference}."
                    st.rerun()
            c4.write("")
            if c4.button("Decline", key=f"decline_{i}_{s.pet_name}_{s.name}"):
                declined.add((s.pet_name, s.name.lower()))
                st.rerun()

    with st.expander("Why this plan?"):
        explanation = None
        if gemini_ok:
            # Same key as the suggestions pool: accepting/declining reuses the same text.
            facts_key = base_key
            explain_cache = st.session_state.setdefault("explain_cache", {})
            if facts_key not in explain_cache:
                try:
                    with st.spinner("Writing explanation..."):
                        explain_cache[facts_key] = llm_suggester.explain_plan(scheduler, suggestions)
                except llm_suggester.LLMUnavailable:
                    explain_cache[facts_key] = None
            explanation = explain_cache[facts_key]
        if explanation:
            st.write(explanation)
            st.caption("✨ Written by Gemini")
        else:
            st.write(scheduler.explain_conversational(suggestions))
            if use_gemini:
                st.caption("Gemini couldn't write this one, so this explanation is from the built-in template.")
