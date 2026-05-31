"""Gestión de configuración persistente en volumen Railway."""
import json
import os

CONFIG_PATH = os.path.join(
    os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", os.path.dirname(os.path.abspath(__file__))),
    "fal_config.json"
)

DEFAULTS = {
    "fal_email": "",
    "fal_password": "",
    "lioren_email": "",
    "lioren_password": "",
    "lioren_jwt": "",
    "rut_emisor": "",
    "tipo_dte": 39,
    "dias_atras": 7,
    "intervalo_min": 30,
    "sync_auto": True,
}


def load_config() -> dict:
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as f:
                saved = json.load(f)
            config = dict(DEFAULTS)
            config.update(saved)
            return config
    except Exception:
        pass
    return dict(DEFAULTS)


def save_config(data: dict):
    config = load_config()
    config.update(data)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
    return config
