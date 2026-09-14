"""Kareler arasında yüzlere kalıcı kimlik atayan basit takipçi.

MediaPipe yüzleri her karede aynı sırayla döndürmez. Kimlik eşleştirmesi
olmazsa kişilerin emoji durumları (EMA, kararlılık sayacı) birbirine karışır
ve emojiler insanlar arasında zıplar. Bu modül araya girip her yüze kareler
boyunca sabit kalan bir ``track_id`` verir.

Bu dosya bilerek saf Python'dur: ne ``cv2``, ne ``mediapipe``, ne ``flask``
import eder. Girdisi yalnızca normalize bbox taşıyan nesnelerdir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Set, Tuple

#: (x, y, w, h), 0..1 aralığında.
NormBBox = Tuple[float, float, float, float]
Point = Tuple[float, float]


@dataclass
class _Track:
    """Tek bir kimliğin takip durumu."""

    center: Point
    missing: int = 0


@dataclass
class FaceTracker:
    """Yüz kutularını kareler arası eşleyip kalıcı kimlik verir.

    Eşleştirme açgözlüdür (greedy): tüm yüz-kimlik çiftleri merkez mesafesine
    göre sıralanır ve en yakından başlayarak boş olanlar eşleştirilir. Optimal
    değildir ama bu ölçekte (en fazla 4 yüz) yeterlidir ve öngörülebilirdir.

    Mesafe normalize koordinatta Öklid mesafesidir. 16:9 bir karede x ve y
    aynı piksel ölçeğine karşılık gelmez, dolayısıyla mesafe anizotropiktir;
    ``max_distance`` seçilirken bu akılda tutulmalı.
    """

    max_distance: float
    lost_frames: int

    _tracks: Dict[int, _Track] = field(default_factory=dict, init=False)
    _next_id: int = field(default=1, init=False)
    _dropped: List[int] = field(default_factory=list, init=False)

    @property
    def active_ids(self) -> Set[int]:
        """Şu an takip edilen (kaybolmuş ama henüz düşmemiş dahil) kimlikler."""
        return set(self._tracks)

    @property
    def dropped_ids(self) -> List[int]:
        """Son ``update`` çağrısında düşürülen kimlikler."""
        return list(self._dropped)

    @property
    def track_count(self) -> int:
        """Takip edilen kimlik sayısı (sızıntı testleri için)."""
        return len(self._tracks)

    def reset(self) -> None:
        """Tüm kimlikleri unutur. Kimlik sayacı sıfırlanmaz."""
        self._tracks.clear()
        self._dropped.clear()

    def update(self, face_results: Sequence[Any]) -> List[Tuple[int, Any]]:
        """Bu karenin yüzlerini kimliklerle eşler.

        Args:
            face_results: ``bbox_norm`` alanı olan yüz sonuçları. ``bbox_norm``
                None olan yüzler atlanır.

        Returns:
            Girdi sırasını koruyan ``(track_id, face_result)`` listesi.
        """
        self._dropped.clear()

        usable = [
            (index, face)
            for index, face in enumerate(face_results)
            if getattr(face, "bbox_norm", None) is not None
        ]
        centers = {index: _center(face.bbox_norm) for index, face in usable}

        assignment = self._match(centers)

        # Eslesen kimlikleri tazele, yeni yuzlere kimlik ver.
        for index, _ in usable:
            track_id = assignment.get(index)
            if track_id is None:
                track_id = self._next_id
                self._next_id += 1
                assignment[index] = track_id
            self._tracks[track_id] = _Track(center=centers[index], missing=0)

        self._age_unmatched(set(assignment.values()))

        return [(assignment[index], face) for index, face in usable]

    def _match(self, centers: Dict[int, Point]) -> Dict[int, int]:
        """Yüzleri mevcut kimliklere açgözlü biçimde eşler.

        Args:
            centers: yüz indeksi -> merkez noktası.

        Returns:
            yüz indeksi -> track_id (yalnızca eşleşenler).
        """
        candidates: List[Tuple[float, int, int]] = []
        for index, center in centers.items():
            for track_id, track in self._tracks.items():
                distance = _distance(center, track.center)
                if distance <= self.max_distance:
                    candidates.append((distance, index, track_id))

        # En yakin ciftten basla; esitlikte kimlik sirasi belirleyici olsun ki
        # sonuc deterministik kalsin.
        candidates.sort(key=lambda item: (item[0], item[2], item[1]))

        assignment: Dict[int, int] = {}
        used_tracks: Set[int] = set()
        for _, index, track_id in candidates:
            if index in assignment or track_id in used_tracks:
                continue
            assignment[index] = track_id
            used_tracks.add(track_id)
        return assignment

    def _age_unmatched(self, matched_ids: Set[int]) -> None:
        """Bu karede görülmeyen kimliklerin sayacını artırır, süresi dolanı düşürür."""
        for track_id in list(self._tracks):
            if track_id in matched_ids:
                continue
            track = self._tracks[track_id]
            track.missing += 1
            if track.missing > self.lost_frames:
                del self._tracks[track_id]
                self._dropped.append(track_id)


def _center(bbox_norm: NormBBox) -> Point:
    """Normalize bbox'ın merkezini döndürür."""
    x, y, w, h = bbox_norm
    return x + w / 2.0, y + h / 2.0


def _distance(a: Point, b: Point) -> float:
    """İki nokta arasındaki Öklid mesafesi."""
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return (dx * dx + dy * dy) ** 0.5
