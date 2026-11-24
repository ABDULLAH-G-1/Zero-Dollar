"""Incremental dlt ingestion pipeline for GitHub repositories to DuckDB/MotherDuck."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import time
from typing import Any, Iterator

import dlt
import requests

# Ensure project root is in sys.path when running as script directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.config import (
    GITHUB_TOKEN,
    LOOKBACK_DAYS,
    TARGET_REPOS,
    get_duckdb_destination,
)

GITHUB_API_BASE = "https://api.github.com"


def _get_headers() -> dict[str, str]:
    """Build standard GitHub REST API v3 request headers."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _handle_response_error(response: requests.Response) -> None:
    """Check response for rate limiting and HTTP errors."""
    if response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0":
        reset_epoch = int(response.headers.get("x-ratelimit-reset", 0))
        wait_seconds = max(reset_epoch - int(time.time()), 0)
        raise RuntimeError(
            f"GitHub API rate limit exceeded. Reset in {wait_seconds} seconds "
            f"(epoch {reset_epoch}). Set GITHUB_TOKEN to increase limits."
        )
    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 10))
        raise RuntimeError(f"GitHub API 429 Too Many Requests. Retry after {retry_after}s.")
    response.raise_for_status()


def _github_request(endpoint: str, params: dict[str, Any] | None = None) -> Any:
    """Execute a GitHub API GET request with retry backoff and rate-limit handling."""
    url = f"{GITHUB_API_BASE}{endpoint}" if endpoint.startswith("/") else endpoint
    headers = _get_headers()
    max_retries = 3

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 5))
                time.sleep(retry_after)
                continue
            _handle_response_error(response)
            return response.json()
        except requests.RequestException:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)

    raise RuntimeError(f"Failed to fetch {url} after {max_retries} attempts.")


