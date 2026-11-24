import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env in the project root if present
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

TARGET_REPOS = [
    "dlt-hub/dlt",
    "duckdb/duckdb",
    "dbt-labs/dbt-core",
]

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
TARGET_ENV = os.getenv("TARGET_ENV", "dev")
MOTHERDUCK_TOKEN = os.getenv("MOTHERDUCK_TOKEN", "")

try:
    LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "90"))
except ValueError:
    LOOKBACK_DAYS = 90


def get_duckdb_destination() -> str:
    """Return local DuckDB file path for dev, or MotherDuck connection string for prod."""
    if TARGET_ENV == "prod":
        return f"md:github_analytics?motherduck_token={MOTHERDUCK_TOKEN}"
    return "data/github_warehouse.duckdb"
