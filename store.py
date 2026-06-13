import json
from pathlib import Path


STORE_PATH = Path("campaigns.json")


def load_store():
    if not STORE_PATH.exists():
        initial = {"campaigns": []}
        save_store(initial)
        return initial

    with STORE_PATH.open("r", encoding="utf-8") as file:
        try:
            data = json.load(file)
        except json.JSONDecodeError:
            data = {"campaigns": []}
            save_store(data)

    if "campaigns" not in data or not isinstance(data["campaigns"], list):
        data = {"campaigns": []}
        save_store(data)

    return data


def save_store(data):
    with STORE_PATH.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def create_campaign(campaign):
    data = load_store()
    data["campaigns"].append(campaign)
    save_store(data)


def get_campaign(campaign_id):
    data = load_store()
    for campaign in data["campaigns"]:
        if campaign.get("id") == campaign_id:
            return campaign
    return None


def update_campaign(campaign_id, updated_campaign):
    data = load_store()
    for index, campaign in enumerate(data["campaigns"]):
        if campaign.get("id") == campaign_id:
            data["campaigns"][index] = updated_campaign
            save_store(data)
            return updated_campaign
    return None


def get_all_campaigns():
    data = load_store()
    return sorted(
        data["campaigns"],
        key=lambda campaign: campaign.get("created_at", ""),
        reverse=True,
    )


def delete_campaign(campaign_id):
    data = load_store()
    original_count = len(data["campaigns"])
    data["campaigns"] = [
        campaign for campaign in data["campaigns"] if campaign.get("id") != campaign_id
    ]
    if len(data["campaigns"]) == original_count:
        return False
    save_store(data)
    return True


def update_lead(campaign_id, lead_id, updated_lead):
    campaign = get_campaign(campaign_id)
    if not campaign:
        return None

    leads = campaign.get("leads", [])
    for index, lead in enumerate(leads):
        if lead.get("id") == lead_id:
            leads[index] = updated_lead
            campaign["leads"] = leads
            update_campaign(campaign_id, campaign)
            return updated_lead
    return None
