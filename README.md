# OutreachAI

OutreachAI is a local, free Flask app that turns a CSV of leads into hyper-personalized cold outreach emails.

## Features

- Create campaigns with offer + tone + subject template
- Upload leads CSV (`name`, `company`, `website`; optional `role`, `email`)
- Scrape websites for personalization context
- Generate personalized emails with Groq (`llama-3.3-70b-versatile`)
- Real-time processing progress with Socket.IO
- Regenerate single lead emails
- Export all results to CSV
- Connect Gmail and send one-by-one or send-all
- JSON file storage (`campaigns.json`) with no database

## Project Structure

```
outreach-ai/
├── app.py
├── scraper.py
├── agent.py
├── gmail_helper.py
├── store.py
├── campaigns.json          # auto-created
├── credentials.json        # from Google Cloud
├── token.json              # auto-generated
├── templates/
│   └── index.html
├── uploads/
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Requirements

- Python 3.10+
- A free Groq API key (`console.groq.com`)
- Optional: Gmail OAuth credentials for sending (`credentials.json`)

## Setup

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Create `.env` from example:

   ```bash
   copy .env.example .env
   ```

3. Add your Groq key in `.env`:

   ```env
   GROQ_API_KEY=your_key_here
   ```

4. (Optional) Gmail sending setup:
   - Go to `console.cloud.google.com`
   - Create project and enable Gmail API
   - Create OAuth 2.0 Client ID (Desktop App)
   - Download file as `credentials.json`
   - Place `credentials.json` in project root

## Run

```bash
python app.py
```

Open: `http://localhost:5000`

## CSV Format

Required columns:

- `name`
- `company`
- `website`

Optional columns:

- `role`
- `email`

If required columns are missing, the API returns:

`CSV must contain columns: name, company, website`

## Notes

- `uploads/` is created automatically on startup
- `campaigns.json` is auto-created as:

  ```json
  {
    "campaigns": []
  }
  ```

- If scraping fails, generation still runs with fallback instructions
- Groq generation is rate-limited by `0.5s` between leads