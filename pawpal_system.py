from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from pet_tasks import SPECIES_TASKS, tasks_for

PRIORITIES = ("high", "medium", "low")
RECURRENCE = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1)}
# Suggested tasks are only placed inside this window (minutes since midnight).
SUGGEST_START = 7 * 60
SUGGEST_END = 21 * 60


@dataclass
class Task:
    name: str
    category: str
    duration: int
    priority: str
    pet_name: str = ""
    preference: str = ""
    frequency: str = "daily"
    completed: bool = False
    due_date: date | None = None
    suggested: bool = False  # True when the task came from a suggestion
    reason: str = ""  # why it was suggested (blank for user-created tasks)

    def __post_init__(self) -> None:
        """Reject non-positive durations and unknown priorities."""
        if self.duration <= 0:
            raise ValueError(f"Duration must be positive, got {self.duration}.")
        if self.priority not in PRIORITIES:
            raise ValueError(f"Priority must be one of {PRIORITIES}, got '{self.priority}'.")

    def mark_complete(self) -> None:
        """Mark this task as done."""
        self.completed = True


@dataclass
class Pet:
    name: str
    species: str
    tasks: list[Task] = field(default_factory=list)

    def add_task(self, task: Task) -> None:
        """Add a task to this pet and record the pet's name on it.

        Raises ValueError if the pet already has an incomplete task with the same name.
        """
        if any(t.name.lower() == task.name.lower() and not t.completed for t in self.tasks):
            raise ValueError(f"{self.name} already has a task named '{task.name}'.")
        task.pet_name = self.name
        self.tasks.append(task)


@dataclass
class Owner:
    name: str
    availability: int
    pets: list[Pet] = field(default_factory=list)
    preferences: dict = field(default_factory=dict)

    def get_all_tasks(self) -> list[Task]:
        """Return every task across all of the owner's pets."""
        return [task for pet in self.pets for task in pet.tasks]

    def filter_tasks(self, pet_name: str | None = None, completed: bool | None = None) -> list[Task]:
        """Return tasks matching the given pet name and/or completion status.

        Args:
            pet_name: keep only this pet's tasks (case-insensitive); None means any pet.
            completed: True for finished tasks, False for pending ones; None means both.
        A filter left as None is ignored; passing both requires both to match.
        Returns: matching tasks in the order they were added (empty if none match).
        """
        return [
            t for t in self.get_all_tasks()
            if (pet_name is None or t.pet_name.lower() == pet_name.lower())
            and (completed is None or t.completed == completed)
        ]


