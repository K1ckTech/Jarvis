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
    client_id: str
    client_secret: str

class PingLLMRequest(BaseModel):
    provider: str
    model: str
    base_url: str = ""
