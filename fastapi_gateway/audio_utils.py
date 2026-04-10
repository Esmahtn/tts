import os
import base64
import logging
import httpx
import edge_tts
import io
import re
from config import settings

logger = logging.getLogger(__name__)

async def transcribe_audio(file_bytes: bytes, filename: str) -> str:
    """
    Groq Whisper API kullanarak ses dosyasını metne dönüştürür.
    (Yerel GPU modeli iptal edildi, en stabil bulut sistemine dönüldü)
    """
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}"
    }
    
    files = {
        "file": (filename, file_bytes),
        "model": (None, "whisper-large-v3-turbo"),
        "language": (None, "tr"),
        "response_format": (None, "json")
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, files=files, timeout=30.0)
            response.raise_for_status()
            return response.json().get("text", "")
        except Exception as e:
            logger.error(f"STT Error (Groq): {e}")
            raise Exception(f"Ses metne dönüştürülemedi: {str(e)}")

def clean_text_for_tts(text: str) -> str:
    """Metindeki n8n etiketlerini (_⚙️ Kural_ vb.), emojileri ve özel sembolleri temizler."""
    
    # 1. Önce markdown içi (altçizgi veya yıldız arasında) n8n etiketlerini temizle
    text = re.sub(r'[_*]+.*?(?:Kural|LLM|System).*?[_*]+', '', text, flags=re.IGNORECASE)
    
    # 2. Yeni satırda tek başına veya başta bulunan "Kural", "Kural:", "⚙ Kural" gibi etiketleri satır bazlı temizle
    text = re.sub(r'^\s*(?:⚙️?\s*|🤖?\s*)?(?:Kural|System|LLM)\b.*$', '', text, flags=re.IGNORECASE | re.MULTILINE)
    
    # 3. Kalan altçizgi ve yıldızları boşluğa çevir (TTS okumasın)
    text = text.replace('_', ' ').replace('*', ' ')
    
    # 4. Emoji ve bazı grafik sembolleri temizle
    text = re.sub(r'[^\w\s,.?!\-\'"]', '', text)
    
    # 5. Fazladan boşluk veya enter'ları tek boşluğa indirge
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

async def synthesize_speech(text: str) -> str:
    """
    Edge-TTS kullanarak metni sese dönüştürür ve Base64 string olarak döner.
    """
    try:
        # Metni TTS için temizle
        clean_text = clean_text_for_tts(text)
        
        communicate = edge_tts.Communicate(clean_text, settings.TTS_VOICE, rate=settings.TTS_RATE)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        
        return base64.b64encode(audio_data).decode("utf-8")
    except Exception as e:
        logger.error(f"TTS Error (Edge-TTS): {e}")
        return "" # Ses üretilemezse boş döner, hata fırlatmaz (text yanıtı hala geçerli)

def split_sentences(text: str):
    """Metni cümlelere böler."""
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return [s.strip() for s in sentences if s.strip()]

async def synthesize_sentences(text: str):
    """
    Metni cümlelere böler ve her cümlenin tamamlanmış MP3 dosyasını
    base64 olarak yield eder. (Sentence-Level Chunking)
    """
    sentences = split_sentences(text)
    import asyncio
    
    async def fetch_audio(sent: str):
        clean = clean_text_for_tts(sent)
        if not clean:
            return b""
        com = edge_tts.Communicate(clean, settings.TTS_VOICE, rate=settings.TTS_RATE)
        data = b""
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                data += chunk["data"]
        return data

    tasks = [asyncio.create_task(fetch_audio(s)) for s in sentences]
    
    for i, (sentence, task) in enumerate(zip(sentences, tasks)):
        try:
            audio_data = await task
            if not audio_data:
                continue
            
            base64_audio = base64.b64encode(audio_data).decode("utf-8")
            is_last = (i == len(sentences) - 1)
            
            yield {
                "text": sentence,
                "audio_base64": base64_audio,
                "is_last_sentence": is_last
            }
        except Exception as e:
            logger.error(f"TTS Sentence Error on '{sentence}': {e}")
