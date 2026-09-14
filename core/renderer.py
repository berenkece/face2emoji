"""Kare üzerine görsel öğeler çizen katman."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

Frame = np.ndarray
BBox = Tuple[int, int, int, int]

#: Debug kutusunun rengi (BGR). Bilerek sönük: görüntünün önüne geçmesin.
BOX_COLOR = (110, 110, 110)

#: Debug kutusunun kalınlığı (piksel).
BOX_THICKNESS = 1

#: Debug panelinin kare içindeki en büyük oranı (genişlik ve yükseklik için).
PANEL_MAX_RATIO = 1.0 / 3.0

#: Panel arka planının opaklığı (0-1).
PANEL_ALPHA = 0.72

PANEL_BG = (20, 20, 20)
PANEL_TEXT = (235, 235, 235)
#: Panel basligi (kac yuz tespit edildigi) biraz daha sonuk.
PANEL_TITLE = (170, 200, 170)
BAR_TRACK = (70, 70, 70)
BAR_COLOR = (165, 165, 165)

#: Katsayı bu eşiği aşınca bar vurgulu renge geçer.
ACTIVE_THRESHOLD = 0.5
BAR_ACTIVE_COLOR = (90, 225, 130)

#: cv2.putText yalnızca ASCII çizebildiği için metinler İngilizce/ASCII.
NO_FACE_TEXT = "NO FACE"
FONT = cv2.FONT_HERSHEY_SIMPLEX


class BubbleRenderer:
    """Kare üzerine emoji balonlarını ve debug öğelerini çizer."""

    def draw_face_box(self, frame: Frame, bboxes: Sequence[Optional[BBox]]) -> Frame:
        """Her yüzün sınırlarını ince, sönük bir dikdörtgenle işaretler.

        Debug amaçlıdır; nihai görselin parçası değildir.

        Args:
            frame: Üzerine çizilecek BGR kare.
            bboxes: (x, y, w, h) piksel kutuları. Boş dizi güvenlidir; dizinin
                içindeki None değerler atlanır.

        Returns:
            Kutular çizilmiş kare (yerinde değiştirilir).
        """
        for bbox in bboxes or ():
            if bbox is None:
                continue
            x, y, w, h = bbox
            cv2.rectangle(frame, (x, y), (x + w, y + h), BOX_COLOR, BOX_THICKNESS)
        return frame

    def draw_debug(
        self,
        frame: Frame,
        faces: Sequence[Any],
        watch_list: Sequence[str],
    ) -> Frame:
        """Sol üste blendshape panelini çizer; çok yüzde en büyüğünü gösterir.

        Args:
            frame: Üzerine çizilecek BGR kare.
            faces: ``blendshapes`` ve ``bbox`` alanları olan yüz sonuçları.
                Boşsa panel yerine uyarı yazılır.
            watch_list: Panelde gösterilecek blendshape isimleri, sırasıyla.

        Returns:
            Panel çizilmiş kare (yerinde değiştirilir).
        """
        height, width = frame.shape[:2]

        if not faces:
            cv2.putText(
                frame, NO_FACE_TEXT, (14, 34), FONT, 0.7, PANEL_TEXT, 2, cv2.LINE_AA
            )
            return frame

        largest = max(faces, key=_bbox_area)
        blendshapes: Dict[str, float] = dict(getattr(largest, "blendshapes", {}) or {})
        title = f"{len(faces)} yuz" + (", en buyuk" if len(faces) > 1 else "")

        rows = [(name, float(blendshapes.get(name, 0.0))) for name in watch_list]
        if not rows:
            return frame

        panel_w = int(width * PANEL_MAX_RATIO)
        panel_h = int(height * PANEL_MAX_RATIO)
        pad = max(6, panel_h // 24)
        # Ilk satir baslik; kalanlar katsayilar.
        row_h = max(1, (panel_h - 2 * pad) // (len(rows) + 1))

        _fill_translucent(frame, 0, 0, panel_w, panel_h)

        # Sütunlar: isim | deger | bar
        name_w = int(panel_w * 0.44)
        value_w = int(panel_w * 0.15)
        bar_x = pad + name_w + value_w
        bar_w = max(1, panel_w - bar_x - pad)
        bar_h = max(3, int(row_h * 0.42))
        font_scale = _fit_font_scale(row_h)

        cv2.putText(
            frame, title, (pad, pad + int(row_h * 0.72)), FONT, font_scale,
            PANEL_TITLE, 1, cv2.LINE_AA,
        )

        for i, (name, score) in enumerate(rows, start=1):
            top = pad + i * row_h
            baseline = top + int(row_h * 0.72)

            label = _short_name(name, name_w, font_scale)
            cv2.putText(
                frame, label, (pad, baseline), FONT, font_scale,
                PANEL_TEXT, 1, cv2.LINE_AA,
            )
            cv2.putText(
                frame, f"{score:.2f}", (pad + name_w, baseline), FONT, font_scale,
                PANEL_TEXT, 1, cv2.LINE_AA,
            )

            bar_top = top + (row_h - bar_h) // 2
            cv2.rectangle(
                frame, (bar_x, bar_top), (bar_x + bar_w, bar_top + bar_h),
                BAR_TRACK, -1,
            )
            filled = int(bar_w * min(max(score, 0.0), 1.0))
            if filled > 0:
                color = BAR_ACTIVE_COLOR if score > ACTIVE_THRESHOLD else BAR_COLOR
                cv2.rectangle(
                    frame, (bar_x, bar_top), (bar_x + filled, bar_top + bar_h),
                    color, -1,
                )

        return frame


def _bbox_area(face: Any) -> int:
    """Yüzün piksel kutusunun alanı; kutu yoksa 0."""
    bbox = getattr(face, "bbox", None)
    if bbox is None:
        return 0
    return int(bbox[2]) * int(bbox[3])


def _fill_translucent(frame: Frame, x: int, y: int, w: int, h: int) -> None:
    """Verilen dikdörtgeni yarı saydam koyu bir zeminle doldurur (yerinde)."""
    region = frame[y : y + h, x : x + w]
    overlay = np.full_like(region, PANEL_BG, dtype=np.uint8)
    cv2.addWeighted(overlay, PANEL_ALPHA, region, 1.0 - PANEL_ALPHA, 0.0, region)


def _fit_font_scale(row_h: int) -> float:
    """Satır yüksekliğine göre okunaklı bir yazı ölçeği seçer."""
    return min(0.62, max(0.34, row_h / 42.0))


def _short_name(name: str, max_width_px: int, font_scale: float) -> str:
    """İsmi kısaltır ve gerekirse sütuna sığacak kadar keser."""
    label = name.replace("Left", "L").replace("Right", "R")
    while label:
        (text_w, _), _ = cv2.getTextSize(label, FONT, font_scale, 1)
        if text_w <= max_width_px - 6:
            return label
        label = label[:-1]
    return label
