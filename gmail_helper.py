import base64
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def get_gmail_service():
    token_path = Path("token.json")
    credentials_path = Path("credentials.json")

    if not credentials_path.exists():
        raise FileNotFoundError(
            "credentials.json not found. Please follow setup instructions."
        )

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=creds)


def send_cold_email(service, to_email, to_name, subject, body):
    try:
        sender_profile = service.users().getProfile(userId="me").execute()
        sender_address = sender_profile.get("emailAddress", "me")

        message = MIMEText(body)
        message["to"] = f"{to_name} <{to_email}>" if to_name else to_email
        message["from"] = sender_address
        message["subject"] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        sent_message = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": encoded_message})
            .execute()
        )
        return {"success": True, "message_id": sent_message.get("id")}
    except Exception as error:
        return {"success": False, "error": str(error)}


def check_gmail_connected():
    try:
        get_gmail_service()
        return True
    except Exception:
        return False
