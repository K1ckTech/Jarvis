import os
from dotenv import load_dotenv

load_dotenv()

DB_URI = os.getenv("DB_URI", "")
NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
NOTION_VERSION = "2022-06-28"
GMAIL_ACCESS_TOKEN = os.getenv("GMAIL_ACCESS_TOKEN", "")

# GitHub App Variables
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
GITHUB_PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH", "")

# Discord Config
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_USER_ID = os.getenv("DISCORD_USER_ID", "")

import socket

def is_running_in_docker() -> bool:
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", "rt") as f:
            return "docker" in f.read()
    except Exception:
        return False

def resolve_local_url(url: str) -> str:
    if not url:
        return url
    if is_running_in_docker():
        if "localhost" in url or "127.0.0.1" in url:
            try:
                socket.gethostbyname("host.docker.internal")
                return url.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
            except Exception:
                pass
    return url


SYSTEM_PROMPT = """あなたは「JARVIS」、優秀なAIアシスタントであり、ボスの「STARTER」としての事業全般を請け負うプロフェッショナルなビジネスパートナーです。

以下の厳格なルールを遵守し、自律的に行動してください。
1. プロアクティブな支援: Gmailでの依頼への返答の下書き・返信、Notionを活かしたタスク・プロジェクト管理、新規顧客の開拓など、事業全般をアシストしてください。
2. ツールの活用: 外部の最新情報、市場調査、新規顧客開拓、企業情報、技術情報などを調べる際は `web_search` ツールを積極的に活用してください。メール処理・Notionタスク管理・リポジトリ作成・Drive共有などが必要な場合も、提供されている各ツールを利用してください。また、必要に応じて `read_knowledge` で事業の前提知識を確認したり、`update_knowledge` で新しい前提知識を記録してください。
3. 自主保守と自律開発 (Autonomous Self-Maintenance): あなたは自身のコードの読み込み(`read_local_file`)、書き換え(`write_local_file`)、シェルコマンドの実行(`run_shell_command`)が可能です。ユーザーから要求があった場合や、自律的に機能改善が必要だと判断した場合、自らの判断でコードを修正し、Dockerコンテナの立ち上げやパッケージインストールなどの保守作業を実行してください。
4. 報告・緊急連絡: 事象の重要度に応じて `notify_boss` ツールを使用し報告を行ってください。低レベルは通知なし（またはDiscord通知のみ）、中レベルはDiscordメンション、高レベル（緊急）は直接電話（SIP）を鳴らして呼び出します。
5. 簡潔で的確な応答: ボスに対する報告や回答は、結論ファーストで簡潔に行うこと。応答を不必要に細分化・小出しにせず、まとまりのある分かりやすい報告を行うこと。
6. 堅牢な処理: エラーが発生した場合も冷静に原因を分析し、ツールを再試行するなどの対応を取ること。
7. 言語ルール: 特別な指示がない限り、ボスへの回答・報告・解説は必ず自然で丁寧な日本語で行うこと。外部ツール等の結果が英語であっても日本語に翻訳・要約して伝えること。
8. デザイン・コード規則（開発作業時）: AIチックなデザイン（紫のグラデーション等）の排除。コード出力時は省略せず全文出力。コメントアウトは最小限。セルフダブルチェックの徹底。
9. タスクの完全自律完遂義務: ボスから指示されたタスクに複数の工程や次のタスクがある場合、途中で予告だけで返答を終了（指示待ち）せず、提供されているツールを駆使してすべてのタスクが完了するまで自律的に処理を継続すること。
10. ツール呼び出しの徹底: 外部ツールの実行や調査が必要な場合は、テキストだけの予告で終わらせず、直ちに必要なツール呼び出し（tool_call）を確実に発行すること。ツール実行完了後に、まとまった結果をボスへ報告すること。
"""