@dataclass
class Scheduler:
    owner: Owner
    scheduled_items: list[Task] = field(default_factory=list)
    skipped_tasks: list[Task] = field(default_factory=list)
    conflict_skipped: list[Task] = field(default_factory=list)

    def generate_plan(self) -> list[Task]:
        """Build today's plan from the owner's tasks and store it on the scheduler.

        Algorithm (greedy):
          1. Keep tasks that are not completed and are not due in the future.
          2. Sort them high -> medium -> low priority (stable, so ties keep their order).
          3. Walk the list, taking each task that still fits in the remaining minutes
             of the owner's availability; tasks that don't fit are skipped. A task
             with a preferred time is also skipped if its [start, start+duration)
             window overlaps one already chosen (higher priority wins). Tasks
             without a preferred time never conflict.
          4. Order the chosen tasks by preferred time with sort_by_time.

        Side effects: replaces scheduled_items and skipped_tasks.
        Returns: the scheduled tasks, in time order.
        """
        by_priority = sorted(
            (
                t for t in self.owner.get_all_tasks()
                if not t.completed and (t.due_date is None or t.due_date <= date.today())
            ),
            key=lambda t: PRIORITIES.index(t.priority),
        )
        self.scheduled_items = []
        self.skipped_tasks = []
        self.conflict_skipped = []
        minutes_left = self.owner.availability
        taken: list[tuple[int, int]] = []  # (start, end) in minutes since midnight
        for task in by_priority:
            interval = None
            if task.preference:
                hours, minutes = (int(p) for p in task.preference.split(":"))
                start = hours * 60 + minutes
                interval = (start, start + task.duration)
                if any(interval[0] < end and start_ < interval[1] for start_, end in taken):
                    self.skipped_tasks.append(task)
                    self.conflict_skipped.append(task)
                    continue
            if task.duration <= minutes_left:
                self.scheduled_items.append(task)
                minutes_left -= task.duration
                if interval:
                    taken.append(interval)
            else:
                self.skipped_tasks.append(task)
        self.scheduled_items = self.sort_by_time(self.scheduled_items)
        return self.scheduled_items

    def detect_conflicts(self) -> list[str]:
        """Warn about scheduled tasks that share the same start time.

        Lightweight check: scheduled_items are grouped by their 'HH:MM' preference
        (compared as numbers, so '8:00' and '08:00' count as the same time) and
        each group with more than one task yields a message. It works across pets
        and within one pet. Tasks without a preferred time are ignored, and only
        identical start times count: overlapping but different times are not flagged.

        Call after generate_plan. Nothing is raised or rearranged.
        Returns: one warning string per clashing time, or an empty list.
        """
        by_start: dict[tuple[int, ...], list[Task]] = {}
        for t in self.scheduled_items:
            if t.preference:
                start = tuple(int(part) for part in t.preference.split(":"))
                by_start.setdefault(start, []).append(t)
        return [
            f"Warning: {len(group)} tasks at {group[0].preference}: "
            + ", ".join(f"{t.name} ({t.pet_name})" for t in group)
            for group in by_start.values()
            if len(group) > 1
        ]

    def suggest_tasks(self, declined: set[tuple[str, str]] | None = None, max_suggestions: int = 5) -> list[Task]:
        """Suggest extra tasks to fill leftover availability, each with a free time slot.

        Call after generate_plan. Candidates come from pet_tasks.tasks_for(species).
        A candidate is skipped if the pet already has a pending task with that name,
        it was declined, it needs more minutes than remain, or no gap of its length
        exists between SUGGEST_START and SUGGEST_END without overlapping a timed
        scheduled task (or an earlier suggestion). Each pick is placed at the earliest
        such gap.

        Args:
            declined: (pet_name, task_name) pairs the user already rejected (lowercase names).
            max_suggestions: cap on how many suggestions to return.
        Returns: new Tasks (suggested=True, preference set to 'HH:MM'); nothing is
        added to any pet until the caller accepts one via Pet.add_task.
        """
        declined = declined or set()
        minutes_left = self.owner.availability - sum(t.duration for t in self.scheduled_items)
        taken = sorted(
            (start, start + t.duration)
            for t in self.scheduled_items if t.preference
            for start in [self._to_minutes(t.preference)]
        )
        suggestions: list[Task] = []
        for pet in self.owner.pets:
            pending = {t.name.lower() for t in pet.tasks if not t.completed}
            for spec in tasks_for(pet.species):
                if len(suggestions) >= max_suggestions:
                    return suggestions
                name = spec["name"]
                if name.lower() in pending or (pet.name, name.lower()) in declined:
                    continue
                if spec["duration"] > minutes_left:
                    continue
                start = self._find_gap(taken, spec["duration"])
                if start is None:
                    continue
                kind = (
                    f"a {pet.species}-specific care task"
                    if spec in SPECIES_TASKS[pet.species]
                    else "a routine care task for any pet"
                )
                time = f"{start // 60:02d}:{start % 60:02d}"
                suggestions.append(Task(
                    name, "suggested", spec["duration"], spec["priority"],
                    pet_name=pet.name, preference=time, frequency="once", suggested=True,
                    reason=(
                        f"{name} is {kind} that {pet.name} has no pending task for, "
                        f"it fits in the {minutes_left} unused minutes, and {time} is a "
                        f"free slot that overlaps nothing else."
                    ),
                ))
                taken.append((start, start + spec["duration"]))
                taken.sort()
                minutes_left -= spec["duration"]
        return suggestions

    @staticmethod
    def _to_minutes(hhmm: str) -> int:
        """Convert 'HH:MM' to minutes since midnight."""
        hours, minutes = (int(p) for p in hhmm.split(":"))
        return hours * 60 + minutes

    @staticmethod
    def _find_gap(taken: list[tuple[int, int]], duration: int) -> int | None:
        """Return the earliest start (minutes) where `duration` fits, or None.

        `taken` is a list of (start, end) intervals sorted by start.
        """
        cursor = SUGGEST_START
        for start, end in taken:
            if start - cursor >= duration:
                break
            cursor = max(cursor, end)
        return cursor if cursor + duration <= SUGGEST_END else None

    def complete_task(self, task: Task) -> Task | None:
        """Mark a task complete and, if it recurs, add its next occurrence to the same pet.

        Daily and weekly tasks get a fresh, incomplete copy whose due_date is one
        timedelta step (1 day or 7 days) after the task's own due_date, or after
        today when it had none. Using timedelta handles month, year and leap-day
        rollover. Any other frequency (e.g. 'once') does not recur.

        Args:
            task: a task belonging to one of the owner's pets.
        Returns: the newly created task, or None if the task does not recur.
        """
        task.mark_complete()
        step = RECURRENCE.get(task.frequency)
        if step is None:
            return None
        next_task = replace(task, completed=False, due_date=(task.due_date or date.today()) + step)
        pet = next(p for p in self.owner.pets if p.name == task.pet_name)
        pet.add_task(next_task)
        return next_task

    @staticmethod
    def sort_by_time(tasks: list[Task]) -> list[Task]:
        """Return tasks ordered by their 'HH:MM' preference, earliest first.

        The sort key is a lambda that turns 'HH:MM' into an (hour, minute) integer
        tuple, so '8:30' sorts before '09:15' (plain string comparison would not).
        Tasks with no preference get (24, 0) and sort last. The sort is stable and
        returns a new list; the input is not modified.

        Args:
            tasks: tasks whose preference is blank or a valid 'HH:MM' string.
        """
        return sorted(
            tasks,
            key=lambda t: tuple(int(part) for part in t.preference.split(":")) if t.preference else (24, 0),
        )

    def explain(self, suggestions: list[Task] | None = None) -> str:
        """Return a text explanation of why tasks were scheduled, skipped or suggested.

        Args:
            suggestions: pending suggestions from suggest_tasks, listed with the reason
                each was offered. Suggestions already accepted appear in the plan,
                tagged '(suggested)' with their reason.
        """
        used = sum(t.duration for t in self.scheduled_items)
        available = self.owner.availability
        lines = [
            f"{self.owner.name} has {available} minutes available today. "
            f"Tasks were chosen by priority (high, then medium, then low) "
            f"until time ran out, then ordered by preferred time.",
            f"Scheduled {used} of {available} minutes ({available - used} left).",
        ]
        for t in self.scheduled_items:
            when = f" at {t.preference}" if t.preference else ""
            tag = " (suggested)" if t.suggested else ""
            lines.append(
                f"  + {t.name}{tag} for {t.pet_name}{when}: "
                f"{t.priority} priority, fits in {t.duration} min."
            )
            if t.reason:
                lines.append(f"      Why suggested: {t.reason}")
        for t in self.skipped_tasks:
            if any(t is c for c in self.conflict_skipped):
                reason = f"its time slot at {t.preference} overlaps a higher-priority task."
            else:
                reason = "not enough time remained."
            lines.append(
                f"  - {t.name} for {t.pet_name} skipped: needs {t.duration} min "
                f"({t.priority} priority) but {reason}"
            )
        if suggestions:
            lines.append("Suggested tasks (not in the plan until accepted):")
            for t in suggestions:
                lines.append(f"  ? {t.name} for {t.pet_name} at {t.preference} ({t.duration} min)")
                lines.append(f"      Why: {t.reason}")
        return "\n".join(lines)
