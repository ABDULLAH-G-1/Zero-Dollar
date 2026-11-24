"""GitHub analytics pipeline ingestion module."""

from .config import (
    GITHUB_TOKEN,
    LOOKBACK_DAYS,
    MOTHERDUCK_TOKEN,
    TARGET_ENV,
    TARGET_REPOS,
    get_duckdb_destination,
)

__all__ = [
    "GITHUB_TOKEN",
    "LOOKBACK_DAYS",
    "MOTHERDUCK_TOKEN",
    "TARGET_ENV",
    "TARGET_REPOS",
    "get_duckdb_destination",
]
