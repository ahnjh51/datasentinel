"""
DataSentinel Autonomous Gemini AI Analyst.
Diagnoses anomalies using structured JSON output from Gemini and triggers autonomous closed-loop actions.
"""
import os
import uuid
import json
from google.cloud import bigquery
from pydantic import BaseModel, Field
import google.generativeai as genai
from datetime import datetime, timezone
from dotenv import load_dotenv
from agent.actions import post_to_discord, create_github_issue

load_dotenv()

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "datasentinel-hackathon")
DATASET_ID = "datasentinel"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 1. Structured Output Schema using Pydantic
class SreDiagnosticReport(BaseModel):
    classification: str = Field(description="Incident severity: 'info', 'warning', or 'critical'")
    anomaly_nature: str = Field(description="Nature of anomaly: 'pipeline_fault', 'real_world_event', or 'policy_violation'")
    root_cause: str = Field(description="Detailed explanation of the diagnosed root cause")
    impact_analysis: str = Field(description="Comprehensive analysis of downstream impact (why this matters)")
    confidence: float = Field(description="Confidence score of the SRE model between 0.0 and 1.0")
    recommended_action: str = Field(description="Immediate physical or system actions recommended to mitigate or resolve the incident")
    action: str = Field(description="Action taken by the SRE agent (e.g. GitHub issue created and Discord alerted)")
    fix_sql: str = Field(description="SQL script designed to fix the database anomaly or log correction context")
    human_message: str = Field(description="Brief user-friendly description to post to Discord alerts")


def analyze_anomaly(anomaly: dict) -> dict:
    """Takes a flagged anomaly, compiles telemetry context, and queries Gemini
    using structured JSON output to retrieve a full diagnostic report.
    Then autonomously creates a GitHub issue to close the SRE loop!
    """
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY is not set. Using local mock analyst.")
        report_data = get_mock_report(anomaly)
        report_data["github_issue_url"] = ""
        return report_data

    # Configure Gemini SDK
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')

    # Gather telemetry context
    context = ""
    if anomaly["source"] == "citybikes":
        context = gather_bike_telemetry(anomaly["metric"])
    else:
        context = gather_github_telemetry(anomaly["id"])

    prompt = f"""
    You are an autonomous Senior DevOps & Site Reliability Engineer (SRE) Swarm Orchestrator.
    You are responding to an incident anomaly detected by DataSentinel.
    
    [Incident Telemetry Details]
    - Anomaly ID: {anomaly["id"]}
    - Source System: {anomaly["source"]}
    - Target Metric/Identifier: {anomaly["metric"]}
    - Detected Value: {anomaly["current_value"]}
    - Historical baseline: {anomaly["baseline_mean"]}
    - Statistical Z-Score: {anomaly["z_score"]}
    - Detection Timestamp: {anomaly["detected_at"]}
    
    [Collected Diagnostic Context]
    {context}
    
    Perform a complete SRE diagnosis.
    Determine:
    1. Incident classification (info, warning, critical)
    2. Nature of the anomaly: Is it a pipeline data pipeline/sensor fault, a real-world event (e.g. morning peak rush, weather, local logistics), or a branch policy violation?
    3. Detailed Root Cause
    4. Downstream Impact Analysis: Why does this matter? What happens if left un-remediated?
    5. Confidence Score (0.0 to 1.0)
    6. Practical recommended recovery actions
    7. Safe SQL script (`fix_sql`) that logs, repairs, or annotates this anomaly status (e.g. updating anomalies_flagged status to investigating/resolved).
    """

    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=SreDiagnosticReport
            )
        )
        report_data = json.loads(response.text)
    except Exception as e:
        print(f"Gemini API diagnosis failed or parsing error: {e}. Falling back to SRE heuristics.")
        report_data = get_fallback_heuristics(anomaly, str(e))

    # --- AUTONOMOUS LOOP CLOSING: CREATE GITHUB ISSUE ---
    github_url = ""
    try:
        issue_title = f"[SRE Incident] Anomaly detected on {anomaly['metric']}"
        
        # Build a beautiful Markdown report for developers inside GitHub Issues
        issue_body = f"""# 🛡️ Autonomous SRE Incident Diagnostic Report

An anomalous metric has been flagged and diagnosed by the **DataSentinel** SRE Swarm.

## 📊 Telemetry Metrics
* **Incident Reference**: `{anomaly["id"]}`
* **Telemetry Source**: `{anomaly["source"].upper()}`
* **Target Metric/Station**: `{anomaly["metric"]}`
* **Detected Outlier Value**: `{anomaly["current_value"]}`
* **Historical Baseline Mean**: `{anomaly["baseline_mean"]}`
* **Statistical Z-Score Deviation**: `{anomaly["z_score"]}`
* **Detection Timestamp**: `{anomaly["detected_at"]}`

---

## 🕵️‍♂️ SRE Cognitive Diagnostics

### 1. Classification & Confidence
* **Severity Classification**: `{report_data["classification"].upper()}`
* **SRE Confidence Level**: `{int(report_data["confidence"] * 100)}%`
* **Anomaly Nature**: `{report_data.get("anomaly_nature", "unknown").upper()}`

### 2. Root Cause Diagnosis
{report_data["root_cause"]}

### 3. Downstream Impact Analysis (Why This Matters)
{report_data.get("impact_analysis", "No impact analysis provided.")}

---

## ⚡ Resolution Action Plan

### 🛠️ Recommended Operator Recovery
{report_data.get("recommended_action", "No recovery instructions listed.")}

### 🤖 Autonomously Formulated Correction SQL (BigQuery)
```sql
{report_data["fix_sql"]}
```

---
*Created autonomously by DataSentinel DevOps AI Agent Swarm.*
"""
        github_url = create_github_issue(issue_title, issue_body)
        if github_url:
            report_data["action"] = f"Autonomously created trackable GitHub issue and alerted operators via Discord."
            print(f"Successfully closed loop. Created GitHub Issue: {github_url}")
    except Exception as git_err:
        print(f"Failed to execute autonomous GitHub action: {git_err}")

    report_data["github_issue_url"] = github_url

    # Log action to BigQuery
    log_report_to_bigquery(anomaly["id"], report_data)

    # Post to Discord
    post_diagnostic_to_discord(anomaly, report_data)

    return report_data


