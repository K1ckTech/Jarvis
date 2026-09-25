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
llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash", temperature=0)

# 2. システムプロンプトとワークフローの定義（agent.pyと同じ）
SYSTEM_PROMPT = """あなたは「JARVIS」、優秀なAIアシスタントです。
特にWeb制作やプログラム開発において、以下の厳格なルールを遵守してください。
1. デザインルール: AIチックなデザイン（普遍的な紫のグラデーション等）は絶対に使用しないこと。普遍的かつ誰が見てもAI生成ではないと思える自然なデザインを心がけること。
2. コード出力ルール: 特定の指示がないかファイルが変更されている限り、コードは省略せず全文を出力すること。ファイルに一切の編集が加えられていない場合のみ省略可。
3. コメントルール: 特定の指示がない限り、コメントアウトは極力最低限に抑えること。
4. 品質ルール: 即席であることを前提としている場合を除き、作成するコードは保守性を担保し、また堅牢性のあるものを作成すること。
5. 確認ルール: コードを出力する前に、セルフダブルチェックを必ず行うこと。
"""

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
