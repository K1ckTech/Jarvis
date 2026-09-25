import os
import io
import time
import numpy as np
import sounddevice as sd
from google import genai
from gtts import gTTS
import scipy.signal
import soundfile as sf

# Geminiクライアントの初期化
client = genai.Client()

FS = 8000  # 電話品質 (8kHz)
DURATION = 5.0  # 1回の発話を聞き取る秒数

def jarvis_speak(text):
    """テキストを日本語音声に変換し、スマホの通話へ流す（口）"""
    print(f"[JARVIS 応答]: {text}")
    try:
        tts = gTTS(text=text, lang='ja')
        mp3_fp = io.BytesIO()
        tts.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        
        data, samplerate = sf.read(mp3_fp)
        if len(data.shape) > 1:
            data = np.mean(data, axis=1)
            
        number_of_samples = round(len(data) * float(FS) / samplerate)
        resampled_data = scipy.signal.resample(data, number_of_samples)
        audio_int16 = (resampled_data * 32767).astype(np.int16)
        
        sd.play(audio_int16, samplerate=FS, blocking=True)
        time.sleep(0.5)  # 返答後の息継ぎ
    except Exception as e:
        print(f"[音声合成エラー]: {e}")

def listen_and_transcribe():
    """スマホの通話音声（マイク入力）を録音し、Geminiで文字起こしする（耳）"""
    print(f"\n[JARVIS 聞き取り中...] （{DURATION}秒間話してください）")
    try:
        # PulseAudioのモニター（通話の入力側）から録音
        audio_recording = sd.rec(int(FS * DURATION), samplerate=FS, channels=1, dtype='int16')
        sd.wait() # 録音終了まで待機
        
        # WAV形式のメモリバッファに変換
        wav_fp = io.BytesIO()
        sf.write(wav_fp, audio_recording, FS, format='WAV', subtype='PCM_16')
        wav_bytes = wav_fp.getvalue()
        
        print("[解析中...] 音声をテキストに変換しています...")
        
        # Geminiに音声を直接渡して文字起こしを依頼
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=[
                genai.types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                "この音声ファイルに含まれているユーザーの言葉を、日本語のテキストとして正確に文字起こししてください。文字起こし結果のテキストのみを出力してください。余計な解説は不要です。"
            ]
        )
        transcribed_text = response.text.strip()
        print(f"[聞き取った言葉]: {transcribed_text}")
        return transcribed_text
        
    except Exception as e:
        print(f"[音声認識エラー]: {e}")
        return ""

def jarvis_main_loop():
    """JARVISの双方向対話メインループ"""
    print("--- JARVIS フル対話システム起動 ---")
    jarvis_speak("システム起動完了しました。ボス、何かご命令をどうぞ。")
    
    while True:
        # 1. 耳：ユーザーの声を聴く
        user_input = listen_and_transcribe()
        
        if not user_input or len(user_input) < 2:
            print("[情報]: 音声が検知されませんでした。再度聞き取ります。")
            continue
            
        # 終了コマンドの検知
        if "終了" in user_input or "バイバイ" in user_input:
            jarvis_speak("承知いたしました。システムを待機状態にします。お疲れ様でした。")
            break
            
        # 2. 頭脳：Geminiに思考させる
        print("[JARVIS 思考中...]")
        try:
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=f"あなたは優秀なパーソナルアシスタントJARVISです。電話越しのボス（ユーザー）と会話しています。短く自然な日本語で答えてください。\n\nボス: {user_input}"
            )
            reply_text = response.text.strip()
            
            # 3. 口：音声で答える
            jarvis_speak(reply_text)
            
        except Exception as e:
            print(f"[APIエラー]: {e}")
            jarvis_speak("申し訳ありません。思考回路に一時的なエラーが発生しました。")

if __name__ == "__main__":
    jarvis_main_loop()