def gather_bike_telemetry(station_id: str) -> str:
    """Queries BigQuery to fetch past 5 snapshots of the station for Gemini context."""
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
    SELECT snapshot_time, free_bikes, availability_pct, delta_from_prior
    FROM `{PROJECT_ID}.{DATASET_ID}.metrics_station_health`
    WHERE station_id = '{station_id}'
    ORDER BY snapshot_time DESC
    LIMIT 5
    """
    try:
        query_job = client.query(query)
        rows = query_job.result()
        telemetry = []
        for r in rows:
            telemetry.append(f"- Time: {r.snapshot_time}, Available: {r.free_bikes}, Pct: {r.availability_pct}%, Delta: {r.delta_from_prior}%")
        return "\n".join(telemetry) if telemetry else "No prior history available."
    except Exception as e:
        return f"Failed to retrieve telemetry context: {e}"


def gather_github_telemetry(event_id: str) -> str:
    """Fetches GitHub event details for contextual analysis."""
    client = bigquery.Client(project=PROJECT_ID)
    query = f"""
    SELECT actor_login, repo, payload, created_at
    FROM `{PROJECT_ID}.{DATASET_ID}.raw_github_events`
    WHERE id = '{event_id}'
    LIMIT 1
    """
    try:
        query_job = client.query(query)
        rows = list(query_job.result())
        if not rows:
            return "No raw event payload found."
        r = rows[0]
        payload_data = json.loads(r.payload) if isinstance(r.payload, str) else r.payload
        ref = payload_data.get("ref", "N/A")
        commits = payload_data.get("commits", [])
        commit_messages = [c.get("message", "") for c in commits]
        
        return f"""
        GitHub Direct Push Event Details:
        - Actor: {r.actor_login}
        - Repository: {r.repo}
        - Pushed Branch: {ref}
        - Commit messages: {commit_messages}
        - Raw Payload snippet: {str(payload_data)[:500]}
        """
    except Exception as e:
        return f"Failed to retrieve GitHub telemetry: {e}"


def log_report_to_bigquery(anomaly_id: str, report: dict) -> None:
    """Saves the SRE Gemini diagnostic report into `agent_actions_log` and updates the flagged anomaly."""
    client = bigquery.Client(project=PROJECT_ID)
    
    rows = [{
        "id":                 str(uuid.uuid4()),
        "triggered_at":        datetime.now(timezone.utc).isoformat(),
        "anomaly_id":          anomaly_id,
        "classification":      report["classification"],
        "anomaly_nature":      report.get("anomaly_nature", "unknown"),
        "root_cause":          report["root_cause"],
        "impact_analysis":     report.get("impact_analysis", "unknown"),
        "confidence":          float(report["confidence"]),
        "recommended_action":  report.get("recommended_action", "unknown"),
        "action":              report["action"],
        "fix_sql":             report["fix_sql"],
        "human_message":       report["human_message"],
        "discord_posted":      True,
        "github_issue_url":    report.get("github_issue_url", "")
    }]
    
    try:
        errors = client.insert_rows_json(f"{PROJECT_ID}.{DATASET_ID}.agent_actions_log", rows)
        if errors:
            print(f"Failed to log agent action to BigQuery: {errors}")
    except Exception as e:
        print(f"Failed to execute agent logging: {e}")

    try:
        # Also update the flagged anomalies table with status and github_issue_url
        if report.get("github_issue_url"):
            update_query = f"""
            UPDATE `{PROJECT_ID}.{DATASET_ID}.anomalies_flagged`
            SET github_issue_url = '{report["github_issue_url"]}'
            WHERE id = '{anomaly_id}'
            """
            client.query(update_query).result()
    except Exception as e:
        print(f"Failed to update anomalies_flagged github_issue_url: {e}")


def post_diagnostic_to_discord(anomaly: dict, report: dict) -> None:
    """Formats and posts the diagnostic report to Discord webhook."""
    severity = report["classification"]
    title = f"DataSentinel Diagnostic: {anomaly['source'].upper()} Incident"
    
    github_block = ""
    if report.get("github_issue_url"):
        github_block = f"\n**GitHub Autonomous Tracking:**\n:link: [Track SRE Incident on GitHub]({report['github_issue_url']})\n"
        
    body = f"""
