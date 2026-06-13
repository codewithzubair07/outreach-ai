import json
import os
import re
import time

from groq import Groq


MODEL = "llama-3.3-70b-versatile"


def _clean_json_response(text):
    raw = (text or "").strip()
    raw = re.sub(r"^```json\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def generate_email(lead, offer, tone_instructions, subject_template):
    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY", ""))
        scraped = lead.get("scraped_content", "")
        if lead.get("scrape_status") == "failed" or not scraped:
            scraped = (
                "Website could not be scraped. Write best possible email "
                "based on company name and domain only."
            )

        system_prompt = (
            "You are an expert cold email copywriter. You write "
            "hyper-personalised cold emails that get replies. Your emails:\n"
            "- Reference something specific about the company from their website\n"
            "- Feel like they were written by a human who did real research\n"
            "- Are concise (150-200 words max for the body)\n"
            "- Have a clear, specific call to action\n"
            "- Never sound spammy or generic\n"
            "- Follow the tone instructions provided exactly"
        )

        user_message = f"""Write a cold email for this lead:

Name: {lead.get('name', '')}
Role: {lead.get('role', '')}
Company: {lead.get('company', '')}
Website: {lead.get('website', '')}

What we found on their website:
{scraped}

What I am offering/pitching:
{offer}

Tone instructions:
{tone_instructions}

Subject line template (adapt it for this lead):
{subject_template}

Respond in this exact JSON format with no extra text:
{{
  "subject": "the subject line",
  "body": "the full email body"
}}"""

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
        )

        content = response.choices[0].message.content
        parsed = json.loads(_clean_json_response(content))
        return {
            "subject": parsed.get("subject", "").strip(),
            "body": parsed.get("body", "").strip(),
        }
    except Exception as error:
        return {"subject": "", "body": "", "error": str(error)}


def generate_emails_batch(
    leads,
    offer,
    tone_instructions,
    subject_template,
    socketio,
    campaign_id,
):
    total = len(leads)
    updated = []

    for index, lead in enumerate(leads):
        socketio.emit(
            "generation_progress",
            {
                "campaign_id": campaign_id,
                "lead_id": lead["id"],
                "company": lead.get("company", ""),
                "status": "generating",
                "current": index + 1,
                "total": total,
                "preview": "",
            },
        )

        result = generate_email(lead, offer, tone_instructions, subject_template)
        enriched = dict(lead)
        if result.get("error"):
            enriched["generation_status"] = "failed"
            enriched["error"] = result["error"]
        else:
            enriched["subject"] = result.get("subject", "")
            enriched["generated_email"] = result.get("body", "")
            enriched["generation_status"] = "generated"
            enriched["error"] = None

        preview = (enriched.get("generated_email", "") or "")[:100]
        socketio.emit(
            "generation_progress",
            {
                "campaign_id": campaign_id,
                "lead_id": lead["id"],
                "company": lead.get("company", ""),
                "status": "done" if not result.get("error") else "failed",
                "current": index + 1,
                "total": total,
                "preview": preview,
            },
        )

        updated.append(enriched)
        time.sleep(0.5)

    return updated


def regenerate_single_email(lead, offer, tone_instructions, subject_template):
    result = generate_email(lead, offer, tone_instructions, subject_template)
    updated = dict(lead)
    if result.get("error"):
        updated["generation_status"] = "failed"
        updated["error"] = result["error"]
    else:
        updated["subject"] = result.get("subject", "")
        updated["generated_email"] = result.get("body", "")
        updated["generation_status"] = "generated"
        updated["error"] = None
    return updated
