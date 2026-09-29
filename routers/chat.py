import time
from fastapi import APIRouter, Request, HTTPException
from langchain_core.messages import HumanMessage
from models.schemas import ChatRequest, ChatClearRequest

router = APIRouter()

@router.post("")
def chat_endpoint(req: ChatRequest, request: Request):
    app_graph = request.app.state.app_graph
    
    config = {"configurable": {"thread_id": req.thread_id, "model_name": req.model}}
    max_retries = 3
    base_delay = 10
    
    for attempt in range(max_retries):
        try:
            result = app_graph.invoke({"messages": [HumanMessage(content=req.message)]}, config)
            content = result['messages'][-1].content
            
            if isinstance(content, list):
                text = "".join(block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text")
            else:
                text = content
                
            return {"reply": text}
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                if attempt < max_retries - 1:
                    time.sleep(base_delay * (2 ** attempt))
                    continue
            return {"reply": f"エラーが発生しました: {err_str}"}

    return {"reply": "エラー: レートリミット制限により処理を完了できませんでした。"}

@router.post("/clear")
def clear_chat_history(req: ChatClearRequest, request: Request):
    pool = request.app.state.db_pool
    if not pool:
        return {"status": "success", "message": "DBが無効のためメモリ上の履歴をリセットしました（再起動で消去されます）。"}
    
    try:
        with pool.connection() as conn:
            conn.execute("DELETE FROM checkpoints WHERE thread_id = %s", (req.thread_id,))
            conn.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", (req.thread_id,))
            conn.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (req.thread_id,))
        return {"status": "success", "message": "チャット履歴を完全に消去しました。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history/{thread_id}")
def get_chat_history(thread_id: str, request: Request):
    app_graph = request.app.state.app_graph
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        state = app_graph.get_state(config)
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
def clear_ui(req: ChatClearRequest, request: Request):
    app_graph = request.app.state.app_graph
    config = {"configurable": {"thread_id": req.thread_id}}
    try:
        app_graph.update_state(config, {"messages": [HumanMessage(content="[UI_CLEAR]")]})
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
