import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from psycopg_pool import ConnectionPool

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_google_genai import ChatGoogleGenerativeAI

from core.config import DB_URI, SYSTEM_PROMPT
from tools.agent_tools import tools
from routers import chat, oauth, knowledge

def call_model(state: MessagesState, config: RunnableConfig = None):
    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
        
    config = config or {}
    model_name = config.get("configurable", {}).get("model_name", "gemini-3.5-flash")
    
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
    llm_with_tools = llm.bind_tools(tools)
    
    filtered_messages = [m for m in messages if m.content != "[UI_CLEAR]"]
    response = llm_with_tools.invoke(filtered_messages)
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
    """JARVISがプロンプト無しに自律的に活動するためのバックグラウンドループ"""
    while True:
        try:
            # 1時間(3600秒)おきに起動し、自律的に思考・行動する
            await asyncio.sleep(3600)
            print("[Agentic Loop] JARVIS is waking up for autonomous tasks...")
            
            config = {"configurable": {"thread_id": "jarvis_autonomous_thread", "model_name": "gemini-3.5-flash"}}
            trigger_msg = HumanMessage(content="[システム自動トリガー] 自主保守(Self-Maintenance)、未読メール確認、GitHub等の新着課題の確認を自律的に行ってください。何らかの問題や重要な通知があれば notify_boss_by_phone または Slack等で報告してください。異常がなければ何もせず待機してください。")
            
            await asyncio.to_thread(graph.invoke, {"messages": [trigger_msg]}, config)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Agentic Loop Error] {e}")
            await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool, app_graph
    if DB_URI:
        pool = ConnectionPool(conninfo=DB_URI, max_size=20, kwargs={"autocommit": True})
        checkpointer = PostgresSaver(pool)
        checkpointer.setup()
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
        pool.close()
    print("JARVIS STARTER API Server is OFFLINE.")

app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def ip_restriction_middleware(request: Request, call_next):
    client_ip = request.client.host
    # Cloudflare Tunnelからのアクセス(172.18.0.1)のみ許可
    if client_ip != "172.18.0.1":
        return JSONResponse(
            status_code=403, 
            content={"detail": "Forbidden: Access restricted."}
        )
    return await call_next(request)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(chat.router, prefix="/api/chat")
app.include_router(oauth.router, prefix="/api/oauth")
app.include_router(knowledge.router, prefix="/api/knowledge")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")