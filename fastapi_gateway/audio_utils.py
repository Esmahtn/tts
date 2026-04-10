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
    # 1. Önce kural/LLM gibi n8n etiketlerini tamamen sil
    text = re.sub(r'_(?:⚙.*?\s*)?(?:Kural|LLM|System).*?_', '', text, flags=re.IGNORECASE)
    text = re.sub(r'_(?:🤖.*?\s*)?(?:Kural|LLM|System).*?_', '', text, flags=re.IGNORECASE)
    
    # Kalan altçizgileri boşluğa çevir (TTS altçizgi okumasın)
    text = text.replace('_', ' ')
    
    # 2. Emoji ve bazı grafik sembolleri temizle
    text = re.sub(r'[^\w\s,.?!\-\'"]', '', text)
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
