import os
import json
from fastapi import APIRouter
from models.schemas import OAuthConfig

router = APIRouter()

@router.get("/status/{provider}")
def get_oauth_status(provider: str):
    if not os.path.exists("oauth_config.json"):
        return {"configured": False, "connected": False}
    with open("oauth_config.json", "r") as f:
        data = json.load(f)
    pdata = data.get(provider, {})
    return {
        "configured": bool(pdata.get("client_id")),
        "connected": bool(pdata.get("access_token"))
    }

@router.post("/config")
def save_oauth_config(config: OAuthConfig):
    data = {}
    if os.path.exists("oauth_config.json"):
        with open("oauth_config.json", "r") as f:
            data = json.load(f)
            
    data[config.provider] = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "access_token": config.client_secret
    }
    with open("oauth_config.json", "w") as f:
        json.dump(data, f)
    return {"status": "success"}
