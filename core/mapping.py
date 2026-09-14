"""Blendshape katsayılarından emoji kararı üreten kural motoru.

Bu dosya bilerek yalnızca sözlük alıp karar döndürür: ne Flask ne de mediapipe
import eder, dolayısıyla test edilmesi için kamera ya da model gerekmez.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

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


@dataclass
class _TrackState:
    """Tek bir kimliğin yumuşatma ve kararlılık durumu."""

    decision: EmojiDecision
    smoothed: Dict[str, float] = field(default_factory=dict)
    candidate_label: Optional[str] = None
    candidate_streak: int = 0


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

        #: track_id -> o kisinin yumusatma ve kararlilik durumu.
        self._tracks: Dict[int, _TrackState] = {}

    @property
    def track_count(self) -> int:
        """Durumu tutulan kimlik sayısı (sızıntı testleri için)."""
        return len(self._tracks)

    @property
    def tracked_ids(self) -> List[int]:
        """Durumu tutulan kimlikler."""
        return list(self._tracks)

    def reset(self) -> None:
        """Tüm kimliklerin durumunu siler."""
        self._tracks.clear()

    def forget(self, track_id: int) -> None:
        """Bir kimliğin durumunu siler; kimlik yoksa sessizce geçer.

        Stand boyunca yüzlerce kişi geçeceği için düşen kimliklerin durumu
        mutlaka silinmelidir; aksi hâlde bu sözlük sınırsız büyür.

        Args:
            track_id: Unutulacak kimlik.
        """
        self._tracks.pop(track_id, None)

    def decide(self, track_id: int, face_result: Any) -> EmojiDecision:
        """Bir kimliğin yüz sonucundan emoji kararı üretir.

        Her kimliğin kendi EMA geçmişi ve kararlılık sayacı vardır; kişiler
        birbirinin durumunu etkilemez.

        Args:
            track_id: FaceTracker'ın verdiği kalıcı kimlik.
            face_result: ``detected`` ve ``blendshapes`` alanları olan sonuç.
                Tip bağı kurulmaz; sözlük yeter.

        Returns:
            Kararlılık kuralı uygulanmış EmojiDecision.
        """
        if not face_result.detected:
            self.forget(track_id)
            return self.fallback

        state = self._tracks.get(track_id)
        if state is None:
            state = _TrackState(decision=self.fallback)
            self._tracks[track_id] = state

        self._update_smoothed(state, face_result.blendshapes)
        winner = self._best_rule(state)
        return self._apply_stability(state, winner)

    def _update_smoothed(
        self, state: "_TrackState", blendshapes: Mapping[str, float]
    ) -> None:
        """Gelen katsayıları üstel hareketli ortalamayla yumuşatır."""
        for name, value in blendshapes.items():
            previous = state.smoothed.get(name)
            if previous is None:
                state.smoothed[name] = float(value)
            else:
                state.smoothed[name] = (
                    self.alpha * float(value) + (1.0 - self.alpha) * previous
                )

    def _best_rule(self, state: "_TrackState") -> EmojiDecision:
        """Tüm koşulları sağlanan kurallardan en yüksek skorluyu seçer.

        Returns:
            Kazanan kuralın kararı; geçerli kural yoksa fallback.
        """
        best: Optional[EmojiDecision] = None

        for rule in self.rules:
            conditions: Sequence[Condition] = rule["conditions"]
            values = [state.smoothed.get(name, 0.0) for name, _, _ in conditions]

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

    def _apply_stability(
        self, state: "_TrackState", winner: EmojiDecision
    ) -> EmojiDecision:
        """Kararı ancak aday üst üste yeterince kazandıysa değiştirir.

        Sayaç mantığı (kimlik başına):
          - Kazanan mevcut kararla aynı etikete sahipse: aday sıfırlanır ve
            mevcut kararın skoru tazelenir.
          - Farklıysa: aynı aday üst üste geldikçe sayaç artar, aday değişirse
            sayaç 1'den başlar. Sayaç ``stability_frames``'e ulaşınca karar
            değişir ve sayaç sıfırlanır. O ana kadar eski karar döndürülür.

        Args:
            state: Bu kimliğin durumu.
            winner: Bu karenin kural kazananı.

        Returns:
            Ekranda gösterilecek karar.
        """
        if winner.label == state.decision.label:
            state.candidate_label = None
            state.candidate_streak = 0
            state.decision = winner
            return state.decision

        if winner.label == state.candidate_label:
            state.candidate_streak += 1
        else:
            state.candidate_label = winner.label
            state.candidate_streak = 1

        if state.candidate_streak >= self.stability_frames:
            state.decision = winner
            state.candidate_label = None
            state.candidate_streak = 0

        return state.decision
