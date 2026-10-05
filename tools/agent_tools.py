import os
import time
import json
import base64
import requests
import jwt # requires PyJWT
import paramiko # requires paramiko
import tempfile
from email.mime.text import MIMEText
from langchain_core.tools import tool

from core.config import (
    NOTION_API_KEY, NOTION_VERSION, GMAIL_ACCESS_TOKEN,
    GITHUB_APP_ID, GITHUB_PRIVATE_KEY_PATH,
    DISCORD_WEBHOOK_URL, DISCORD_USER_ID
)

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
        "properties": {"title": [{"text": {"content": title}}]}
    }
    if content_text:
        payload["children"] = [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": content_text}}]}}]
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
    payload = {"children": [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]}}]}
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
    """Gmailからキーワードに関連するメールを検索し、IDの一覧を返す"""
    if not GMAIL_ACCESS_TOKEN:
        return "エラー: GMAIL_ACCESS_TOKENが設定されていません。"
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?q={query_keyword}&maxResults=5"
    headers = {"Authorization": f"Bearer {GMAIL_ACCESS_TOKEN}"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            messages = response.json().get("messages", [])
            if not messages:
                return f"「{query_keyword}」に一致するメールは見つかりませんでした。"
            return "検索ヒット結果:\n" + "\n".join([f"- ID: {m.get('id')}" for m in messages]) + "\n※詳細を確認するには get_email_details を使ってください。"
        return f"Gmail APIエラー: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Gmail通信エラー: {str(e)}"

@tool
def get_email_details(message_id: str) -> str:
    """メール詳細を取得する"""
    if not GMAIL_ACCESS_TOKEN:
        return "エラー: GMAIL_ACCESS_TOKENが設定されていません。"
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}"
    headers = {"Authorization": f"Bearer {GMAIL_ACCESS_TOKEN}"}
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            snippet = data.get("snippet", "本文なし")
            headers_list = data.get("payload", {}).get("headers", [])
            subject = next((h.get("value") for h in headers_list if h.get("name") == "Subject"), "（件名なし）")
            sender = next((h.get("value") for h in headers_list if h.get("name") == "From"), "（差出人不明）")
            return f"【メール詳細】\n差出人: {sender}\n件名: {subject}\n本文プレビュー: {snippet}"
        return f"Gmail API詳細取得エラー: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Gmail通信エラー: {str(e)}"

@tool
def send_email(to_email: str, subject: str, body_text: str) -> str:
    """新しいメールを送信する"""
    if not GMAIL_ACCESS_TOKEN:
        return "エラー: GMAIL_ACCESS_TOKENが設定されていません。"
    message = MIMEText(body_text)
    message['To'] = to_email
    message['Subject'] = subject
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    headers = {"Authorization": f"Bearer {GMAIL_ACCESS_TOKEN}", "Content-Type": "application/json"}
    try:
        res = requests.post(url, json={"raw": raw_message}, headers=headers)
        if res.status_code == 200:
            return f"成功: 「{to_email}」宛にメールを送信しました。"
        return f"Gmail送信エラー: {res.status_code} - {res.text}"
    except Exception as e:
        return f"Gmail通信エラー: {str(e)}"

@tool
def create_email_draft(to_email: str, subject: str, body_text: str) -> str:
    """Gmailに下書きを作成する"""
    if not GMAIL_ACCESS_TOKEN:
        return "エラー: GMAIL_ACCESS_TOKENが設定されていません。"
    message = MIMEText(body_text)
    message['To'] = to_email
    message['Subject'] = subject
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    url = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
    headers = {"Authorization": f"Bearer {GMAIL_ACCESS_TOKEN}", "Content-Type": "application/json"}
    try:
        res = requests.post(url, json={"message": {"raw": raw_message}}, headers=headers)
        if res.status_code == 200:
            return f"成功: 「{to_email}」宛のメールを下書きに保存しました。"
        return f"Gmail下書き作成エラー: {res.status_code} - {res.text}"
    except Exception as e:
        return f"Gmail通信エラー: {str(e)}"

@tool
def web_search(query: str) -> str:
    """インターネット上でキーワード検索を行い情報を取得する"""
    try:
        from ddgs import DDGS
        results = DDGS().text(query, max_results=5)
        if not results:
            return "検索結果が見つかりませんでした。"
        return "ウェブ検索結果:\n" + "\n".join([f"- {r.get('title')} ({r.get('href')})\n  {r.get('body')}" for r in results])
    except Exception as e:
        return f"検索エラー: {str(e)}"

@tool
def read_knowledge() -> str:
    """ナレッジベースを読み込む"""
    try:
        with open("knowledge.md", "r", encoding="utf-8") as f:
            content = f.read()
            return content if content else "事前知識は現在空です。"
    except FileNotFoundError:
        return "現在事前知識は登録されていません。update_knowledge ツールで記録してください。"

