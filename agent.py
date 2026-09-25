import os
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_google_genai import ChatGoogleGenerativeAI

# 1. 環境変数の読み込み
load_dotenv()
DB_URI = os.getenv("DB_URI")

# 2. LLMの初期化 (Geminiに変更)
llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash", temperature=0)

# 3. 厳格なシステムプロンプトの定義 (事前要件の反映)
SYSTEM_PROMPT = """あなたは「JARVIS」、優秀なAIアシスタントです。
特にWeb制作やプログラム開発において、以下の厳格なルールを遵守してください。

1. デザインルール: AIチックなデザイン（普遍的な紫のグラデーション等）は絶対に使用しないこと。普遍的かつ誰が見てもAI生成ではないと思える自然なデザインを心がけること。
2. コード出力ルール: 特定の指示がないかファイルが変更されている限り、コードは省略せず全文を出力すること。ファイルに一切の編集が加えられていない場合のみ省略可。
3. コメントルール: 特定の指示がない限り、コメントアウトは極力最低限に抑えること。
4. 品質ルール: 即席であることを前提としている場合を除き、作成するコードは保守性を担保し、また堅牢性のあるものを作成すること。
5. 確認ルール: コードを出力する前に、セルフダブルチェックを必ず行うこと。
"""

# 4. エージェントの処理ノード
def call_model(state: MessagesState):
    messages = state["messages"]
    # 最初のメッセージの前にシステムプロンプトを挿入
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
    
    response = llm.invoke(messages)
    return {"messages": [response]}

# 5. グラフ（ワークフロー）の構築
workflow = StateGraph(MessagesState)
workflow.add_node("agent", call_model)
workflow.add_edge(START, "agent")
workflow.add_edge("agent", END)

# 6. メイン処理（CLIでのチャットループ）
def main():
    # PostgreSQLへのコネクションプールを作成 (autocommitを有効化)
    with ConnectionPool(
        conninfo=DB_URI, 
        max_size=20,
        kwargs={"autocommit": True}
    ) as pool:
        # PostgresSaverを直接インスタンス化
        checkpointer = PostgresSaver(pool)
        checkpointer.setup()

        # 記憶機能（checkpointer）を組み込んでグラフをコンパイル
        app = workflow.compile(checkpointer=checkpointer)

        print("JARVIS: システムオンライン。会話を開始します。(終了するには 'quit' または 'exit' と入力)")

        # スレッドID（このIDが同じなら、DiscordからでもWebからでも同じ記憶を引き出せる）
        config = {"configurable": {"thread_id": "jarvis_main_thread"}}

        while True:
            user_input = input("You: ")
            if user_input.lower() in ["quit", "exit"]:
                print("JARVIS: システムをシャットダウンします。")
                break

            # ユーザーの入力をグラフに渡し、ストリーミングで応答を受け取る
            for event in app.stream({"messages": [HumanMessage(content=user_input)]}, config):
                for value in event.values():
                    content = value['messages'][-1].content
                    # Gemini特有のリスト形式データを綺麗な文字列に抽出
                    if isinstance(content, list):
                        text = "".join(block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text")
                    else:
                        text = content
                    print(f"JARVIS:\n{text}\n")

if __name__ == "__main__":
    main()