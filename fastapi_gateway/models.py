from typing import Optional
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    text: str = Field(..., description="Kullanıcıdan gelen ham metin", examples=["merhaba", "başlayalım"])
    session_id: str = Field(..., description="Benzersiz oturum kimliği", examples=["user-123", "abc-456"])

class ChatResponse(BaseModel):
    text: str = Field(..., description="Asistanın verdiği yanıt")
    state: int = Field(..., description="Mevcut state numarası (0-5)")
    sub_state: str = Field(..., description="State içindeki alt durum (INIT, WAITING_AISLE vb.)")
    emotion: Optional[str] = Field(None, description="Kullanıcının veya asistanın o anki duygu durumu (n8n'den gelirse)")
    source: Optional[str] = Field(None, description="Yanıtın kaynağı (rule veya llm)")
    audio_base64: Optional[str] = Field(None, description="Asistan yanıtının ses dosyası (Base64)")
