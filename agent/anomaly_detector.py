"""
DataSentinel Z-Score Anomaly Detector.
Runs statistical anomaly detection on metrics tables and logs incidents.
"""
import os
import uuid
from google.cloud import bigquery
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "datasentinel-hackathon")
DATASET_ID = "datasentinel"
Z_THRESHOLD = 3.0  # Absolute Z-Score threshold for anomalies


def detect_station_anomalies() -> list[dict]:
    """Detects statistical anomalies in bike station availability.
    Uses window-based historical metrics (past 7 days) as baselines.
    """
    client = bigquery.Client(project=PROJECT_ID)

    # Core statistical query computing mean, standard deviation, and Z-Score in BigQuery
    query = f"""
    WITH baselines AS (
      -- Calculate rolling average and stddev over past 7 days excluding current snapshot
      SELECT
        station_id,
        AVG(availability_pct) as baseline_mean,
        STDDEV(availability_pct) as baseline_stddev
      FROM `{PROJECT_ID}.{DATASET_ID}.metrics_station_health`
      WHERE DATE(snapshot_time) BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY) AND DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
      GROUP BY station_id
    ),
    current_metrics AS (
      -- Get latest snapshots from the past 1 hour
      SELECT
        station_id,
        snapshot_time as detected_at,
        availability_pct as current_value
      FROM `{PROJECT_ID}.{DATASET_ID}.metrics_station_health`
      WHERE snapshot_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
    ),
    z_scores AS (
      SELECT
        c.station_id,
        c.detected_at,
        c.current_value,
        b.baseline_mean,
        -- Handle zero-variance cases to avoid division by zero
        CASE
          WHEN b.baseline_stddev IS NULL OR b.baseline_stddev = 0 THEN 0.0
          ELSE ROUND((c.current_value - b.baseline_mean) / b.baseline_stddev, 2)
        END as z_score
      FROM current_metrics c
      JOIN baselines b ON c.station_id = b.station_id
    )
    SELECT
      station_id,
      detected_at,
      current_value,
      baseline_mean,
      z_score
    FROM z_scores
    WHERE ABS(z_score) > {Z_THRESHOLD}
      -- Deduplicate against recently flagged anomalies
      AND CONCAT(station_id, CAST(detected_at AS STRING)) NOT IN (
        SELECT CONCAT(metric, CAST(detected_at AS STRING)) FROM `{PROJECT_ID}.{DATASET_ID}.anomalies_flagged`
        WHERE detected_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR)
      )
    """

    query_job = client.query(query)
    results = query_job.result()

    anomalies = []
    now = datetime.now(timezone.utc).isoformat()
    
    for row in results:
        anomalies.append({
            "id":             str(uuid.uuid4()),
            "detected_at":    row.detected_at.isoformat(),
            "source":         "citybikes",
            "metric":         row.station_id,
            "z_score":        row.z_score,
            "current_value":  float(row.current_value),
            "baseline_mean":  float(row.baseline_mean),
            "status":         "new"
        })

    if anomalies:
        # Batch insert flagged anomalies into BigQuery
        errors = client.insert_rows_json(f"{PROJECT_ID}.{DATASET_ID}.anomalies_flagged", anomalies)
        if errors:
            raise RuntimeError(f"BigQuery insert errors for anomalies: {errors}")
            
    return anomalies


def detect_github_anomalies() -> list[dict]:
    """Detects anomalies in GitHub repository events.
    Specifically flags direct pushes bypassing branch rules immediately.
    """
    client = bigquery.Client(project=PROJECT_ID)

    query = f"""
    SELECT
      event_id,
      created_at as detected_at,
      actor_login,
      repo,
      metric_type,
      metric_value
    FROM `{PROJECT_ID}.{DATASET_ID}.metrics_dora`
    WHERE metric_type = 'direct_push'
      AND created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
      AND event_id NOT IN (
        SELECT DISTINCT id FROM `{PROJECT_ID}.{DATASET_ID}.anomalies_flagged`
      )
    """

    query_job = client.query(query)
    results = query_job.result()

    anomalies = []
    for row in results:
        anomalies.append({
            "id":             row.event_id,
            "detected_at":    row.detected_at.isoformat(),
            "source":         "github",
            "metric":         f"direct_push_by_{row.actor_login}",
            "z_score":        99.0,  # Infinite Z-Score for severe policy violations
            "current_value":  1.0,
            "baseline_mean":  0.0,
            "status":         "new"
        })

    if anomalies:
        errors = client.insert_rows_json(f"{PROJECT_ID}.{DATASET_ID}.anomalies_flagged", anomalies)
        if errors:
            raise RuntimeError(f"BigQuery insert errors for GitHub anomalies: {errors}")

    return anomalies


if __name__ == "__main__":
    print("Testing Anomaly Detector...")
    try:
        cb_anom = detect_station_anomalies()
        gh_anom = detect_github_anomalies()
        print(f"CityBikes anomalies flagged: {len(cb_anom)}")
        print(f"GitHub anomalies flagged: {len(gh_anom)}")
    except Exception as e:
        print(f"Anomaly Detection failed: {e}")
