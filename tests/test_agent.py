"""
DataSentinel AI SRE Agent & Alerting Unit Tests.
Mocks external API calls to verify alert formatting and heuristics pipelines offline.
"""
from unittest.mock import patch, MagicMock
from agent.actions import post_to_discord
from agent.ai_analyst import analyze_anomaly, get_mock_report


@patch("agent.actions.DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/mock")
@patch("agent.actions.requests.post")
def test_discord_webhook_alert_format(mock_post):
    """Verifies that post_to_discord correctly structures JSON embeds for webhooks."""
    # Mocking standard successful webhook post
    mock_response = MagicMock()
    mock_response.status_code = 204
    mock_post.return_value = mock_response

    result = post_to_discord(
        severity="critical",
        title="Direct Push Detected on Main",
        body="Commit direct push by developer bypassing policies."
    )

    assert result["status"] == "posted"
    assert result["code"] == 204
    assert mock_post.called

    # Verify JSON structure format matches Discord Embed guidelines
    args, kwargs = mock_post.call_args
    posted_json = kwargs["json"]
    assert "embeds" in posted_json
    assert len(posted_json["embeds"]) == 1
    assert posted_json["embeds"][0]["title"] == "[CRITICAL] Direct Push Detected on Main"
    assert posted_json["embeds"][0]["color"] == 0xED4245  # Matches Critical brand red


def test_sre_heuristics_diagnostic_fallbacks():
    """Verifies SRE fallback diagnostics properly compile context and generate valid correction SQL scripts."""
    mock_anomaly = {
        "id": "test-cb-101",
        "source": "citybikes",
        "metric": "docomo-tokyo-shinjuku-01",
        "current_value": 0.0,
        "baseline_mean": 15.2,
        "z_score": -3.85,
        "detected_at": "2026-05-27T23:59:00+09:00"
    }

    report = get_mock_report(mock_anomaly)
    
    assert report["classification"] in ["info", "warning", "critical"]
    assert "fix_sql" in report
    assert "root_cause" in report
    assert "confidence" in report
    assert float(report["confidence"]) > 0.0
    assert "UPDATE" in report["fix_sql"] or "INSERT" in report["fix_sql"]


@patch("agent.ai_analyst.GEMINI_API_KEY", "mock-key")
@patch("agent.ai_analyst.genai.GenerativeModel")
@patch("agent.ai_analyst.post_to_discord")
@patch("agent.ai_analyst.log_report_to_bigquery")
@patch("agent.ai_analyst.gather_github_telemetry")
@patch("agent.ai_analyst.gather_bike_telemetry")
def test_ai_analyst_agent_loop(mock_gather_bike, mock_gather_github, mock_log, mock_post_discord, mock_genai):
    """Verifies the complete AI Analyst diagnosis execution pipeline with mock Gemini API responses."""
    mock_model_instance = MagicMock()
    mock_response = MagicMock()
    # Mocking Gemini structured JSON output matching SreDiagnosticReport schema
    mock_response.text = """
    {
        "classification": "critical",
        "root_cause": "A severe capacity failure has occurred at Shibuya station due to physical sensor metadata mismatch.",
        "confidence": 0.95,
        "action": "Triggered immediate failover metadata repair.",
        "fix_sql": "UPDATE `datasentinel.anomalies_flagged` SET status = 'repaired' WHERE id = 'test-anom-001'",
        "human_message": "Shibuya station has experienced a severe capacity drop."
    }
    """
    mock_model_instance.generate_content.return_value = mock_response
    mock_genai.return_value = mock_model_instance
    mock_gather_bike.return_value = "Mock bike telemetry context."
    mock_gather_github.return_value = "Mock github telemetry context."

    mock_anomaly = {
        "id": "test-anom-001",
        "source": "citybikes",
        "metric": "docomo-tokyo-shibuya-01",
        "current_value": 0.0,
        "baseline_mean": 24.5,
        "z_score": -4.8,
        "detected_at": "2026-05-27T23:59:00+09:00"
    }

    # Execute SRE AI analyst loop
    report = analyze_anomaly(mock_anomaly)

    assert report["classification"] == "critical"
    assert report["confidence"] == 0.95
    assert "Shibuya" in report["root_cause"]
    assert "UPDATE" in report["fix_sql"]
    assert mock_log.called
    assert mock_post_discord.called


def test_api_telemetry_simulated():
    """Verifies that the get_telemetry endpoint function correctly returns simulated telemetry."""
    from app.main import get_telemetry
    data = get_telemetry("docomo-tokyo-shinjuku-east")
    assert len(data) == 24
    assert "time" in data[0]
    assert "actual" in data[0]
    assert "baseline" in data[0]


def test_api_chat_heuristics():
    """Verifies that the SRE Swarm Chat function responds successfully to operator questions."""
    from app.main import sre_chat
    payload = {
        "anomaly_id": "mock-351a87b2",
        "message": "Why did this trigger?"
    }
    data = sre_chat(payload)
    assert "response" in data
    assert len(data["response"]) > 10
