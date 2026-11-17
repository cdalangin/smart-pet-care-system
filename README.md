# PawPal+ 🐾

This project came from the PawPal+ Starter, which is a Streamlit app that helps a pet owner plan care tasks for their pet. The original app lets users input their pets and the tasks they need for each pet, then the app will generate a schedule ordered by the time the user inputted and priorities.

## Summary

PawPal+ is a pet-care planning assistant for pet owners on the go. They can often forget things, double-book themselves, and rarely know what *else* their pet could use. PawPal+ helps with all three:

- **Plans the day.** The owner enters pets, tasks (duration, priority, optional start time) and the minutes they have available. PawPal+ picks tasks by priority, organizes them them by start time, and ensures tasks don't that overlap.
- **Suggests more.** If there is time left over, it proposes extra care tasks for each pet's species and places each one in a free slot. The owner can pick a time to schedule this, and any conflicting times will get blocked.
- **Explains itself.** The schedule builder explains the suggested plan to show what was chosen, what was left out, and why each suggestion was offered.

Suggestions and the explanation can come from **Gemini**, but the app works fully without it by using a built-in rule-based fallback.

## Architecture Overview

Full diagram is in [diagrams/architecture.mmd](diagrams/architecture.mmd).

Original functionality stays the same, which is that user gets to add information about themselves and their pet(s), and tasks they need to fulfill for each pet. 

The UI builds the plan with `Scheduler.generate_plan()`. With the Gemini toggle **off** (default) it calls `suggest_tasks()` and `explain_conversational()`. With the toggle **on** it asks Gemini via `llm_suggester`, then passes Gemini's raw ideas through `Scheduler.build_suggestions()`, which checks them in code before anything is shown. If Gemini fails or times out, the UI shows a warning and falls back to the rule-based path. Accepting a suggestion adds it to the `Pet` and re-plans.

## Setup Instructions