@tool
def update_knowledge(content: str, append: bool = True) -> str:
    """ナレッジベースに記録・追記する"""
    mode = "a" if append else "w"
    try:
        with open("knowledge.md", mode, encoding="utf-8") as f:
            f.write(content + "\n")
        return "事前知識を保存・更新しました。"
    except Exception as e:
        return f"事前知識の保存エラー: {str(e)}"

@tool
def notify_boss_by_phone(reason: str) -> str:
    """ボスに緊急の連絡がある場合、SIP通話で要件を音声で読み上げる"""
    import subprocess, glob, io, numpy as np, scipy.signal, soundfile as sf
    from gtts import gTTS

    try:
        FS = 16000
        tts = gTTS(text=reason, lang='ja')
        mp3_fp = io.BytesIO()
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        data, samplerate = sf.read(mp3_fp)
        if len(data.shape) > 1: data = np.mean(data, axis=1)
        resampled = scipy.signal.resample(data, round(len(data) * float(FS) / samplerate))
        audio_int16 = (resampled * 32767).astype(np.int16)
        
        wav_path = "/tmp/jarvis_notify.wav"
        sf.write(wav_path, audio_int16, FS, format='WAV', subtype='PCM_16')

        home_dir = os.path.expanduser("~")
        pjsua_bin = next((m for pattern in [f"{home_dir}/pjproject/pjsip-apps/bin/pjsua-*", f"{home_dir}/pjproject*/pjsip-apps/bin/pjsua-*", f"{home_dir}/Workspace/pjproject/pjsip-apps/bin/pjsua-*"] for m in glob.glob(pattern) if os.path.isfile(m) and not m.endswith('.o')), None)
                
        if not pjsua_bin:
            return f"電話発信エラー: pjsuaバイナリが見つかりません。"

        cmd = f"\"{pjsua_bin}\" --local-port=5062 --id sip:rxjarv@sip.linphone.org --registrar sip:sip.linphone.org --realm sip.linphone.org --username rxjarv --password PqssW0rd! --use-srtp=2 --srtp-secure=0 --play-file={wav_path} --auto-play --null-audio sip:rin7rx@sip.linphone.org"
        wait_time = int(len(audio_int16) / FS) + 15
        subprocess.Popen(f"(sleep {wait_time}; echo 'q') | {cmd}", shell=True, executable="/bin/bash")
        return "成功: ボスに電話をかけて音声を読み上げました。"
    except Exception as e:
        return f"電話発信エラー: {str(e)}"

@tool
def notify_boss(level: str, reason: str) -> str:
    """重要度に応じてボスに報告や通知を行う。levelは 'low', 'medium', 'high' のいずれか。"""
    if level == "high":
        # 緊急時は電話をかける
        return notify_boss_by_phone(reason)
    
    elif level == "medium":
        # 中レベル: Discordへメンション付きで通知
        if not DISCORD_WEBHOOK_URL:
            return "Discord Webhookが設定されていません。"
        mention = f"<@{DISCORD_USER_ID}> " if DISCORD_USER_ID else "@here "
        payload = {"content": f"{mention} **【通知: 中レベル】**\n{reason}"}
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=payload)
            return "成功: Discordでメンション付き通知を送信しました。"
        except Exception as e:
            return f"Discord通知エラー: {str(e)}"
            
    elif level == "low":
        # 低レベル: Discordへ通知（メンションなし）
        if not DISCORD_WEBHOOK_URL:
            return "Discord Webhookが設定されていません。"
        payload = {"content": f"**【通知: 低レベル】**\n{reason}"}
        try:
            requests.post(DISCORD_WEBHOOK_URL, json=payload)
            return "成功: Discordで通知（メンションなし）を送信しました。"
        except Exception as e:
            return f"Discord通知エラー: {str(e)}"
            
    return "無効なレベルが指定されました。"

