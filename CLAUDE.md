# CLAUDE.md — BIST Haber Analiz Uygulaması

Bu dosya projenin ana bağlam dosyasıdır. Her oturumun başında oku. Önemli bir karar değiştiğinde bu dosyayı güncelle.

## 1. Proje özeti

Borsa İstanbul hisseleriyle ilgili haberleri ve KAP bildirimlerini otomatik olarak toplayan, **yerel bir LLM ile analiz eden** ve sonuçları bir mobil uygulamada gösteren bir sistem.

- **Amaç:** Portföy projesi. Hedef roller quant/algo trading ve AI engineer. Kod kalitesi, mimari ve README, mülakatta gösterilecek seviyede olmalı.
- **Kullanıcı:** Sadece Bora (kişisel kullanım). Uygulama kamuya yayınlanmayacak.
- **Dil:** Uygulama arayüzü ve analiz çıktıları Türkçe. Kod, değişken isimleri ve commit mesajları İngilizce.

## 2. Kesin kurallar (ihlal etme)

1. **Sıfır bütçe.** Ücretli API, ücretli veri kaynağı ya da ücretli bulut servisi kullanılmayacak. Tüm AI işlemleri yerelde Ollama ile çalışacak.
2. **Al/sat sinyali yok.** Uygulama yatırım tavsiyesi vermez. Çıktılarda "al", "sat", "tut", "hedef fiyat", "kesin yükselir" gibi ifadeler bulunmayacak. Analiz betimleyici olmalı: ne oldu, neden önemli olabilir, hangi göstergelerle ilgili. Bu kuralı prompt'a ek olarak kod seviyesinde bir post-processing filtresiyle de uygula.
3. **Sayıları LLM üretmez.** Finansal oranlar ve tüm hesaplamalar deterministik olarak kodla yapılır. LLM sadece sınıflandırır, özetler ve yorumlar.
4. **Kaynaklara saygı.** KAP ve haber sitelerine düşük frekansla, cache kullanarak istek at (rate limit ve User-Agent ayarla). Haberlerin tam metni saklanmaz ve gösterilmez. Sadece başlık, kaynak, tarih, link ve kendi ürettiğimiz özet tutulur.
5. **Her haber bir kez analiz edilir.** Sonuç veritabanına yazılır. Aynı haber için LLM'e tekrar gidilmez.

## 3. Geliştirme ortamı

- OS: Ubuntu 24.04 (makine adı `boraPC`, kullanıcı `bora`)
- CPU: AMD Ryzen 7 5700X
- GPU: **RTX 3050, 6 GB VRAM** (masaüstü ve tarayıcı yaklaşık 450 MB kullanıyor, LLM için yaklaşık 5.5 GB kalıyor)
- Driver 595.84, CUDA 13.2
- IDE: Cursor + Claude Code
- GitHub: CagilciBora
- Araçlar: Python 3.12.3, uv 0.11, Docker 29 + Compose v2, Node 22, Ollama 0.40 (host üzerinde, systemd servisi)

## 4. Claude modelleri (Bora için not)

Claude kendi modelini değiştiremez, geçişi Bora `/model` ile yapar. Claude, uygun anlarda Bora'ya hatırlatma yapmalı.

- **Opus 5.5:** Plan modu, mimari kararlar, veri modeli tasarımı, zor bug'lar, faz sonu kod review'ları.
- **Sonnet 5.5:** Plan onaylandıktan sonra uygulama işleri: CRUD, endpoint'ler, ekranlar, testler, küçük düzeltmeler.
- Kullanım limiti (`/usage`) dolmaya yaklaşırsa rutin işler Sonnet'e kaydırılır.
- Kotayı korumak için: her faz için yeni oturum aç, oturum uzarsa `/compact` kullan, gereksiz yere bütün repo'yu baştan okuma.

## 5. Yerel LLM stratejisi (6 GB VRAM)

