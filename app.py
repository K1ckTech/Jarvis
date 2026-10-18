import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from psycopg_pool import AsyncConnectionPool

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama

from core.config import DB_URI, SYSTEM_PROMPT, resolve_local_url
from tools.agent_tools import tools
from routers import chat, oauth, knowledge, settings

async def call_model(state: MessagesState, config: RunnableConfig):
    messages = state["messages"]
    
    clear_indices = [i for i, m in enumerate(messages) if getattr(m, 'content', '') == "[UI_CLEAR]"]
    if clear_indices:
        messages = messages[clear_indices[-1] + 1:]

    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
        
    config = config or {}
    model_name = config.get("configurable", {}).get("model_name", "gemini-3.8-flash")
    provider = config.get("configurable", {}).get("provider", "gemini")
    base_url = config.get("configurable", {}).get("base_url", "")
    configurable_api_key = config.get("configurable", {}).get("api_key")
    api_key = configurable_api_key.strip() if configurable_api_key and str(configurable_api_key).strip() else os.getenv("LOCAL_LLM_KEY", "dummy")
    llm_timeout = int(os.getenv("LLM_TIMEOUT", "60"))

    if provider == "openai":
        url = base_url if base_url else os.getenv("LOCAL_LLM_URL", "http://localhost:8000/v1")
        url = resolve_local_url(url)
        if "11434" in url and not url.rstrip("/").endswith("/v1"):
            url = url.rstrip("/") + "/v1"
        print(f"[LLM Exec] Using Local LLM ({model_name}) at {url}")
        llm = ChatOpenAI(
            model=model_name,
            base_url=url,
            api_key=api_key,
            temperature=0,
            timeout=llm_timeout,
            max_retries=1
        )
    elif provider == "ollama":
        url = base_url if base_url else os.getenv("LOCAL_LLM_URL", "http://localhost:11434")
        url = resolve_local_url(url)
        print(f"[LLM Exec] Using Ollama ({model_name}) at {url}")
        client_kwargs = {}
        if configurable_api_key and str(configurable_api_key).strip():
            client_kwargs["headers"] = {"Authorization": f"Bearer {configurable_api_key.strip()}"}
        llm = ChatOllama(
            model=model_name,
            base_url=url,
            temperature=0,
            client_kwargs=client_kwargs if client_kwargs else None
        )
    else:
        print(f"[LLM Exec] Using Google Gemini ({model_name})")
        gemini_model = os.getenv("GEMINI_MODEL", model_name)
        llm = ChatGoogleGenerativeAI(model=gemini_model, temperature=0, streaming=True, request_timeout=llm_timeout)
        
    filtered_messages = [m for m in messages if m.content != "[UI_CLEAR]"]
    retry_delays = [3, 8, 15, 20]
    response = None
    for attempt in range(len(retry_delays) + 1):
        try:
            try:
                llm_with_tools = llm.bind_tools(tools)
                response = await llm_with_tools.ainvoke(filtered_messages, config=config)
            except Exception as bind_err:
                bind_err_str = str(bind_err)
                if "429" in bind_err_str or "RESOURCE_EXHAUSTED" in bind_err_str:
                    raise bind_err
                print(f"[LLM Exec] Tool binding failed ({bind_err}). Retrying with direct model call...")
                clean_messages = [m for m in filtered_messages if getattr(m, 'type', '') in ('human', 'system') or (getattr(m, 'type', '') == 'ai' and not getattr(m, 'tool_calls', None))]
                response = await llm.ainvoke(clean_messages, config=config)
            break
        except Exception as e:
            err_str = str(e)
            if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < len(retry_delays):
                delay = retry_delays[attempt]
                print(f"[LLM Exec RateLimit] 429 received. Backing off for {delay}s (attempt {attempt + 1}/{len(retry_delays)})...")
                await asyncio.sleep(delay)
                continue
            raise e
    return {"messages": [response]}

workflow = StateGraph(MessagesState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", ToolNode(tools))

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", tools_condition)
workflow.add_edge("tools", "agent")

pool = None
app_graph = None

import asyncio

async def autonomous_agent_loop(graph, pool):
    while True:
        try:
            await asyncio.sleep(3600)
            print("[Agentic Loop] JARVIS is waking up for autonomous tasks...")
            
            config = {"configurable": {"thread_id": "jarvis_autonomous_thread", "model_name": "gemini-3.8-flash"}}
            trigger_msg = HumanMessage(content="[システム自動トリガー] 自主保守(Self-Maintenance)、未読メール確認、GitHub等の新着課題の確認を自律的に行ってください。何らかの問題や重要な通知があれば notify_boss_by_phone または Slack等で報告してください。異常がなければ何もせず待機してください。")
            
            await graph.ainvoke({"messages": [trigger_msg]}, config)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Agentic Loop Error] {e}")
            await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool, app_graph
    if DB_URI:
        pool = AsyncConnectionPool(conninfo=DB_URI, max_size=20, kwargs={"autocommit": True})
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        app_graph = workflow.compile(checkpointer=checkpointer)
    else:
        app_graph = workflow.compile()
        
    app.state.db_pool = pool
    app.state.app_graph = app_graph
    
    # 自律行動ループを起動
    loop_task = asyncio.create_task(autonomous_agent_loop(app_graph, pool))
    
    print("JARVIS STARTER API Server is ONLINE.")
    yield
    
    loop_task.cancel()
    if pool:
        await pool.close()
    print("JARVIS STARTER API Server is OFFLINE.")

app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def ip_restriction_middleware(request: Request, call_next):
    allowed_ips_env = os.getenv("ALLOWED_IPS", "").strip()
    if allowed_ips_env:
        allowed_ips = [ip.strip() for ip in allowed_ips_env.split(",") if ip.strip()]
        client_ip = request.client.host
        if client_ip not in allowed_ips:
            return JSONResponse(
                status_code=403, 
                content={"detail": "Forbidden: Access restricted."}
            )
    return await call_next(request)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(chat.router, prefix="/api/chat")
app.include_router(oauth.router, prefix="/api/oauth")
app.include_router(knowledge.router, prefix="/api/knowledge")
app.include_router(settings.router, prefix="/api/settings")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")