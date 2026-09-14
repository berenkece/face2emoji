"""Kamerayı tek bir arka plan worker'ında okuyup MJPEG'e çeviren katman.

Bu dosya bilerek Flask'tan bağımsızdır: HTTP katmanı (app/server.py) burayı
kullanır, tersi olmaz.

Mimari: **üretici-tüketici**. Kamerayı yalnızca worker thread'i okur; HTTP
bağlantıları (tüketiciler) worker'ın yayımladığı son kareyi bekleyip gönderir.
Böylece kaç sekme açık olursa olsun worker hızı değişmez ve FaceAnalyzer ile
EmojiMapper tek thread'den erişildiği için kilide ihtiyaç duymaz.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Iterator, List, NamedTuple, Optional, Tuple

import cv2
import numpy as np

from config import (
    CAMERA_RECONNECT_DELAYS,
    CONSUMER_WAIT_TIMEOUT,
    DEBUG_OVERLAY,
    JPEG_QUALITY,
    TARGET_FPS,
    WATCH_BLENDSHAPES,
    WORKER_START_TIMEOUT,
    WORKER_STOP_TIMEOUT,
)
from core.camera import CameraStream
from core.face import FaceAnalyzer, FaceResult, NormBBox
from core.mapping import EmojiDecision, EmojiMapper
from core.renderer import BubbleRenderer
from core.tracking import FaceTracker

logger = logging.getLogger(__name__)

Frame = np.ndarray

#: MJPEG multipart akışında kareleri ayıran sınır (server.py ile aynı olmalı).
BOUNDARY = b"frame"


class FaceState(NamedTuple):
    """Tek bir kişinin yayımlanmış durumu."""

    id: int
    decision: EmojiDecision
    bbox_norm: Optional[NormBBox]


class PipelineState(NamedTuple):
    """Tek kilit altında alınmış tutarlı durum görüntüsü."""

    faces: List[FaceState]
    frame_id: int
    camera_ok: bool


class Pipeline:
    """Kamerayı tek worker'da okur, tüketicilere son kareyi dağıtır.

    Tasarım kararı: tek kamera, tek sahne. Karar artık **kişi başınadır** --
    kadrajdaki her yüz kendi kimliğini, kendi EMA geçmişini ve kendi emojisini
    taşır. Ama sahne tektir: tüm izleyiciler aynı kareyi ve aynı kişi listesini
    görür; izleyiciye özel durum yoktur.
    """

    def __init__(
        self,
        camera: CameraStream,
        face_analyzer: FaceAnalyzer,
        tracker: FaceTracker,
        emoji_mapper: EmojiMapper,
        renderer: BubbleRenderer,
    ) -> None:
        """Pipeline'ı bileşenlerine bağlar; hiçbir kaynağı açmaz.

        Args:
            camera: Kare kaynağı olarak kullanılacak CameraStream.
            face_analyzer: Kareleri analiz edecek FaceAnalyzer.
            tracker: Yüzlere kareler arası kimlik atayacak FaceTracker.
            emoji_mapper: Kimlik başına emoji seçecek EmojiMapper.
            renderer: Kare üzerine çizim yapacak BubbleRenderer.
        """
        self.camera = camera
        self.face_analyzer = face_analyzer
        self.tracker = tracker
        self.emoji_mapper = emoji_mapper
        self.renderer = renderer

        # Paylasilan durum: yalnizca bu kilit altinda okunur/yazilir.
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._latest_jpeg: Optional[bytes] = None
        self._latest_faces: List[FaceState] = []
        self._frame_id = 0
        self._camera_ok = False

        # Worker yasam dongusu.
        self._worker: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._ready = threading.Event()
        self._load_error: Optional[BaseException] = None

    # --- yaşam döngüsü -----------------------------------------------------

    def start(self) -> None:
        """Kamerayı açar, worker'ı başlatır ve modelin yüklenmesini bekler.

        Raises:
            RuntimeError: Kamera açılamazsa ya da worker süresinde hazır olmazsa.
            Exception: Modelin yüklenmesi sırasında oluşan hata (ör. model
                dosyası yoksa ``FileNotFoundError``) burada yeniden fırlatılır.
        """
        if self._worker is not None and self._worker.is_alive():
            return

        self._stop_event.clear()
        self._ready.clear()
        self._load_error = None

        # Bilincli asimetri: KAMERA ana thread'de aciliyor, MODEL worker'in
        # icinde yaratiliyor.
        #   - Kamera: mevcut kod zaten kamerayi thread'ler arasi kullaniyor ve
        #     calistigina dair ampirik kanit var. Ayrica ana thread'de acmak
        #     macOS kamera izni hatasini acilista gorunur kiliyor.
        #   - Model: boyle bir kanit yoktu. Thread bagliligi riskini sarta
        #     baglamak yerine tamamen ortadan kaldiriyoruz; model worker'da
        #     yaratilip yalnizca orada kullaniliyor.
        self.camera.open()

        worker = threading.Thread(
            target=self._run, name="face2emoji-worker", daemon=True
        )
        self._worker = worker
        worker.start()

        if not self._ready.wait(WORKER_START_TIMEOUT):
            raise RuntimeError(
                f"Yüz modeli {WORKER_START_TIMEOUT:.0f} saniyede yüklenemedi ve "
                "worker başlamadı. Model dosyası çok yavaş bir diskten "
                "okunuyor olabilir; config.py içindeki WORKER_START_TIMEOUT "
                "değerini artırmayı deneyin."
            )
        if self._load_error is not None:
            raise self._load_error

    def stop(self) -> None:
        """Worker'ı durdurur, kamerayı ve modeli bırakır. Birden çok kez çağrılabilir."""
        self._stop_event.set()
        with self._cond:
            self._cond.notify_all()

        worker = self._worker
        if (
            worker is not None
            and worker.is_alive()
            and worker is not threading.current_thread()
        ):
            worker.join(WORKER_STOP_TIMEOUT)
            if worker.is_alive():
                logger.warning(
                    "Worker %.1f saniyede durmadı; kaynaklar yine de bırakılıyor.",
                    WORKER_STOP_TIMEOUT,
                )
        self._worker = None

        self.camera.release()
        self.face_analyzer.close()

    # --- worker ------------------------------------------------------------

    def _run(self) -> None:
        """Worker thread'inin giriş noktası: önce modeli yükler, sonra döngü."""
        try:
            self.face_analyzer.load()
        except BaseException as error:  # noqa: BLE001 - ana thread'e tasinacak
            self._load_error = error
            return
        finally:
            # Basari da hata da ana thread'e bildirilmeli.
            self._ready.set()

        self._loop()

    def _loop(self) -> None:
        """Kare okur, işler ve yayımlar. Programda kameraya dokunan tek yer."""
        interval = 1.0 / TARGET_FPS if TARGET_FPS > 0 else 0.0
        failures = 0
        # Mutlak hedef zamani: "gecen sureyi olc, kalani uyu" yaklasimi her
        # turda uyanma gecikmesini biriktirip hizi dusuruyordu (30 yerine 27).
        next_deadline = time.monotonic() + interval

        while not self._stop_event.is_set():
            frame = self.camera.read()

            if frame is None:
                failures += 1
                self._set_camera_ok(False)
                if self._reconnect(failures):
                    failures = 0
                next_deadline = time.monotonic() + interval
                continue

            failures = 0
            self._publish(frame)

            now = time.monotonic()
            remaining = next_deadline - now
            if remaining > 0:
                # Kesintiye ugrayabilen uyku: stop() aninda uyanir.
                self._stop_event.wait(remaining)
                next_deadline += interval
            else:
                # Geride kaldik: birikmis gecikmeyi kovalamak yerine sifirla,
                # yoksa sonraki turlar hic uyumadan kosar.
                next_deadline = now + interval

    def _process(self, frame: Frame) -> Tuple[Frame, List[FaceState]]:
        """Kareyi analiz eder, kimlik başına karar üretir, debug öğelerini çizer.

        Emoji kareye çizilmez; HTML katmanı ``/state``'ten okur.

        Args:
            frame: İşlenecek BGR kare.

        Returns:
            (çizilmiş kare, kişi durumları listesi) ikilisi.
        """
        faces = self.face_analyzer.analyze(frame)
        tracked = self.tracker.update(faces)

        # Dusen kimliklerin durumu SILINMELI: stand boyunca yuzlerce kisi
        # gececek, temizlenmezse mapper'in sozlugu sinirsiz buyur.
        for lost_id in self.tracker.dropped_ids:
            self.emoji_mapper.forget(lost_id)

        states = [
            FaceState(
                id=track_id,
                decision=self.emoji_mapper.decide(track_id, face),
                bbox_norm=face.bbox_norm,
            )
            for track_id, face in tracked
        ]

        # Yuz kutusu da debug ogesi: stand sunumunda ziyaretcinin yuzunde
        # dikdortgen gorunmesin diye panelle ayni bayraga bagli.
        drawn = frame
        if DEBUG_OVERLAY:
            drawn = self.renderer.draw_face_box(drawn, [f.bbox for f in faces])
            drawn = self.renderer.draw_debug(drawn, faces, WATCH_BLENDSHAPES)
        return drawn, states

    def _publish(self, frame: Frame) -> None:
        """Kareyi işler ve paylaşılan duruma yazıp tüketicileri uyandırır."""
        drawn, states = self._process(frame)
        jpeg = self.encode_jpeg(drawn)
        if jpeg is None:
            return

        with self._cond:
            self._latest_jpeg = jpeg
            self._latest_faces = states
            self._camera_ok = True
            self._frame_id += 1
            self._cond.notify_all()

    def _set_camera_ok(self, value: bool) -> None:
        """Kamera durumunu kilit altında günceller."""
        with self._cond:
            self._camera_ok = value

    def _reconnect(self, attempt: int) -> bool:
        """Kamerayı artan beklemeyle kapatıp yeniden açmayı dener.

        Bu sırada yeni kare yayımlanmadığı için tüketiciler son geçerli kareyi
        göstermeye devam eder (donmuş görüntü, siyah ekran değil).

        Args:
            attempt: Kaçıncı ardışık başarısızlık (1'den başlar).

        Returns:
            Yeniden bağlanma başarılıysa True.
        """
        index = min(attempt - 1, len(CAMERA_RECONNECT_DELAYS) - 1)
        delay = CAMERA_RECONNECT_DELAYS[index]
        logger.warning(
            "Kameradan kare alınamadı (ardışık %d. hata). "
            "%.1f saniye sonra yeniden bağlanılacak.",
            attempt,
            delay,
        )
        if self._stop_event.wait(delay):
            return False

        # release() sart: kopmus kamerada isOpened() hala True donebiliyor,
        # bu durumda open() erken cikip sahte basari verir.
        self.camera.release()
        try:
            self.camera.open()
        except RuntimeError as error:
            logger.warning("Kamera yeniden açılamadı: %s", error)
            return False

        logger.info("Kameraya yeniden bağlanıldı (%d. denemede).", attempt)
        return True

    # --- tüketiciler -------------------------------------------------------

    def mjpeg_frames(self) -> Iterator[bytes]:
        """Worker'ın yayımladığı kareleri multipart MJPEG blokları olarak verir.

        Kameraya dokunmaz. Her tüketici yalnızca kendi görmediği bir kare
        geldiğinde uyanır; aynı kare iki kez gönderilmez ve meşgul bekleme
        yapılmaz.

        Yields:
            ``--frame`` sınırı, JPEG başlığı ve kare verisinden oluşan bloklar.
        """
        last_seen = -1

        while not self._stop_event.is_set():
            with self._cond:
                ready = self._cond.wait_for(
                    lambda: self._stop_event.is_set()
                    or (
                        self._frame_id != last_seen
                        and self._latest_jpeg is not None
                    ),
                    timeout=CONSUMER_WAIT_TIMEOUT,
                )
                if self._stop_event.is_set():
                    return
                if not ready:
                    # Zaman asimi: yeni kare yok (ornegin kamera kopuk).
                    continue
                jpeg = self._latest_jpeg
                last_seen = self._frame_id

            yield (
                b"--" + BOUNDARY + b"\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            )

    def snapshot(self) -> PipelineState:
        """Kişi listesini ve kamera durumunu tek kilit altında döndürür.

        Returns:
            Aynı kareye ait tutarlı PipelineState.
        """
        with self._cond:
            return PipelineState(
                faces=list(self._latest_faces),
                frame_id=self._frame_id,
                camera_ok=self._camera_ok,
            )

    @property
    def faces(self) -> List[FaceState]:
        """Kilit altında okunan son kişi listesi."""
        with self._cond:
            return list(self._latest_faces)

    # --- yardımcı ----------------------------------------------------------

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
