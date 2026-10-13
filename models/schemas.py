from pydantic import BaseModel
from typing import Optional

class ChatRequest(BaseModel):
    message: str
    thread_id: str = "jarvis_main_thread"
    model: str = "gemini-3.5-flash"
    provider: str = "gemini"
    base_url: Optional[str] = ""

class ChatClearRequest(BaseModel):
    thread_id: str = "jarvis_main_thread"

class OAuthConfig(BaseModel):
    provider: str
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    refresh_token: Optional[str] = None
    access_token: Optional[str] = None
    auth_code: Optional[str] = None
    redirect_uri: Optional[str] = None
    extra_data: Optional[dict] = None

class GoogleExchangeRequest(BaseModel):
    code: str
    redirect_uri: str
    client_id: Optional[str] = None
    client_secret: Optional[str] = None

class PingLLMRequest(BaseModel):
    provider: str
    model: str
    base_url: str = ""
