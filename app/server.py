"""Pipeline'ı MJPEG ve JSON durum olarak sunan Flask uygulaması."""

from __future__ import annotations

from typing import Any, Dict, List

from flask import Flask, Response, render_template, send_from_directory

from app.pipeline import BOUNDARY, Pipeline
from config import EMOJI_RULES

MJPEG_MIMETYPE = f"multipart/x-mixed-replace; boundary={BOUNDARY.decode()}"


def create_app(pipeline: Pipeline) -> Flask:
    """Verilen pipeline'a bağlı bir Flask uygulaması kurar.

    Args:
        pipeline: Kare üretecek, önceden start() edilmiş Pipeline.

    Returns:
        Rotaları tanımlanmış Flask uygulaması.
    """
    app = Flask(__name__)
    # Emoji karakterleri JSON'a ham UTF-8 olarak yazilsin (\uXXXX kacisi yerine).
    app.json.ensure_ascii = False

    @app.get("/")
    def index() -> str:
        """Stand ekranını döndürür; ipucu şeridi EMOJI_RULES'tan üretilir."""
        return render_template("index.html", hints=_rule_hints())

    @app.get("/favicon.ico")
    def favicon() -> Response:
        """Tarayıcının kök dizinden istediği favicon'u karşılar (404 olmasın)."""
        return send_from_directory(
            app.static_folder, "img/favicon.png", mimetype="image/png"
        )

    @app.get("/video")
    def video() -> Response:
        """Canlı MJPEG akışını döndürür."""
        return Response(pipeline.mjpeg_frames(), mimetype=MJPEG_MIMETYPE)

    @app.get("/state")
    def state() -> Response:
        """Son emoji kararını ve normalize yüz kutusunu JSON olarak döndürür."""
        return app.response_class(
            response=app.json.dumps(_state_payload(pipeline)),
            mimetype="application/json; charset=utf-8",
        )

    return app


def _rule_hints() -> List[Dict[str, str]]:
    """İpucu şeridinin içeriğini EMOJI_RULES'tan üretir.

    Şerit elle yazılmaz: yeni bir kural eklendiğinde kendiliğinden görünür.
    ``hint`` alanı yoksa ``label`` kullanılır.

    Returns:
        Her kural için ``emoji`` ve ``text`` taşıyan sözlükler.
    """
    return [
        {"emoji": rule["emoji"], "text": rule.get("hint") or rule["label"]}
        for rule in EMOJI_RULES
    ]


def _state_payload(pipeline: Pipeline) -> Dict[str, Any]:
    """Pipeline'ın son durumunu JSON'a uygun sözlüğe çevirir.

    Args:
        pipeline: Durumu okunacak Pipeline.

    Returns:
        Kamera yeniden bağlanırken False olan ``camera_ok`` ve kadrajdaki her
        kişi için bir girdi taşıyan ``faces`` listesi (``id``, ``emoji``,
        ``label``, ``score``, normalize ``box``). Yüz yoksa ``faces`` boştur.
    """
    # Tek kilit altinda alinmis tutarli goruntu: kararlar ile yuz kutulari
    # ayni kareden gelir, farkli karelerden karismaz.
    state = pipeline.snapshot()

    faces = []
    for face in state.faces:
        if face.bbox_norm is None:
            continue
        x, y, w, h = face.bbox_norm
        faces.append(
            {
                "id": face.id,
                "emoji": face.decision.emoji,
                "label": face.decision.label,
                "score": round(face.decision.score, 4),
                "box": {
                    "x": round(x, 4),
                    "y": round(y, 4),
                    "w": round(w, 4),
                    "h": round(h, 4),
                },
            }
        )

    return {"camera_ok": state.camera_ok, "faces": faces}
