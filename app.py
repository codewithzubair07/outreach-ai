import csv
import io
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_file
from flask_socketio import SocketIO

from agent import generate_emails_batch, regenerate_single_email
from gmail_helper import check_gmail_connected, get_gmail_service, send_cold_email
from scraper import scrape_multiple
from store import (
    create_campaign,
    delete_campaign,
    get_all_campaigns,
    get_campaign,
    update_campaign,
    update_lead,
)


load_dotenv()

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

running_campaigns = set()
running_lock = threading.Lock()


def _serialize_campaign_light(campaign):
    leads = campaign.get("leads", [])
    safe_leads = []
    for lead in leads:
        clone = dict(lead)
        clone.pop("generated_email", None)
        clone.pop("scraped_content", None)
        safe_leads.append(clone)
    cloned = dict(campaign)
    cloned["leads"] = safe_leads
    return cloned


def _campaign_worker(campaign_id):
    try:
        campaign = get_campaign(campaign_id)
        if not campaign:
            return

        leads = campaign.get("leads", [])
        leads = scrape_multiple(leads, socketio, campaign_id)
        leads = generate_emails_batch(
            leads,
            campaign.get("offer", ""),
            campaign.get("tone_instructions", ""),
            campaign.get("subject_template", ""),
            socketio,
            campaign_id,
        )

        campaign["leads"] = leads
        campaign["status"] = "completed"
        update_campaign(campaign_id, campaign)
        socketio.emit("campaign_complete", {"campaign_id": campaign_id})
    finally:
        with running_lock:
            running_campaigns.discard(campaign_id)


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/campaign/create")
def api_create_campaign():
    payload = request.get_json(force=True)
    campaign_id = str(uuid4())
    campaign = {
        "id": campaign_id,
        "name": payload.get("name", "Untitled Campaign"),
        "created_at": datetime.now().isoformat(),
        "offer": payload.get("offer", ""),
        "tone_instructions": payload.get("tone_instructions", ""),
        "subject_template": payload.get("subject_template", ""),
        "status": "draft",
        "leads": [],
    }
    create_campaign(campaign)
    return jsonify({"success": True, "campaign_id": campaign_id})


@app.post("/api/campaign/<campaign_id>/upload")
def api_upload_csv(campaign_id):
    campaign = get_campaign(campaign_id)
    if not campaign:
        return jsonify({"success": False, "error": "Campaign not found"}), 404

    if "file" not in request.files:
        return jsonify({"success": False, "error": "CSV file is required"}), 400

    file = request.files["file"]
    temp_path = UPLOADS_DIR / f"{uuid4()}.csv"
    file.save(temp_path)

    try:
        frame = pd.read_csv(temp_path)
        required_columns = {"name", "company", "website"}
        if not required_columns.issubset(set(frame.columns)):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "CSV must contain columns: name, company, website",
                    }
                ),
                400,
            )

        leads = []
        for _, row in frame.iterrows():
            leads.append(
                {
                    "id": str(uuid4()),
                    "name": str(row.get("name", "")).strip(),
                    "company": str(row.get("company", "")).strip(),
                    "website": str(row.get("website", "")).strip(),
                    "role": str(row.get("role", "Decision Maker") or "Decision Maker").strip(),
                    "scraped_content": "",
                    "scrape_status": "pending",
                    "email": str(row.get("email", "") or "").strip(),
                    "generated_email": "",
                    "subject": "",
                    "generation_status": "pending",
                    "sent": False,
                    "sent_at": None,
                    "error": None,
                }
            )

        campaign["leads"] = leads
        campaign["status"] = "ready"
        update_campaign(campaign_id, campaign)
        return jsonify({"success": True, "leads_count": len(leads), "leads": leads})
    finally:
        if temp_path.exists():
            temp_path.unlink()


@app.post("/api/campaign/<campaign_id>/run")
def api_run_campaign(campaign_id):
    campaign = get_campaign(campaign_id)
    if not campaign:
        return jsonify({"success": False, "error": "Campaign not found"}), 404

    with running_lock:
        if campaign_id in running_campaigns:
            return jsonify({"success": False, "error": "Campaign already running"}), 400
        running_campaigns.add(campaign_id)

    campaign["status"] = "running"
    update_campaign(campaign_id, campaign)

    thread = threading.Thread(target=_campaign_worker, args=(campaign_id,), daemon=True)
    thread.start()
    return jsonify({"success": True, "message": "Processing started"})


@app.get("/api/campaign/<campaign_id>")
def api_get_campaign(campaign_id):
    campaign = get_campaign(campaign_id)
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404
    return jsonify({"campaign": campaign})


@app.get("/api/campaigns")
def api_get_campaigns():
    campaigns = [_serialize_campaign_light(campaign) for campaign in get_all_campaigns()]
    return jsonify({"campaigns": campaigns})


