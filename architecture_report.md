# AI Destekli Sosyal Beceri Simülasyonu - Mimari Rapor

Bu rapor, Unity simülasyonu, FastAPI Gateway ve n8n karar motoru arasındaki entegrasyonu ve FastAPI katmanının teknik detaylarını açıklar.

## 🏗️ Genel Mimari

Sistem, düşük gecikme süreli ve esnek bir yapı sağlamak amacıyla üç katmanlı olarak tasarlanmıştır:

1.  **Unity (Frontend):** Kullanıcı etkileşimini, 3D görselleştirmeyi ve sesli/metin çıktılarını yönetir.
2.  **FastAPI (Gateway):** Unity ile n8n arasında güvenli, hızlı ve temiz bir köprü görevi görür. Veri formatlarını dönüştürür ve API standartlarını korur.
3.  **n8n (Workflow Backend):** State machine (durum makinesi), senaryo kuralları, hafıza (session) ve LLM (Groq) mantığını yürütür.

## 🔄 Veri Akışı (Data Flow)

Kullanıcının her mesajı şu döngüden geçer:

1.  **Unity**, FastAPI'ye bir `POST /chat` isteği gönderir.
2.  **FastAPI**, gelen isteği doğrular ve n8n'in beklediği formata dönüştürür (`userInput`, `sessionId`).
3.  **n8n**, mevcut durumu (state) kontrol eder, gerekiyorsa LLM'e (Groq - Llama 3) danışır ve bir dizi (array) formatında yanıt döner.
4.  **FastAPI**, n8n'den gelen dizinin ilk elemanını alır, alan adlarını Unity'nin beklediği isimlere (`text`, `state`, `sub_state`) haritalar.
5.  **Unity**, dönen yanıta göre karakteri konuşturur veya yeni bir animasyona/duruma geçer.

## 🛠️ FastAPI Gateway Detayları

-   **Endpoint:** `POST /chat`
-   **Kütüphaneler:** FastAPI, HTTPX (Async Client), Pydantic Settings.
-   **Hata Yönetimi:**
    -   n8n ulaşılamazsa: `503 Service Unavailable`
    -   n8n hata dönerse: `502 Bad Gateway`
    -   Beklenmedik format: `502 Bad Gateway` (Ayrıntılı loglama ile).

## 🚀 n8n Entegrasyon Notları

-   **Webhook URL:** `http://178.104.62.105:5678/webhook/shopping-assistant`
-   **Field Mapping:**
    -   `response` ⮕ `text`
    -   `currentState` ⮕ `state`
    -   `subState` ⮕ `sub_state`

> [!TIP]
> Mevcut n8n workflow'unda `emotion` ve `source` alanları henüz `RespondToWebhook` düğümüne dahil edilmemiştir. FastAPI bu alanları şimdilik `null` dönecek şekilde ayarlanmıştır. n8n workflow'u güncellendiğinde FastAPI herhangi bir kod değişikliği gerektirmeden bu alanları da yansıtacaktır.
