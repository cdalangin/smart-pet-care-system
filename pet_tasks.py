"""Single source of truth for the pet species and suggested care tasks.

COMMON_TASKS apply to every species; SPECIES_TASKS add 3 tasks unique to each.
Every entry has a name, a duration in minutes, and a priority (always "low").
"""

SPECIES = ("dog", "cat", "fish", "rabbit", "hamster")

COMMON_TASKS = [
    {"name": "Fresh water check", "duration": 5, "priority": "low"},
    {"name": "Feeding", "duration": 10, "priority": "low"},
    {"name": "Cuddle or bonding time", "duration": 15, "priority": "low"},
    {"name": "Habitat or bedding tidy", "duration": 10, "priority": "low"},
    {"name": "Health and behavior check", "duration": 5, "priority": "low"},
]

SPECIES_TASKS = {
    "dog": [
        {"name": "Walk", "duration": 30, "priority": "low"},
        {"name": "Fetch or tug play", "duration": 15, "priority": "low"},
        {"name": "Brushing", "duration": 10, "priority": "low"},
    ],
    "cat": [
        {"name": "Wand toy play", "duration": 15, "priority": "low"},
        {"name": "Litter box scoop", "duration": 5, "priority": "low"},
        {"name": "Scratching post training", "duration": 10, "priority": "low"},
    ],
    "fish": [
        {"name": "Tank glass wipe", "duration": 10, "priority": "low"},
        {"name": "Partial water change", "duration": 30, "priority": "low"},
        {"name": "Water temperature and pH test", "duration": 10, "priority": "low"},
    ],
    "rabbit": [
        {"name": "Supervised hop time", "duration": 30, "priority": "low"},
        {"name": "Hay refill", "duration": 5, "priority": "low"},
        {"name": "Nail trim", "duration": 15, "priority": "low"},
    ],
    "hamster": [
        {"name": "Wheel and cage cleaning", "duration": 15, "priority": "low"},
        {"name": "Out-of-cage ball time", "duration": 20, "priority": "low"},
        {"name": "Hide-and-forage treat game", "duration": 10, "priority": "low"},
    ],
}


def tasks_for(species: str) -> list[dict]:
    """Return the 5 common tasks plus the 3 unique ones for a species (8 total)."""
    return COMMON_TASKS + SPECIES_TASKS[species]
