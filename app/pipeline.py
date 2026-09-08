"""Kamera karelerini işleyip MJPEG akışına çeviren katman.

Bu dosya bilerek Flask'tan bağımsızdır: HTTP katmanı (app/server.py) burayı
kullanır, tersi olmaz.
"""

from __future__ import annotations

from typing import Iterator, Optional

import cv2
import numpy as np

from config import DEBUG_OVERLAY, JPEG_QUALITY, WATCH_BLENDSHAPES
from core.camera import CameraStream
from core.face import FaceAnalyzer, FaceResult
from core.mapping import EmojiDecision, EmojiMapper
from core.renderer import BubbleRenderer

Frame = np.ndarray

#: MJPEG multipart akışında kareleri ayıran sınır (server.py ile aynı olmalı).
BOUNDARY = b"frame"


class Pipeline:
    """Kameradan kare alır, işler ve MJPEG parçaları üretir."""

    def __init__(
        self,
        camera: CameraStream,
        face_analyzer: FaceAnalyzer,
        emoji_mapper: EmojiMapper,
        renderer: BubbleRenderer,
    ) -> None:
        """Pipeline'ı bileşenlerine bağlar; hiçbir kaynağı açmaz.

        Args:
            camera: Kare kaynağı olarak kullanılacak CameraStream.
            face_analyzer: Kareleri analiz edecek FaceAnalyzer.
            emoji_mapper: Blendshape'lerden emoji seçecek EmojiMapper.
            renderer: Kare üzerine çizim yapacak BubbleRenderer.
        """
        self.camera = camera
        self.face_analyzer = face_analyzer
        self.emoji_mapper = emoji_mapper
        self.renderer = renderer
        #: Son karenin analiz sonucu; diğer katmanlar buradan okuyabilir.
        self.last_face_result = FaceResult(detected=False)
        #: Son emoji kararı. Emoji kareye çizilmez; HTML katmanı buradan okur.
        self.current_decision: EmojiDecision = emoji_mapper.current

    def start(self) -> None:
        """Kamerayı açar ve yüz modelini yükler."""
        self.camera.open()
        self.face_analyzer.load()

    def process(self, frame: Frame) -> Frame:
        """Kareyi analiz eder, emoji kararını günceller ve debug öğelerini çizer.

        Emoji kareye çizilmez; yalnızca ``current_decision`` güncellenir.

        Args:
            frame: İşlenecek BGR kare.

        Returns:
            Görüntülenecek BGR kare.
        """
        self.last_face_result = self.face_analyzer.analyze(frame)
        self.current_decision = self.emoji_mapper.decide(self.last_face_result)
        frame = self.renderer.draw_face_box(frame, self.last_face_result.bbox)
        if DEBUG_OVERLAY:
            frame = self.renderer.draw_debug(
                frame, self.last_face_result.blendshapes, WATCH_BLENDSHAPES
            )
        return frame

    def encode_jpeg(self, frame: Frame) -> Optional[bytes]:
        """Kareyi JPEG baytlarına çevirir.

        Args:
            frame: Kodlanacak BGR kare.

        Returns:
            JPEG baytları, ya da kodlama başarısızsa None.
        """
        ok, buffer = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
        )
        if not ok:
            return None
        return buffer.tobytes()

    def mjpeg_frames(self) -> Iterator[bytes]:
        """İşlenmiş kareleri multipart MJPEG blokları olarak üretir.

        Yields:
            ``--frame`` sınırı, JPEG başlığı ve kare verisinden oluşan bloklar.
            Kamera akışı bitince generator sona erer.
        """
        for frame in self.camera.frames():
            jpeg = self.encode_jpeg(self.process(frame))
            if jpeg is None:
                continue
            yield (
                b"--" + BOUNDARY + b"\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            )

    def stop(self) -> None:
        """Kamerayı ve yüz modelini serbest bırakır. Birden çok kez çağrılabilir."""
        self.camera.release()
        self.face_analyzer.close()
