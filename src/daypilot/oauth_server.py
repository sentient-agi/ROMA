from __future__ import annotations
import os, json, base64, hmac, hashlib
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, PlainTextResponse
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from cryptography.fernet import Fernet
from sqlalchemy import Column, Integer, String, Text, DateTime, func
from sqlalchemy.orm import declarative_base
from .storage import get_session

app = FastAPI()
Base = declarative_base()

FERNET = Fernet(os.getenv("FERNET_SECRET").encode())
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI")
BASE_URL = os.getenv("OAUTH_BASE_URL", "http://localhost:8000")

SCOPES = ["https://www.googleapis.com/auth/calendar"]

class GoogleAuth(Base):
    __tablename__ = "google_auth"
    user_id = Column(Integer, primary_key=True)
    email = Column(String(255))
    token_encrypted = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

def _ensure_tables():
    s = get_session()
    engine = s.get_bind()
    Base.metadata.create_all(bind=engine)

def _client_config():
    return {
        "web": {
            "client_id": CLIENT_ID,
            "project_id": "daypilot",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": CLIENT_SECRET,
            "redirect_uris": [REDIRECT_URI],
        }
    }

def _sign_state(uid: int) -> str:
    msg = str(uid).encode()
    sig = hmac.new(CLIENT_SECRET.encode(), msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(msg + b"." + sig).decode()

def _verify_state(state: str) -> int:
    raw = base64.urlsafe_b64decode(state.encode())
    msg, sig = raw.split(b".", 1)
    expected = hmac.new(CLIENT_SECRET.encode(), msg, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(400, "Bad state")
    return int(msg.decode())

@app.get("/connect")
def connect(uid: int):
    """Start OAuth for a Telegram user id: /connect?uid=12345"""
    _ensure_tables()
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=_sign_state(uid),
    )
    return RedirectResponse(auth_url)

@app.get("/oauth2/callback")
def oauth2_callback(request: Request):
    _ensure_tables()
    state = request.query_params.get("state")
    code = request.query_params.get("code")
    if not state or not code:
        raise HTTPException(400, "Missing state or code")
    uid = _verify_state(state)

    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=REDIRECT_URI)
    flow.fetch_token(code=code)
    creds = flow.credentials
    token_json = json.dumps({
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    })


    try:
        service = build("calendar", "v3", credentials=creds)
        cal = service.calendars().get(calendarId="primary").execute()
        email = cal.get("id")
    except Exception:
        email = None

    s = get_session()
    row = s.get(GoogleAuth, uid)
    if row is None:
        row = GoogleAuth(user_id=uid)
    row.email = email
    row.token_encrypted = FERNET.encrypt(token_json.encode()).decode()
    s.add(row); s.commit()

    return PlainTextResponse("✅ Google Calendar connected. You can return to Telegram and run /sync.")
