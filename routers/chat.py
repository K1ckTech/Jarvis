import time
from fastapi import APIRouter, Request, HTTPException
from langchain_core.messages import HumanMessage
from models.schemas import ChatRequest, ChatClearRequest, PingLLMRequest

router = APIRouter()

from fastapi.responses import StreamingResponse
import json
import asyncio

@router.post("")
async def chat_endpoint(req: ChatRequest, request: Request):
    app_graph = request.app.state.app_graph
    
    config = {
        "configurable": {
            "thread_id": req.thread_id, 
            "model_name": req.model,
            "provider": req.provider,
            "base_url": req.base_url
        }
    }
    
    async def generate_response():
        task = asyncio.create_task(app_graph.ainvoke({"messages": [HumanMessage(content=req.message)]}, config))
        
        # Keep-alive heartbeat to prevent timeouts
        while not task.done():
            yield b" "
            await asyncio.sleep(5)
            
        try:
            result = task.result()
            content = result['messages'][-1].content
            
            if isinstance(content, list):
                text = "".join(block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text")
            else:
                text = content
                
            yield json.dumps({"reply": text}).encode('utf-8')
        except Exception as e:
            yield json.dumps({"reply": f"エラーが発生しました: {str(e)}"}).encode('utf-8')

    return StreamingResponse(generate_response(), media_type="application/json")


@router.post("/clear")
async def clear_chat_history(req: ChatClearRequest, request: Request):
    pool = request.app.state.db_pool
    if not pool:
        return {"status": "success", "message": "DBが無効のためメモリ上の履歴をリセットしました（再起動で消去されます）。"}
    
    try:
        async with pool.connection() as conn:
            await conn.execute("DELETE FROM checkpoints WHERE thread_id = %s", (req.thread_id,))
            await conn.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", (req.thread_id,))
            await conn.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (req.thread_id,))
        return {"status": "success", "message": "チャット履歴を完全に消去しました。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/{thread_id}")
async def get_chat_history(thread_id: str, request: Request):
    app_graph = request.app.state.app_graph
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        state = await app_graph.aget_state(config)
    except Exception:
        return {"history": []}
        
    messages = state.values.get("messages", [])
    
    history = []
    for m in messages:
        if m.type == "human":
            if m.content == "[UI_CLEAR]":
                history = []
            else:
                history.append({"sender": "You", "text": m.content, "type": "user"})
        elif m.type == "ai":
            text = ""
            if isinstance(m.content, list):
                text = "".join(block.get("text", "") for block in m.content if isinstance(block, dict) and block.get("type") == "text")
            else:
                text = m.content
            if text:
                history.append({"sender": "JARVIS", "text": text, "type": "jarvis"})
            
    return {"history": history}

@router.post("/clear_ui")
async def clear_ui(req: ChatClearRequest, request: Request):
    app_graph = request.app.state.app_graph
    config = {"configurable": {"thread_id": req.thread_id}}
    try:
        await app_graph.aupdate_state(config, {"messages": [HumanMessage(content="[UI_CLEAR]")]})
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/ping_llm")
def ping_llm(req: PingLLMRequest):
    try:
        if req.provider == "openai":
            from langchain_openai import ChatOpenAI
            import os
            api_key = os.getenv("LOCAL_LLM_KEY", "dummy")
            url = req.base_url if req.base_url else os.getenv("LOCAL_LLM_URL", "http://localhost:8000/v1")
            llm = ChatOpenAI(model=req.model, base_url=url, api_key=api_key, max_retries=1)
            llm.invoke("Hi")
        else:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(model=req.model, max_retries=1)
            llm.invoke("Hi")
            
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
