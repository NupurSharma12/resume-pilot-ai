"""Temporary utility: print every Gemini model name available to this API key.

Not part of the application's runtime path, but reuses
`app.core.config.get_settings()` (which loads `.env` the same way the app
does) rather than reading `RESUMEPILOT_GEMINI_API_KEY` from `os.environ`
directly — `.env` values aren't exported into the shell's environment, only
`Settings` parses that file, so going through `get_settings()` is what
makes running this with just a populated `.env` (no manual `export`) work.

Usage:
    uv run python scripts/list_models.py
"""

from google import genai

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)
    for model in client.models.list():
        print(model.name)


if __name__ == "__main__":
    main()
