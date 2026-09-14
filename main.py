"""Face2Emoji giriş noktası: bileşenleri bağlar ve web sunucusunu başlatır."""

from __future__ import annotations

import logging
import signal
import sys
import threading
from types import FrameType
from typing import Optional

from werkzeug.serving import make_server

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
    TRACK_LOST_FRAMES,
    TRACK_MAX_DISTANCE,
)
from core.camera import CameraStream
from core.face import FaceAnalyzer
from core.mapping import EmojiMapper
from core.native_logs import quiet_native_logs
from core.renderer import BubbleRenderer
from core.tracking import FaceTracker

logger = logging.getLogger("face2emoji")


def _setup_logging() -> None:
    """Kendi loglarımızı stdout'a verir, mediapipe gürültüsünü susturur."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    quiet_native_logs()


def _install_signal_handlers(shutdown: threading.Event) -> None:
    """Ctrl+C ve SIGTERM'de sunucuyu durduracak bayrağı kurar.

    Stand'de kritik: sürec temiz kapanmazsa kamera kilitli kalıyor ve bir
    sonraki başlatmada "device busy" alınıyor.
    """

    def handle(signum: int, _frame: Optional[FrameType]) -> None:
        name = signal.Signals(signum).name
        logger.info("%s alındı, kapatılıyor...", name)
        shutdown.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, handle)


def main() -> None:
    """Kamerayı ve modeli başlatır, sunucuyu çalıştırır, çıkışta kaynakları bırakır."""
    _setup_logging()

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
    tracker = FaceTracker(
        max_distance=TRACK_MAX_DISTANCE,
        lost_frames=TRACK_LOST_FRAMES,
    )
    pipeline = Pipeline(
        camera, face_analyzer, tracker, emoji_mapper, BubbleRenderer()
    )
    app = create_app(pipeline)

    shutdown = threading.Event()
    _install_signal_handlers(shutdown)

    # app.run() yerine sunucu nesnesini elde tutuyoruz: boylece sinyal
    # geldiginde shutdown() cagirip serve_forever'dan cikabiliyoruz.
    # app.run()'da KeyboardInterrupt guvenilir sekilde islenmiyordu ve surec
    # bazen kamerayi birakmadan asili kaliyordu.
    server = make_server(HOST, PORT, app, threaded=True)

    def wait_and_stop() -> None:
        shutdown.wait()
        server.shutdown()

    threading.Thread(target=wait_and_stop, name="shutdown", daemon=True).start()

    try:
        pipeline.start()
        logger.info("Hazır: http://%s:%d", HOST, PORT)
        server.serve_forever()
    finally:
        shutdown.set()
        server.server_close()
        pipeline.stop()
        logger.info("Kapatıldı, kamera serbest.")


if __name__ == "__main__":
    main()
