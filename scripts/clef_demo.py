"""Smoke test against the real Workers AI endpoint.

Needs CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN in the environment or .env.

    python scripts/clef_demo.py "put a party hat on the cat in my photo"
"""

from __future__ import annotations

import sys

from jev import ClefClient, Noul

ROUTES = {
    "generate": "The user wants a brand-new image generated from a description.",
    "edit": "The user wants changes made to an image they already sent.",
    "chat": "The user is just talking or asking a question; no image work.",
}


def main() -> None:
    message = " ".join(sys.argv[1:]) or "can you make the sky in my photo look like a sunset?"
    with ClefClient.from_settings() as clef:
        print(f"model: {clef.model}")
        print(f"message: {message!r}\n")
        route = clef.choose(message, "Which action should the Telegram image bot take for this message?", ROUTES)
        for option, p in sorted(route.probabilities.items(), key=lambda kv: -kv[1]):
            print(f"  {option:<9} {p:.3f}")
        print(f"-> {route.choice}")
        safe = clef.ask(message, Noul("Is this request safe and appropriate to fulfil?"))
        print(f"\nsafe: {safe.probability:.3f}")


if __name__ == "__main__":
    main()
