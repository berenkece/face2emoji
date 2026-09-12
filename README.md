# Face2Emoji

Kameraya bakan kişinin yüz ifadesinden hangi emojiye benzediğini bulup görüntünün yanında canlı olarak gösteren bir web uygulaması.

Üniversite yapay zeka kulübünün oryantasyon standı için yapıldı: standa gelen kişi ekrana bakıyor, gülümsediğinde yüzünün yanında 😄 beliriyor. Amaç, yüz analizinin ne olduğunu tek bakışta anlatan kısa bir demo.

## Nasıl çalışır

Kameradan gelen her kare MediaPipe FaceLandmarker modeline veriliyor; model yüzü bulup 478 landmark ve **52 blendshape katsayısı** üretiyor. Bu katsayılar (`mouthSmileLeft`, `jawOpen`, `browDownRight` gibi) mimiklerin ne kadar güçlü yapıldığını 0-1 arasında ölçüyor. Katsayılar önce üstel hareketli ortalamayla (EMA) yumuşatılıyor, sonra `config.py` içindeki basit kural listesiyle eşleştirilip bir emojiye karar veriliyor; karar birkaç kare üst üste tekrarlanmadan değişmiyor, böylece emoji titremiyor.

Kamerayı **tek bir arka plan worker thread'i** okuyor; tüm tarayıcı bağlantıları bu worker'ın yayımladığı son kareyi alıyor, dolayısıyla kaç sekme açık olursa olsun kare hızı düşmüyor. Görüntü tarayıcıya MJPEG akışı olarak (`/video`) gidiyor. Emoji karenin üzerine **çizilmiyor**: tarayıcı ayrıca `/state` uç noktasını 100 ms'de bir yoklayıp emojiyi ve yüzün normalize koordinatlarını alıyor, baloncuğu HTML/CSS ile videonun üzerine konumlandırıyor. Bu sayede emoji keskin kalıyor ve animasyonlar CSS ile yapılabiliyor.

## Ekran Görüntüsü

Yakında.

## Gereksinimler

- **Python 3.12** — 3.13 ile çalışmaz, mediapipe bu sürümü desteklemiyor.
- Webcam.
- **macOS** — proje macOS'ta (Apple Silicon) geliştirildi ve yalnızca orada test edildi. Kamera seçimi macOS'a özgü bir katman kullanıyor (`core/devices.py`). Linux/Windows'ta kurulum çalışır ama kamera seçimi denenmedi.

## Kurulum

