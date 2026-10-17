"""Typed questions and answers for Jev-style decision models.

A decision model never generates text. Each question has a type and the model
returns a probability distribution over the allowed answers:

- ``noul``: yes/no. The answer is the probability of yes.
- ``choice``: pick one option from a named set.
- ``score``: pick a level from an ordered scale (lowest first).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union


@dataclass(frozen=True)
class Noul:
    """A yes/no question."""

    instructions: str

    def to_json(self) -> dict[str, Any]:
        return {"type": "noul", "instructions": self.instructions}


@dataclass(frozen=True)
class Choice:
    """Pick one of several options. ``options`` maps option key to description."""

    instructions: str
    options: dict[str, str]

    def __post_init__(self) -> None:
        if len(self.options) < 2:
            raise ValueError("a choice question needs at least two options")

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "choice",
            "instructions": self.instructions,
            "criteria": dict(self.options),
        }


@dataclass(frozen=True)
class Score:
    """Rate on an ordered scale. ``levels`` runs from lowest to highest."""

    instructions: str
    levels: list[str]

    def __post_init__(self) -> None:
        if len(self.levels) < 2:
            raise ValueError("a score question needs at least two levels")

    def to_json(self) -> dict[str, Any]:
        return {
            "type": "score",
            "instructions": self.instructions,
            "criteria": list(self.levels),
        }


Question = Union[Noul, Choice, Score]


@dataclass(frozen=True)
class NoulAnswer:
    probability: float
    """Probability that the answer is yes."""

    @property
    def yes(self) -> bool:
        return self.probability >= 0.5


@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    probabilities: dict[str, float]
    confidence: float | None = None


@dataclass(frozen=True)
class ScoreAnswer:
    score: float
    """Probability-weighted level index, where 0 is the lowest level."""
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float | None = None


Answer = Union[NoulAnswer, ChoiceAnswer, ScoreAnswer]
