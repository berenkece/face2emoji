"""Face2Emoji giriş noktası: bileşenleri bağlar ve web sunucusunu başlatır."""

from __future__ import annotations

import logging

from app.pipeline import Pipeline
from app.server import create_app
from config import (
    CAMERA_HEIGHT,
    CAMERA_MIRROR,
    CAMERA_WARMUP_FRAMES,
    CAMERA_WIDTH,
    EMOJI_FALLBACK,
    EMOJI_RULES,
    FACE_MODEL_PATH,
    HOST,
    MIN_FACE_DETECTION_CONFIDENCE,
    NUM_FACES,
    PORT,
    SMOOTHING_ALPHA,
    STABILITY_FRAMES,
)
from core.camera import CameraStream
from core.face import FaceAnalyzer
from core.mapping import EmojiMapper
from core.renderer import BubbleRenderer


def main() -> None:
    """Kamerayı ve modeli başlatır, sunucuyu çalıştırır, çıkışta kaynakları bırakır."""
    # Worker'in yeniden baglanma ve kamera secimi mesajlari gorunsun.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    camera = CameraStream(
        width=CAMERA_WIDTH,
        height=CAMERA_HEIGHT,
        mirror=CAMERA_MIRROR,
        warmup_frames=CAMERA_WARMUP_FRAMES,
    )
    face_analyzer = FaceAnalyzer(
        model_path=FACE_MODEL_PATH,
        num_faces=NUM_FACES,
        min_confidence=MIN_FACE_DETECTION_CONFIDENCE,
    )
    emoji_mapper = EmojiMapper(
        rules=EMOJI_RULES,
        fallback=EMOJI_FALLBACK,
        alpha=SMOOTHING_ALPHA,
        stability_frames=STABILITY_FRAMES,
    )
    pipeline = Pipeline(camera, face_analyzer, emoji_mapper, BubbleRenderer())
    app = create_app(pipeline)

    try:
        # start() modelin yuklenmesini bekler; hata olursa burada firlar.
        pipeline.start()
        # use_reloader=False sart: reloader ikinci bir surec baslatir ve
        # kamera iki kez acilmaya calisilir.
        app.run(
            host=HOST,
            port=PORT,
            threaded=True,
            debug=False,
            use_reloader=False,
        )
    finally:
        pipeline.stop()


if __name__ == "__main__":
    main()