```bash
git clone <depo-adresi>
cd face2emoji

python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Model dosyasını indirin (atlanamaz)

Model dosyası 3.7 MB olduğu için depoya dahil edilmiyor (`.gitignore`). **Bu adım atlanırsa uygulama `FileNotFoundError` ile açılmaz.**

```bash
curl -L -o models/face_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
```

Doğrulama:

```bash
shasum -a 256 models/face_landmarker.task
# 64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff
```

Modelin yolunu değiştirmek isterseniz `config.py` içindeki `FACE_MODEL_PATH` sabitini düzenleyin.

## Çalıştırma

```bash
source venv/bin/activate
python main.py
```

Ardından tarayıcıda: **http://127.0.0.1:5001**

Sunucu yalnızca `127.0.0.1` üzerinde dinler, yani aynı makineden erişilir. Adres ve port `config.py` içindeki `HOST` / `PORT` sabitlerinden değiştirilir; standda ikinci bir ekran/tablet kullanacaksanız `HOST`'u değiştirmeniz gerekir.

**Port 5000 kullanmayın.** macOS'ta AirPlay Receiver (ControlCenter) `*:5000` dinliyor ve bağlantıları kapıyor: birebir aynı kod port 5056'da 30 fps verirken port 5000'de 0 kare üretti, `/state` boş döndü. Varsayılan bu yüzden 5001.

### macOS kamera izni

İlk çalıştırmada macOS kamera izni isteyebilir. **İzin verilmezse uygulama hata vermez, siyah kare akar.** İzni sonradan vermek için:

> Sistem Ayarları > Gizlilik ve Güvenlik > Kamera

Listeden uygulamayı çalıştırdığınız programı (Terminal, iTerm, VS Code) işaretleyin ve **programı tamamen kapatıp yeniden açın** — açık bir uygulamaya verilen izin çalışırken etkinleşmez.

## Proje yapısı

Temel kural: **`core/` Flask bilmez.** Görüntü işleme ve karar mantığı web katmanından tamamen bağımsız; `core/` içindeki hiçbir modül `flask` import etmez. Bağımlılık tek yönlüdür: `app/` → `core/`. Böylece karar motoru kamera ya da sunucu olmadan test edilebilir, ve ileride aynı çekirdek farklı bir arayüzle (masaüstü penceresi, kiosk) kullanılabilir.

| Yol | Görevi |
|---|---|
| `main.py` | Giriş noktası: bileşenleri `config.py`'den okuyup kurar, sunucuyu başlatır, çıkışta kaynakları bırakır. |
| `config.py` | Tüm ayarlar ve eşikler. Kodun hiçbir yerinde sabit sayı yok. |
| `core/camera.py` | `CameraStream` — OpenCV kamera sarmalayıcısı; çözünürlük, ayna görüntüsü, ısınma kareleri, context manager. |
| `core/devices.py` | macOS'ta kameraları isimleriyle listeler, dahili Mac kamerasının OpenCV index'ini bulur; iPhone/iPad (Continuity Camera) asla otomatik seçilmez. |
| `core/face.py` | `FaceAnalyzer` — MediaPipe FaceLandmarker'ı çalıştırır; 52 blendshape ve yüz kutusunu (piksel + normalize) döndürür. |
| `core/mapping.py` | `EmojiMapper` — EMA yumuşatma, kural değerlendirme, kararlılık sayacı. Yalnızca sözlük alır; mediapipe bile import etmez. |
| `core/renderer.py` | `BubbleRenderer` — kare üzerine yüz kutusu ve blendshape debug panelini çizer. Emojiyi çizmez. |
| `core/gesture.py` | **Boş.** El/kafa hareketi tanıma için ayrılmış yer tutucu, henüz yazılmadı. |
| `app/pipeline.py` | `Pipeline` — üretici-tüketici çekirdeği: worker thread kamerayı okur, analiz eder, karar verir, çizer ve JPEG'i paylaşılan duruma yayımlar; tüketiciler bu kareyi bekleyip gönderir. Kamera kopmasında artan beklemeyle yeniden bağlanır. Flask import etmez. |
| `app/server.py` | Flask uygulaması: `/` (sayfa), `/video` (MJPEG akışı), `/state` (JSON karar + yüz konumu + `camera_ok`). |
| `app/templates/index.html` | Video ve emoji baloncuğunun ortak konumlandırma sarmalayıcısı. |
| `app/static/js/main.js` | `/state`'i 100 ms'de bir yoklar; `object-fit: contain` ile ölçeklenen görüntünün gerçek dikdörtgenini hesaplayıp baloncuğu doğru piksele koyar. |
| `app/static/css/style.css` | Baloncuk görünümü, konum geçişi, emoji değişiminde "pop" animasyonu, `prefers-reduced-motion` desteği. |

## Yapılandırma

Bütün ayarlar `config.py` içinde. Kamera çözünürlüğünden JPEG kalitesine, emoji kurallarından yumuşatma katsayısına kadar her sayı burada; başka hiçbir dosyada sabit eşik yok.

Sık kullanılanlar:

| Sabit | Ne yapar |
|---|---|
| `CAMERA_WIDTH` / `CAMERA_HEIGHT` | İstenen kamera çözünürlüğü. |
| `CAMERA_MIRROR` | Ayna görüntüsü (stand için `True` daha doğal). |
| `CAMERA_REQUIRE_BUILTIN` | `True` ise yalnızca dahili MacBook kamerası kullanılır; bulunamazsa hata verilir (telefona bağlanmaz). |
| `DEBUG_OVERLAY` | Blendshape debug panelini açar/kapatır. **Canlı sunumda `False` yapın.** |
| `WATCH_BLENDSHAPES` | Debug panelinde gösterilecek katsayılar. |
| `SMOOTHING_ALPHA` | EMA'da yeni örneğin ağırlığı. Küçültmek daha yumuşak ama daha geç tepki verir. |
| `STABILITY_FRAMES` | Emojinin değişmesi için gereken üst üste kare sayısı. Büyütmek titremeyi azaltır, gecikmeyi artırır. |
| `NUM_FACES` | Aynı anda takip edilecek yüz sayısı (şu an 1). |
| `HOST` / `PORT` | Sunucu adresi. Port 5000'den uzak durun (bkz. Çalıştırma). |
| `TARGET_FPS` | Worker'ın aşmaya çalışmadığı kare hızı. Düşürmek CPU'yu rahatlatır. |
| `CAMERA_RECONNECT_DELAYS` | Kamera koptuğunda yeniden bağlanma beklemeleri; son değer tekrarlanır. |
| `WORKER_START_TIMEOUT` | Modelin yüklenmesi için tanınan süre. |

### Yeni emoji nasıl eklenir

`EMOJI_RULES` listesine bir girdi ekleyin. Örneğin "üzgün" ifadesi:

```python
EMOJI_RULES = [
    # ... mevcut kurallar ...
    {
        "label": "uzgun",
        "emoji": "🙁",
        "conditions": [
            ("mouthFrownLeft", ">", 0.4),
            ("mouthFrownRight", ">", 0.4),
        ],
    },
]
```

Kuralların çalışma biçimi:

- Bir kuralın geçerli sayılması için **tüm** koşulları sağlanmalıdır (VE mantığı).
- Kuralın **skoru**, koşullarda geçen katsayıların ortalamasıdır. Yukarıdaki örnekte `mouthFrownLeft` 0.6 ve `mouthFrownRight` 0.5 ise skor 0.55 olur.
- Aynı anda birden çok kural geçerliyse **skoru en yüksek olan** kazanır. Bu yüzden dar kapsamlı kuralların eşiklerini yüksek tutmak, genel kuralların önüne geçmelerini sağlar.
- Hiçbir kural geçerli değilse `EMOJI_FALLBACK` (😐 `notr`) kullanılır.
- Kullanılabilir operatörler: `>`, `>=`, `<`, `<=`.
- Blendshape isimleri MediaPipe'ın verdiği isimlerle **birebir** aynı olmalıdır (büyük/küçük harf dahil). Geçerli isimlerin listesini görmek için `scratch_blendshapes.py` çalıştırın.

## Kalibrasyon

**`config.py`'deki mevcut eşikler geçicidir — tahminle konmuştur, gerçek veriyle doğrulanmamıştır.** Kimin yüzünde ne kadar iyi çalıştıkları bilinmiyor. Standa çıkmadan önce kalibrasyon yapılması gerekir.

### Örnek toplama

```bash
python scratch_calibrate.py
```

Bir pencere açılır ve canlı görüntüyü blendshape paneliyle birlikte gösterir. Bir mimiği yapın, sabit tutun ve ilgili tuşa basın:

| Tuş | Etiket |
|---|---|
| `1` | mutlu |
| `2` | saskin |
| `3` | kizgin |
| `4` | notr |
| `5` | dudak_buzme |
| `6` | goz_kirpma |
| `q` / `Esc` | Kaydet ve çık |

Her basışta o karenin **52 katsayısının tamamı** etiketiyle birlikte saklanır ve ekranda `kaydedildi: mutlu (3. ornek)` bilgisi belirir. Yüz bulunamıyorsa kayıt yapılmaz, uyarı verilir.

Aynı etiketten istediğiniz kadar örnek alın — **farklı kişiler, farklı ışık, farklı kamera açısı** ile. Standdaki koşullar geliştirme masasındakinden farklı olacağı için mümkünse standın kendi ışığında toplayın.

Çıkışta örnekler `calibration.json` dosyasına yazılır:

```json
{
  "mutlu": [ { "browDownLeft": 0.02, "mouthSmileLeft": 0.83, ... }, ... ],
  "notr":  [ { ... }, ... ]
}
```

Araç, dosya zaten varsa **üzerine ekler**; birden fazla oturumda veri toplayabilirsiniz. `calibration.json` `.gitignore` içindedir.

### Eşikleri türetme

Bu adım şu an **elle** yapılıyor; otomatik bir araç yok. `calibration.json`'ı açıp her etiket için ilgili katsayının dağılımına bakın:

1. Hedef mimikte (ör. `mutlu` → `mouthSmileLeft`) değerin **en düşük** kaçlara indiğini bulun.
2. Aynı katsayının diğer etiketlerde, özellikle `notr`'de **en yüksek** kaça çıktığını bulun.
3. Eşiği bu iki sayının arasına koyun. Aralarında boşluk yoksa o katsayı tek başına ayırt edici değildir; kurala ikinci bir koşul ekleyin.
4. Yeni eşiği `config.py`'ye yazıp `python main.py` ile deneyin.

`goz_kirpma` etiketi kalibrasyon aracında toplanabiliyor ancak `EMOJI_RULES` içinde henüz karşılığı olan bir kural yok.

## Geliştirme araçları

Kök dizindeki üç `scratch_*.py` betiği, uygulamanın tamamını çalıştırmadan tek tek parçaları denemek içindir.

| Betik | Ne işe yarar |
|---|---|
| `scratch_camera.py` | Kamerayı bir pencerede gösterir. `--list` ile kameraları isimleriyle listeler, `-s N` ile belirli bir index'i zorlar, `--no-mirror` ayna görüntüsünü kapatır. Yanlış kamera açıldığında ilk bakılacak yer. |
| `scratch_blendshapes.py` | Tek kare alır, yüzü analiz eder, kaç blendshape döndüğünü ve ilk 10'unu isim/değer olarak yazar. Model kurulumunun doğruluğunu ve geçerli katsayı isimlerini görmek için. |
| `scratch_calibrate.py` | Yukarıdaki kalibrasyon aracı. |

## Bilinen sorunlar

### mediapipe sürümü sabittir — yükseltmeyin

`mediapipe==1.0.1`, macOS arm64'te `FaceLandmarker` **oluşturulurken** native olarak çöküyor (`DrishtiMetalHelper` içinde Metal servisi bulunamıyor). Bu bir Python istisnası değil, sürecin tamamı ölüyor — `try/except` yakalayamaz. `create_from_options`, `create_from_model_path`, IMAGE ve VIDEO modları, `delegate=CPU` ve `MEDIAPIPE_DISABLE_GPU=1` denendi; hepsinde aynı sonuç.

`0.10.35` aynı model dosyasıyla sorunsuz çalışıyor ve `requirements.txt` bu sürüme sabitlenmiştir. Sürümü yükseltirseniz uygulama açılışta sessizce ölür ve hata mesajı model dosyası sorunu gibi görünür.

### Tüm izleyiciler aynı kararı paylaşır

Tek kamera, tek sahne: kamerayı yalnızca bir arka plan worker'ı okur, tüm bağlantılar aynı kareyi ve aynı emoji kararını alır. `/state` küresel tek bir karar döndürür; izleyici başına ayrı durum yoktur.

Bu **bilinçli bir tasarım kararıdır**, kısıt değil: standda kadrajda tek kişi olur ve tüm ekranların aynı şeyi göstermesi istenir. Sonucu olarak birden fazla sekme açmak akışı yavaşlatmaz — her sekme tam hızda aynı kareleri alır.

### iPhone kamerası (Continuity Camera)

macOS, yakındaki iPhone'u bir kamera olarak listeye ekler ve genellikle **index 0'a**, yani dahili kameranın önüne koyar. Proje varsayılan olarak **yalnızca dahili MacBook kamerasını** kullanır:

- `CAMERA_REQUIRE_BUILTIN = True` (varsayılan): dahili kamera bulunamazsa **hiçbir şeye düşülmez** — ne telefona, ne harici webcam'e, ne de körlemesine index 0'a. Bunun yerine `NoUsableCameraError` ile açıklayıcı bir hata verilir. Telefona yanlışlıkla bağlanmak imkansızdır.
- Kamera seçimi her `open()` çağrısında **yeniden** yapılır. Uygulama açıkken telefon menzile girip index'leri kaydırsa bile dahili kameraya bağlı kalınır.
- Hangi kameranın seçildiği log'a yazılır; seçim değişirse yeniden loglanır.

Dahili kamera bulunamadı hatası alırsanız genelde sebep, kamerayı başka bir uygulamanın (FaceTime, Zoom, Photo Booth, açık bir tarayıcı sekmesi) tutuyor olmasıdır.

Harici bir webcam kullanmak isterseniz `config.py`'de `CAMERA_REQUIRE_BUILTIN = False` yapın; o zaman sıra dahili kamera → Continuity olmayan ilk cihaz şeklinde işler (telefon yine otomatik seçilmez). Belirli bir kamerayı zorlamak için `CameraStream(source=<index>)`; index'leri görmek için `python scratch_camera.py --list`.

### Kadrajda birden fazla kişi

`NUM_FACES = 1`. Kadraja ikinci bir kişi girerse modelin hangi yüzü seçtiği garanti değildir; **emoji kişiler arasında zıplayabilir** ve yumuşatma iki farklı yüzün değerlerini karıştırabilir. Stand düzenini tek kişi kadraja girecek şekilde kurun.

### Debug paneli açık geliyor

`DEBUG_OVERLAY = True` olduğu için sol üstte blendshape katsayılarını gösteren bir panel akışın üzerine çiziliyor. Geliştirirken faydalı, **canlı sunumda kapatılmalı**: `config.py` içinde `DEBUG_OVERLAY = False`.

## Yol haritası

- **El hareketi tanıma** — `core/gesture.py` bunun için ayrılmış ama boş. El işaretlerinin (baş parmak, barış işareti) emoji kararına katılması.
- **Stand modu arayüzü** — debug öğelerinden arındırılmış, tam ekran, uzaktan okunabilir bir görünüm; kimse kadrajda yokken bekleme ekranı.
- **Çoklu izleyici desteği** — kareyi tek yerde okuyup tüm bağlantılara dağıtan bir yapı, böylece birden fazla sekme/ekran akışı yavaşlatmaz.
