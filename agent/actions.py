"""
DataSentinel Alert Actions.
Handles outgoing Discord Webhook structured alerts.
"""
import os
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


def post_to_discord(severity: str, title: str, body: str) -> dict:
    """Post a structured color-coded alert to Discord webhook.
    Returns response dictionary with HTTP status and code.
    """
    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL is not set. Skipping Discord alert posting.")
        return {"status": "skipped", "reason": "No webhook URL"}

    # Color Palette matching Discord brand colors
    color_map = {
        "info":     0x5865F2,   # Discord Blue
        "warning":  0xFEE75C,   # Discord Yellow
        "critical": 0xED4245,   # Discord Red
        "resolved": 0x2ead4b,   # Wise Green (Success)
    }

    payload = {
        "embeds": [{
            "title": f"[{severity.upper()}] {title}",
            "description": body,
            "color": color_map.get(severity.lower(), 0x5865F2),
            "footer": {
                "text": "DataSentinel · Autonomous SRE Agent"
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    }

    try:
        resp = requests.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=15
        )
        resp.raise_for_status()
        return {"status": "posted", "code": resp.status_code}
    except Exception as e:
        print(f"Failed to post alert to Discord: {e}")
        return {"status": "failed", "reason": str(e)}


if __name__ == "__main__":
    print("Testing Discord notification...")
    result = post_to_discord(
        severity="info",
        title="DataSentinel Active",
        body="DataSentinel autonomous DevOps/SRE agent has successfully connected to the monitoring loop."
    )
    print(f"Result: {result}")
