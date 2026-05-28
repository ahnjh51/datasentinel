"""
GitHub Events ingestion.
Watches repository events and inserts to BigQuery.
"""
import os
import json
import requests
from google.cloud import bigquery
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

REPO = os.getenv("GITHUB_REPO", "ahnjh51/datasentinel")
PAT = os.getenv("GITHUB_PAT")
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "datasentinel-hackathon")
TABLE_ID = f"{PROJECT_ID}.datasentinel.raw_github_events"
ETAG_FILE = ".github_etag"


def get_cached_etag() -> str | None:
    """Read the cached ETag from file."""
    if os.path.exists(ETAG_FILE):
        try:
            with open(ETAG_FILE, "r") as f:
                return f.read().strip()
        except Exception:
            pass
    return None


def save_etag(etag: str) -> None:
    """Save ETag to file."""
    try:
        with open(ETAG_FILE, "w") as f:
            f.write(etag)
    except Exception:
        pass


def ingest_github_events() -> int:
    """Fetch GitHub events, parse, and write to BigQuery. Uses ETag caching."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    if PAT:
        headers["Authorization"] = f"Bearer {PAT}"
    
    etag = get_cached_etag()
    if etag:
        headers["If-None-Match"] = etag

    url = f"https://api.github.com/repos/{REPO}/events"
    resp = requests.get(url, headers=headers, timeout=15)

    if resp.status_code == 304:
        print("No new events (304 Not Modified).")
        return 0

    resp.raise_for_status()

    # Save new ETag
    new_etag = resp.headers.get("ETag")
    if new_etag:
        save_etag(new_etag)

    events = resp.json()
    if not events or not isinstance(events, list):
        return 0

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for e in events:
        # Convert payload dict/object to JSON string for BQ JSON compatibility
        payload_data = e.get("payload", {})
        
        rows.append({
            "id":          e["id"],
            "type":        e["type"],
            "actor_login": e.get("actor", {}).get("login"),
            "repo":        e.get("repo", {}).get("name"),
            "payload":     json.dumps(payload_data),
            "created_at":  e.get("created_at"),
            "ingested_at": now,
        })

    bq = bigquery.Client(project=PROJECT_ID)
    errors = bq.insert_rows_json(TABLE_ID, rows)

    if errors:
        raise RuntimeError(f"BigQuery insert errors: {errors}")
    return len(rows)


if __name__ == "__main__":
    print(f"Testing GitHub Events ingestion for repo: {REPO}...")
    try:
        count = ingest_github_events()
        print(f"Successfully ingested {count} events into {TABLE_ID}.")
    except Exception as e:
        print(f"GitHub Ingestion failed: {e}")