@app.post("/api/campaign/<campaign_id>/lead/<lead_id>/regenerate")
def api_regenerate(campaign_id, lead_id):
    campaign = get_campaign(campaign_id)
    if not campaign:
        return jsonify({"success": False, "error": "Campaign not found"}), 404

    lead = next((item for item in campaign.get("leads", []) if item.get("id") == lead_id), None)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found"}), 404

    updated = regenerate_single_email(
        lead,
        campaign.get("offer", ""),
        campaign.get("tone_instructions", ""),
        campaign.get("subject_template", ""),
    )
    update_lead(campaign_id, lead_id, updated)
    return jsonify({"success": True, "lead": updated})


@app.post("/api/campaign/<campaign_id>/lead/<lead_id>/send")
def api_send_single(campaign_id, lead_id):
    payload = request.get_json(force=True)
    campaign = get_campaign(campaign_id)
    if not campaign:
        return jsonify({"success": False, "error": "Campaign not found"}), 404

    lead = next((item for item in campaign.get("leads", []) if item.get("id") == lead_id), None)
    if not lead:
        return jsonify({"success": False, "error": "Lead not found"}), 404

    target_email = payload.get("email") or lead.get("email", "")
    if not target_email:
        return jsonify({"success": False, "error": "Email is required"}), 400

    try:
        service = get_gmail_service()
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 400

    result = send_cold_email(
        service,
        target_email,
        lead.get("name", ""),
        lead.get("subject", ""),
        lead.get("generated_email", ""),
    )
    if not result.get("success"):
        return jsonify(result), 400

    lead["email"] = target_email
    lead["sent"] = True
    lead["sent_at"] = datetime.now().isoformat()
    lead["error"] = None
    update_lead(campaign_id, lead_id, lead)
    return jsonify({"success": True})


@app.post("/api/campaign/<campaign_id>/send-all")
def api_send_all(campaign_id):
    campaign = get_campaign(campaign_id)
    if not campaign:
        return jsonify({"success": False, "error": "Campaign not found"}), 404

    try:
        service = get_gmail_service()
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 400

    sent = 0
    failed = 0
    for lead in campaign.get("leads", []):
        if not lead.get("email"):
            continue
        result = send_cold_email(
            service,
            lead.get("email", ""),
            lead.get("name", ""),
            lead.get("subject", ""),
            lead.get("generated_email", ""),
        )
        if result.get("success"):
            lead["sent"] = True
            lead["sent_at"] = datetime.now().isoformat()
            lead["error"] = None
            sent += 1
        else:
            lead["error"] = result.get("error")
            failed += 1

    update_campaign(campaign_id, campaign)
    return jsonify({"success": True, "sent": sent, "failed": failed})


@app.get("/api/campaign/<campaign_id>/export")
def api_export(campaign_id):
    campaign = get_campaign(campaign_id)
    if not campaign:
        return jsonify({"success": False, "error": "Campaign not found"}), 404

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["name", "company", "website", "role", "email", "subject", "body", "sent"])
    for lead in campaign.get("leads", []):
        writer.writerow(
            [
                lead.get("name", ""),
                lead.get("company", ""),
                lead.get("website", ""),
                lead.get("role", ""),
                lead.get("email", ""),
                lead.get("subject", ""),
                lead.get("generated_email", ""),
                lead.get("sent", False),
            ]
        )

    output.seek(0)
    filename = f"{campaign.get('name', 'campaign').replace(' ', '_')}_{datetime.now().date()}.csv"
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


@app.delete("/api/campaign/<campaign_id>")
def api_delete_campaign(campaign_id):
    deleted = delete_campaign(campaign_id)
    if not deleted:
        return jsonify({"success": False, "error": "Campaign not found"}), 404
    return jsonify({"success": True})


@app.get("/api/gmail/auth")
def api_gmail_auth():
    try:
        get_gmail_service()
        return redirect("/")
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 400


@app.get("/api/gmail/status")
def api_gmail_status():
    return jsonify({"connected": check_gmail_connected()})


@app.post("/api/gmail/disconnect")
def api_gmail_disconnect():
    token = Path("token.json")
    if token.exists():
        token.unlink()
    return jsonify({"success": True})


if __name__ == "__main__":
    print(
        """
============================================
⚡ OUTREACHAI — COLD EMAIL PERSONALISER
============================================

Setup checklist:
[ ] 1. Get FREE Groq API Key → console.groq.com
       Add to .env as GROQ_API_KEY

[ ] 2. Gmail Setup (optional, for sending):
       → console.cloud.google.com
       → Create project → Enable Gmail API
       → Credentials → OAuth 2.0 → Desktop App
       → Download as credentials.json
       → Place in this folder

[ ] 3. Install dependencies:
       pip install -r requirements.txt

Running at: http://localhost:5000
============================================
"""
    )
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
