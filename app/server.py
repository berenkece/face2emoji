"""Pipeline'ı MJPEG ve JSON durum olarak sunan Flask uygulaması."""

from __future__ import annotations

from typing import Any, Dict

from flask import Flask, Response, render_template

from app.pipeline import BOUNDARY, Pipeline

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
        """Video akışını gösteren sayfayı döndürür."""
        return render_template("index.html")

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


def _state_payload(pipeline: Pipeline) -> Dict[str, Any]:
    """Pipeline'ın son durumunu JSON'a uygun sözlüğe çevirir.

    Args:
        pipeline: Durumu okunacak Pipeline.

    Returns:
        ``emoji``, ``label``, ``score`` ve yüz yoksa None olan ``face`` alanları.
    """
    decision = pipeline.current_decision
    bbox_norm = pipeline.last_face_result.bbox_norm

    face = None
    if pipeline.last_face_result.detected and bbox_norm is not None:
        x, y, w, h = bbox_norm
        face = {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)}

    return {
        "emoji": decision.emoji,
        "label": decision.label,
        "score": round(decision.score, 4),
        "face": face,
    }
