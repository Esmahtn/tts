"""
Shopping Simulation — Interaktif Test İstemcisi

  Boş Enter     → mikrofon kaydı başlar anında, tekrar Enter → gönder
  Yazı + Enter  → metin olarak gönder
  'exit'        → çık
"""
import asyncio, base64, os, tempfile, threading, time, uuid

import asyncio, base64, os, tempfile, threading, time, uuid, ctypes

import httpx
import numpy as np
import scipy.io.wavfile as wav
import sounddevice as sd

BASE_URL    = "http://127.0.0.1:8000"
SAMPLE_RATE = 16000
MIN_RECORD_SECS = 0.5   # çok kısa kayıtları reddet


# ─── Ses Oynatma ve Dosya Temizliği (Windows MCI) ────────────────────────────

def cleanup_cache():
    """audio_cache klasöründe sadece en yeni 2 mic_ ve 2 resp_ dosyasını tutar, eskileri siler."""
    cache_dir = os.path.abspath("audio_cache")
    os.makedirs(cache_dir, exist_ok=True)
    
    for prefix in ["mic_", "resp_"]:
        files = [os.path.join(cache_dir, f) for f in os.listdir(cache_dir) if f.startswith(prefix)]
        files.sort(key=os.path.getmtime, reverse=True) # En yeniler başta
        
        # 3. ve daha eski dosyaları sil
        for old_file in files[2:]:
            try:
                os.remove(old_file)
            except Exception:
                pass

def play_async(mp3_bytes: bytes):
    """Yeni ses geldiğinde eskisini keser, arka planda MP3 çalar."""
    cache_dir = os.path.abspath("audio_cache")
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"resp_{int(time.time()*1000)}.mp3")
    
    with open(path, "wb") as f:
        f.write(mp3_bytes)

    # Önceki sesi durdur ve kapat
    ctypes.windll.winmm.mciSendStringW(f"close current_mp3", None, 0, None)
    
    # Yeni sesi aç ve çal (arka planda)
    cmd_open = f"open \"{path}\" type mpegvideo alias current_mp3"
    ctypes.windll.winmm.mciSendStringW(cmd_open, None, 0, None)
    ctypes.windll.winmm.mciSendStringW("play current_mp3", None, 0, None)
    
    cleanup_cache()

# ─── Mikrofon Kaydı ──────────────────────────────────────────────────────────

def record_mic() -> bytes | None:
    """Anında kaydı başlatır; Enter sonrası durdurur. WAV bytes döner."""
    chunks = []
    stop = threading.Event()
    start_ts = time.time()

    def collect():
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as s:
            while not stop.is_set():
                chunk, _ = s.read(512)
                chunks.append(chunk.copy())

    t = threading.Thread(target=collect, daemon=True)
    t.start()
    print("  🔴 Kayıt... (Enter = durdur)")

    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass

    stop.set()
    t.join(timeout=1)

    duration = time.time() - start_ts
    if not chunks or duration < MIN_RECORD_SECS:
        print("  ⚠️  Çok kısa kayıt, tekrar dene.")
        return None

    audio = np.concatenate(chunks)
    
    # Ana dizin yerine audio_cache klasörüne kaydet
    cache_dir = os.path.abspath("audio_cache")
    os.makedirs(cache_dir, exist_ok=True)
    mic_path = os.path.join(cache_dir, f"mic_{int(time.time()*1000)}.wav")
    
    wav.write(mic_path, SAMPLE_RATE, audio)
    
    with open(mic_path, "rb") as f:
        data = f.read()
        
    cleanup_cache()
    return data


# ─── API ─────────────────────────────────────────────────────────────────────

async def chat_text(client, text, sid):
    r = await client.post(f"{BASE_URL}/chat",
                          json={"text": text, "session_id": sid})
    r.raise_for_status()
    return r.json()


async def chat_voice(client, wav_bytes, sid):
    r = await client.post(
        f"{BASE_URL}/chat/voice",
        files={"audio_file": ("audio.wav", wav_bytes, "audio/wav")},
        data={"session_id": sid},
    )
    r.raise_for_status()
    return r.json()


# ─── Yanıt ───────────────────────────────────────────────────────────────────

def show(data: dict):
    print(f"\n🤖  {data['text']}")
    print(f"📍  State {data['state']} | {data['sub_state']}")
    if data.get("audio_base64"):
        play_async(base64.b64decode(data["audio_base64"]))


# ─── Ana Döngü ───────────────────────────────────────────────────────────────

async def run():
    sid = str(uuid.uuid4())[:8]
    print("=" * 50)
    print(f"🛒  Alışveriş Simülasyonu  |  Session: {sid}")
    print("  Boş Enter = 🎤 Mikrofon   |   Yazı + Enter = ✏️  Metin")
    print("=" * 50)

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            show(await chat_text(client, "başlayalım", sid))
        except Exception as e:
            print(f"❌ Başlatılamadı: {e}")
            return

        while True:
            try:
                user = input("\n➤ ").strip()
            except (KeyboardInterrupt, EOFError):
                break

            if user.lower() in ("exit", "quit", "çık"):
                break

            try:
                if user == "":
                    # ── Mikrofon ──────────────────────────────
                    wav_bytes = record_mic()
                    if wav_bytes is None:
                        continue
                    print("  ✅ Gönderiliyor...")
                    show(await chat_voice(client, wav_bytes, sid))
                else:
                    # ── Metin ─────────────────────────────────
                    show(await chat_text(client, user, sid))

            except httpx.HTTPStatusError as e:
                print(f"❌ API hatası {e.response.status_code}: {e.response.text[:200]}")
            except Exception as e:
                print(f"❌ {e}")

    print("\n👋 Görüşmek üzere!")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n👋 Görüşmek üzere!")