- **Runtime:** Ollama, Docker'da değil doğrudan host üzerinde çalışacak (GPU erişimi daha basit).
- **Birincil aday:** `qwen3.5:4b-q4_K_M` (3.3 GB, tamamen GPU'ya sığar). Qwen3.5 düşünme (thinking) modu destekler; API çağrılarında `think: false` gönderilir.
- **İkincil aday:** `gemma4:e4b-it-q4_K_M` (6.6 GB, bir kısmı CPU'ya kayar). Farklı model ailesi, güçlü çok dilli destek. Gece çalışan toplu işler için kabul edilebilir hız.
- (Seçim Faz 0'da, Ekim 2026 itibarıyla ollama.com/library üzerinden kontrol edilerek yapıldı.)
- **Faz 0 smoke test gözlemleri (3 başlık, `format`=JSON schema, `think:false`, temperature 0):**
  - Her iki model 3/3 geçerli JSON üretti. Qwen ~39 tok/s, %100 GPU. Gemma ~47-55 tok/s. Soğuk başlatma qwen 54 sn, gemma 26 sn, sonrası 2-5 sn/haber.
  - Qwen temettü haberini `finansal_sonuc` olarak etiketledi; Gemma THY yolcu artışını `yeni_is_sozlesme` olarak etiketledi. İkisi de `related_metrics`'i hep boş bıraktı. Faz 3'te prompt'a konu tanımları ve few-shot örnekleri eklenecek.
  - Qwen, başlıkta olmayan çıkarımlar yaptı (ör. "nakit akışının sağlıklı olduğunu gösterir"). Prompt'ta "başlıkta olmayan bilgiyi ekleme" vurgulanmalı.
  - Gemma4 için `/api/ps` ve `ollama ps` VRAM'i yanlış (250 MB) raporluyor. VRAM ölçümü `nvidia-smi` ile yapılmalı (gemma yüklüyken ~4.5 GB).
- `num_ctx` değerini 4096 civarında tut (VRAM tasarrufu).
- Yapılandırılmış çıktı için Ollama'nın JSON schema / `format` desteğini kullan, sonucu Pydantic ile doğrula. Geçersiz çıktıda bir kez retry yap, yine başarısız olursa kural tabanlı analyzer'a düş.
- Model seçimi ölçümle yapılacak: Bora'nın etiketlediği yaklaşık 20-30 haberlik küçük bir değerlendirme seti hazırla ve iki modeli doğruluk ve hız açısından karşılaştır. Sonuçlar README'ye girecek.

## 6. Mimari

```
[RSS / KAP kaynakları] --> [Collector (zamanlanmış)] --> [PostgreSQL]
                                                           |
                       [Analyzer worker] <-----------------+
                       (RuleBased | Ollama)                |
                                                           v
                                    [FastAPI REST API] --> [Expo mobil uygulama]
```

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, httpx, feedparser, APScheduler
- **Veritabanı:** PostgreSQL (Docker Compose ile)
- **Mobil:** Expo (React Native + TypeScript). Telefonda Expo Go ile, aynı ağ üzerinden backend'e bağlanılarak test edilir.
- **Test:** pytest. Collector ve analyzer için birim testleri, dış kaynaklar mock'lanarak.
- **Konfigürasyon:** `.env` dosyası (repo'ya girmez), `.env.example` dosyası (repo'ya girer)

### Onaylanmış mimari kararlar

- **İki süreç:** `api` (FastAPI) ve `worker` (APScheduler: collector, analiz, gece raporu job'ları). Scheduler API içine gömülmez.
- **Testler gerçek Postgres'te:** Compose içindeki ayrı `bist_test` veritabanı (JSONB/ARRAY nedeniyle SQLite yok). Dış kaynaklar (RSS, KAP, Ollama) mock'lanır; Ollama'ya gerçekten giden testler `@pytest.mark.ollama` ile işaretlenir ve varsayılan olarak atlanır.
- **Bağımlılık yönetimi:** `uv` (`backend/pyproject.toml` + `uv.lock`).
- **KAP collector ayrı alt faz (2b).**
- **Yasaklı ifade filtresi** (`app/analyzers/safety_filter.py`) her analyzer çıktısına uygulanır.

### Repo yapısı

```
financemobile/
├── CLAUDE.md, README.md, .env.example, docker-compose.yml
├── backend/
│   ├── app/{core,models,schemas,collectors,analyzers,workers,api}/
│   ├── alembic/
│   ├── scripts/        # seed_stocks, ollama_smoke_test
│   ├── config/         # stocks.yaml
│   └── tests/
├── mobile/             # Expo + TypeScript
└── eval/               # etiketli set + model karşılaştırma
```

### Analyzer arayüzü

```python
class Analyzer(Protocol):
    name: str
    def analyze_news(self, item: NewsItem, stock: Stock) -> NewsAnalysis: ...
    def summarize_stock(self, stock: Stock, items: list[NewsItem], period_days: int) -> StockReport: ...
```

Implementasyonlar: `RuleBasedAnalyzer` (anahtar kelime ve KAP bildirim türü bazlı) ve `OllamaAnalyzer`. İleride bir API tabanlı analyzer eklenebilecek şekilde tasarla ama şimdi yazma.

### Haber analizi çıktı şeması

- `topic`: finansal_sonuc | temettu | sermaye_artirimi | yeni_is_sozlesme | yatirim | yonetim_degisikligi | hukuki | sektorel | makro | diger
- `summary`: 2-3 cümlelik Türkçe özet
- `why_it_matters`: şirket açısından neden önemli olabileceği (1-2 cümle)
- `related_metrics`: ilgili göstergeler listesi (ör. ciro, net kâr, borçluluk, temettü verimi)
- `tone`: olumlu | olumsuz | nötr | belirsiz (betimleyici, sinyal değil)
- `relevance`: 0-1 arası, haberin bu hisseyle gerçekten ne kadar ilgili olduğu

### Dönemsel hisse raporu

Gece çalışan bir job, her hisse için son N günün (varsayılan 7) analiz edilmiş haberlerini toplayıp kısa bir "dönem özeti" üretir: öne çıkan gelişmeler, konu dağılımı, ton dağılımı. Bu rapor da tek sefer üretilip saklanır.

## 7. Veri kaynakları

- **Google News RSS (tr):** Hisse kodu ve şirket adıyla sorgulanır. Başlık, kaynak, tarih ve link alınır.
- **KAP (kap.org.tr):** Resmi REST API ücretli yetkilendirme gerektirdiği için kullanılmayacak. Kamuya açık sayfalardan düşük frekanslı, cache'li erişim yapılacak. Bildirim türü bilgisi rule-based sınıflandırmada kullanılacak.
- **Fiyat verisi (opsiyonel, sonraki faz):** Sadece kişisel kullanım için yfinance (`.IS` uzantılı semboller).

## 8. Veri modeli (ilk taslak)

- `stocks`: id, ticker, name, aliases (dizi), sector, is_active
- `news_items`: id, source_type (rss | kap), source_name, url (unique), title, published_at, fetched_at, content_hash, kap_disclosure_type (nullable)
- `news_stock_links`: news_id, stock_id, match_method (ticker | alias | kap), match_score
- `news_analyses`: id, news_id, stock_id, analyzer_name, model_name, result (JSONB), created_at, unique (news_id, stock_id, analyzer_name)
- `stock_reports`: id, stock_id, period_start, period_end, analyzer_name, model_name, result (JSONB), created_at

## 9. Fazlar

Her fazın sonunda: testler geçer, kısa bir durum raporu verilir, anlamlı commit'ler atılmış olur.

**Faz 0 — Kurulum**
Repo iskeleti, Docker Compose ile Postgres, Alembic, `.env.example`, Ollama kurulumu ve iki aday modelin çekilmesi, basit bir Ollama smoke test (Türkçe bir haber başlığını JSON şemaya göre sınıflandırma). Kabul kriteri: `docker compose up` ve smoke test çalışıyor.

**Faz 1 — Hisse tablosu**
Seed script. Başlangıç listesi: THYAO, ASELS, GARAN, AKBNK, BIMAS, EREGL, KCHOL, SISE, TUPRS, FROTO. Her hisse için şirket adı ve yaygın alternatif isimler (ör. THYAO için "Türk Hava Yolları" ve "THY"). Liste config'den genişletilebilir olmalı.

**Faz 2 — Haber toplayıcı**
RSS collector, duplicate tespiti (URL ve content hash), hisse eşleştirme (ticker, alias, kelime sınırı kontrolüyle). KAP collector ayrı alt faz (2b). APScheduler ile periyodik çalışma. Kabul kriteri: 10 hisse için haberler veritabanına düşüyor, duplicate yok.

**Faz 3 — Analiz katmanı**
`RuleBasedAnalyzer` ve `OllamaAnalyzer`, yasaklı ifade filtresi, analiz edilmemiş haberleri işleyen worker. Kabul kriteri: yeni haberler otomatik analiz ediliyor, geçersiz LLM çıktısı sistemi çökertmiyor.

**Faz 4 — REST API**
Endpoint'ler: hisse listesi, hisse detayı, hisseye ait haber akışı (analizleriyle birlikte), dönem raporu. Sayfalama ve OpenAPI dokümantasyonu.

**Faz 5 — Mobil uygulama**
Expo + TypeScript. Ekranlar: hisse listesi, hisse detayı (dönem özeti + haber akışı), haber detayı (özet, neden önemli, ton, kaynağa link). Her ekranda "Yatırım tavsiyesi değildir, bilgilendirme amaçlıdır" notu.

**Faz 6 — Dönemsel raporlar**
Gece çalışan hisse raporu job'u ve mobilde gösterimi.

**Faz 7 — Değerlendirme ve cila**
Model karşılaştırma değerlendirme seti, README (mimari diyagram, kurulum, ekran görüntüleri, model karşılaştırma sonuçları, tasarım kararları), kod temizliği.

**Sonraki fikirler (şimdi yapma):** KAP finansal tablolarından oran hesaplama, haberleri finansal metriklerle ilişkilendirme, fiyat grafiği.

## 10. Çalışma şekli

- Bora hızlı ilerlemek istiyor. Genel planı **bir kez** Bora'ya onaylat, sonra fazları sırayla ilerlet. Her küçük adımda onay isteme. Sadece mimariyi değiştiren ya da geri alınması zor kararlarda dur ve sor.
- Her faz sonunda 3-5 cümlelik bir durum raporu ver: ne yapıldı, nasıl test edilir, sırada ne var.
- Komutları ve çıktıları açıkla. Bora'nın çalıştırması gereken bir şey varsa (ör. `ollama pull`, telefonda Expo Go) bunu açıkça belirt.
- Bir kütüphanenin ya da modelin güncel sürümünden emin değilsen varsayma, kontrol et.
- Gizli bilgileri (şifre, token) asla commit etme.
- Bu dosyayı güncel tut: biten fazları işaretle, değişen kararları yaz.

## 11. Durum

Genel plan onaylandı (2026-10-07).

- [x] Faz 0 — Kurulum (2026-10-07)
- [x] Faz 1 — Hisse tablosu (2026-10-07). Liste `backend/config/stocks.yaml`; `scripts/seed_stocks.py` ticker'a göre upsert yapar, listeden çıkarılan hisseyi silmez (`is_active: false` ile kapatılır). Alias'lara ASCII varyantlar (Tupras, Sisecam) eklenmedi: Faz 2'de eşleştirme casefold + diakritik normalizasyonu ile yapılacak.
- [ ] Faz 2 — Haber toplayıcı (2a RSS, 2b KAP)
- [ ] Faz 3 — Analiz katmanı
- [ ] Faz 4 — REST API
- [ ] Faz 5 — Mobil uygulama
- [ ] Faz 6 — Dönemsel raporlar
- [ ] Faz 7 — Değerlendirme ve cila