def _github_request_paginated(endpoint: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Fetch a list from GitHub API endpoint; returns empty list if no results."""
    data = _github_request(endpoint, params=params)
    if isinstance(data, list):
        return data
    return [data] if data else []


def _get_initial_lookback_date(days: int = LOOKBACK_DAYS) -> str:
    """Calculate the UTC ISO 8601 timestamp for LOOKBACK_DAYS ago."""
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_utc_iso(dt_val: Any) -> str:
    """Format a cursor date/datetime/string into ISO 8601 UTC timestamp."""
    if isinstance(dt_val, (datetime, date)):
        if isinstance(dt_val, datetime) and dt_val.tzinfo is not None:
            return dt_val.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return dt_val.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(dt_val, str):
        try:
            dt = datetime.fromisoformat(dt_val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return dt_val
    return str(dt_val)


def _to_utc_datetime(dt_val: Any) -> datetime:
    """Parse a datetime, date, or ISO string to a timezone-aware UTC datetime."""
    if isinstance(dt_val, datetime):
        if dt_val.tzinfo is None:
            return dt_val.replace(tzinfo=timezone.utc)
        return dt_val.astimezone(timezone.utc)
    if isinstance(dt_val, str):
        dt = datetime.fromisoformat(dt_val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)


@dlt.resource(name="raw_repos", write_disposition="merge", primary_key="id")
def raw_repos(repos: tuple[str, ...] = tuple(TARGET_REPOS)) -> Iterator[dict[str, Any]]:
    """Fetch repository metadata for each repo in TARGET_REPOS and add ingested_at_utc."""
    for repo in repos:
        repo_data = _github_request(f"/repos/{repo}")
        repo_data["ingested_at_utc"] = datetime.now(timezone.utc).isoformat()
        yield repo_data


@dlt.resource(name="raw_commits", write_disposition="merge", primary_key="sha")
def raw_commits(
    repos: tuple[str, ...] = tuple(TARGET_REPOS),
    cursor_date: dlt.sources.incremental = dlt.sources.incremental(
        "commit.committer.date",
        initial_value=_get_initial_lookback_date(),
    ),
) -> Iterator[dict[str, Any]]:
    """Incremental fetch of commits on commit.committer.date for TARGET_REPOS."""
    cursor_val = cursor_date.start_value if cursor_date.start_value is not None else cursor_date.last_value
    since_param = _to_utc_iso(cursor_val)

    for repo in repos:
        page = 1
        while True:
            params = {
                "since": since_param,
                "per_page": 100,
                "page": page,
            }
            commits = _github_request_paginated(f"/repos/{repo}/commits", params=params)
            if not commits:
                break

            for commit in commits:
                commit["repo_full_name"] = repo
                yield commit

            if len(commits) < 100:
                break

            page += 1


@dlt.resource(name="raw_pull_requests", write_disposition="merge", primary_key="id")
def raw_pull_requests(
    repos: tuple[str, ...] = tuple(TARGET_REPOS),
    cursor_date: dlt.sources.incremental = dlt.sources.incremental(
        "updated_at",
        initial_value=_get_initial_lookback_date(),
    ),
) -> Iterator[dict[str, Any]]:
    """Incremental fetch of pull requests for TARGET_REPOS, stopping when updated_at is older than cursor."""
    cursor_val = cursor_date.start_value if cursor_date.start_value is not None else cursor_date.last_value
    cutoff_dt = _to_utc_datetime(cursor_val)

    for repo in repos:
        page = 1
        while True:
            params = {
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": 100,
                "page": page,
            }
            pulls = _github_request_paginated(f"/repos/{repo}/pulls", params=params)
            if not pulls:
                break

            stop_repo = False
            for pr in pulls:
                updated_at_str = pr.get("updated_at")
                if updated_at_str:
                    pr_dt = _to_utc_datetime(updated_at_str)
                    if pr_dt < cutoff_dt:
                        stop_repo = True
                        break

                pr["repo_full_name"] = repo
                yield pr

            if stop_repo or len(pulls) < 100:
                break

            page += 1


@dlt.resource(name="raw_issues", write_disposition="merge", primary_key="id")
def raw_issues(
    repos: tuple[str, ...] = tuple(TARGET_REPOS),
    cursor_date: dlt.sources.incremental = dlt.sources.incremental(
        "updated_at",
        initial_value=_get_initial_lookback_date(),
    ),
) -> Iterator[dict[str, Any]]:
    """Incremental fetch of issues on updated_at for TARGET_REPOS, filtering out pull requests."""
    cursor_val = cursor_date.start_value if cursor_date.start_value is not None else cursor_date.last_value
    since_param = _to_utc_iso(cursor_val)

    for repo in repos:
        page = 1
        while True:
            params = {
                "state": "all",
                "since": since_param,
                "per_page": 100,
                "page": page,
            }
            issues = _github_request_paginated(f"/repos/{repo}/issues", params=params)
            if not issues:
                break

            for issue in issues:
                # GitHub issues endpoint includes pull requests; exclude them
                if "pull_request" in issue:
                    continue
                issue["repo_full_name"] = repo
                yield issue

            if len(issues) < 100:
                break

            page += 1


@dlt.source(name="github")
def github_source(repos: tuple[str, ...] = tuple(TARGET_REPOS)) -> list[Any]:
    """Dlt source exposing GitHub repositories, commits, pull requests, and issues."""
    return [
        raw_repos(repos=repos),
        raw_commits(repos=repos),
        raw_pull_requests(repos=repos),
        raw_issues(repos=repos),
    ]


def run_pipeline() -> Any:
    """Run the GitHub ingestion pipeline targeting the configured DuckDB destination."""
    destination_str = get_duckdb_destination()
    pipeline = dlt.pipeline(
        pipeline_name="github_pipeline",
        destination=dlt.destinations.duckdb(destination_str),
        dataset_name="github_raw",
    )
    load_info = pipeline.run(github_source())
    print(load_info)
    return load_info


if __name__ == "__main__":
    run_pipeline()
