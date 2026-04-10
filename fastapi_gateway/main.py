import logging
from typing import List, Dict, Any
import struct
import io

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from models import ChatRequest, ChatResponse
from audio_utils import transcribe_audio, synthesize_speech
from fastapi import UploadFile, File, Form
import json
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Shopping Simulation Gateway",
    description="Unity Frontend ve n8n Backend arasındaki köprü FastAPI servisi (STT/TTS destekli).",
    version="1.1.0"
)

# CORS ayarları (Unity webgl veya farklı domainler için)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat_endpoint(request_data: ChatRequest, include_audio: bool = True):
    """
    Metin bazlı chat. İsteğe bağlı olarak yanıtı ses (TTS) olarak da döner.
    """
    n8n_payload = {
        "userInput": request_data.text,
        "sessionId": request_data.session_id
    }
    
    n8n_response = await _call_n8n(n8n_payload)
    
    audio_b64 = None
    if include_audio and n8n_response.get("response"):
        audio_b64 = await synthesize_speech(n8n_response["response"])
    
    return ChatResponse(
        text=n8n_response.get("response", "Anlaşılamadı."),
        state=int(n8n_response.get("currentState", 0)),
        sub_state=n8n_response.get("subState", "INIT"),
        emotion=n8n_response.get("emotion"),
        source=n8n_response.get("source"),
        audio_base64=audio_b64
    )

@app.post("/chat/voice", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat_voice_endpoint(
    audio_file: UploadFile = File(...),
    session_id: str = Form(...)
):
    """
    Ses bazlı chat (STT -> n8n -> TTS).
    """
    # 1. STT: Sesi metne dönüştür
    audio_bytes = await audio_file.read()
    text_input = await transcribe_audio(audio_bytes, audio_file.filename)
    logger.info(f"STT Result: {text_input}")
    
    # 2. n8n'e gönder
    n8n_payload = {
        "userInput": text_input,
        "sessionId": session_id
    }
    n8n_response = await _call_n8n(n8n_payload)
    
    # 3. TTS: Yanıtı sese dönüştür
    audio_b64 = await synthesize_speech(n8n_response.get("response", ""))
    
    return ChatResponse(
        text=n8n_response.get("response", "Anlaşılamadı."),
        state=int(n8n_response.get("currentState", 0)),
        sub_state=n8n_response.get("subState", "INIT"),
        emotion=n8n_response.get("emotion"),
        source=n8n_response.get("source"),
        audio_base64=audio_b64
    )

async def _call_n8n(payload: Dict[str, Any]) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=settings.N8N_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(settings.N8N_WEBHOOK_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            return data[0] if isinstance(data, list) and data else data
        except Exception as e:
            logger.error(f"n8n logic error: {e}")
            raise HTTPException(status_code=502, detail="n8n bağlantı hatası.")

@app.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    from audio_utils import synthesize_sentences, clean_text_for_tts

    try:
        while True:
            # 1. Ses verilerini Client'ten topla
            audio_chunks: List[bytes] = []
            
            # İstemciden ses al ya da kontrol mesajı bekle
            while True:
                data = await websocket.receive()
                
                if "bytes" in data:
                    audio_chunks.append(data["bytes"])
                    
                elif "text" in data:
                    msg = json.loads(data["text"])
                    if msg.get("event") == "stop":
                        break
            
            # 2. Toplanan ham PCM sesini WAV formatına çevir
            raw_pcm = b"".join(audio_chunks)
            
            # WAV başlığı (header) oluştur: 16kHz, Mono, 16-bit PCM
            sample_rate = 16000
            num_channels = 1
            bits_per_sample = 16
            byte_rate = sample_rate * num_channels * bits_per_sample // 8
            block_align = num_channels * bits_per_sample // 8
            data_size = len(raw_pcm)
            
            wav_header = struct.pack(
                '<4sI4s4sIHHIIHH4sI',
                b'RIFF',
                36 + data_size,
                b'WAVE',
                b'fmt ',
                16,           # Subchunk1Size (PCM)
                1,            # AudioFormat (PCM = 1)
                num_channels,
                sample_rate,
                byte_rate,
                block_align,
                bits_per_sample,
                b'data',
                data_size
            )
            wav_bytes = wav_header + raw_pcm
            
            # 3. Groq Whisper STT
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
                    data_form = {
                        "model": "whisper-large-v3-turbo",
                        "language": "tr",
                        "response_format": "json"
                    }
                    groq_response = await client.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                        files=files,
                        data=data_form
                    )
                    groq_response.raise_for_status()
                    final_text = groq_response.json().get("text", "").strip()
            except Exception as e:
                logger.error(f"Groq STT Error: {e}")
                final_text = ""
            
            if not final_text:
                final_text = "Anlaşılamadı."
            
            logger.info(f"Groq STT: {final_text}")
            await websocket.send_json({"type": "final_transcript", "text": final_text})
            
            # 4. N8N'e gönder
            n8n_payload = {"userInput": final_text, "sessionId": session_id}
            n8n_response = await _call_n8n(n8n_payload)
            
            raw_bot_text = n8n_response.get("response", "Anlaşılamadı.")
            clean_bot_text = clean_text_for_tts(raw_bot_text)
            
            # Unity'ye metni gönder
            await websocket.send_json({
                "type": "bot_text", 
                "text": clean_bot_text,
                "state": int(n8n_response.get("currentState", 0)),
                "sub_state": n8n_response.get("subState", "INIT")
            })
            
            # 5. TTS (Cümle Bazlı, Paralel)
            if clean_bot_text:
                async for sentence_data in synthesize_sentences(clean_bot_text):
                    await websocket.send_json({
                        "type": "bot_sentence",
                        "text": sentence_data["text"],
                        "audio_base64": sentence_data["audio_base64"],
                        "is_last_sentence": sentence_data["is_last_sentence"]
                    })
                    
    except WebSocketDisconnect:
        logger.info("Client disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket Error: {e}")
        try: await websocket.send_json({"error": str(e)})
        except: pass
        
    try: await websocket.close()
    except: pass

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


