"""Face2Emoji genel ayarları."""

from __future__ import annotations

# --- Yüz modeli ---
FACE_MODEL_PATH = "models/face_landmarker.task"
MIN_FACE_DETECTION_CONFIDENCE = 0.5
NUM_FACES = 4

# --- Yuz takibi (kimlik eslestirme) ---
#: Bir yuzun onceki karedeki kimlige atanabilmesi icin merkezler arasindaki
#: en buyuk mesafe (normalize 0-1 koordinatta). Buyutmek hizli hareketi
#: tolere eder ama yakin duran kisilerin kimliklerini karistirabilir.
TRACK_MAX_DISTANCE = 0.15

#: Bir kimlik bu kadar kare ust uste gorunmezse dusurulur ve durumu silinir.
TRACK_LOST_FRAMES = 15

# --- Kamera ---
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_MIRROR = True
CAMERA_WARMUP_FRAMES = 5

#: True ise YALNIZCA dahili Mac kamerasi kullanilir. Dahili kamera
#: bulunamazsa (iPhone Continuity Camera, harici webcam ya da cihaz listesi
#: okunamamasi fark etmez) baska bir kameraya DUSULMEZ; acik bir hata verilir.
#: Telefon kamerasina yanlislikla baglanmayi tamamen imkansiz kilar.
#: macOS disinda calistiracaksaniz False yapin (cihaz listesi okunamaz).
CAMERA_REQUIRE_BUILTIN = True

# --- Akış ---
JPEG_QUALITY = 80

# --- Debug ---
#: Blendshape panelini kareye cizer. Stand sunumunda KAPALI olmali;
#: esik ayari yaparken True yapin.
DEBUG_OVERLAY = False

#: Debug panelinde izlenecek blendshape'ler (52 katsayıdan seçili olanlar).
WATCH_BLENDSHAPES = [
    "mouthSmileLeft",
    "mouthSmileRight",
    "mouthFrownLeft",
    "mouthFrownRight",
    "mouthPucker",
    "jawOpen",
    "browInnerUp",
    "browDownLeft",
    "browDownRight",
    "eyeSquintLeft",
    "eyeWideLeft",
    "cheekPuff",
]

# --- Emoji karar motoru ---
# NOT: Buradaki esikler GECICIDIR. scratch_calibrate.py ile toplanan gercek
# kalibrasyon verisi geldiginde bu sayilar guncellenecek. Tum esikler bilerek
# tek yerde: kodda hicbir yerde sabit esik yok.

#: Kurallar sirayla degerlendirilir; tum kosullari saglayanlar arasindan
#: skoru en yuksek olan kazanir. Kosul: (blendshape adi, operator, esik).
#:
#: "hint" opsiyoneldir: stand ekranindaki ipucu seridinde gosterilen, ziyaretciye
#: NE YAPACAGINI soyleyen kisa Turkce metin. Verilmezse "label" kullanilir.
#: Serit bu listeden otomatik uretilir -- yeni kural eklendiginde kendiliginden
#: gorunur, ayrica elle guncellenmesi gereken bir yer yoktur.
EMOJI_RULES = [
    {
        "label": "mutlu",
        "emoji": "😄",
        "hint": "gülümse",
        "conditions": [
            ("mouthSmileLeft", ">", 0.4),
            ("mouthSmileRight", ">", 0.4),
        ],
    },
    {
        "label": "saskin",
        "emoji": "😲",
        "hint": "şaşır",
        "conditions": [
            ("jawOpen", ">", 0.4),
            ("browInnerUp", ">", 0.3),
        ],
    },
    {
        "label": "kizgin",
        "emoji": "😠",
        "hint": "kaşlarını çat",
        "conditions": [
            ("browDownLeft", ">", 0.4),
            ("browDownRight", ">", 0.4),
        ],
    },
    {
        "label": "dudak_buzme",
        "emoji": "😗",
        "hint": "dudak büz",
        "conditions": [
            ("mouthPucker", ">", 0.5),
        ],
    },
]

#: Hicbir kural gecerli degilse kullanilan karar.
EMOJI_FALLBACK = {"label": "notr", "emoji": "😐"}

#: EMA yumusatma katsayisi: yeni orneklerin agirligi (1.0 = yumusatma yok).
SMOOTHING_ALPHA = 0.6

#: Yeni bir kazananin karari degistirmesi icin gereken ust uste kare sayisi.
STABILITY_FRAMES = 4

# --- Sunucu ---
HOST = "127.0.0.1"

#: DIKKAT: port 5000 macOS'ta AirPlay Receiver (ControlCenter) tarafindan
#: dinleniyor ve baglantilari kapiyor -- olculdu: ayni kod 5056'da 30 fps,
#: 5000'de 0 kare. Bu yuzden varsayilan 5001. AirPlay'i kapatirsaniz
#: 5000'e donebilirsiniz.
PORT = 5001

# --- Worker (uretici-tuketici) ---
#: Worker bu kare hizini asmaya calismaz; bosuna CPU yakmasin.
TARGET_FPS = 30

#: start() modelin yuklenmesini bu kadar bekler. Bilerek comert: ilk yukleme
#: yavas olabilir ve dar bir timeout acilista sahte hata uretir.
WORKER_START_TIMEOUT = 30.0

#: stop() worker'in bitmesini bu kadar bekler.
WORKER_STOP_TIMEOUT = 5.0

#: Tuketici bu araliklarla uyanip durdurma bayragini kontrol eder.
CONSUMER_WAIT_TIMEOUT = 1.0

#: Kamera kopunca yeniden baglanma gecikmeleri; son deger tekrarlanir.
CAMERA_RECONNECT_DELAYS = (0.5, 1.0, 2.0, 5.0)
