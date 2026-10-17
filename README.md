# jev

A small Python client for Jev-style **decision models**. These models don't generate text. You give them a state and typed questions, and they return a probability for each allowed answer.

The first provider is Cloudflare's **Clef** family on Workers AI (Apache-2.0 open weights):

| Model | Workers AI ID | Notes |
| --- | --- | --- |
| `clef-flash` (default) | `@cf/cloudflare/clef-flash` | 9B, lowest latency and cost |
| `clef` | `@cf/cloudflare/clef` | 27B, highest accuracy |

## Question types

| Type | Class | Answer |
| --- | --- | --- |
| `noul` (yes/no) | `Noul(instructions)` | `NoulAnswer.probability` (probability of yes) |
| `choice` | `Choice(instructions, {key: description})` | `ChoiceAnswer.choice`, `.probabilities`, `.confidence` |
| `score` | `Score(instructions, [lowest, ..., highest])` | `ScoreAnswer.score` (0 = lowest level), `.probabilities` |

You can ask up to 64 questions in one call.

## Setup

1. In the Cloudflare dashboard, open **AI → Workers AI** and copy your **Account ID**.
2. Create an API token: **My Profile → API Tokens → Create Token**, then pick the **Workers AI** template.
3. Copy `.env.example` to `.env` and fill both values in. `.env` is git-ignored.

```bash
pip install -e ".[dev]"
pytest -q                     # mocked, no network
python scripts/clef_demo.py   # one real call to Workers AI
```

## Usage

```python
from jev import ClefClient, Choice, Noul, Score

with ClefClient.from_settings() as clef:          # reads .env / environment
    answers = clef.decide(
        "Checkout has been failing for every customer for the last hour.",
        {
            "urgent": Noul("Is this support request urgent?"),
            "team": Choice("Which team should handle it?", {
                "billing": "Payments, invoices and refunds",
                "technical": "Bugs, outages and errors",
            }),
            "severity": Score("How severe is it?", ["No impact", "Minor", "Major", "Critical"]),
        },
    )
    answers["urgent"].probability   # e.g. 0.99
    answers["team"].choice          # "technical"
    answers["severity"].score       # e.g. 2.96

    route = clef.choose(message, "Which action should the bot take?", {
        "generate": "Make a new image", "edit": "Change an existing image", "chat": "Just talk",
    })
```

Any HTTP error, `success: false` body or malformed answer raises `ClefError`.

## Status

`scripts/clef_demo.py` has been run against the live `clef-flash` endpoint (2026-10-17), and the answer parsing matched the real response. The sample message "can you make the sky in my photo look like a sunset?" routed to `edit` 0.910 (`chat` 0.051, `generate` 0.039), and `safe` came back 0.879.
