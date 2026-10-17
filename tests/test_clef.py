import json

import httpx
import pytest

from jev import (
    Choice,
    ChoiceAnswer,
    ClefClient,
    ClefError,
    Noul,
    NoulAnswer,
    Score,
    ScoreAnswer,
    Settings,
)


def make_client(handler, model="clef-flash"):
    transport = httpx.MockTransport(handler)
    return ClefClient("acct123", "tok-secret", model, client=httpx.Client(transport=transport))


def ok(result):
    return httpx.Response(200, json={"success": True, "errors": [], "messages": [], "result": result})


QUESTIONS = {
    "urgent": Noul("Is this support request urgent?"),
    "team": Choice("Which team should handle it?", {"billing": "Payments", "technical": "Bugs and outages"}),
    "severity": Score("How severe is it?", ["No impact", "Minor", "Major", "Critical"]),
}

ANSWERS = {
    "urgent": {"type": "noul", "noul": 0.9917},
    "team": {
        "type": "choice",
        "choice": "technical",
        "probabilities": {"billing": 0.1912, "technical": 0.8088},
        "confidence": 0.62,
    },
    "severity": {
        "type": "score",
        "score": 2.9573,
        "legend": ["No impact", "Minor", "Major", "Critical"],
        "probabilities": [0.0, 0.01, 0.02, 0.97],
        "confidence": 0.9,
    },
}


def test_builds_request():
    seen = {}

    def handler(request):
        seen["request"] = request
        return ok({"model": "clef-flash", "answers": ANSWERS})

    make_client(handler).decide("Checkout is down for everyone.", QUESTIONS)

    request = seen["request"]
    assert request.method == "POST"
    assert str(request.url) == (
        "https://api.cloudflare.com/client/v4/accounts/acct123/ai/run/@cf/cloudflare/clef-flash"
    )
    assert request.headers["authorization"] == "Bearer tok-secret"
    body = json.loads(request.content)
    assert body == {
        "model": "clef-flash",
        "state": "Checkout is down for everyone.",
        "questions": {
            "urgent": {"type": "noul", "instructions": "Is this support request urgent?"},
            "team": {
                "type": "choice",
                "instructions": "Which team should handle it?",
                "criteria": {"billing": "Payments", "technical": "Bugs and outages"},
            },
            "severity": {
                "type": "score",
                "instructions": "How severe is it?",
                "criteria": ["No impact", "Minor", "Major", "Critical"],
            },
        },
    }


def test_parses_answers():
    answers = make_client(lambda r: ok({"model": "clef-flash", "answers": ANSWERS})).decide("x", QUESTIONS)

    assert answers["urgent"] == NoulAnswer(probability=0.9917)
    assert answers["urgent"].yes
    assert answers["team"] == ChoiceAnswer(
        choice="technical", probabilities={"billing": 0.1912, "technical": 0.8088}, confidence=0.62
    )
    severity = answers["severity"]
    assert isinstance(severity, ScoreAnswer)
    assert severity.score == pytest.approx(2.9573)
    assert severity.probabilities["Critical"] == pytest.approx(0.97)


def test_accepts_unwrapped_result_and_mapping_score_probabilities():
    raw = dict(ANSWERS, severity={"type": "score", "score": 1.0, "probabilities": {"Minor": 1.0}})
    answers = make_client(lambda r: httpx.Response(200, json={"answers": raw})).decide("x", QUESTIONS)
    assert answers["severity"].probabilities == {"Minor": 1.0}


def test_choose_helper_uses_full_model_name():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return ok({"answers": {"q": ANSWERS["team"]}})

    answer = make_client(handler, model="clef").choose(
        "Refund me", "Route this", {"billing": "Payments", "technical": "Bugs"}
    )
    assert answer.choice == "technical"
    assert seen["url"].endswith("/ai/run/@cf/cloudflare/clef")
    assert seen["body"]["model"] == "clef"


def test_http_error_raises():
    def handler(request):
        return httpx.Response(401, json={"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]})

    with pytest.raises(ClefError, match="HTTP 401.*Authentication error"):
        make_client(handler).decide("x", QUESTIONS)


def test_success_false_raises():
    def handler(request):
        return httpx.Response(200, json={"success": False, "errors": [{"message": "bad input"}]})

    with pytest.raises(ClefError, match="bad input"):
        make_client(handler).decide("x", QUESTIONS)


def test_non_json_body_raises():
    with pytest.raises(ClefError, match="HTTP 502"):
        make_client(lambda r: httpx.Response(502, text="<html>bad gateway</html>")).decide("x", QUESTIONS)


def test_missing_answer_raises():
    partial = {k: v for k, v in ANSWERS.items() if k != "team"}
    with pytest.raises(ClefError, match="missing an answer for 'team'"):
        make_client(lambda r: ok({"answers": partial})).decide("x", QUESTIONS)


def test_malformed_answer_raises():
    bad = dict(ANSWERS, urgent={"type": "noul"})
    with pytest.raises(ClefError, match="malformed noul answer"):
        make_client(lambda r: ok({"answers": bad})).decide("x", QUESTIONS)


def test_network_error_raises():
    def handler(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(ClefError, match="request to Workers AI failed"):
        make_client(handler).decide("x", QUESTIONS)


def test_validates_inputs():
    client = make_client(lambda r: ok({}))
    with pytest.raises(ValueError):
        client.decide("x", {})
    with pytest.raises(ValueError):
        client.decide("x", {f"q{i}": Noul("?") for i in range(65)})
    with pytest.raises(ValueError):
        ClefClient("a", "t", "jev")
    with pytest.raises(ValueError):
        Choice("one option", {"only": "x"})


def test_from_settings(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-env")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok-env")
    monkeypatch.setenv("CLEF_MODEL", "clef")
    settings = Settings(_env_file=None)
    assert "tok-env" not in repr(settings)

    client = ClefClient.from_settings(settings)
    assert client.url.endswith("/accounts/acct-env/ai/run/@cf/cloudflare/clef")
