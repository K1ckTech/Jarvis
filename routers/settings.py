import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict
import dotenv

router = APIRouter()

class SettingsUpdate(BaseModel):
    settings: Dict[str, str]

@router.get("")
def get_settings():
    env_path = ".env"
    if not os.path.exists(env_path):
        return {"settings": {}}
    
    # Read raw key-values from .env file
    settings = dotenv.dotenv_values(env_path)
    return {"settings": settings}

@router.post("")
def update_settings(req: SettingsUpdate):
    env_path = ".env"
    if not os.path.exists(env_path):
        open(env_path, 'a').close()
        
    for k, v in req.settings.items():
        if v:
            dotenv.set_key(env_path, k, v)
        else:
            dotenv.unset_key(env_path, k)
            
    # Reload environment variables for the current process
    dotenv.load_dotenv(env_path, override=True)
    return {"status": "success"}
