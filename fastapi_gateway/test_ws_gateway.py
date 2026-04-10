import asyncio
import websockets
import json
import base64
import os
import time
import uuid
import threading
import ctypes
import sounddevice as sd

BASE_URL_WS = "ws://127.0.0.1:8000/ws/voice"
SAMPLE_RATE = 16000

def play_async(mp3_bytes: bytes):
    cache_dir = os.path.abspath("audio_cache")
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"ws_resp_{int(time.time()*1000)}.mp3")
    
    with open(path, "wb") as f:
        f.write(mp3_bytes)

    ctypes.windll.winmm.mciSendStringW(f"close current_mp3", None, 0, None)
    cmd_open = f"open \"{path}\" type mpegvideo alias current_mp3"
    ctypes.windll.winmm.mciSendStringW(cmd_open, None, 0, None)
    ctypes.windll.winmm.mciSendStringW("play current_mp3", None, 0, None)

async def test_ws():
    session_id = str(uuid.uuid4())[:8]
    print("=" * 60)
    print("⚡ GERÇEK ZAMANLI (STREAMING) MİMARİ TESTİ")
    print("=" * 60)
    
    url = f"{BASE_URL_WS}?session_id={session_id}"
    
    try:
        async with websockets.connect(url) as ws:
            print("✅ Canlı Bağlantı Kuruldu!")
            
            async def receive_messages():
                try:
                    while True:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        if data.get("type") == "live_transcript":
                            print(f"\r🗣️ Söylediğin: {data['text']} ", end="", flush=True)
                        elif data.get("type") == "final_transcript":
                            print(f"\n✅ SEN: {data['text']}")
                            print("⏳ [0.1s] STT tamamlandı, n8n düşünülüyor...")
                        elif data.get("type") == "bot_text":
                            print(f"🤖 ASİSTAN: {data['text']}")
                        elif data.get("type") == "bot_audio":
                            print("🔊 Ses geldi, çalınıyor...")
                            play_async(base64.b64decode(data["audio_base64"]))
                        elif data.get("error"):
                            print(f"\n❌ Sunucu Hatası: {data['error']}")
                except websockets.exceptions.ConnectionClosed as e:
                    print(f"\n⚠️ Sunucu bağlantıyı kapattı: {e.code} - {e.reason}")
            
            # Arka planda sunucudan gelecek mesajları hep dinle
            recv_task = asyncio.create_task(receive_messages())
            
            while True:
                print("\n" + "-"*40)
                print("🎤 [ENTER]'a bas ve konuşmaya başla...")
                await asyncio.to_thread(input)
                
                stop_event = threading.Event()
                loop = asyncio.get_running_loop()
                
                print("🔴 CANLI YAYIN: Konuşuyorsun... (Durdurmak için tekrar ENTER'a bas)")
                
                def audio_callback(indata, frames, time_info, status):
                    if not stop_event.is_set():
                        try:
                            # Sesi fırlat
                            asyncio.run_coroutine_threadsafe(ws.send(indata.tobytes()), loop)
                        except Exception:
                            pass
                
                stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=4096, callback=audio_callback)
                stream.start()
                
                # Susa kadar bekle
                await asyncio.to_thread(input)
                
                stop_event.set()
                stream.stop()
                stream.close()
                
                try:
                    await ws.send(json.dumps({"event": "stop"}))
                except Exception as e:
                    print("⚠️ Sunucuya stop mesajı iletilemedi:", e)
                    
                print("⏳ Ses bitti, cevap bekleniyor...")
                
                # Cevap sesinin gelmesini (recv_task içinde) biraz bekle
                await asyncio.sleep(8)
                
    except Exception as e:
        print(f"❌ Bağlantı başarısız: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(test_ws())
    except KeyboardInterrupt:
        print("\n👋 Çıkıldı.")
