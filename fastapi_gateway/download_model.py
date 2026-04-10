from faster_whisper import WhisperModel
import logging

logging.basicConfig(level=logging.INFO)

print("="*60)
print("📥  STT Yapay Zeka Modeli İndiriliyor (Büyük Boyutlu)...")
print("İnternet kesintisi olduysa bile daha önce inen kısımdan devam edecektir.")
print("="*60)

try:
    model = WhisperModel("small", device="cuda", compute_type="int8_float16")
    print("\n✅ İNDİRME BAŞARIYLA TAMAMLANDI! Artık FastAPI'yi test edebilirsin.")
except Exception as e:
    print(f"\n❌ İndirme sırasında hata oluştu: {e}")
