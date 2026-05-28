"""
DataSentinel BigQuery Setup Script.
Creates the `datasentinel` dataset and all required tables
in the asia-northeast1 (Tokyo) region securely using Google Cloud SDK.
"""
import os
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "datasentinel-hackathon")
DATASET_ID = "datasentinel"
LOCATION = "asia-northeast1"  # Tokyo region to match bike data origin

def run_setup():
    print("Initializing BigQuery Client...")
    # Client automatically uses GOOGLE_APPLICATION_CREDENTIALS from environment
    client = bigquery.Client(project=PROJECT_ID)
    
    # 1. Create Dataset if not exists
    dataset_ref = bigquery.DatasetReference(PROJECT_ID, DATASET_ID)
    try:
        dataset = client.get_dataset(dataset_ref)
        print(f"Dataset {PROJECT_ID}.{DATASET_ID} already exists in location {dataset.location}.")
    except Exception as e:
        from google.api_core.exceptions import Conflict
        print(f"Dataset {DATASET_ID} not found or accessible. Trying to create in location {LOCATION}...")
        try:
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = LOCATION
            dataset.description = "DataSentinel data and anomaly log layers"
            dataset = client.create_dataset(dataset, timeout=30)
            print(f"Dataset {PROJECT_ID}.{DATASET_ID} successfully created.")
        except Conflict:
            print(f"Dataset {PROJECT_ID}.{DATASET_ID} already exists (received Conflict 409). Proceeding...")
        except Exception as create_error:
            print(f"Could not create dataset: {create_error}. Proceeding with caution...")

    # 2. Table Definitions
    tables = {
        "raw_citybikes_stations": {
            "schema": [
                bigquery.SchemaField("station_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("free_bikes", "INT64", mode="NULLABLE"),
                bigquery.SchemaField("empty_slots", "INT64", mode="NULLABLE"),
                bigquery.SchemaField("latitude", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("longitude", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
            ],
            "partitioning": bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="ingested_at"
            ),
            "desc": "Raw bike station snapshots, ingested every 5 minutes"
        },
        "raw_github_events": {
            "schema": [
                bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("type", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("actor_login", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("repo", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("payload", "JSON", mode="NULLABLE"),
                bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
            ],
            "partitioning": bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="created_at"
            ),
            "desc": "Raw repository events ingested from GitHub API"
        },
        "metrics_station_health": {
            "schema": [
                bigquery.SchemaField("station_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("snapshot_time", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("free_bikes", "INT64", mode="NULLABLE"),
                bigquery.SchemaField("availability_pct", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("delta_from_prior", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("null_flag", "BOOLEAN", mode="NULLABLE"),
                bigquery.SchemaField("capacity_mismatch", "BOOLEAN", mode="NULLABLE"),
            ],
            "partitioning": bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="snapshot_time"
            ),
            "desc": "Aggregated metrics for bike stations health state"
        },
        "metrics_dora": {
            "schema": [
                bigquery.SchemaField("event_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("actor_login", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("repo", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("metric_type", "STRING", mode="NULLABLE"), # 'deploy_freq' | 'pr_cycle_time' | 'direct_push'
                bigquery.SchemaField("metric_value", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("flag_value", "INT64", mode="NULLABLE"),
            ],
            "partitioning": bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="created_at"
            ),
            "desc": "Aggregated DORA metrics parsed from raw github events"
        },
        "anomalies_flagged": {
            "schema": [
                bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("detected_at", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("source", "STRING", mode="NULLABLE"),  # 'citybikes' | 'github'
                bigquery.SchemaField("metric", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("z_score", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("current_value", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("baseline_mean", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("status", "STRING", mode="NULLABLE"),    # 'new' | 'investigating' | 'fixed' | 'escalated'
            ],
            "partitioning": bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="detected_at"
            ),
            "desc": "Incident and performance anomalies flagged via statistical Z-Scoring"
        },
        "agent_actions_log": {
            "schema": [
                bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("triggered_at", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("anomaly_id", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("classification", "STRING", mode="NULLABLE"), # 'info' | 'warning' | 'critical'
                bigquery.SchemaField("root_cause", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("confidence", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("action", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("fix_sql", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("human_message", "STRING", mode="NULLABLE"),
                bigquery.SchemaField("discord_posted", "BOOLEAN", mode="NULLABLE"),
            ],
            "partitioning": bigquery.TimePartitioning(
                type_=bigquery.TimePartitioningType.DAY,
                field="triggered_at"
            ),
            "desc": "Autonomous SRE Gemini Analyst diagnostic logs and resolution actions"
        }
    }

    # 3. Create tables
    for table_name, config in tables.items():
        table_ref = dataset_ref.table(table_name)
        try:
            client.get_table(table_ref)
            print(f"Table {table_name} already exists.")
        except Exception:
            print(f"Table {table_name} not found. Creating table...")
            table = bigquery.Table(table_ref, schema=config["schema"])
            table.time_partitioning = config["partitioning"]
            table.description = config["desc"]
            client.create_table(table, timeout=30)
            print(f"Table {table_name} successfully created.")

    print("\nAll BigQuery resources configured successfully.")

if __name__ == "__main__":
    run_setup()
