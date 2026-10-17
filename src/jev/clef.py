"""Client for Cloudflare's Clef decision models on Workers AI.

Calls ``POST /client/v4/accounts/{account_id}/ai/run/@cf/cloudflare/{model}``
with ``{"model", "state", "questions"}`` and parses the typed answers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from jev.questions import (
    Answer,
    Choice,
    ChoiceAnswer,
    Noul,
    NoulAnswer,
    Question,
    Score,
    ScoreAnswer,
)
from jev.settings import Settings

API_BASE = "https://api.cloudflare.com/client/v4"
MODELS = ("clef", "clef-flash")
MAX_QUESTIONS = 64
MAX_IMAGES = 4


class ClefError(Exception):
    """The Workers AI call failed or returned a body we could not parse."""


class ClefClient:
    def __init__(
        self,
        account_id: str,
        api_token: str,
        model: str = "clef-flash",
        *,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        if model not in MODELS:
            raise ValueError(f"model must be one of {MODELS}, got {model!r}")
        self.model = model
        self.url = f"{API_BASE}/accounts/{account_id}/ai/run/@cf/cloudflare/{model}"
        self._headers = {"Authorization": f"Bearer {api_token}"}
        self._client = client or httpx.Client(timeout=timeout)

    @classmethod
    def from_settings(cls, settings: Settings | None = None, **kwargs: Any) -> ClefClient:
        settings = settings or Settings()
        return cls(
            settings.cloudflare_account_id,
            settings.cloudflare_api_token.get_secret_value(),
            settings.clef_model,
            **kwargs,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ClefClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def decide(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
        *,
        images: Sequence[str] | None = None,
    ) -> dict[str, Answer]:
        """Ask several questions about ``state`` in one call.

        ``images`` are base64 data URLs (PNG, JPEG or WebP); remote URLs are not
        accepted by Workers AI.
        """
        if not questions:
            raise ValueError("ask at least one question")
        if len(questions) > MAX_QUESTIONS:
            raise ValueError(f"at most {MAX_QUESTIONS} questions per call")
        body: dict[str, Any] = {
            "model": self.model,
            "state": state,
            "questions": {key: q.to_json() for key, q in questions.items()},
        }
        if images:
            if len(images) > MAX_IMAGES:
                raise ValueError(f"at most {MAX_IMAGES} images per call")
            body["images"] = list(images)

        result = self._post(body)
        raw_answers = result.get("answers")
        if not isinstance(raw_answers, dict):
            raise ClefError(f"response has no answers object: {result!r}")
        answers: dict[str, Answer] = {}
        for key, question in questions.items():
            if key not in raw_answers:
                raise ClefError(f"response is missing an answer for {key!r}")
            answers[key] = _parse_answer(question, raw_answers[key])
        return answers

    def ask(self, state: str | Mapping[str, Any], question: Question) -> Answer:
        return self.decide(state, {"q": question})["q"]

    def choose(self, state: str | Mapping[str, Any], instructions: str, options: Mapping[str, str]) -> ChoiceAnswer:
        answer = self.ask(state, Choice(instructions, dict(options)))
        assert isinstance(answer, ChoiceAnswer)
        return answer

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(self.url, json=body, headers=self._headers)
        except httpx.HTTPError as exc:
            raise ClefError(f"request to Workers AI failed: {exc}") from exc
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.status_code >= 400 or not isinstance(payload, dict) or payload.get("success") is False:
            errors = payload.get("errors") if isinstance(payload, dict) else response.text[:500]
            raise ClefError(f"Workers AI returned HTTP {response.status_code}: {errors}")
        # REST responses wrap the output in Cloudflare's {"result": ...} envelope.
        result = payload.get("result", payload)
        if not isinstance(result, dict):
            raise ClefError(f"unexpected response body: {payload!r}")
        return result


def _parse_answer(question: Question, raw: Any) -> Answer:
    if not isinstance(raw, dict):
        raise ClefError(f"answer is not an object: {raw!r}")
    try:
        if isinstance(question, Noul):
            return NoulAnswer(probability=float(raw["noul"]))
        if isinstance(question, Choice):
            return ChoiceAnswer(
                choice=str(raw["choice"]),
                probabilities={str(k): float(v) for k, v in raw["probabilities"].items()},
                confidence=_optional_float(raw.get("confidence")),
            )
        if isinstance(question, Score):
            return ScoreAnswer(
                score=float(raw["score"]),
                probabilities=_level_probabilities(question.levels, raw.get("probabilities")),
                confidence=_optional_float(raw.get("confidence")),
            )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ClefError(f"malformed {type(question).__name__.lower()} answer: {raw!r}") from exc
    raise TypeError(f"unknown question type: {question!r}")


def _level_probabilities(levels: list[str], raw: Any) -> dict[str, float]:
    # The docs don't pin this down: accept a list aligned with the levels or a mapping.
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(k): float(v) for k, v in raw.items()}
    values = list(raw)
    if len(values) != len(levels):
        raise ValueError("score probabilities don't match the number of levels")
    return {level: float(p) for level, p in zip(levels, values)}


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
