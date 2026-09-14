"""MediaPipe FaceLandmarker ile yüz tespiti ve blendshape çıkarımı.

Bu dosya bilerek Flask'tan bağımsızdır.

Kurulu mediapipe 0.10.35'te doğrulanmış API isimleri:
``mediapipe.tasks.python.vision.FaceLandmarker`` / ``FaceLandmarkerOptions`` /
``RunningMode`` (IMAGE, VIDEO, LIVE_STREAM).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

Frame = np.ndarray
BBox = Tuple[int, int, int, int]
NormBBox = Tuple[float, float, float, float]


@dataclass
class FaceResult:
    """Tek bir karenin yüz analizi sonucu."""

    detected: bool
    blendshapes: Dict[str, float] = field(default_factory=dict)
    bbox: Optional[BBox] = None  # piksel cinsinden (x, y, w, h)
    bbox_norm: Optional[NormBBox] = None  # 0..1 aralığında (x, y, w, h)


class FaceAnalyzer:
    """Kareleri MediaPipe FaceLandmarker ile analiz eder."""

    def __init__(
        self,
        model_path: str,
        num_faces: int = 1,
        min_confidence: float = 0.5,
    ) -> None:
        """Analizciyi yapılandırır; model yüklenmez, bunun için load() çağrılmalı.

        Args:
            model_path: ``.task`` model paketinin yolu.
            num_faces: Aynı anda takip edilecek en fazla yüz sayısı.
            min_confidence: Yüz tespiti için en düşük güven skoru.
        """
        self.model_path = model_path
        self.num_faces = num_faces
        self.min_confidence = min_confidence
        self._landmarker: Optional[vision.FaceLandmarker] = None
        self._last_timestamp_ms: int = -1

    def load(self) -> "FaceAnalyzer":
        """Modeli VIDEO modunda, blendshape çıktısı açık olarak yükler.

        Returns:
            Zincirleme kullanım için self.

        Raises:
            FileNotFoundError: Model dosyası bulunamazsa.
        """
        if self._landmarker is not None:
            return self

        if not os.path.isfile(self.model_path):
            raise FileNotFoundError(
                f"Yüz modeli bulunamadı: {self.model_path!r}. "
                "MediaPipe FaceLandmarker paketini (face_landmarker.task) indirip "
                "bu yola koyun; dosya yaklaşık 3.7 MB'dir. Yolu config.py içindeki "
                "FACE_MODEL_PATH ile değiştirebilirsiniz."
            )

        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=self.model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=self.num_faces,
            min_face_detection_confidence=self.min_confidence,
            output_face_blendshapes=True,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        return self

    def _next_timestamp_ms(self) -> int:
        """Kesin olarak artan bir zaman damgası (ms) üretir.

        detect_for_video aynı ya da geriye giden damgayı reddeder; monotonic saat
        aynı milisaniyeyi iki kez verirse damgayı bir artırarak ilerletiyoruz.
        """
        now_ms = time.monotonic_ns() // 1_000_000
        timestamp = max(now_ms, self._last_timestamp_ms + 1)
        self._last_timestamp_ms = timestamp
        return timestamp

    def analyze(self, frame_bgr: Frame) -> List[FaceResult]:
        """Bir karedeki tüm yüzleri analiz eder.

        En fazla ``num_faces`` yüz döndürülür. MediaPipe yüzleri her karede
        aynı sırayla vermeyebilir; kimlik eşleştirmesi core.tracking'in işidir.

        Args:
            frame_bgr: Analiz edilecek BGR kare.

        Returns:
            Her yüz için bir FaceResult (kendi blendshape'leri ve bbox'ıyla).
            Yüz yoksa **boş liste**.

        Raises:
            RuntimeError: load() çağrılmadan kullanılırsa.
        """
        if self._landmarker is None:
            raise RuntimeError("FaceAnalyzer.load() önce çağrılmalı.")

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(image, self._next_timestamp_ms())

        if not result.face_landmarks:
            return []

        height, width = frame_bgr.shape[:2]
        all_blendshapes = result.face_blendshapes or []

        faces: List[FaceResult] = []
        for index, landmarks in enumerate(result.face_landmarks):
            blendshapes: Dict[str, float] = {}
            if index < len(all_blendshapes):
                blendshapes = {
                    category.category_name: float(category.score)
                    for category in all_blendshapes[index]
                }

            bbox_norm = _landmarks_to_bbox_norm(landmarks)
            faces.append(
                FaceResult(
                    detected=True,
                    blendshapes=blendshapes,
                    bbox=_norm_bbox_to_pixels(bbox_norm, width, height),
                    bbox_norm=bbox_norm,
                )
            )
        return faces

    def close(self) -> None:
        """Modeli serbest bırakır. Birden çok kez çağrılabilir."""
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None


def _landmarks_to_bbox_norm(landmarks) -> NormBBox:
    """Landmark'ların min/max'inden 0..1 aralığında bbox üretir.

    Args:
        landmarks: Normalize (0-1) x/y taşıyan landmark dizisi.

    Returns:
        0..1 aralığına kırpılmış (x, y, w, h).
    """
    xs = [lm.x for lm in landmarks]
    ys = [lm.y for lm in landmarks]

    x_min = _clamp01(min(xs))
    y_min = _clamp01(min(ys))
    x_max = _clamp01(max(xs))
    y_max = _clamp01(max(ys))

    return x_min, y_min, max(0.0, x_max - x_min), max(0.0, y_max - y_min)


def _norm_bbox_to_pixels(bbox_norm: NormBBox, width: int, height: int) -> BBox:
    """Normalize bbox'ı kare boyutlarıyla çarpıp piksele çevirir.

    Args:
        bbox_norm: 0..1 aralığında (x, y, w, h).
        width: Kare genişliği (piksel).
        height: Kare yüksekliği (piksel).

    Returns:
        Kare sınırları içinde (x, y, w, h).
    """
    x, y, w, h = bbox_norm
    x_px = min(int(x * width), width - 1)
    y_px = min(int(y * height), height - 1)
    return x_px, y_px, min(int(w * width), width - x_px), min(int(h * height), height - y_px)


def _clamp01(value: float) -> float:
    """Değeri 0..1 aralığına sıkıştırır."""
    return max(0.0, min(1.0, float(value)))
