"""macOS kamera cihazlarını isimleriyle listeler ve OpenCV index'lerine eşler.

OpenCV'nin AVFoundation backend'i kamerayı şu listedeki sıraya göre indeksler:
``AVCaptureDevice.devicesWithMediaType(video)`` + aynı sorgunun ``muxed`` hâli.
Burada aynı listeyi okuyoruz, dolayısıyla bulduğumuz index doğrudan
``cv2.VideoCapture(index)`` ile kullanılabilir.

pyobjc kurulu değilse (ya da platform macOS değilse) fonksiyonlar boş liste /
None döner; çağıran taraf index 0'a düşmelidir.
"""

from __future__ import annotations

from typing import List, NamedTuple, Optional

# Dahili MacBook kamerasının AVFoundation cihaz tipi. Continuity Camera
# (iPhone) "AVCaptureDeviceTypeContinuityCamera" olarak gelir ve elenir.
_BUILTIN_TYPE = "AVCaptureDeviceTypeBuiltInWideAngleCamera"
_BUILTIN_NAME_HINTS = ("macbook", "facetime", "built-in", "imac", "studio display")


class CameraDevice(NamedTuple):
    """Tek bir kamera cihazı."""

    index: int
    name: str
    device_type: str
    unique_id: str

    @property
    def is_builtin(self) -> bool:
        """Cihazın Mac'in dahili kamerası olup olmadığını tahmin eder."""
        if self.device_type == _BUILTIN_TYPE:
            return True
        lowered = self.name.lower()
        return any(hint in lowered for hint in _BUILTIN_NAME_HINTS)


def list_devices() -> List[CameraDevice]:
    """Kameraları OpenCV index sırasıyla döndürür.

    Returns:
        CameraDevice listesi. pyobjc yoksa ya da platform macOS değilse boş liste.
    """
    try:
        import AVFoundation as AVF  # type: ignore[import-not-found]
    except ImportError:
        return []

    devices = list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeVideo))
    # OpenCV muxed cihazları listenin sonuna ekliyor; index parity için biz de ekliyoruz.
    devices += list(AVF.AVCaptureDevice.devicesWithMediaType_(AVF.AVMediaTypeMuxed))

    return [
        CameraDevice(
            index=i,
            name=str(d.localizedName()),
            device_type=str(d.deviceType()),
            unique_id=str(d.uniqueID()),
        )
        for i, d in enumerate(devices)
    ]


def find_builtin_index() -> Optional[int]:
    """Dahili Mac kamerasının OpenCV index'ini döndürür.

    Returns:
        Index, ya da cihaz listesi alınamazsa / dahili kamera bulunamazsa None.
    """
    for device in list_devices():
        if device.is_builtin:
            return device.index
    return None
