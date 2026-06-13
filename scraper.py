import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}


def _normalize_url(url):
    clean_url = (url or "").strip()
    if not clean_url.startswith(("http://", "https://")):
        clean_url = f"https://{clean_url}"
    return clean_url


def _extract_from_soup(soup):
    parts = []

    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        parts.append(meta["content"].strip())

    if soup.title and soup.title.string:
        parts.append(soup.title.string.strip())

    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = tag.get_text(" ", strip=True)
        if text:
            parts.append(text)

    section_keywords = ["about", "service", "hero", "mission", "what we do"]
    for element in soup.find_all(["section", "div", "article"]):
        joined = " ".join(element.get("class", [])).lower()
        element_id = (element.get("id") or "").lower()
        if any(keyword in joined or keyword in element_id for keyword in section_keywords):
            text = element.get_text(" ", strip=True)
            if text:
                parts.append(text)

    body_text = ""
    if soup.body:
        body_text = soup.body.get_text(" ", strip=True)
    words = body_text.split()
    if words:
        parts.append(" ".join(words[:500]))

    combined = " ".join(parts)
    combined = re.sub(r"\s+", " ", combined).strip()
    return combined[:2000]


def scrape_website(url):
    normalized_url = _normalize_url(url)
    try:
        response = requests.get(normalized_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        all_content = [_extract_from_soup(soup)]

        for path in ["/about", "/services"]:
            page_url = urljoin(normalized_url, path)
            try:
                sub_response = requests.get(page_url, headers=HEADERS, timeout=10)
                if sub_response.ok:
                    sub_soup = BeautifulSoup(sub_response.text, "html.parser")
                    all_content.append(_extract_from_soup(sub_soup))
            except Exception:
                continue

        combined = re.sub(r"\s+", " ", " ".join(filter(None, all_content))).strip()[:2000]
        return {"success": True, "content": combined, "url": normalized_url}
    except Exception as error:
        return {
            "success": False,
            "content": "",
            "error": str(error),
            "url": normalized_url,
        }


def scrape_multiple(leads, socketio, campaign_id):
    total = len(leads)
    updated_leads = []

    for index, lead in enumerate(leads):
        socketio.emit(
            "scrape_progress",
            {
                "campaign_id": campaign_id,
                "lead_id": lead["id"],
                "company": lead.get("company", ""),
                "status": "scraping",
                "current": index + 1,
                "total": total,
            },
        )

        result = scrape_website(lead.get("website", ""))
        enriched = dict(lead)
        enriched["scraped_content"] = result.get("content", "")
        enriched["scrape_status"] = "success" if result.get("success") else "failed"
        if not result.get("success"):
            enriched["error"] = result.get("error")

        socketio.emit(
            "scrape_progress",
            {
                "campaign_id": campaign_id,
                "lead_id": lead["id"],
                "company": lead.get("company", ""),
                "status": "done" if result.get("success") else "failed",
                "current": index + 1,
                "total": total,
            },
        )
        updated_leads.append(enriched)

    return updated_leads
