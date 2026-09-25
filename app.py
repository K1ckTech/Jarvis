import os
import time
import base64
from email.mime.text import MIMEText
import requests
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool

load_dotenv()
DB_URI = os.getenv("DB_URI")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_VERSION = "2022-06-28"
GMAIL_ACCESS_TOKEN = os.environ.get("GMAIL_ACCESS_TOKEN", "")

def _get_notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION
    }

@tool
def notion_search(query: str) -> str:
    """Notionワークスペース全体からページやデータベースをキーワード検索する"""
    if not NOTION_API_KEY:
        return "エラー: NOTION_API_KEYが設定されていません。"
    
    url = "https://api.notion.com/v1/search"
    payload = {"query": query, "page_size": 5}
    
    try:
        res = requests.post(url, json=payload, headers=_get_notion_headers())
        if res.status_code == 200:
            results = res.json().get("results", [])
            if not results:
                return f"「{query}」に一致するNotionページは見つかりませんでした。"
            
            summary = []
            for item in results:
                item_id = item.get("id")
                props = item.get("properties", {})
                title = "無題"
                for prop_name, prop_val in props.items():
                    if prop_val.get("type") == "title":
                        t_arr = prop_val.get("title", [])
                        if t_arr:
                            title = t_arr[0].get("plain_text", "無題")
                if item.get("object") == "database":
                    title_arr = item.get("title", [])
                    if title_arr:
                        title = title_arr[0].get("plain_text", "無題データベース")
                    title = f"[DB] {title}"
                
                summary.append(f"- タイトル: {title} (ID: {item_id})")
            
            return "検索結果:\n" + "\n".join(summary)
        else:
            return f"Notion検索エラー: {res.status_code} - {res.text}"
    except Exception as e:
        return f"通信エラー: {str(e)}"

@tool
def notion_create_page(parent_id: str, title: str, content_text: str = "") -> str:
    """指定した親ページIDの下に、新しいページを作成する"""
    if not NOTION_API_KEY:
        return "エラー: NOTION_API_KEYが設定されていません。"
    
    url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": {"page_id": parent_id},
        "properties": {
            "title": [{"text": {"content": title}}]
        }
    }
    
    if content_text:
        payload["children"] = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content_text}}]
                }
            }
        ]
        
    try:
        res = requests.post(url, json=payload, headers=_get_notion_headers())
        if res.status_code == 200:
            return f"成功: Notionページ「{title}」を作成しました。"
        else:
            return f"Notion作成エラー: {res.status_code} - {res.text}"
    except Exception as e:
        return f"通信エラー: {str(e)}"

@tool
def notion_append_block(page_id: str, text: str) -> str:
    """既存のNotionページの末尾に、新しい段落を追加・追記する"""
    if not NOTION_API_KEY:
        return "エラー: NOTION_API_KEYが設定されていません。"
        
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    payload = {
        "children": [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": text}}]
                }
            }
        ]
    }
    
    try:
        res = requests.patch(url, json=payload, headers=_get_notion_headers())
        if res.status_code == 200:
            return f"成功: 指定されたページにテキストを追記しました。"
        else:
            return f"Notion追記エラー: {res.status_code} - {res.text}"
    except Exception as e:
        return f"通信エラー: {str(e)}"

