"""
Tokyo CityBikes ingestion.
Called by FastAPI /ingest/citybikes endpoint.
"""
import os
import requests
from google.cloud import bigquery
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

NETWORK_ID = os.getenv("CITYBIKES_NETWORK_ID", "docomo-cycle-tokyo")
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "datasentinel-hackathon")
TABLE_ID = f"{PROJECT_ID}.datasentinel.raw_citybikes_stations"


def fetch_stations() -> list[dict]:
    """Fetch raw station data from CityBikes API."""
    url = f"https://api.citybik.es/v2/networks/{NETWORK_ID}"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()["network"]["stations"]


def build_rows(stations: list[dict]) -> list[dict]:
    """Transform raw stations into BigQuery row format.
    Ensures missing/null capacity fields are preserved as None.
    """
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for s in stations:
        rows.append({
            "station_id":  s["id"],
            "name":        s.get("name"),
            "free_bikes":  s.get("free_bikes") if s.get("free_bikes") is not None else None,
            "empty_slots": s.get("empty_slots") if s.get("empty_slots") is not None else None,
            "latitude":    s.get("latitude"),
            "longitude":   s.get("longitude"),
            "ingested_at": now,
        })
    return rows


def ingest_citybikes() -> int:
    """Full ingestion: fetch -> parse -> write to BigQuery. Returns row count."""
    stations = fetch_stations()
    rows = build_rows(stations)

    # Initialize BigQuery client using the active project and credentials
    bq = bigquery.Client(project=PROJECT_ID)
    errors = bq.insert_rows_json(TABLE_ID, rows)

    if errors:
        raise RuntimeError(f"BigQuery insert errors: {errors}")
    return len(rows)


if __name__ == "__main__":
    print(f"Testing CityBikes ingestion for network: {NETWORK_ID}...")
    try:
        count = ingest_citybikes()
        print(f"Successfully ingested {count} stations into {TABLE_ID}.")
    except Exception as e:
        print(f"Ingestion failed: {e}")