**Status:** :shield: Flagged & Diagnosed
**Severity:** `{severity.upper()}` (Confidence: {int(report['confidence']*100)}%)
**Anomaly Nature:** `{report.get('anomaly_nature', 'unknown').upper()}`
{github_block}
**Anomaly Summary:** 
* Source: `{anomaly['source']}`
* Metric/Station: `{anomaly['metric']}`
* Current Value: `{anomaly['current_value']}`
* Baseline: `{anomaly['baseline_mean']}`
* Z-Score: `{anomaly['z_score']}`

**SRE Diagnosis:**
{report['root_cause']}

**Downstream Impact Analysis (Why This Matters):**
{report.get('impact_analysis', 'unknown')}

**Resolution Action Taken:**
{report['action']}

**Automated Database Fix SQL:**
```sql
{report['fix_sql']}
```

**SRE Analyst message:**
{report['human_message']}
"""
    post_to_discord(severity, title, body)


def get_mock_report(anomaly: dict) -> dict:
    """Helper method for local development if Gemini key is not set."""
    if anomaly["source"] == "citybikes":
        return {
            "classification": "warning",
            "anomaly_nature": "real_world_event",
            "root_cause": "Station availability dropped significantly below historical moving average due to local peak hour checkout surge.",
            "impact_analysis": "Commuters will experience empty docks at critical hubs, affecting bike-sharing service level agreements.",
            "confidence": 0.85,
            "recommended_action": "Coordinate Tokyo operations to dispatch re-balancing vehicles to top up available bicycles at this station.",
            "action": "Flagged station capacity drop; triggered warning alerts to re-balance operators.",
            "fix_sql": f"UPDATE `{PROJECT_ID}.{DATASET_ID}.anomalies_flagged` SET status = 'investigating' WHERE id = '{anomaly['id']}'",
            "human_message": f"Bike station {anomaly['metric']} availability is low. Alerting central Tokyo re-balancing teams.",
            "github_issue_url": ""
        }
    else:
        return {
            "classification": "critical",
            "anomaly_nature": "policy_violation",
            "root_cause": "Developer direct push detected on protected main branch. Policy violation.",
            "impact_analysis": "Bypassing pull request gates directly threatens production codebase stability, risking docker compile crashes and pipeline disruptions.",
            "confidence": 0.99,
            "recommended_action": "Notify development lead immediately. Review push events, freeze deployment triggers, and enforce branch protection policies.",
            "action": "Immediate critical policy alert posted to SRE channel; locking down deployment triggers.",
            "fix_sql": f"UPDATE `{PROJECT_ID}.{DATASET_ID}.anomalies_flagged` SET status = 'escalated' WHERE id = '{anomaly['id']}'",
            "human_message": "Direct push detected on branch main! Bypassed pull request controls.",
            "github_issue_url": ""
        }


def get_fallback_heuristics(anomaly: dict, error_msg: str) -> dict:
    """Fallback diagnostic logic if Gemini returns an invalid schema or fails."""
    report = get_mock_report(anomaly)
    report["root_cause"] += f" (Fallback applied. Gemini SRE connection error: {error_msg})"
    return report


if __name__ == "__main__":
    print("Testing AI Analyst with mock anomaly...")
    mock_anomaly = {
        "id": "mock-id-12345",
        "source": "citybikes",
        "metric": "docomo-shinjuku-01",
        "current_value": 0.0,
        "baseline_mean": 85.0,
        "z_score": -5.6,
        "detected_at": datetime.now(timezone.utc).isoformat()
    }
    report = analyze_anomaly(mock_anomaly)
    print(f"Diagnostic report: {json.dumps(report, indent=2)}")
