"""MediaPipe'ın C++ katmanından gelen gürültülü stderr satırlarını süzer.

Bu satırlar (telemetri denemeleri, GL sürüm bilgisi, xnnpack notları) Python
``logging`` ile bastırılamaz: doğrudan işletim sistemi seviyesinde fd 2'ye
yazılıyorlar. ``GLOG_minloglevel`` de etkisiz -- ölçüldü.

Çözüm: fd 2'yi bir boruya çeviririz, arka plan thread'i satırları okur ve
bilinen gürültüyü atıp kalanı gerçek stderr'e geçirir. Böylece beklenmedik
native hatalar (ör. mediapipe 1.0.1'in çökme izi) görünür kalır.
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Tuple

#: Bu parcalari iceren satirlar atilir. Hepsi zararsiz mediapipe gurultusu.
NOISE_MARKERS: Tuple[str, ...] = (
    "clearcut",
    "portable_clearcut_uploader",
    "Source Location Trace",
    "wireless/android/play/playlog",
    "Fiber init:",
    "gl_context.cc",
    "inference_feedback_manager",
    "face_landmarker_graph.cc",
    "Created TensorFlow Lite XNNPACK delegate",
    "AVCaptureDeviceTypeExternal is deprecated",
    "NSCameraUseContinuityCameraDeviceType",
)

_installed = False


def is_noise(line: str) -> bool:
    """Satırın bilinen mediapipe gürültüsü olup olmadığını söyler."""
    return any(marker in line for marker in NOISE_MARKERS)


def quiet_native_logs() -> None:
    """stderr'i süzmeye başlar. Birden çok kez çağrılması güvenlidir.

    Python tarafındaki ``logging`` çıktısı etkilenmez; ``main.py`` onu
    stdout'a yönlendirir.
    """
    global _installed
    if _installed:
        return
    _installed = True

    read_fd, write_fd = os.pipe()
    real_stderr_fd = os.dup(2)
    os.dup2(write_fd, 2)
    os.close(write_fd)

    def pump() -> None:
        """Boruyu satır satır okur, gürültü olmayanı gerçek stderr'e yazar."""
        with os.fdopen(read_fd, "rb", buffering=0) as pipe, os.fdopen(
            real_stderr_fd, "wb", buffering=0
        ) as out:
            buffer = b""
            while True:
                try:
                    chunk = pipe.read(4096)
                except (OSError, ValueError):
                    return
                if not chunk:
                    return
                buffer += chunk
                while b"\n" in buffer:
                    raw, buffer = buffer.split(b"\n", 1)
                    line = raw.decode("utf-8", "replace")
                    if not is_noise(line):
                        out.write(raw + b"\n")

    threading.Thread(target=pump, name="stderr-filter", daemon=True).start()

    # sys.stderr hala fd 2'ye (artik boruya) yaziyor; satir satir aksin ki
    # suzgec bloklarda takilmasin.
    sys.stderr.reconfigure(line_buffering=True)
