# followup.py
import time
import threading
from datetime import datetime, timedelta
from agent import generate_email
from gmail_helper import get_gmail_service, send_cold_email
from store import load_store, save_store

def check_and_send_followups(days=3):
    """
    Check all sent leads. If sent more than `days` ago and not replied,
    send a follow-up email automatically.
    """
    store = load_store()
    campaigns = store.get("campaigns", [])
    followup_count = 0

    try:
        service = get_gmail_service()
    except Exception as e:
        print(f"Gmail not connected for followups: {e}")
        return 0

    for campaign in campaigns:
        for lead in campaign.get("leads", []):
            if not lead.get("sent"):
                continue
            if lead.get("followup_sent"):
                continue
            if not lead.get("email"):
                continue

            sent_at = lead.get("sent_at")
            if not sent_at:
                continue

            sent_time = datetime.fromisoformat(sent_at)
            if datetime.now() - sent_time < timedelta(days=days):
                continue

            # Generate follow-up
            followup_body = generate_followup_email(
                lead,
                campaign.get("offer", ""),
                campaign.get("tone_instructions", "")
            )

            result = send_cold_email(
                service,
                lead["email"],
                lead["name"],
                f"Re: {lead.get('subject', '')}",
                followup_body
            )

            if result.get("success"):
                lead["followup_sent"] = True
                lead["followup_sent_at"] = datetime.now().isoformat()
                followup_count += 1

    save_store(store)
    return followup_count


def generate_followup_email(lead, offer, tone_instructions):
    from groq import Groq
    import os

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    prompt = f"""Write a short, friendly follow-up email for a cold outreach.
The original email was sent to {lead['name']} at {lead['company']}.
Offer: {offer}
Tone: {tone_instructions}

Keep it under 80 words. Reference that you reached out before.
Just checking in, no pressure. End with a simple question.
Return only the email body, no subject line."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )

    return response.choices[0].message.content.strip()


def start_followup_scheduler(days=3, check_interval_hours=12):
    """Run follow-up checker every 12 hours in background."""
    def loop():
        while True:
            print(f"[FollowUp] Checking for leads to follow up...")
            count = check_and_send_followups(days=days)
            print(f"[FollowUp] Sent {count} follow-up emails")
            time.sleep(check_interval_hours * 3600)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()