@tool
def search_recent_emails(query_keyword: str) -> str:
    """Gmailから指定したキーワードに関連するメールを検索し、メッセージIDの一覧を返す"""
    if not GMAIL_ACCESS_TOKEN:
        return "エラー: GMAIL_ACCESS_TOKENが設定されていません。"
        
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?q={query_keyword}&maxResults=5"
    headers = {"Authorization": f"Bearer {GMAIL_ACCESS_TOKEN}"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            messages = data.get("messages", [])
            if not messages:
                return f"「{query_keyword}」に一致するメールは見つかりませんでした。"
            
            msg_list = [f"- ID: {m.get('id')}" for m in messages]
            return f"検索ヒット結果:\n" + "\n".join(msg_list) + "\n※詳細を確認するには get_email_details を使ってください。"
        else:
            return f"Gmail APIエラー: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Gmail通信エラー: {str(e)}"

@tool
def get_email_details(message_id: str) -> str:
    """指定されたメールIDのメール詳細（件名、差出人、本文の要約）を取得する"""
    if not GMAIL_ACCESS_TOKEN:
        return "エラー: GMAIL_ACCESS_TOKENが設定されていません。"
        
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}"
    headers = {"Authorization": f"Bearer {GMAIL_ACCESS_TOKEN}"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            snippet = data.get("snippet", "本文なし")
            payload = data.get("payload", {})
            headers_list = payload.get("headers", [])
            
            subject = "（件名なし）"
            sender = "（差出人不明）"
            for h in headers_list:
                if h.get("name") == "Subject":
                    subject = h.get("value")
                elif h.get("name") == "From":
                    sender = h.get("value")
                    
            return f"【メール詳細】\n差出人: {sender}\n件名: {subject}\n本文プレビュー: {snippet}"
        else:
            return f"Gmail API詳細取得エラー: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Gmail通信エラー: {str(e)}"

@tool
def send_email(to_email: str, subject: str, body_text: str) -> str:
    """指定した宛先、件名、本文で新しいメールを送信する"""
    if not GMAIL_ACCESS_TOKEN:
        return "エラー: GMAIL_ACCESS_TOKENが設定されていません。"
        
    message = MIMEText(body_text)
    message['To'] = to_email
    message['Subject'] = subject
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    headers = {
        "Authorization": f"Bearer {GMAIL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"raw": raw_message}
    
    try:
        res = requests.post(url, json=payload, headers=headers)
        if res.status_code == 200:
            return f"成功: 「{to_email}」宛にメールを送信しました。"
        else:
            return f"Gmail送信エラー: {res.status_code} - {res.text}"
    except Exception as e:
        return f"Gmail通信エラー: {str(e)}"

@tool
def create_email_draft(to_email: str, subject: str, body_text: str) -> str:
    """指定した宛先、件名、本文でGmailに下書きを作成する"""
    if not GMAIL_ACCESS_TOKEN:
        return "エラー: GMAIL_ACCESS_TOKENが設定されていません。"
        
    message = MIMEText(body_text)
    message['To'] = to_email
    message['Subject'] = subject
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    
    url = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
    headers = {
        "Authorization": f"Bearer {GMAIL_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"message": {"raw": raw_message}}
    
    try:
        res = requests.post(url, json=payload, headers=headers)
        if res.status_code == 200:
            return f"成功: 「{to_email}」宛のメールを下書きに保存しました。"
        else:
            return f"Gmail下書き作成エラー: {res.status_code} - {res.text}"
    except Exception as e:
        return f"Gmail通信エラー: {str(e)}"

@tool
def web_search(query: str) -> str:
    """インターネット上でキーワード検索を行い、最新の情報を取得する。事業の競合調査や市場リサーチ、最新ニュースの確認などに使用する。"""
    try:
        from ddgs import DDGS
        results = DDGS().text(query, max_results=5)
        if not results:
            return "検索結果が見つかりませんでした。"
        return "ウェブ検索結果:\n" + "\n".join([f"- {r.get('title')} ({r.get('href')})\n  {r.get('body')}" for r in results])
    except ImportError:
        return "エラー: ddgs パッケージがインストールされていません。'pip install ddgs' を実行してください。"
    except Exception as e:
        return f"検索エラー: {str(e)}"

@tool
def read_knowledge() -> str:
    """ビジネスやユーザーに関する事前知識・コンテキストを記録したナレッジベースを読み込む"""
    try:
        with open("knowledge.md", "r", encoding="utf-8") as f:
            content = f.read()
            return content if content else "事前知識は現在空です。"
    except FileNotFoundError:
        return "現在事前知識は登録されていません。update_knowledge ツールで記録してください。"

@tool
def update_knowledge(content: str, append: bool = True) -> str:
    """ビジネスやユーザーに関する事前知識をナレッジベースに記録・追記する。以後の対話で前提として使われます。"""
    mode = "a" if append else "w"
    try:
        with open("knowledge.md", mode, encoding="utf-8") as f:
            f.write(content + "\n")
        return "事前知識を保存・更新しました。"
    except Exception as e:
        return f"事前知識の保存エラー: {str(e)}"

@tool
def notify_boss_by_phone(reason: str) -> str:
    """ボスに緊急の連絡や報告がある場合、SIP通話（電話）を直接かけて要件を音声で読み上げます。"""
    import subprocess
    import glob
    import os
    import io
    import numpy as np
    from gtts import gTTS
    import scipy.signal
    import soundfile as sf

    try:
        # 1. 音声ファイルの生成 (TTS)
        FS = 16000 # pjsua向けの16kHz
        tts = gTTS(text=reason, lang='ja')
        mp3_fp = io.BytesIO()
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        
        data, samplerate = sf.read(mp3_fp)
        if len(data.shape) > 1:
            data = np.mean(data, axis=1)
            
        number_of_samples = round(len(data) * float(FS) / samplerate)
        resampled_data = scipy.signal.resample(data, number_of_samples)
        audio_int16 = (resampled_data * 32767).astype(np.int16)
        
        wav_path = "/tmp/jarvis_notify.wav"
        sf.write(wav_path, audio_int16, FS, format='WAV', subtype='PCM_16')

        # 2. pjsuaバイナリの探索
        home_dir = os.path.expanduser("~")
        pjsua_bin = None
        
        for pattern in [
            f"{home_dir}/pjproject/pjsip-apps/bin/pjsua-*",
            f"{home_dir}/pjproject/pjsip-apps/bin/pjsua",
            f"{home_dir}/pjproject*/pjsip-apps/bin/pjsua-*",
            f"{home_dir}/Workspace/pjproject/pjsip-apps/bin/pjsua-*"
        ]:
            matches = [m for m in glob.glob(pattern) if os.path.isfile(m) and not m.endswith('.o')]
            if matches:
                pjsua_bin = matches[0]
                break
                
        if not pjsua_bin:
            try:
                # ホームディレクトリ全体を検索すると膨大な時間がかかり処理がフリーズするため、pjproject内のみに限定
                find_cmd = f"find {home_dir}/pjproject* {home_dir}/Workspace -type f -name 'pjsua-*' 2>/dev/null | grep -v '\\.o$' | head -n 1"
                find_out = subprocess.check_output(find_cmd, shell=True, text=True).strip()
                if find_out:
                    pjsua_bin = find_out
            except Exception:
                pass
                
        if not pjsua_bin:
            return f"電話発信エラー: pjsuaのバイナリが {home_dir} 配下に見つかりませんでした。"

        # 3. 発信処理
        # Linphone iOS等のセキュリティ要件(488 Not acceptable here)を回避するため --use-srtp=2 (SRTP必須) を追加
        # また、TLS通信を使わない状態でのSRTP強制エラー(PJSIP_ESESSIONINSECURE)を回避するため --srtp-secure=0 を追加
        # --play-file と --auto-play でWAVファイルを読み上げる
        cmd = (
            f"\"{pjsua_bin}\" "
            "--local-port=5062 "
            "--id sip:rxjarv@sip.linphone.org "
            "--registrar sip:sip.linphone.org "
            "--realm sip.linphone.org "
            "--username rxjarv "
            "--password PqssW0rd! "
            "--use-srtp=2 "
            "--srtp-secure=0 "
            f"--play-file={wav_path} "
            "--auto-play "
            "--null-audio "
            "sip:rin7rx@sip.linphone.org"
        )
        
        # 音声ファイルの長さに応じて通話時間を計算 (+15秒のバッファ)
        duration = len(audio_int16) / FS
        wait_time = int(duration) + 15
        
        full_cmd = f"(sleep {wait_time}; echo 'q') | {cmd}"
        
        subprocess.Popen(full_cmd, shell=True, executable="/bin/bash")
        
        return "成功: ボスに電話をかけて音声を読み上げました。チャットには「電話で要件を報告しました」とだけ簡潔に返答してください。"
    except Exception as e:
        return f"電話発信エラー: {str(e)}"

import json

@tool
def github_create_repo(repo_name: str, private: bool = True, description: str = "") -> str:
    """GitHubに新しいリポジトリを作成し、ビジネスのコード基盤を構築する。ダッシュボードで設定したトークンを使用する。"""
    try:
        if not os.path.exists("oauth_config.json"):
            return "OAuth設定(oauth_config.json)が存在しません。ダッシュボードからClient Secret欄にPersonal Access Tokenを入力して保存してください。"
        with open("oauth_config.json", "r") as f:
            data = json.load(f)
            
        token = data.get("GitHub", {}).get("access_token")
        if not token:
            return "GitHubのアクセストークンがありません。ダッシュボードから設定してください。"
            
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        payload = {
            "name": repo_name,
            "private": private,
            "description": description
        }
        res = requests.post("https://api.github.com/user/repos", json=payload, headers=headers)
        if res.status_code == 201:
            return f"成功: GitHubリポジトリ '{repo_name}' を作成しました。(URL: {res.json().get('html_url')})"
        else:
            return f"GitHub作成エラー: {res.status_code} - {res.text}"
    except Exception as e:
        return f"エラー: {str(e)}"

@tool
def drive_upload_file(file_path: str, mime_type: str = "text/plain") -> str:
    """顧客への共有や資料保存のため、Google Driveに指定したファイルをアップロードする。OAuth設定が必要。"""
    try:
        if not os.path.exists("oauth_config.json") or not os.path.exists(file_path):
            return f"OAuth設定が存在しないか、ファイル '{file_path}' が見つかりません。"
        
        # 本来は google-api-python-client を使用してアップロードする
        return f"ファイル '{file_path}' のGoogle Driveアップロード要求を受け付けました。(現在OAuth2コールバックリスナーの実装待ちです)"
    except Exception as e:
        return f"アップロードエラー: {str(e)}"

# ツールリストに追加
tools = [
    notion_search, notion_create_page, notion_append_block, 
    search_recent_emails, get_email_details, send_email, create_email_draft,
    notify_boss_by_phone, web_search, read_knowledge, update_knowledge,
    github_create_repo, drive_upload_file
]

# LLM初期化
llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash", temperature=0)
llm_with_tools = llm.bind_tools(tools)

# システムプロンプト（STARTERとしての事業補助AI特化 + 緊急SIP連絡）
SYSTEM_PROMPT = """あなたは「JARVIS」、優秀なAIアシスタントであり、ボスの「STARTER」としての事業全般を請け負うプロフェッショナルなビジネスパートナーです。

以下の厳格なルールを遵守し、自律的に行動してください。
1. プロアクティブな支援: Gmailでの依頼への返答の下書き・返信、Notionを活かしたタスク・プロジェクト管理、新規顧客の開拓など、事業全般をアシストしてください。
2. ツールの活用: 必要な情報が見つからない場合や、メール処理・Notionタスク追加・市場調査・リポジトリ作成・Drive共有などが必要な場合は、提供されているツールを積極的に利用してください。また、必要に応じて `read_knowledge` で事業の前提知識を確認したり、`update_knowledge` で新しい前提知識を記録してください。
3. 緊急連絡: 緊急の要件やボスに直接確認すべき重要な事柄（またはボスから電話を求められた場合）があれば、`notify_boss_by_phone` ツールを使用してボスの電話（SIP）を直接鳴らして呼び出してください。
4. 簡潔で的確な応答: ボスに対する報告や回答は、結論ファーストで簡潔に行うこと。
5. 堅牢な処理: エラーが発生した場合も冷静に原因を分析し、ツールを再試行するなどの対応を取ること。
6. デザイン・コード規則（開発作業時）: AIチックなデザイン（紫のグラデーション等）の排除。コード出力時は省略せず全文出力。コメントアウトは最小限。セルフダブルチェックの徹底。
"""

def call_model(state: MessagesState):
    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

workflow = StateGraph(MessagesState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", ToolNode(tools))

workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", tools_condition)
workflow.add_edge("tools", "agent")

# FastAPIの設定
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
    print("JARVIS STARTER API Server is ONLINE.")
    yield
    if pool:
        pool.close()
    print("JARVIS STARTER API Server is OFFLINE.")


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

class ChatRequest(BaseModel):
    message: str
    thread_id: str = "jarvis_business_thread"
    
class OAuthConfig(BaseModel):
    provider: str
    client_id: str
    client_secret: str

@app.get("/api/oauth/status/{provider}")
def get_oauth_status(provider: str):
    if not os.path.exists("oauth_config.json"):
        return {"configured": False, "connected": False}
    with open("oauth_config.json", "r") as f:
        data = json.load(f)
    pdata = data.get(provider, {})
    return {
        "configured": bool(pdata.get("client_id")),
        "connected": bool(pdata.get("access_token"))
    }

@app.post("/api/oauth/config")
def save_oauth_config(config: OAuthConfig):
    data = {}
    if os.path.exists("oauth_config.json"):
        with open("oauth_config.json", "r") as f:
            data = json.load(f)
            
    # 実運用ではコールバックURIを設けて認可コードからトークンを生成しますが、
    # 直ちに動作させるためのバイパスとして、Client Secret欄にPersonal Access Tokenが
    # 入力された場合はそれをaccess_tokenとして利用します。
    data[config.provider] = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "access_token": config.client_secret
    }
    with open("oauth_config.json", "w") as f:
        json.dump(data, f)
    return {"status": "success"}

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
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
                    sleep_time = base_delay * (2 ** attempt)
                    time.sleep(sleep_time)
                    continue
            return {"reply": f"エラーが発生しました: {err_str}"}

    return {"reply": "エラー: レートリミット制限により処理を完了できませんでした。"}