def _get_github_app_token() -> str:
    """Generate a JWT and get an installation token for GitHub App"""
    if not GITHUB_APP_ID or not GITHUB_PRIVATE_KEY_PATH:
        raise Exception("GitHub App ID or Private Key Path is not configured.")
        
    with open(GITHUB_PRIVATE_KEY_PATH, "r") as f:
        private_key = f.read()

    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + (10 * 60),
        "iss": GITHUB_APP_ID
    }
    encoded_jwt = jwt.encode(payload, private_key, algorithm="RS256")
    
    headers = {
        "Authorization": f"Bearer {encoded_jwt}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Get installations
    res = requests.get("https://api.github.com/app/installations", headers=headers)
    res.raise_for_status()
    installations = res.json()
    if not installations:
        raise Exception("No installations found for this GitHub App.")
        
    inst_id = installations[0]["id"]
    
    # Get token for installation
    token_url = f"https://api.github.com/app/installations/{inst_id}/access_tokens"
    t_res = requests.post(token_url, headers=headers)
    t_res.raise_for_status()
    return t_res.json()["token"]

@tool
def github_create_repo(repo_name: str, private: bool = True, description: str = "") -> str:
    """GitHubに新しいリポジトリを作成する (GitHub App または PAT)"""
    try:
        # Fallback to App Auth if PAT is not in oauth_config
        token = None
        if os.path.exists("oauth_config.json"):
            with open("oauth_config.json", "r") as f:
                data = json.load(f)
            token = data.get("GitHub", {}).get("access_token")
            
        if not token:
            try:
                token = _get_github_app_token()
            except Exception as e:
                return f"GitHub App トークン取得エラー: {str(e)}。PATも設定されていません。"
                
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        payload = {"name": repo_name, "private": private, "description": description}
        res = requests.post("https://api.github.com/user/repos", json=payload, headers=headers)
        if res.status_code == 201:
            return f"成功: GitHubリポジトリ '{repo_name}' を作成しました。(URL: {res.json().get('html_url')})"
        return f"GitHub作成エラー: {res.status_code} - {res.text}"
    except Exception as e:
        return f"エラー: {str(e)}"

@tool
def drive_upload_file(file_path: str, mime_type: str = "text/plain") -> str:
    """Google Driveにファイルをアップロードする。"""
    try:
        if not os.path.exists("oauth_config.json") or not os.path.exists(file_path):
            return f"OAuth設定が存在しないか、ファイル '{file_path}' が見つかりません。"
        return f"ファイル '{file_path}' のGoogle Driveアップロード要求を受け付けました。(現在OAuth2コールバックリスナーの実装待ちです)"
    except Exception as e:
        return f"アップロードエラー: {str(e)}"

@tool
def execute_ssh_command(hostname: str, username: str, command: str, password: str = None, key_filename: str = None, key_content: str = None, port: int = 22) -> str:
    """指定されたSSHサーバに接続してコマンドを実行する"""
    temp_key_path = None
    if key_content:
        fd, temp_key_path = tempfile.mkstemp(text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(key_content)
        key_filename = temp_key_path

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=hostname, port=port, username=username, password=password, key_filename=key_filename, timeout=15)
        stdin, stdout, stderr = client.exec_command(command, timeout=30)
        output = stdout.read().decode('utf-8')
        err_output = stderr.read().decode('utf-8')
        client.close()
        
        res = "【標準出力】\n" + (output if output else "なし\n")
        if err_output:
            res += "\n【エラー出力】\n" + err_output
        return f"成功: コマンドを実行しました。\n{res}"
    except Exception as e:
        return f"SSHコマンド実行エラー: {str(e)}"
    finally:
        if temp_key_path and os.path.exists(temp_key_path):
            os.remove(temp_key_path)

@tool
def upload_file_ssh(hostname: str, username: str, local_path: str, remote_path: str, password: str = None, key_filename: str = None, key_content: str = None, port: int = 22) -> str:
    """指定されたSSHサーバにファイルをアップロードする"""
    temp_key_path = None
    if key_content:
        fd, temp_key_path = tempfile.mkstemp(text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(key_content)
        key_filename = temp_key_path

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=hostname, port=port, username=username, password=password, key_filename=key_filename, timeout=15)
        sftp = client.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()
        client.close()
        return f"成功: ファイル '{local_path}' をリモートの '{remote_path}' にアップロードしました。"
    except Exception as e:
        return f"SSHアップロードエラー: {str(e)}"
    finally:
        if temp_key_path and os.path.exists(temp_key_path):
            os.remove(temp_key_path)

@tool
def download_file_ssh(hostname: str, username: str, remote_path: str, local_path: str, password: str = None, key_filename: str = None, key_content: str = None, port: int = 22) -> str:
    """指定されたSSHサーバからファイルをダウンロードする"""
    temp_key_path = None
    if key_content:
        fd, temp_key_path = tempfile.mkstemp(text=True)
        with os.fdopen(fd, 'w') as f:
            f.write(key_content)
        key_filename = temp_key_path

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=hostname, port=port, username=username, password=password, key_filename=key_filename, timeout=15)
        sftp = client.open_sftp()
        sftp.get(remote_path, local_path)
        sftp.close()
        client.close()
        return f"成功: リモートのファイル '{remote_path}' を '{local_path}' にダウンロードしました。"
    except Exception as e:
        return f"SSHダウンロードエラー: {str(e)}"
    finally:
        if temp_key_path and os.path.exists(temp_key_path):
            os.remove(temp_key_path)


from tools.browser_tools import browser_tools

tools = [
    notion_search, notion_create_page, notion_append_block, 
    search_recent_emails, get_email_details, send_email, create_email_draft,
    notify_boss_by_phone, notify_boss, web_search, read_knowledge, update_knowledge,
    github_create_repo, drive_upload_file, execute_ssh_command, upload_file_ssh, download_file_ssh
] + browser_tools
