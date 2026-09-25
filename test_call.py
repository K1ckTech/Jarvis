import time
from pyVoIP.VoIP import VoIPPhone

SIP_SERVER = "sip.linphone.org"
SIP_USERNAME = "rxjarv" # 修正: JARVIS用アカウント
SIP_PASSWORD = "PqssW0rd!"   # 修正: JARVIS用パスワード
TARGET_SIP = "sip:rin7rx@sip.linphone.org" # スマホのアカウント

def main():
    # 標準のSIPポート(5060)を使用して初期化
    phone = VoIPPhone(SIP_SERVER, 5060, SIP_USERNAME, SIP_PASSWORD)
    
    try:
        print("JARVIS SIPモジュール起動 (Local Port: 5060)")
        phone.start()
        print(f"{TARGET_SIP} へ発信中...")
        
        call = phone.call(TARGET_SIP)
        
        for _ in range(20):
            print(f"現在の通話ステータス: {call.state}")
            if "ANSWERED" in str(call.state):
                print("応答を確認しました！着信テスト大成功です！")
                break
            elif "CLOSED" in str(call.state):
                print("通話が切断、または拒否されました。")
                break
            time.sleep(1)
            
    except Exception as e:
        print(f"発信エラー: {e}")
    finally:
        if 'call' in locals():
            call.hangup()
        phone.stop()
        print("SIPモジュールを終了しました。")

if __name__ == "__main__":
    main()