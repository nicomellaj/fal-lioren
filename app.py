"""App Flask — Falabella Seller Center → Lioren boletas automáticas."""
import logging
import os
import threading
from flask import Flask, render_template, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

from config import load_config, save_config
from database import init_db, get_all_orders, get_stats, get_logs, mark_pdf_descargado

@app.before_request
def ensure_db():
    init_db()
from sync_service import SyncService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
scheduler = BackgroundScheduler()

with app.app_context():
    init_db()
_sync_lock = threading.Lock()
_sync_service = None


def get_sync_service():
    global _sync_service
    config = load_config()
    _sync_service = SyncService(config)
    return _sync_service


def run_sync():
    if _sync_lock.locked():
        return
    with _sync_lock:
        try:
            svc = get_sync_service()
            svc.sync()
        except Exception as e:
            logger.error(f"Error en sync: {e}")


def setup_scheduler():
    config = load_config()
    if config.get("sync_auto"):
        interval = int(config.get("intervalo_min", 30))
        if scheduler.get_job("sync"):
            scheduler.remove_job("sync")
        scheduler.add_job(run_sync, "interval", minutes=interval, id="sync")
        if not scheduler.running:
            scheduler.start()
        logger.info(f"Scheduler activo cada {interval} min")


# ─── Rutas ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    config = load_config()
    orders = get_all_orders()[:20]
    stats = get_stats()
    logs = get_logs(50)
    configured = bool(config.get("fal_email") and config.get("lioren_jwt"))
    interval = config.get("intervalo_min", 30)
    dias = config.get("dias_atras", 7)
    return render_template(
        "index.html",
        orders=orders,
        stats=stats,
        logs=logs,
        configured=configured,
        interval=interval,
        dias=dias,
    )


@app.route("/todos")
def todos():
    config = load_config()
    orders = get_all_orders()
    stats = get_stats()
    logs = get_logs(50)
    configured = bool(config.get("fal_email") and config.get("lioren_jwt"))
    interval = config.get("intervalo_min", 30)
    dias = config.get("dias_atras", 7)
    return render_template(
        "index.html",
        orders=orders,
        stats=stats,
        logs=logs,
        configured=configured,
        interval=interval,
        dias=dias,
        mostrar_todos=True,
    )


@app.route("/config", methods=["GET", "POST"])
def config_page():
    config = load_config()
    saved = False
    if request.method == "POST":
        data = {
            "fal_email": request.form.get("fal_email", "").strip(),
            "fal_password": request.form.get("fal_password", "").strip(),
            "lioren_email": request.form.get("lioren_email", "").strip(),
            "lioren_password": request.form.get("lioren_password", "").strip(),
            "lioren_jwt": request.form.get("lioren_jwt", "").strip(),
            "rut_emisor": request.form.get("rut_emisor", "").strip(),
            "tipo_dte": int(request.form.get("tipo_dte", 39)),
            "dias_atras": int(request.form.get("dias_atras", 7)),
            "intervalo_min": int(request.form.get("intervalo_min", 30)),
            "sync_auto": request.form.get("sync_auto") == "on",
        }
        config = save_config(data)
        setup_scheduler()
        saved = True
    return render_template("config.html", config=config, saved=saved)


@app.route("/api/sync", methods=["POST"])
def api_sync():
    thread = threading.Thread(target=run_sync)
    thread.daemon = True
    thread.start()
    return jsonify({"ok": True, "message": "Sincronización iniciada"})


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


@app.route("/api/mark-descargado/<order_id>", methods=["POST"])
def api_mark_descargado(order_id):
    mark_pdf_descargado(order_id)
    return jsonify({"ok": True})


@app.route("/api/debug")
def api_debug():
    vol = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "no definido")
    files = os.listdir(vol) if os.path.exists(vol) else []
    return jsonify({"volume": vol, "files": files})


if __name__ == "__main__":
    init_db()
    setup_scheduler()
    port = int(os.environ.get("PORT", 8081))
    app.run(host="0.0.0.0", port=port, debug=False)
