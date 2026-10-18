import os
import json
import time
import requests
from typing import Optional, Dict, Any
from urllib.parse import urlencode
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    Credentials = None
    Request = None
    GOOGLE_AUTH_AVAILABLE = False

OAUTH_CONFIG_FILE = "oauth_config.json"
GOOGLE_DRIVE_PROVIDER = "Google Drive"
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]
TOKEN_URI = "https://oauth2.googleapis.com/token"
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"

def read_oauth_config() -> Dict[str, Any]:
    if not os.path.exists(OAUTH_CONFIG_FILE):
        return {}
    try:
        with open(OAUTH_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def write_oauth_config(data: Dict[str, Any]) -> None:
    with open(OAUTH_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_google_drive_config() -> Dict[str, Any]:
    data = read_oauth_config()
    return data.get(GOOGLE_DRIVE_PROVIDER, {})

def get_google_drive_status() -> Dict[str, Any]:
    config = get_google_drive_config()
    client_id = config.get("client_id", "").strip()
    client_secret = config.get("client_secret", "").strip()
    refresh_token = config.get("refresh_token", "").strip()
    access_token = config.get("access_token", "").strip()
    
    is_configured = bool(client_id and client_secret)
    is_connected = bool(refresh_token or access_token)
    
    return {
        "configured": is_configured,
        "connected": is_connected,
        "client_id": client_id,
        "has_refresh_token": bool(refresh_token),
        "expires_at": config.get("expires_at")
    }

def generate_google_auth_url(redirect_uri: str, client_id: Optional[str] = None, state: Optional[str] = None) -> str:
    if not client_id:
        config = get_google_drive_config()
        client_id = config.get("client_id", "").strip()
    
    if not client_id:
        raise ValueError("Client IDが設定されていません。")

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true"
    }
    if state:
        params["state"] = state
    return f"{AUTH_URI}?{urlencode(params)}"

def exchange_code_for_tokens(
    code: str, 
    redirect_uri: str, 
    client_id: Optional[str] = None, 
    client_secret: Optional[str] = None
) -> Dict[str, Any]:
    config = get_google_drive_config()
    c_id = (client_id or config.get("client_id", "")).strip()
    c_secret = (client_secret or config.get("client_secret", "")).strip()

    if not c_id or not c_secret:
        raise ValueError("Client IDまたはClient Secretが指定されていません。")

    payload = {
        "code": code,
        "client_id": c_id,
        "client_secret": c_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    
    response = requests.post(TOKEN_URI, data=payload, timeout=15)
    if response.status_code != 200:
        raise RuntimeError(f"トークン取得失敗 ({response.status_code}): {response.text}")
        
    token_data = response.json()
    save_google_drive_config(
        client_id=c_id,
        client_secret=c_secret,
        refresh_token=token_data.get("refresh_token") or config.get("refresh_token"),
        access_token=token_data.get("access_token"),
        expires_in=token_data.get("expires_in")
    )
    return token_data

def save_google_drive_config(
    client_id: str,
    client_secret: str,
    refresh_token: Optional[str] = None,
    access_token: Optional[str] = None,
    expires_in: Optional[int] = None
) -> None:
    data = read_oauth_config()
    drive_data = data.get(GOOGLE_DRIVE_PROVIDER, {})
    
    drive_data["client_id"] = client_id.strip()
    drive_data["client_secret"] = client_secret.strip()
    drive_data["token_uri"] = TOKEN_URI
    drive_data["scopes"] = SCOPES
    
    if refresh_token:
        drive_data["refresh_token"] = refresh_token.strip()
    if access_token:
        drive_data["access_token"] = access_token.strip()
    if expires_in:
        drive_data["expires_at"] = int(time.time()) + int(expires_in)
        
    data[GOOGLE_DRIVE_PROVIDER] = drive_data
    write_oauth_config(data)

def get_google_drive_credentials() -> Optional[Any]:
    if not GOOGLE_AUTH_AVAILABLE or not Credentials:
        return None

    config = get_google_drive_config()
    client_id = config.get("client_id", "").strip()
    client_secret = config.get("client_secret", "").strip()
    refresh_token = config.get("refresh_token", "").strip()
    access_token = config.get("access_token", "").strip()

    if not client_id or not client_secret:
        return None

    if not refresh_token and not access_token:
        return None

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES
    )

    if creds and (not creds.valid or creds.expired):
        if creds.refresh_token:
            try:
                creds.refresh(Request())
                save_google_drive_config(
                    client_id=client_id,
                    client_secret=client_secret,
                    refresh_token=creds.refresh_token,
                    access_token=creds.token,
                    expires_in=3600
                )
            except Exception as e:
                print(f"Google Driveトークン更新エラー: {e}")
                return None
        else:
            return None

    return creds