1. **Create and activate a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
3. **(Optional) Enable Gemini.** Get an API key from [Google AI Studio](https://aistudio.google.com/), then create a file named `.env` in this folder:
   ```
   GEMINI_API_KEY=your-key-here
   # Optional, defaults to gemini-3.8-flash:
   # GEMINI_MODEL=gemini-3.8-flash
   ```
   `.env` is git-ignored. Without a key, the Gemini toggle is disabled and the app uses the built-in rules.
4. **Run the app**
   ```bash
   streamlit run app.py
   ```
5. **Use it:** add an owner and a pet, add tasks, click **Generate schedule**. Turn on **Use Gemini for suggestions** if you configured a key.
6. **Run the tests**
   ```bash
   python -m pytest
   ```
7. **Command-line demo (no UI):** `python main.py`

## Sample Interactions

These outputs were produced by running the code without a Gemini API key, so these show the rule-based path that Gemini falls back to.

### 1. Overlapping tasks: the lower-priority one is skipped

**Input:** Jordan has 90 minutes. Biscuit the dog has *Morning walk* (30 min, high, 08:00), *Flea treatment* (5 min, medium, 08:15) and *Brush teeth* (5 min, low, 09:00).

**Output:**
```
08:00 Morning walk (30 min, high)
09:00 Brush teeth (5 min, low)

Scheduled 35 of 90 minutes (55 left).
  + Morning walk for Biscuit at 08:00: high priority, fits in 30 min.
  + Brush teeth for Biscuit at 09:00: low priority, fits in 5 min.
  - Flea treatment for Biscuit skipped: needs 5 min (medium priority) but its
    time slot at 08:15 overlaps a higher-priority task.
```

### 2. Suggestions for the leftover 55 minutes, with reasons

**Output (first three suggestions, reasons abridged):**
```
07:00 Fresh water check (5 min)       Biscuit has no pending task for it, it fits in the 55 unused minutes, 07:00 is a free slot
07:05 Feeding (10 min)                same reasoning, 50 unused minutes, 07:05 free
07:15 Cuddle or bonding time (15 min) same reasoning, 40 unused minutes, 07:15 free
```
Each appears as a card with an editable start time, an **Accept** button and a **Decline** button.

**"Why this plan?" text (template fallback, 4 sentences):**
> You have 90 minutes today, and I scheduled 2 tasks using 35 of them, choosing the highest-priority tasks first and then ordering them by time. I had to leave out Flea treatment for Biscuit because it either overlapped a more important task or didn't fit in your time. Since you still have 55 minutes free, I'm suggesting Fresh water check for Biscuit and 2 more. For example, fresh water check is a routine care task for any pet that Biscuit has no pending task for, it fits in the 55 unused minutes, and 07:00 is a free slot that overlaps nothing else.

### 3. Editing a suggestion's start time

**Input:** the owner moves the first suggestion from 07:00 to 08:10.

**Output:**
```
08:10 -> BLOCKED: overlaps Morning walk (08:00)     (Accept is disabled, red message shown)
07:00 -> accepted
```

### 4. Gemini unavailable

If the key is missing, the request times out after 10 seconds, or Google returns a busy error, the app shows
`⚠️ Gemini unavailable, showing built-in suggestions instead. (<reason>)` with a **Retry Gemini** button, and Examples 2 and 3 above still work.

> **Live Gemini output isn't included.** I couldn't call the real API while writing this. With a key set, the suggestion cards show "✨ Gemini" and a model-written reason, and the explanation shows "✨ Written by Gemini". 

## Design Decisions

- **Greedy scheduling, not an optimizer.** Tasks are taken in priority order to fit as much as it can, though it's not guaranteed to pack the day perfectly.
- **Overlaps are prevented, not just warned about.** `generate_plan` skips a task whose time window overlaps a higher-priority one already chosen. The trade-off is that a lower-priority task can silently drop out, so the skip is shown in the plan and the explanation. `detect_conflicts` stays as a lightweight check.
- **Every AI feature has a non-AI fallback.** Both suggestions and the explanation fall back to rule-based versions. The cost is two code paths to maintain.
- **Gemini is off by default and time-boxed.** A call has a hard 10-second budget, so a slow API can't freeze the page. The trade-off is that a slow but working response will not be seen.
- **Suggested tasks are always low priority and one-time.** Taken from `pet_tasks.py`, so they never push out the owner's own tasks. Suggestions only appear between 07:00 and 21:00 (a constant in `pawpal_system.py`).
- **Start times are plain `HH:MM` text.** Easy to sort and compare, but there are no dates or multi-day schedules.

## Testing Summary

**What worked:** testing the AI layer with a stubbed client, so tests are fast, free and don't need a key.

**What didn't:**
- Making `generate_plan` overlap-free broke an existing test that expected conflicting tasks to stay in the plan. I rewrote it to test `detect_conflicts` on a hand-built plan.
- I couldn't test against the real Gemini API since I kept getting 503 "high demand" errors, and a spinner that hung with no timeout. 

**What I learned:** stubs prove your code's handling of a failure, not that the real service behaves that way. Anything that calls an external service needs a timeout, a retry limit and a visible fallback from the start.

## Reflection

This project taught me how to integrate AI into a project, and that code around it is just as important as the AI functionality. I still needed to make further updates to validate its output, put limits on time and retries, and made sure a failure is visible and the app still works. Building the rule-based version made sure the app still fulfills smart features in case the API fails. I also learned that a feature that "works" in a happy-path demo can still hang, break old tests, or quietly re-spend API calls, and that bugs like these only surface when you run the real thing.

## Reliability and Evaluation

Run with `python -m pytest`. **43 tests, all passing.**

**What the tests covered**

- **Core scheduling:** marking tasks complete, adding tasks to a pet, rejecting duplicate names and invalid durations or priorities, sorting by time (untimed tasks last), filtering by pet and status, recurring daily and weekly tasks, conflict warnings, and plans that come out in time order.
- **Overlap-free planning:** lower-priority tasks that overlap a higher-priority one are skipped, back-to-back tasks are allowed, and untimed tasks never conflict.
- **Overlap checking:** `find_overlaps` on tasks inside, straddling, adjacent to and swallowing another, plus rejection of malformed times.
- **Suggestions:** they fit the free minutes, don't overlap the plan or each other, skip tasks the pet already has or the owner declined, appear only when there is spare time, and an accepted one is planned without conflict.
- **Pet task list:** each species has 5 common and 3 unique tasks, all low priority.
- **Gemini idea validation:** invalid ideas are dropped, bad or overlapping times are moved to a free slot, and the total never exceeds the free minutes.
- **Failure handling:** a missing API key, temporary errors retried until they succeed, permanent errors not retried, and a long explanation cut to 4 sentences.
- **Explanation fallback:** the template explanation is 3 to 4 sentences, with or without left-out and suggested tasks.