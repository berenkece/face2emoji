"""macOS kamera cihazlarını isimleriyle listeler ve OpenCV index'lerine eşler.

OpenCV'nin AVFoundation backend'i kamerayı şu listedeki sıraya göre indeksler:
``AVCaptureDevice.devicesWithMediaType(video)`` + aynı sorgunun ``muxed`` hâli.
Burada aynı listeyi okuyoruz, dolayısıyla bulduğumuz index doğrudan
``cv2.VideoCapture(index)`` ile kullanılabilir.

pyobjc kurulu değilse (ya da platform macOS değilse) fonksiyonlar boş liste /
None döner; çağıran taraf index 0'a düşmelidir.
"""

from __future__ import annotations

import logging
from typing import List, NamedTuple, Optional

# Dahili MacBook kamerasının AVFoundation cihaz tipi. Continuity Camera
# (iPhone) "AVCaptureDeviceTypeContinuityCamera" olarak gelir ve elenir.
_BUILTIN_TYPE = "AVCaptureDeviceTypeBuiltInWideAngleCamera"

#: Continuity Camera: iPhone/iPad'in kendini kamera olarak sunmasi. Kullanici
#: telefonunu kamera olarak istemiyor, bu yuzden asla otomatik secilmez.
_CONTINUITY_TYPE = "AVCaptureDeviceTypeContinuityCamera"
_PHONE_NAME_HINTS = ("iphone", "ipad")
_BUILTIN_NAME_HINTS = ("macbook", "facetime", "built-in", "imac", "studio display")

logger = logging.getLogger(__name__)


#: En son loglanan secim; ayni secim tekrar tekrar loglanmasin diye tutulur.
#: Secim DEGISTIGINDE (ornegin iPhone listeye girip index'leri kaydirdiginda)
#: yeniden loglanir -- kullanicinin gormesi gereken sey tam da budur.
_last_logged_selection: Optional[tuple] = None


def _log_selection(index: int, name: str) -> None:
    """Seçimi loglar; aynı seçim art arda tekrarlanırsa sessiz kalır."""
    global _last_logged_selection
    selection = (index, name)
    if selection == _last_logged_selection:
        return
    _last_logged_selection = selection
    logger.info("Kamera seçildi: index %d - %s", index, name)


class NoUsableCameraError(RuntimeError):
    """Yalnızca telefon kamerası bulundu; kullanılabilir kamera yok."""


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

    @property
    def is_continuity(self) -> bool:
        """Cihazın iPhone/iPad (Continuity Camera) olup olmadığını tahmin eder."""
        if self.device_type == _CONTINUITY_TYPE:
            return True
        lowered = self.name.lower()
        return any(hint in lowered for hint in _PHONE_NAME_HINTS)


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

    Dahili kamera bulunamazsa çağıran taraf index 0'a düşer; bu sessiz kalırsa
    yanlış kamera açılır ve kimse fark etmez. Bu yüzden her başarısızlık
    durumu net bir uyarıyla loglanır.

    Returns:
        Index, ya da cihaz listesi alınamazsa / dahili kamera bulunamazsa None.
    """
    devices = list_devices()

    if not devices:
        logger.warning(
            "Kamera cihaz listesi alınamadı (pyobjc kurulu değil ya da platform "
            "macOS değil). Kamera index 0 kullanılacak -- YANLIŞ KAMERA "
            "açılabilir (macOS'ta Continuity Camera iPhone'u index 0'a itebilir). "
            "Kameraları görmek için: python scratch_camera.py --list"
        )
        return None

    for device in devices:
        if device.is_builtin:
            return device.index

    logger.warning(
        "Dahili Mac kamerası bulunamadı; index 0 kullanılacak -- YANLIŞ KAMERA "
        "açılabilir. Bulunan cihazlar: %s",
        ", ".join(f"{d.index}: {d.name} [{d.device_type}]" for d in devices),
    )
    return None


def select_camera_index() -> Optional[int]:
    """Kullanılacak kameranın OpenCV index'ini seçer.

    Öncelik sırası:
      1. Dahili Mac kamerası.
      2. Continuity Camera **olmayan** ilk cihaz (harici webcam).
      3. Hiçbiri yoksa None -- çağıran taraf index 0'a düşer.

    iPhone/iPad asla otomatik seçilmez: telefonu kamera olarak kullanmak
    istemeyen kullanıcı, Continuity Camera listeye girip index'leri kaydırdığında
    sessizce telefona bağlanmamalı.

    Bu fonksiyon her ``CameraStream.open()`` çağrısında yeniden çalıştırılır,
    çünkü cihaz sıralaması telefon menzile girip çıktıkça değişir.

    Returns:
        Seçilen index, ya da cihaz listesi alınamazsa None.
    """
    devices = list_devices()

    if not devices:
        logger.warning(
            "Kamera cihaz listesi alınamadı (pyobjc kurulu değil ya da platform "
            "macOS değil). Kamera index 0 kullanılacak -- YANLIŞ KAMERA "
            "açılabilir. Kameraları görmek için: python scratch_camera.py --list"
        )
        return None

    for device in devices:
        if device.is_builtin:
            _log_selection(device.index, device.name)
            return device.index

    for device in devices:
        if not device.is_continuity:
            logger.warning(
                "Dahili Mac kamerası bulunamadı; Continuity olmayan ilk cihaz "
                "seçildi: index %d - %s. Bulunan cihazlar: %s",
                device.index,
                device.name,
                _describe(devices),
            )
            return device.index

    # Index 0'a dusmek burada TELEFONA baglanmak demek olurdu; bilerek hata
    # veriyoruz ki macOS'un iPhone baglanti istemi tekrar tekrar cikmasin.
    raise NoUsableCameraError(
        "Yalnızca Continuity Camera (iPhone/iPad) bulundu, dahili Mac kamerası "
        f"görünmüyor. Bulunan cihazlar: {_describe(devices)}. "
        "Telefon kamerası bilerek kullanılmıyor. Dahili kamera başka bir "
        "uygulama (FaceTime, Zoom, Photo Booth) tarafından tutuluyor olabilir; "
        "o uygulamayı kapatıp tekrar deneyin. Belirli bir kamerayı zorlamak "
        "için config.py yerine CameraStream(source=<index>) kullanın; "
        "kameraları listelemek için: python scratch_camera.py --list"
    )


def _describe(devices: List[CameraDevice]) -> str:
    """Cihaz listesini log mesajı için okunur hâle getirir."""
    return ", ".join(f"{d.index}: {d.name} [{d.device_type}]" for d in devices)
