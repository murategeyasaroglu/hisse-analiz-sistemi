# 📈 Otonom Hisse Etki Skoru & Analiz Paneli

BIST ve küresel hisse senetleri için canlı nicel bilanço verilerini ve niteliksel haber analizlerini birleştiren hibrit karar destek sistemi.

## 🚀 Özellikler
- **Canlı Bilanço & Fiyat Akışı:** `yfinance` entegrasyonu ile anlık BIST/Global veri çekme.
- **Dinamik Fiyat Grafiği:** Google Finans stilinde alan (area) fiyat grafiği ve dönem referans çizgileri.
- **Haber Pipeline'ı:** Google News TR & RSS üzerinden Türkçe haber çekme, özetleme ve haber etki skoru calculation.
- **Sektörel Ayrıştırma:** Reel sektör ve finansal kuruluşlar (Bankacılık vb.) için özelleştirilmiş rasyo kontrolleri.

## 🛠️ Kurulum
```bash
git clone [https://github.com/KULLANICI_ADI/hisse-analiz-sistemi.git](https://github.com/KULLANICI_ADI/hisse-analiz-sistemi.git)
cd hisse-analiz-sistemi
pip install -r requirements.txt
python -m streamlit run app.py
