import numpy as np
import sounddevice as sd

# オーディオ設定（電話品質：8000Hz, モノラル）
FS = 8000
DURATION = 2.0  # 秒

print("JARVIS音声テストを開始します... スマホの通話音声を確認してください。")

# 440Hz（ラの音）のテスト用サイン波を生成
t = np.linspace(0, DURATION, int(FS * DURATION), endpoint=False)
audio_data = 0.3 * np.sin(2 * np.pi * 440 * t)

# 16bit整数型に変換
audio_int16 = (audio_data * 32767).astype(np.int16)

# PulseAudio（出力デバイス）へストリーミング再生
# デバイス指定を省略した場合はデフォルトのPulseAudioシンクへ流れます
sd.play(audio_int16, samplerate=FS, blocking=True)

print("テスト音の送信が完了しました。")
