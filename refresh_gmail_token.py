import os
import time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose'
]

def main():
    token_path = 'token.json'
    
    if not os.path.exists(token_path):
        print(f"エラー: {token_path} が見つかりません。")
        print("まずは get_gmail_token.py を実行して初期認証を行ってください。")
        return

    print("Gmailトークン自動更新スクリプトを開始します（バックグラウンド待機中）...")
    
    while True:
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            
            # トークンが有効期限切れ、または無効な場合はリフレッシュ
            if creds and (not creds.valid or creds.expired):
                if creds.refresh_token:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] トークンの有効期限が切れています。リフレッシュを実行します...")
                    creds.refresh(Request())
                    
                    # 更新されたトークンを token.json に保存
                    with open(token_path, 'w') as token_file:
                        token_file.write(creds.to_json())
                        
                    # 互換性のため token.txt にも新しいアクセストークンを保存
                    with open('token.txt', 'w') as txt_file:
                        txt_file.write(creds.token)
                        
                    print("トークンを正常に更新しました。")
                else:
                    print("エラー: リフレッシュトークンが存在しません。get_gmail_token.pyで再度認証を行ってください。")
                    break
            else:
                # デバッグ用に表示したい場合はコメントアウトを外す
                # print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] トークンはまだ有効です。")
                pass
                
        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] トークン更新中にエラーが発生しました: {e}")
            
        # 30分（1800秒）ごとにチェック (Googleのトークンは通常1時間で切れるため)
        time.sleep(1800)

if __name__ == '__main__':
    main()
