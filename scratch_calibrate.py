"""Kalibrasyon aracı: mimikleri etiketleyip blendshape örnekleri toplar.

Canlı görüntüyü debug paneliyle gösterir. Bir mimik yapıp ilgili tuşa basınca
o karenin 52 blendshape katsayısı etiketiyle kaydedilir. 'q' ile çıkışta tüm
örnekler calibration.json dosyasına yazılır.

Çalıştırma:
    python scratch_calibrate.py
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, List

import cv2

from config import (
    CAMERA_HEIGHT,
    CAMERA_MIRROR,
    CAMERA_WARMUP_FRAMES,
    CAMERA_WIDTH,
    FACE_MODEL_PATH,
    MIN_FACE_DETECTION_CONFIDENCE,
    NUM_FACES,
    WATCH_BLENDSHAPES,
)
from core.camera import CameraStream
from core.face import FaceAnalyzer
from core.renderer import BubbleRenderer

WINDOW = "Face2Emoji - kalibrasyon"
OUTPUT_PATH = "calibration.json"

#: Tuş -> etiket eşlemesi.
LABELS: Dict[str, str] = {
    "1": "mutlu",
    "2": "saskin",
    "3": "kizgin",
    "4": "notr",
    "5": "dudak_buzme",
    "6": "goz_kirpma",
}

#: Kaydedildi bilgisinin ekranda kalma süresi (saniye).
TOAST_SECONDS = 1.5

#: cv2.putText ASCII cizdigi icin ekran metinleri ASCII.
HINT = "1 mutlu  2 saskin  3 kizgin  4 notr  5 dudak  6 goz  |  q cikis"

Samples = Dict[str, List[Dict[str, float]]]


def load_existing(path: str) -> Samples:
    """Varsa önceki örnekleri okur, böylece yeni oturum üzerine ekler.

    Args:
        path: calibration.json yolu.

    Returns:
        Etiket -> örnek listesi sözlüğü; dosya yoksa ya da bozuksa boş sözlük.
    """
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Uyari: {path} okunamadi ({error}); sifirdan baslaniyor.")
        return {}
    return {label: list(items) for label, items in data.items()}


def save(path: str, samples: Samples) -> None:
    """Tüm örnekleri JSON olarak yazar.

    Args:
        path: Yazılacak dosya yolu.
        samples: Etiket -> 52 katsayılık örnek listesi.
    """
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(samples, handle, ensure_ascii=False, indent=2)


def draw_hud(frame, message: str) -> None:
    """Tuş yardımını ve son kayıt bilgisini karenin altına yazar."""
    height = frame.shape[0]
    cv2.putText(
        frame, HINT, (12, height - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
        (235, 235, 235), 1, cv2.LINE_AA,
    )
    if message:
        cv2.putText(
            frame, message, (12, height - 44), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
            (90, 225, 130), 2, cv2.LINE_AA,
        )


def main() -> None:
    """Kalibrasyon döngüsünü çalıştırır ve örnekleri diske yazar."""
    samples = load_existing(OUTPUT_PATH)
    if samples:
        total = sum(len(v) for v in samples.values())
        print(f"{OUTPUT_PATH} icinde {total} mevcut ornek bulundu, uzerine eklenecek.")

    analyzer = FaceAnalyzer(
        model_path=FACE_MODEL_PATH,
        num_faces=NUM_FACES,
        min_confidence=MIN_FACE_DETECTION_CONFIDENCE,
    )
    analyzer.load()
    renderer = BubbleRenderer()
    message = ""
    message_until = 0.0

    try:
        with CameraStream(
            width=CAMERA_WIDTH,
            height=CAMERA_HEIGHT,
            mirror=CAMERA_MIRROR,
            warmup_frames=CAMERA_WARMUP_FRAMES,
        ) as camera:
            cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
            for frame in camera.frames():
                faces = analyzer.analyze(frame)
                # Kalibrasyon tek kisilik: ornek EN BUYUK yuzden alinir ki
                # arkadan gecen biri kaydi kirletmesin.
                result = (
                    max(faces, key=lambda f: f.bbox[2] * f.bbox[3])
                    if faces
                    else None
                )
                renderer.draw_face_box(frame, [f.bbox for f in faces])
                renderer.draw_debug(frame, faces, WATCH_BLENDSHAPES)

                if time.monotonic() > message_until:
                    message = ""
                draw_hud(frame, message)
                cv2.imshow(WINDOW, frame)

                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break

                label = LABELS.get(chr(key)) if key != 255 else None
                if label is None:
                    continue

                if result is None:
                    message = "yuz yok - kaydedilmedi"
                    print("Yuz bulunamadi, ornek kaydedilmedi.")
                else:
                    samples.setdefault(label, []).append(dict(result.blendshapes))
                    count = len(samples[label])
                    message = f"kaydedildi: {label} ({count}. ornek)"
                    print(f"kaydedildi: {label} ({count}. ornek)")
                message_until = time.monotonic() + TOAST_SECONDS
    finally:
        analyzer.close()
        cv2.destroyAllWindows()
        save(OUTPUT_PATH, samples)
        total = sum(len(v) for v in samples.values())
        breakdown = ", ".join(f"{k}: {len(v)}" for k, v in sorted(samples.items()))
        print(f"\n{OUTPUT_PATH} yazildi - toplam {total} ornek ({breakdown or 'bos'})")


if __name__ == "__main__":
    main()
