import time
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from langchain_core.messages import HumanMessage, AIMessage
from models.schemas import ChatRequest, ChatClearRequest, PingLLMRequest

router = APIRouter()

from fastapi.responses import StreamingResponse
import json
import asyncio

def _extract_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if "text" in content:
            return str(content["text"])
        return str(content)
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif "text" in block:
                    parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)

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
        try:
            task = asyncio.create_task(app_graph.ainvoke({"messages": [HumanMessage(content=req.message)]}, config))
            
            while not task.done():
                yield b" "
                await asyncio.sleep(2)
                
            result = await task
            messages = result.get('messages', [])
            ai_msg = next((m for m in reversed(messages) if (getattr(m, 'type', None) or (m.get('type') if isinstance(m, dict) else None)) == 'ai'), None)
            if ai_msg:
                content = getattr(ai_msg, 'content', None) or (ai_msg.get('content') if isinstance(ai_msg, dict) else None)
                text = _extract_text(content)
            elif messages:
                last_m = messages[-1]
                content = getattr(last_m, 'content', None) or (last_m.get('content') if isinstance(last_m, dict) else None)
                text = _extract_text(content)
            else:
                text = ""
                
            if not text:
                text = "処理が完了しました。"
                
            yield json.dumps({"reply": text}).encode('utf-8')
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                reply_text = "【API利用枠の一時制限】Gemini API（無料枠）の1分間あたりのリクエスト数上限に達しました。約1分後に自動復旧しますので、少しお待ちになってから再度お試しください。"
            else:
                reply_text = f"エラーが発生しました: {err_msg}"
                
            try:
                await app_graph.aupdate_state(config, {"messages": [HumanMessage(content=req.message), AIMessage(content=reply_text)]})
            except Exception:
                pass
                
            yield json.dumps({"reply": reply_text}).encode('utf-8')

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
        m_type = getattr(m, "type", None) or (m.get("type") if isinstance(m, dict) else None)
        m_content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else None)
        
        if m_type == "human":
            if m_content == "[UI_CLEAR]":
                history = []
            else:
                history.append({"sender": "You", "text": _extract_text(m_content), "type": "user"})
        elif m_type == "ai":
            text = _extract_text(m_content)
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
            if "11434" in url and not url.rstrip("/").endswith("/v1"):
                url = url.rstrip("/") + "/v1"
            llm = ChatOpenAI(model=req.model, base_url=url, api_key=api_key, max_retries=1, timeout=60)
            llm.invoke("Hi")
        elif req.provider == "ollama":
            from langchain_ollama import ChatOllama
            import os
            url = req.base_url if req.base_url else os.getenv("LOCAL_LLM_URL", "http://localhost:11434")
            llm = ChatOllama(model=req.model, base_url=url)
            llm.invoke("Hi")
        else:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(model=req.model, max_retries=1)
            llm.invoke("Hi")
            
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
