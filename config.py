"""Face2Emoji genel ayarları."""

from __future__ import annotations

# --- Yüz modeli ---
FACE_MODEL_PATH = "models/face_landmarker.task"
MIN_FACE_DETECTION_CONFIDENCE = 0.5
NUM_FACES = 1

# --- Kamera ---
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
CAMERA_MIRROR = True
CAMERA_WARMUP_FRAMES = 5

# --- Akış ---
JPEG_QUALITY = 80

# --- Debug ---
DEBUG_OVERLAY = True

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
EMOJI_RULES = [
    {
        "label": "mutlu",
        "emoji": "😄",
        "conditions": [
            ("mouthSmileLeft", ">", 0.4),
            ("mouthSmileRight", ">", 0.4),
        ],
    },
    {
        "label": "saskin",
        "emoji": "😲",
        "conditions": [
            ("jawOpen", ">", 0.4),
            ("browInnerUp", ">", 0.3),
        ],
    },
    {
        "label": "kizgin",
        "emoji": "😠",
        "conditions": [
            ("browDownLeft", ">", 0.4),
            ("browDownRight", ">", 0.4),
        ],
    },
    {
        "label": "dudak_buzme",
        "emoji": "😗",
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
