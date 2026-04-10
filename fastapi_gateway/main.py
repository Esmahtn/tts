import logging
from typing import List, Dict, Any

import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from models import ChatRequest, ChatResponse
from audio_utils import transcribe_audio, synthesize_speech
from fastapi import UploadFile, File, Form
# Loglama ayarları
import json
import asyncio
import websockets
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
    from audio_utils import synthesize_speech, clean_text_for_tts

    try:
        while True:
            # 1. Connect to Deepgram STT WebSocket per utterance
            dg_url = "wss://api.deepgram.com/v1/listen?model=nova-2&language=tr&smart_format=true&encoding=linear16&sample_rate=16000&channels=1"
            
            async with websockets.connect(
                dg_url, 
                additional_headers={"Authorization": f"Token {settings.DEEPGRAM_API_KEY}"}
            ) as dg_socket:
                
                transcript = ""
                
                # Task to receive from Deepgram
                async def receive_from_deepgram():
                    nonlocal transcript
                    try:
                        async for message in dg_socket:
                            data = json.loads(message)
                            if data.get("is_final"):
                                alts = data.get("channel", {}).get("alternatives", [])
                                if alts and alts[0].get("transcript"):
                                    transcript += alts[0]["transcript"] + " "
                                    await websocket.send_json({"type": "live_transcript", "text": alts[0]["transcript"]})
                    except Exception as e:
                        logger.error(f"Deepgram receive error: {e}")
                        
                dg_task = asyncio.create_task(receive_from_deepgram())
                
                # Receive audio from Client
                while True:
                    data = await websocket.receive()
                    
                    if "bytes" in data:
                        await dg_socket.send(data["bytes"])
                        
                    elif "text" in data:
                        msg = json.loads(data["text"])
                        if msg.get("event") == "stop":
                            # Tell deepgram we are done sending audio
                            await dg_socket.send(b"")
                            # Wait briefly for deepgram to send final transcript
                            await asyncio.sleep(0.5)
                            break
                            
                # Force cancel deepgram task if it didn't finish
                dg_task.cancel()
                
                final_text = transcript.strip()
                if not final_text:
                    final_text = "Anlaşılamadı."
                    
                # Send final text to Unity so it knows what it heard
                await websocket.send_json({"type": "final_transcript", "text": final_text})
                
                # 2. Send text to n8n
                n8n_payload = {"userInput": final_text, "sessionId": session_id}
                n8n_response = await _call_n8n(n8n_payload)
                
                raw_bot_text = n8n_response.get("response", "Anlaşılamadı.")
                clean_bot_text = clean_text_for_tts(raw_bot_text)
                
                # Send text to Unity
                await websocket.send_json({
                    "type": "bot_text", 
                    "text": clean_bot_text,
                    "state": int(n8n_response.get("currentState", 0)),
                    "sub_state": n8n_response.get("subState", "INIT")
                })
                
                # 3. TTS (Edge-TTS)
                if clean_bot_text:
                    audio_b64 = await synthesize_speech(clean_bot_text)
                    await websocket.send_json({"type": "bot_audio", "audio_base64": audio_b64})
                    
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


