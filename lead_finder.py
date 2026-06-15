import requests
from bs4 import BeautifulSoup
import time
import re
from ddgs import DDGS

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def find_leads(query, count=10):
    leads = []
    skip = ["youtube.com", "facebook.com", "twitter.com",
            "linkedin.com", "instagram.com", "wikipedia.org",
            "reddit.com", "amazon.com", "yelp.com"]

    try:
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=count * 3)

        for r in results:
            url = r.get("href", "")
            title = r.get("title", "")

            if not url.startswith("http"):
                continue
            if any(s in url for s in skip):
                continue

            company = title.split("|")[0].split("-")[0].strip()

            leads.append({
                "name": "Decision Maker",
                "company": company,
                "website": url.split("?")[0],
                "role": "Decision Maker",
                "email": ""
            })

            if len(leads) >= count:
                break

    except Exception as e:
        print(f"Lead finder error: {e}")

    return leads


def find_email_for_domain(domain):
    common_patterns = ["info", "hello", "contact", "hi", "team"]
    guesses = [f"{p}@{domain}" for p in common_patterns]
    return guesses[0]