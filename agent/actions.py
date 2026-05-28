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


def create_github_issue(title: str, body: str) -> str:
    """Autonomously opens a trackable GitHub issue in the repo for the SRE incident.
    Returns the HTML URL of the created issue, or an empty string if it fails.
    """
    token = os.getenv("GITHUB_PAT")
    repo = os.getenv("GITHUB_REPO", "ahnjh51/datasentinel")
    
    if not token:
        print("GITHUB_PAT is not set. Skipping autonomous GitHub issue creation.")
        return ""
        
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    payload = {
        "title": title,
        "body": body,
        "labels": ["sre-incident", "data-sentinel", "automated-alert"]
    }
    
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 201:
            data = resp.json()
            return data.get("html_url", "")
        else:
            print(f"Failed to create GitHub issue: {resp.status_code} - {resp.text}")
            return ""
    except Exception as e:
        print(f"Error creating GitHub issue: {e}")
        return ""


def close_github_issue(issue_url: str, comment_text: str) -> bool:
    """Autonomously closes a GitHub issue and posts a resolution comment.
    Returns True if successfully closed, False otherwise.
    """
    token = os.getenv("GITHUB_PAT")
    repo = os.getenv("GITHUB_REPO", "ahnjh51/datasentinel")
    
    if not token or not issue_url:
        print("Missing credentials or issue_url. Skipping GitHub issue resolution.")
        return False
        
    # Extract issue number from URL (e.g., https://github.com/.../issues/12)
    try:
        issue_number = issue_url.split("/issues/")[-1]
    except Exception as e:
        print(f"Failed to parse issue number from {issue_url}: {e}")
        return False
        
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
    comment_url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    # 1. Post comment
    try:
        comment_resp = requests.post(comment_url, json={"body": comment_text}, headers=headers, timeout=15)
        if comment_resp.status_code != 201:
            print(f"Failed to post resolution comment to GitHub issue: {comment_resp.text}")
    except Exception as e:
        print(f"Error posting comment to GitHub: {e}")

    # 2. Close issue
    try:
        close_resp = requests.patch(url, json={"state": "closed", "state_reason": "completed"}, headers=headers, timeout=15)
        if close_resp.status_code == 200:
            print(f"Successfully closed GitHub issue #{issue_number}.")
            return True
        else:
            print(f"Failed to close GitHub issue #{issue_number}: {close_resp.text}")
            return False
    except Exception as e:
        print(f"Error closing GitHub issue: {e}")
        return False


if __name__ == "__main__":
    print("Testing Discord notification...")
    result = post_to_discord(
        severity="info",
        title="DataSentinel Active",
        body="DataSentinel autonomous DevOps/SRE agent has successfully connected to the monitoring loop."
    )
    print(f"Result: {result}")
