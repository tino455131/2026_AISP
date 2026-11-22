from dotenv import load_dotenv

from sqlite_api import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env", interpolate=False)  # BOT_DB, MEETING_SUMMARIZER, OPENAI_API_KEY…; never printed

from .cli import main  # noqa: E402

raise SystemExit(main())
