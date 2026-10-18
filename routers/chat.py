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

from core.config import resolve_local_url, has_pending_action

@router.post("")
async def chat_endpoint(req: ChatRequest, request: Request):
    app_graph = request.app.state.app_graph
    
    resolved_base_url = resolve_local_url(req.base_url)
    config = {
        "configurable": {
            "thread_id": req.thread_id, 
            "model_name": req.model,
            "provider": req.provider,
            "base_url": resolved_base_url,
            "api_key": req.api_key or ""
        }
    }
    
    async def generate_response():
        emitted_any = False
        queue = asyncio.Queue()

        async def stream_producer():
            try:
                async for chunk in app_graph.astream(
                    {"messages": [HumanMessage(content=req.message)]}, 
                    config, 
                    stream_mode="updates"
                ):
                    await queue.put(("chunk", chunk))
                await queue.put(("done", None))
            except Exception as e:
                await queue.put(("error", e))

        producer_task = asyncio.create_task(stream_producer())

        try:
            yield (json.dumps({"type": "ping"}) + "\n").encode('utf-8')

            while True:
                try:
                    item_type, item_data = await asyncio.wait_for(queue.get(), timeout=8.0)
                except asyncio.TimeoutError:
                    yield (json.dumps({"type": "ping"}) + "\n").encode('utf-8')
                    continue

                if item_type == "done":
                    break
                elif item_type == "error":
                    raise item_data
                elif item_type == "chunk":
                    chunk = item_data
                    for node_name, node_output in chunk.items():
                        if node_name == "auto_continue":
                            continue
                        if node_name == "agent":
                            node_msgs = node_output.get("messages", [])
                            for m in node_msgs:
                                content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else None)
                                tool_calls = getattr(m, "tool_calls", None) or (m.get("tool_calls") if isinstance(m, dict) else None)
                                text = _extract_text(content).strip()
                                
                                if text:
                                    has_pending = has_pending_action(text)
                                    parts = [p.strip() for p in text.split("---MESSAGE_BREAK---") if p.strip()]
                                    for idx, part in enumerate(parts):
                                        is_last_part = (idx == len(parts) - 1)
                                        is_done = is_last_part and not bool(tool_calls) and not has_pending
                                        emitted_any = True
                                        yield (json.dumps({"reply": part, "done": is_done}) + "\n").encode('utf-8')
                                elif tool_calls:
                                    tool_name = tool_calls[0].get("name", "") if isinstance(tool_calls[0], dict) else getattr(tool_calls[0], "name", "")
                                    tool_args = tool_calls[0].get("args", {}) if isinstance(tool_calls[0], dict) else getattr(tool_calls[0], "args", {})
                                    
                                    status_msg = None
                                    if tool_name == "web_search":
                                        q = tool_args.get("query") or tool_args.get("keyword") or tool_args.get("keywords") or tool_args.get("search_query") or tool_args.get("q") or ""
                                        status_msg = f"「{q}」についてWeb検索を開始します..." if q else "Web検索を実行して最新情報を調査します..."
                                    elif tool_name == "notion_search":
                                        status_msg = "Notion内のタスク・情報を検索しています..."
                                    elif tool_name == "read_knowledge":
                                        status_msg = "社内ナレッジベース（事前知識）を確認しています..."
                                    elif "github" in tool_name:
                                        status_msg = "GitHubの操作（リポジトリ・Issue確認等）を実行しています..."
                                    elif "drive" in tool_name:
                                        status_msg = "Google Driveのファイル・フォルダを確認しています..."
                                    elif tool_name:
                                        status_msg = f"{tool_name} を実行しています..."
                                        
                                    if status_msg:
                                        emitted_any = True
                                        yield (json.dumps({"reply": status_msg, "done": False}) + "\n").encode('utf-8')

            if not emitted_any:
                yield (json.dumps({"reply": "処理が完了しました。", "done": True}) + "\n").encode('utf-8')
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                reply_text = "【API利用枠の一時制限】Gemini API（無料枠）の1分間あたりのリクエスト数上限に達しました。約1分後に自動復旧しますので、少しお待ちになってから再度お試しください。"
            elif "timeout" in err_msg.lower() or "timed out" in err_msg.lower():
                reply_text = f"【タイムアウト】LLMまたは外部ツールの応答がタイムアウトしました ({err_msg})。モデルやURLの設定をご確認ください。"
            else:
                reply_text = f"エラーが発生しました: {err_msg}"
                
            try:
                await app_graph.aupdate_state(config, {"messages": [HumanMessage(content=req.message), AIMessage(content=reply_text)]})
            except Exception:
                pass
                
            yield (json.dumps({"reply": reply_text, "done": True}) + "\n").encode('utf-8')
        finally:
            if not producer_task.done():
                producer_task.cancel()

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
    return StreamingResponse(generate_response(), headers=headers, media_type="application/x-ndjson")


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
            elif str(m_content).startswith("[システム自動"):
                continue
            else:
                history.append({"sender": "You", "text": _extract_text(m_content), "type": "user"})
        elif m_type == "ai":
            raw_text = _extract_text(m_content)
            if raw_text:
                parts = [p.strip() for p in raw_text.split("---MESSAGE_BREAK---") if p.strip()]
                for part in parts:
                    history.append({"sender": "JARVIS", "text": part, "type": "jarvis"})
            
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
            api_key = req.api_key.strip() if req.api_key and req.api_key.strip() else os.getenv("LOCAL_LLM_KEY", "dummy")
            url = req.base_url if req.base_url else os.getenv("LOCAL_LLM_URL", "http://localhost:8000/v1")
            url = resolve_local_url(url)
            if "11434" in url and not url.rstrip("/").endswith("/v1"):
                url = url.rstrip("/") + "/v1"
            llm = ChatOpenAI(model=req.model, base_url=url, api_key=api_key, max_retries=1, timeout=20)
            llm.invoke("Hi")
        elif req.provider == "ollama":
            from langchain_ollama import ChatOllama
            import os
            url = req.base_url if req.base_url else os.getenv("LOCAL_LLM_URL", "http://localhost:11434")
            url = resolve_local_url(url)
            client_kwargs = {}
            if req.api_key and req.api_key.strip():
                client_kwargs["headers"] = {"Authorization": f"Bearer {req.api_key.strip()}"}
            llm = ChatOllama(model=req.model, base_url=url, client_kwargs=client_kwargs if client_kwargs else None)
            llm.invoke("Hi")
        else:
            from langchain_google_genai import ChatGoogleGenerativeAI
            import os
            gemini_model = os.getenv("GEMINI_MODEL", req.model)
            llm = ChatGoogleGenerativeAI(model=gemini_model, max_retries=1, request_timeout=20)
            llm.invoke("Hi")
            
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
