"""Kamera erişimi için ince bir OpenCV VideoCapture sarmalayıcısı."""

from __future__ import annotations

from types import TracebackType
from typing import Iterator, Optional, Type, Union

import cv2
import numpy as np

from core.devices import select_camera_index

Frame = np.ndarray


def _resolve_source(source: Union[int, str, None]) -> Union[int, str]:
    """None gelirse uygun kamerayı seçer, bulunamazsa index 0'a düşer."""
    if source is not None:
        return source
    index = select_camera_index()
    return 0 if index is None else index


class CameraStream:
    """Bir kameradan (ya da video dosyasından) BGR kareler okur.

    Kullanım:
        with CameraStream() as cam:
            for frame in cam.frames():
                ...
    """

    def __init__(
        self,
        source: Union[int, str, None] = None,
        width: int = 1280,
        height: int = 720,
        mirror: bool = True,
        warmup_frames: int = 5,
    ) -> None:
        """Akışı yapılandırır; kamera açılmaz, bunun için open() çağrılmalı.

        Args:
            source: Kamera indeksi ya da video dosyası yolu. None (varsayılan)
                ise dahili Mac kamerası otomatik seçilir ve bu seçim **her
                open() çağrısında yeniden yapılır** -- Continuity Camera
                iPhone'u listeye sokup index'leri kaydırsa bile telefona
                bağlanılmaz. Açıkça bir index verilirse o index aynen kullanılır.
            width: İstenen kare genişliği (sürücü desteklemeyebilir).
            height: İstenen kare yüksekliği.
            mirror: True ise kareler yatay çevrilir (ayna görüntüsü).
            warmup_frames: open() sonunda okunup atılacak kare sayısı. Kameranın
                ilk kareleri pozlama oturmadan geldiği için karanlık olur.
        """
        # Istek olarak sakla: None ise her open()'da yeniden cozulur, cunku
        # cihaz siralamasi telefon menzile girip ciktikca degisiyor.
        self._requested_source = source
        self.source: Union[int, str] = _resolve_source(source)
        self.width = width
        self.height = height
        self.mirror = mirror
        self.warmup_frames = warmup_frames
        self._cap: Optional[cv2.VideoCapture] = None

    @property
    def is_open(self) -> bool:
        """Akışın şu anda açık olup olmadığını döndürür."""
        return self._cap is not None and self._cap.isOpened()

    def open(self) -> "CameraStream":
        """Kaynağı açar ve çözünürlüğü ayarlar.

        Returns:
            Zincirleme kullanım için self.

        Raises:
            RuntimeError: Kaynak açılamazsa.
        """
        if self.is_open:
            return self

        # Her acilista yeniden coz: uygulama acikken iPhone menzile girerse
        # AVFoundation siralamasi kayar ve eski index telefonu gosterir.
        self.source = self._current_source()

        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(
                f"Kamera açılamadı (source={self.source!r}). "
                "macOS'ta bu genellikle kamera izni verilmemiş olmasından kaynaklanır: "
                "Sistem Ayarları > Gizlilik ve Güvenlik > Kamera bölümünden bu uygulamaya "
                "(Terminal / iTerm / VS Code) izin verip programı yeniden başlatın. "
                "Ayrıca kameranın başka bir uygulama tarafından kullanılmadığından ve "
                "source indeksinin doğru olduğundan emin olun."
            )

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap = cap
        self._warm_up()
        return self

    def _current_source(self) -> Union[int, str]:
        """Bu açılışta kullanılacak kaynağı döndürür.

        Açıkça bir kaynak verildiyse o aynen kullanılır; ``None`` ise cihaz
        listesi yeniden okunup uygun kamera seçilir.
        """
        return _resolve_source(self._requested_source)

    def _warm_up(self) -> None:
        """Pozlama oturana kadar ilk kareleri okuyup atar."""
        for _ in range(self.warmup_frames):
            if self.read() is None:
                break

    def read(self) -> Optional[Frame]:
        """Tek bir kare okur.

        Returns:
            BGR numpy dizisi, ya da kare alınamazsa None.
            mirror=True ise kare yatay çevrilmiş olarak döner.
        """
        if self._cap is None:
            return None

        ok, frame = self._cap.read()
        if not ok or frame is None:
            return None

        if self.mirror:
            frame = cv2.flip(frame, 1)
        return frame

    def frames(self) -> Iterator[Frame]:
        """Kareleri sonsuza dek üretir; akış bittiğinde durur.

        Yields:
            Ardışık BGR kareler. İlk None karede generator sona erer.
        """
        while True:
            frame = self.read()
            if frame is None:
                break
            yield frame

    def release(self) -> None:
        """Kamerayı serbest bırakır. Birden çok kez çağrılabilir."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self) -> "CameraStream":
        """Kamerayı açar ve akışın kendisini döndürür."""
        return self.open()

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        """Bir hata olsa da olmasa da kamerayı serbest bırakır."""
        self.release()
