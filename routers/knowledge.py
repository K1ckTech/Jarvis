import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

KNOWLEDGE_FILE = "knowledge.md"

class KnowledgeRequest(BaseModel):
    content: str

@router.get("")
def get_knowledge():
    if not os.path.exists(KNOWLEDGE_FILE):
        return {"content": ""}
    try:
        with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
            return {"content": f.read()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
def update_knowledge(req: KnowledgeRequest):
    try:
        with open(KNOWLEDGE_FILE, "w", encoding="utf-8") as f:
            f.write(req.content)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
