"""Blendshape katsayılarından emoji kararı üreten kural motoru.

Bu dosya bilerek yalnızca sözlük alıp karar döndürür: ne Flask ne de mediapipe
import eder, dolayısıyla test edilmesi için kamera ya da model gerekmez.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

#: Kural koşullarında kullanılabilecek operatörler.
OPERATORS: Dict[str, Callable[[float, float], bool]] = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}

Condition = Tuple[str, str, float]
Rule = Mapping[str, Any]


@dataclass(frozen=True)
class EmojiDecision:
    """Tek bir karenin emoji kararı."""

    emoji: str
    label: str
    score: float


class EmojiMapper:
    """Yumuşatılmış blendshape'leri kurallarla eşleyip emoji seçer."""

    def __init__(
        self,
        rules: Sequence[Rule],
        fallback: Mapping[str, str],
        alpha: float,
        stability_frames: int,
    ) -> None:
        """Karar motorunu yapılandırır.

        Args:
            rules: Her biri ``label``, ``emoji`` ve ``conditions`` taşıyan kurallar.
            fallback: Hiçbir kural geçerli değilken kullanılacak ``label``/``emoji``.
            alpha: EMA'da yeni örneğin ağırlığı (0-1). 1.0 yumuşatmayı kapatır.
            stability_frames: Yeni bir kazananın kararı değiştirmesi için gereken
                üst üste kare sayısı. 1 ise değişim anında olur.
        """
        self.rules = list(rules)
        self.fallback = EmojiDecision(
            emoji=fallback["emoji"], label=fallback["label"], score=0.0
        )
        self.alpha = alpha
        self.stability_frames = max(1, stability_frames)

        #: Blendshape adı -> EMA ile yumuşatılmış değer.
        self._smoothed: Dict[str, float] = {}
        #: Şu an ekranda olan karar.
        self._current: EmojiDecision = self.fallback
        #: Kararı değiştirmeye çalışan aday etiketi ve üst üste kaç kez kazandığı.
        self._candidate_label: Optional[str] = None
        self._candidate_streak: int = 0

    @property
    def current(self) -> EmojiDecision:
        """Şu an geçerli olan kararı döndürür."""
        return self._current

    def reset(self) -> None:
        """Yumuşatmayı, adayı ve kararı başlangıç durumuna döndürür."""
        self._smoothed.clear()
        self._current = self.fallback
        self._candidate_label = None
        self._candidate_streak = 0

    def decide(self, face_result: Any) -> EmojiDecision:
        """Bir yüz sonucundan emoji kararı üretir.

        Args:
            face_result: ``detected`` ve ``blendshapes`` alanları olan sonuç
                (core.face.FaceResult). Tip bağı kurulmaz; sözlük yeter.

        Returns:
            Kararlılık kuralı uygulanmış EmojiDecision.
        """
        if not face_result.detected:
            self.reset()
            return self._current

        self._update_smoothed(face_result.blendshapes)
        winner = self._best_rule()
        return self._apply_stability(winner)

    def _update_smoothed(self, blendshapes: Mapping[str, float]) -> None:
        """Gelen katsayıları üstel hareketli ortalamayla yumuşatır."""
        for name, value in blendshapes.items():
            previous = self._smoothed.get(name)
            if previous is None:
                self._smoothed[name] = float(value)
            else:
                self._smoothed[name] = (
                    self.alpha * float(value) + (1.0 - self.alpha) * previous
                )

    def _best_rule(self) -> EmojiDecision:
        """Tüm koşulları sağlanan kurallardan en yüksek skorluyu seçer.

        Returns:
            Kazanan kuralın kararı; geçerli kural yoksa fallback.
        """
        best: Optional[EmojiDecision] = None

        for rule in self.rules:
            conditions: Sequence[Condition] = rule["conditions"]
            values = [self._smoothed.get(name, 0.0) for name, _, _ in conditions]

            satisfied = all(
                OPERATORS[op](value, threshold)
                for value, (_, op, threshold) in zip(values, conditions)
            )
            if not satisfied or not values:
                continue

            candidate = EmojiDecision(
                emoji=rule["emoji"],
                label=rule["label"],
                score=sum(values) / len(values),
            )
            if best is None or candidate.score > best.score:
                best = candidate

        return best if best is not None else self.fallback

    def _apply_stability(self, winner: EmojiDecision) -> EmojiDecision:
        """Kararı ancak aday üst üste yeterince kazandıysa değiştirir.

        Sayaç mantığı:
          - Kazanan mevcut kararla aynı etikete sahipse: aday sıfırlanır ve
            mevcut kararın skoru tazelenir.
          - Farklıysa: aynı aday üst üste geldikçe sayaç artar, aday değişirse
            sayaç 1'den başlar. Sayaç ``stability_frames``'e ulaşınca karar
            değişir ve sayaç sıfırlanır. O ana kadar eski karar döndürülür.

        Args:
            winner: Bu karenin kural kazananı.

        Returns:
            Ekranda gösterilecek karar.
        """
        if winner.label == self._current.label:
            self._candidate_label = None
            self._candidate_streak = 0
            self._current = winner
            return self._current

        if winner.label == self._candidate_label:
            self._candidate_streak += 1
        else:
            self._candidate_label = winner.label
            self._candidate_streak = 1

        if self._candidate_streak >= self.stability_frames:
            self._current = winner
            self._candidate_label = None
            self._candidate_streak = 0

        return self._current
