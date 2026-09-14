"""Task 4 ön kontrolü: tek karede kaç blendshape döndüğünü gösterir.

Çalıştırma:
    python scratch_blendshapes.py
"""

from __future__ import annotations

from config import (
    CAMERA_HEIGHT,
    CAMERA_MIRROR,
    CAMERA_WIDTH,
    FACE_MODEL_PATH,
    MIN_FACE_DETECTION_CONFIDENCE,
    NUM_FACES,
)
from core.camera import CameraStream
from core.face import FaceAnalyzer

TOP_N = 10


def main() -> None:
    """Kameradan tek kare alır, analiz eder ve ilk blendshape'leri yazdırır."""
    analyzer = FaceAnalyzer(
        model_path=FACE_MODEL_PATH,
        num_faces=NUM_FACES,
        min_confidence=MIN_FACE_DETECTION_CONFIDENCE,
    )
    analyzer.load()
    try:
        with CameraStream(
            width=CAMERA_WIDTH, height=CAMERA_HEIGHT, mirror=CAMERA_MIRROR
        ) as camera:
            frame = camera.read()

        if frame is None:
            print("Kameradan kare alinamadi.")
            return

        faces = analyzer.analyze(frame)
        print(f"kare: {frame.shape[1]}x{frame.shape[0]}")
        print(f"bulunan yuz sayisi: {len(faces)}")
        if not faces:
            print("Yuz yok - kameraya bakip tekrar deneyin.")
            return

        # Bu arac tek kisilik kullanim icin: en buyuk yuzu gosterir.
        result = max(faces, key=lambda f: f.bbox[2] * f.bbox[3])
        if len(faces) > 1:
            print("(birden fazla yuz var; en buyugu gosteriliyor)")

        print(f"bbox (x, y, w, h): {result.bbox}")
        print(f"blendshape sayisi: {len(result.blendshapes)}")
        print(f"--- ilk {TOP_N} blendshape ---")
        for name, score in list(result.blendshapes.items())[:TOP_N]:
            print(f"  {name:<28} {score:.4f}")
    finally:
        analyzer.close()


if __name__ == "__main__":
    main()
