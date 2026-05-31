"""
Sesión Falabella via cookies guardadas en config.
Las cookies se inyectan manualmente desde el navegador autenticado.
"""
import json, logging, os, requests
from datetime import datetime

logger = logging.getLogger(__name__)
BASE_URL = "https://sellercenter.falabella.com"
HEADERS = {
    "x-channel-id": "WEB",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}

class FalabellaSession:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._logged_in = False

    def load_cookies_from_config(self):
        """Carga cookies guardadas via /api/set-cookies."""
        try:
            from config import load_config
            cfg = load_config()
            cookies = cfg.get("fal_cookies", {})
            if not cookies:
                logger.warning("No hay cookies guardadas en config")
                return False
            for k, v in cookies.items():
                self.session.cookies.set(k, v, domain=".sellercenter.falabella.com")
            self._logged_in = True
            logger.info(f"Cookies cargadas desde config: {len(cookies)}")
            return True
        except Exception as e:
            logger.error(f"Error cargando cookies: {e}")
            return False

    def ensure_authenticated(self):
        if self._logged_in:
            return True
        return self.load_cookies_from_config()

    def get(self, path, params=None):
        if not self.ensure_authenticated():
            return {"error": "No autenticado - carga cookies desde /api/set-cookies"}
        url = f"{BASE_URL}{path}"
        try:
            r = self.session.get(url, params=params, timeout=15)
            if r.status_code in (401, 403):
                self._logged_in = False
                return {"error": f"Sesión expirada ({r.status_code}) - recarga cookies"}
            return r.json()
        except Exception as e:
            return {"error": str(e)}
