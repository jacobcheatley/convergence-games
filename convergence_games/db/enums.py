import enum


class GameCrunch(enum.StrEnum):
    LIGHT = "Light"
    MEDIUM = "Medium"
    HEAVY = "Heavy"


class GameNarrativism(enum.StrEnum):
    NARRATIVIST = "Narrativist"
    BALANCED = "Balanced"
    GAMEIST = "Gameist"


class GameTone(enum.StrEnum):
    GOOFY = "Goofy"
    LIGHT_HEARTED = "Light-hearted"
    SERIOUS = "Serious"
    DARK = "Dark"