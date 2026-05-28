"""
DataSentinel BigQuery ETL Analytics Layer.
Executes partitioned SQL queries for station health and repository DORA metrics.
"""
import os
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "datasentinel-hackathon")
DATASET_ID = "datasentinel"


def calculate_station_health() -> int:
    """Calculates bike station metrics from raw logs.
    Computes delta_from_prior, availability_pct, and flags nulls/mismatches.
    """
    client = bigquery.Client(project=PROJECT_ID)
    
    # Core ETL query with window functions to compute deltas
    query = f"""
    INSERT INTO `{PROJECT_ID}.{DATASET_ID}.metrics_station_health`
    (station_id, snapshot_time, free_bikes, availability_pct, delta_from_prior, null_flag, capacity_mismatch)
    
    WITH ranked_snapshots AS (
      SELECT
        station_id,
        ingested_at as snapshot_time,
        free_bikes,
        empty_slots,
        -- availability_pct = free / (free + empty)
        CASE 
          WHEN (free_bikes IS NULL OR empty_slots IS NULL) THEN NULL
          WHEN (free_bikes + empty_slots) = 0 THEN 0.0
          ELSE ROUND(free_bikes / (free_bikes + empty_slots) * 100.0, 2)
        END as availability_pct,
        -- capacity mismatch flag if capacity is negative or unreasonably large
        CASE
          WHEN (free_bikes + empty_slots) < 0 OR (free_bikes + empty_slots) > 200 THEN TRUE
          ELSE FALSE
        END as capacity_mismatch,
        -- null_flag
        CASE WHEN free_bikes IS NULL OR empty_slots IS NULL THEN TRUE ELSE FALSE END as null_flag
      FROM `{PROJECT_ID}.{DATASET_ID}.raw_citybikes_stations`
      -- Process current partition
      WHERE DATE(ingested_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
    ),
    with_lag AS (
      SELECT
        station_id,
        snapshot_time,
        free_bikes,
        availability_pct,
        LAG(availability_pct) OVER (PARTITION BY station_id ORDER BY snapshot_time) as prior_availability_pct,
        null_flag,
        capacity_mismatch
      FROM ranked_snapshots
    )
    SELECT
      station_id,
      snapshot_time,
      free_bikes,
      availability_pct,
      -- availability delta
      CASE
        WHEN prior_availability_pct IS NULL THEN 0.0
        ELSE ROUND(availability_pct - prior_availability_pct, 2)
      END as delta_from_prior,
      null_flag,
      capacity_mismatch
    FROM with_lag
    -- Prevent duplicate records if run frequently
    WHERE snapshot_time NOT IN (
      SELECT DISTINCT snapshot_time FROM `{PROJECT_ID}.{DATASET_ID}.metrics_station_health`
      WHERE DATE(snapshot_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
    )
    """
    
    # Running query
    query_job = client.query(query)
    query_job.result()  # Wait for query to complete
    return query_job.num_dml_affected_rows if query_job.num_dml_affected_rows is not None else 0


def calculate_dora_metrics() -> int:
    """Extracts DORA operational metrics from raw GitHub event logs.
    Monitors deployment frequency and flags direct pushes.
    """
    client = bigquery.Client(project=PROJECT_ID)
    
    query = f"""
    INSERT INTO `{PROJECT_ID}.{DATASET_ID}.metrics_dora`
    (event_id, created_at, actor_login, repo, metric_type, metric_value, flag_value)
    
    SELECT
      id as event_id,
      created_at,
      actor_login,
      repo,
      -- metric type classification
      CASE 
        WHEN type = 'PushEvent' AND JSON_VALUE(payload, '$.ref') = 'refs/heads/main' THEN 'direct_push'
        WHEN type = 'CreateEvent' AND JSON_VALUE(payload, '$.ref_type') = 'tag' THEN 'deploy_freq'
        ELSE 'repository_event'
      END as metric_type,
      1.0 as metric_value,
      -- flag value (1 for direct pushes bypassing branch rules, 0 otherwise)
      CASE 
        WHEN type = 'PushEvent' AND JSON_VALUE(payload, '$.ref') = 'refs/heads/main' THEN 1
        ELSE 0
      END as flag_value
    FROM `{PROJECT_ID}.{DATASET_ID}.raw_github_events`
    WHERE DATE(created_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
      AND id NOT IN (
        SELECT DISTINCT event_id FROM `{PROJECT_ID}.{DATASET_ID}.metrics_dora`
        WHERE DATE(created_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
      )
    """
    
    query_job = client.query(query)
    query_job.result()
    return query_job.num_dml_affected_rows if query_job.num_dml_affected_rows is not None else 0


if __name__ == "__main__":
    print("Testing Analytics ETL process...")
    try:
        sh_rows = calculate_station_health()
        dora_rows = calculate_dora_metrics()
        print(f"Station Health ETL completed: {sh_rows} rows inserted.")
        print(f"GitHub DORA ETL completed: {dora_rows} rows inserted.")
    except Exception as e:
        print(f"ETL Execution failed: {e}")
