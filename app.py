import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from psycopg_pool import AsyncConnectionPool

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama

from core.config import DB_URI, SYSTEM_PROMPT
from tools.agent_tools import tools
from routers import chat, oauth, knowledge, settings

async def call_model(state: MessagesState, config: RunnableConfig):
    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
        
    model_name = config.get("configurable", {}).get("model_name", "gemini-3.5-flash")
    provider = config.get("configurable", {}).get("provider", "gemini")
    base_url = config.get("configurable", {}).get("base_url", "")
    
    if provider == "openai":
        api_key = os.getenv("LOCAL_LLM_KEY", "dummy")
        url = base_url if base_url else os.getenv("LOCAL_LLM_URL", "http://localhost:8000/v1")
        print(f"[LLM Exec] Using Local LLM ({model_name}) at {url}")
        llm = ChatOpenAI(
            model=model_name,
            base_url=url,
            api_key=api_key,
            temperature=0,
            streaming=True
        )
    elif provider == "ollama":
        url = base_url if base_url else os.getenv("LOCAL_LLM_URL", "http://localhost:11434")
        print(f"[LLM Exec] Using Ollama ({model_name}) at {url}")
        llm = ChatOllama(
            model=model_name,
            base_url=url,
            temperature=0
        )
    else:
        print(f"[LLM Exec] Using Google Gemini ({model_name})")
        llm = ChatGoogleGenerativeAI(model=model_name, temperature=0, streaming=True)
        
    llm_with_tools = llm.bind_tools(tools)
    
    filtered_messages = [m for m in messages if m.content != "[UI_CLEAR]"]
    response = await llm_with_tools.ainvoke(filtered_messages, config=config)
    return {"messages": [response]}

workflow = StateGraph(MessagesState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", ToolNode(tools))

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", tools_condition)
workflow.add_edge("tools", "agent")

pool = None
app_graph = None

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
    
    print("JARVIS STARTER API Server is ONLINE.")
    yield
    if pool:
        await pool.close()
    print("JARVIS STARTER API Server is OFFLINE.")

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(chat.router, prefix="/api/chat")
app.include_router(oauth.router, prefix="/api/oauth")
app.include_router(knowledge.router, prefix="/api/knowledge")
app.include_router(settings.router, prefix="/api/settings")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")