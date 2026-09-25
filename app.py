import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from psycopg_pool import ConnectionPool

from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_google_genai import ChatGoogleGenerativeAI

from core.config import DB_URI, SYSTEM_PROMPT
from tools.agent_tools import tools
from routers import chat, oauth

def call_model(state: MessagesState, config: dict):
    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
        
    model_name = config.get("configurable", {}).get("model_name", "gemini-3.5-flash")
    
    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
    llm_with_tools = llm.bind_tools(tools)
    
    response = llm_with_tools.invoke(messages)
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
        pool = ConnectionPool(conninfo=DB_URI, max_size=20, kwargs={"autocommit": True})
        checkpointer = PostgresSaver(pool)
        checkpointer.setup()
        app_graph = workflow.compile(checkpointer=checkpointer)
    else:
        app_graph = workflow.compile()
        
    app.state.db_pool = pool
    app.state.app_graph = app_graph
    
    print("JARVIS STARTER API Server is ONLINE.")
    yield
    if pool:
        pool.close()
    print("JARVIS STARTER API Server is OFFLINE.")

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(chat.router, prefix="/api/chat")
app.include_router(oauth.router, prefix="/api/oauth")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")