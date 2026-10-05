import os
from google_auth_oauthlib.flow import InstalledAppFlow

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose'
]

def main():
    if not os.path.exists('credentials.json'):
        print("エラー: credentials.json が見つかりません。")
        return

    # クライアントシークレットファイルからフローを作成
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    
    # 承認済みリダイレクトURIに http://localhost が登録されている前提
    flow.redirect_uri = 'http://localhost'

    # ログイン時に必ずアカウント選択画面と同意画面を表示させる設定
    auth_url, _ = flow.authorization_url(
        prompt='select_account consent',
        access_type='offline',
        include_granted_scopes='true'
    )

    print("\n1. 以下のURLを【お手元のローカルPCのブラウザ】で開いてください:\n")
    print(auth_url)
    print("\n")
    print("2. Googleアカウントでログインし、アクセスを許可すると、ブラウザが 'このサイトにアクセスできません' (localhostへの接続拒否) の画面になります。")
    print("3. その時の【ブラウザのアドレスバーに表示されたURL全体（http://localhost/?code=...）】をコピーして、ここに貼り付けてください。\n")

    # リダイレクトされたURL全体を入力してもらう
    redirected_url = input("ブラウザのアドレスバーのURL全体を貼り付け: ").strip()

    # URLからコードを抽出してトークンを取得
    flow.fetch_token(authorization_response=redirected_url)
    creds = flow.credentials

    print("\n--- 認証成功！ ---")
    print(f"Access Token: {creds.token}")
    print(f"Refresh Token: {creds.refresh_token}")

    with open('token.txt', 'w') as token_file:
        token_file.write(creds.token)

    # 自動更新スクリプト用にリフレッシュトークンを含む情報を保存
    with open('token.json', 'w') as json_file:
        json_file.write(creds.to_json())
    print("\nAccess Tokenを token.txt に保存しました。")

if __name__ == '__main__':
    main()