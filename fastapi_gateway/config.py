from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    N8N_WEBHOOK_URL: str = "http://178.104.62.105:5678/webhook/shopping-assistant"
    N8N_TIMEOUT_SECONDS: float = 30.0
    
    # STT & TTS Settings
    GROQ_API_KEY: str  # .env dosyasından okunur
    DEEPGRAM_API_KEY: str # .env
    TTS_VOICE: str = "tr-TR-AhmetNeural"  # Alternatif: tr-TR-EmelNeural
    TTS_RATE: str = "+25%"  # Konuşma hızı: +0%=normal, +25%=hızlı, +50%=çok hızlı
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
