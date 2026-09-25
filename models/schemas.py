from pydantic import BaseModel
from typing import Optional

class ChatRequest(BaseModel):
    message: str
    thread_id: str = "jarvis_business_thread"
    model: str = "gemini-3.8-flash" # デフォルトモデルを設定（動的変更用）

class ChatClearRequest(BaseModel):
    thread_id: str = "jarvis_business_thread"

class OAuthConfig(BaseModel):
    provider: str
    client_id: str
    client_secret: str
