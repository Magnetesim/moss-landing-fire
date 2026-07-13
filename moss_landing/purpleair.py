"""PurpleAir API key loading and HTTP helpers."""

from __future__ import annotations

import time
from pathlib import Path

import requests

from moss_landing.paths import PROJECT_ROOT

API_BASE_URL = "https://api.purpleair.com/v1"
DEFAULT_API_KEY_PATH = PROJECT_ROOT / "purple_air_api.txt"
DEFAULT_TIMEOUT_SECONDS = 60.0
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def load_api_key(path: Path | None = None) -> str:
    key_path = Path(path) if path is not None else DEFAULT_API_KEY_PATH
    if not key_path.is_file():
        raise FileNotFoundError(
            f"PurpleAir API key file not found: {key_path}\n"
            "Create it with: cp purple_air_api.txt.example purple_air_api.txt "
            "and paste your API key into it."
        )
    key = key_path.read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError(f"PurpleAir API key file is empty: {key_path}")
    return key


def get_json(
    url: str,
    api_key: str,
    params: dict[str, object] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = 3,
) -> dict[str, object]:
    """GET a PurpleAir endpoint with timeout, status checking, and basic retries.

    Retries transient failures (429 rate limits and 5xx responses) with a
    short exponential backoff, honoring Retry-After when provided.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        response = requests.get(url, headers={"X-API-Key": api_key}, params=params, timeout=timeout)
        if response.status_code not in RETRYABLE_STATUS_CODES:
            response.raise_for_status()
            return response.json()
        last_error = requests.HTTPError(f"{response.status_code} from {url}", response=response)
        if attempt < max_attempts:
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2.0**attempt
            time.sleep(delay)
    assert last_error is not None
    raise last_error


def get_sensor_history(
    sensor_index: int,
    api_key: str,
    start_timestamp: int,
    end_timestamp: int,
    fields: str,
    average: int = 60,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Fetch the /sensors/{index}/history payload for one sensor."""
    return get_json(
        f"{API_BASE_URL}/sensors/{sensor_index}/history",
        api_key,
        params={
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
            "average": average,
            "fields": fields,
        },
        timeout=timeout,
    )
