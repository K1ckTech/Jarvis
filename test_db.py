import os
import psycopg
from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv()
DB_URI = os.getenv("DB_URI")

try:
    with psycopg.connect(DB_URI) as conn:
        print("データベースへの接続に成功しました！JARVISの記憶領域へのアクセスOKです。")
except Exception as e:
    print(f"接続エラー: {e}")
