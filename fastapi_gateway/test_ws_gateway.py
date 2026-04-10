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

import queue
import threading

audio_queue = queue.Queue()

def audio_player_worker():
    cache_dir = os.path.abspath("audio_cache")
    os.makedirs(cache_dir, exist_ok=True)
    while True:
        mp3_bytes = audio_queue.get()
        if mp3_bytes is None:
            continue
        path = os.path.join(cache_dir, f"ws_resp_{int(time.time()*1000)}.mp3")
        with open(path, "wb") as f:
            f.write(mp3_bytes)
            
        alias = f"mp3_{int(time.time()*1000)}"
        ctypes.windll.winmm.mciSendStringW(f"open \"{path}\" type mpegvideo alias {alias}", None, 0, None)
        ctypes.windll.winmm.mciSendStringW(f"play {alias} wait", None, 0, None)
        ctypes.windll.winmm.mciSendStringW(f"close {alias}", None, 0, None)
        # Çalınan dosyayı anında sil (disk şişmesin)
        try:
            os.remove(path)
        except Exception:
            pass

threading.Thread(target=audio_player_worker, daemon=True).start()

def queue_play_async(mp3_bytes: bytes):
    audio_queue.put(mp3_bytes)

async def test_ws():
    session_id = str(uuid.uuid4())[:8]
    print("=" * 60)
    print("⚡ GERÇEK ZAMANLI (STREAMING) MİMARİ TESTİ")
    print("=" * 60)
    
    url = f"{BASE_URL_WS}?session_id={session_id}"
    
    try:
        async with websockets.connect(url) as ws:
            print("✅ Canlı Bağlantı Kuruldu!")
            stop_time = 0.0
            stt_done_time = 0.0
            n8n_done_time = 0.0
            ttfb_done = False

            async def receive_messages():
                nonlocal stop_time, stt_done_time, n8n_done_time, ttfb_done
                try:
                    while True:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        now = time.time()
                        
                        if data.get("type") == "live_transcript":
                            print(f"\r🗣️ Söylediğin: {data['text']} ", end="", flush=True)
                        elif data.get("type") == "final_transcript":
                            stt_done_time = now
                            latency_stt = (stt_done_time - stop_time) * 1000 if stop_time > 0 else 0
                            print(f"\n✅ SEN: {data['text']}")
                            print(f"⏱️  [STT Gecikmesi: {latency_stt:.0f} ms]")
                        elif data.get("type") == "bot_text":
                            n8n_done_time = now
                            latency_n8n = (n8n_done_time - stt_done_time) * 1000 if stt_done_time > 0 else 0
                            print(f"🤖 ASİSTAN: {data['text']}")
                            print(f"⏱️  [N8N Gecikmesi: {latency_n8n:.0f} ms]")
                            ttfb_done = False
                        elif data.get("type") == "bot_sentence":
                            if not ttfb_done:
                                ttfb_done = True
                                latency_ttfb = (now - n8n_done_time) * 1000 if n8n_done_time > 0 else 0
                                print(f"🔊 [İLK CÜMLE ULAŞTI!] ⏱️  [İlk Cümle Gecikmesi: {latency_ttfb:.0f} ms]")
                            
                            print(f"🎵 Cümle Çalınıyor: {data['text']}")
                            queue_play_async(base64.b64decode(data["audio_base64"]))
                            
                            if data.get("is_last_sentence"):
                                latency_total = (now - stop_time) * 1000 if stop_time > 0 else 0
                                print(f"⚡ TOPLAM GECİKME (Tüm Konuşma Sonu): {latency_total:.0f} ms\n")
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
                
                stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=1024, callback=audio_callback)
                stream.start()
                
                # Susa kadar bekle
                await asyncio.to_thread(input)
                
                stop_time = time.time()
                
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
