import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_google_genai import ChatGoogleGenerativeAI

# 1. 環境設定とLLMの初期化
load_dotenv()
DB_URI = os.getenv("DB_URI")
llm = ChatGoogleGenerativeAI(model="gemini-3.8-flash", temperature=0)

from core.config import SYSTEM_PROMPT

def call_model(state: MessagesState):
    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
    response = llm.invoke(messages)
    return {"messages": [response]}

workflow = StateGraph(MessagesState)
workflow.add_node("agent", call_model)
workflow.add_edge(START, "agent")
workflow.add_edge("agent", END)

# 3. サーバー起動時・終了時の処理（データベース接続の管理）
pool = None
app_graph = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool, app_graph
    # サーバー起動時にデータベース接続とグラフのコンパイルを行う
    pool = ConnectionPool(conninfo=DB_URI, max_size=20, kwargs={"autocommit": True})
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    app_graph = workflow.compile(checkpointer=checkpointer)
    print("JARVIS API Server is ONLINE.")
    yield
    # サーバー終了時にデータベース接続を閉じる
    pool.close()
    print("JARVIS API Server is OFFLINE.")

# FastAPIアプリケーションの初期化
app = FastAPI(lifespan=lifespan)

# リクエストデータの形式を定義
class ChatRequest(BaseModel):
    message: str
    thread_id: str = "jarvis_main_thread"  # デフォルトはメインスレッド（共通の記憶）

# 4. チャット用APIエンドポイントの作成
@app.post("/chat")
def chat(request: ChatRequest):
    config = {"configurable": {"thread_id": request.thread_id}}
    try:
        # LLMを呼び出し
        result = app_graph.invoke({"messages": [HumanMessage(content=request.message)]}, config)
        content = result['messages'][-1].content
        
        # 形式の整形
        if isinstance(content, list):
            text = "".join(block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text")
        else:
            text = content
            
        return {"reply": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
