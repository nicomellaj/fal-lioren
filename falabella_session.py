"""
Manejo de sesión Falabella Seller Center via Playwright.
Login SSO Keycloak → cookies → llamadas a API interna /s/order/
"""
import json
import logging
import os
import time
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

SESSION_FILE = os.path.join(
    os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", os.path.dirname(os.path.abspath(__file__))),
    "fal_session.json"
)

BASE_URL = "https://sellercenter.falabella.com"
HEADERS_BASE = {
    "x-channel-id": "WEB",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


class FalabellaSession:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self._logged_in = False

    def login(self) -> bool:
        """Login via Playwright y guarda cookies en requests.Session."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright no instalado")
            return False

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()

                logger.info("Navegando al login de Falabella...")
                page.goto(f"{BASE_URL}/", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=15000)

                # Ingresar email
                page.fill('input[type="text"], input[type="email"]', self.email)
                page.click('button[type="submit"]')
                page.wait_for_load_state("networkidle", timeout=10000)

                # Si pide contraseña
                try:
                    pwd_field = page.locator('input[type="password"]')
                    if pwd_field.count() > 0:
                        pwd_field.fill(self.password)
                        page.click('button[type="submit"]')
                        page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

                # Esperar dashboard
                time.sleep(3)
                current_url = page.url
                logger.info(f"URL después de login: {current_url}")

                if "auth/login" in current_url:
                    logger.error("Login fallido — aún en página de login")
                    browser.close()
                    return False

                # Extraer cookies
                cookies = context.cookies()
                browser.close()

                # Cargar cookies en requests.Session
                for cookie in cookies:
                    self.session.cookies.set(
                        cookie["name"],
                        cookie["value"],
                        domain=cookie.get("domain", ".sellercenter.falabella.com")
                    )

                self.session.headers.update(HEADERS_BASE)
                self._logged_in = True

                # Guardar cookies en disco para reutilizar
                self._save_session(cookies)
                logger.info("✅ Login Falabella exitoso")
                return True

        except Exception as e:
            logger.error(f"Error en login Falabella: {e}")
            return False

    def _save_session(self, cookies):
        try:
            data = {
                "cookies": cookies,
                "timestamp": datetime.utcnow().isoformat()
            }
            with open(SESSION_FILE, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.error(f"Error guardando sesión: {e}")

    def load_session(self) -> bool:
        """Intenta cargar sesión guardada en disco."""
        try:
            if not os.path.exists(SESSION_FILE):
                return False
            with open(SESSION_FILE) as f:
                data = json.load(f)

            # Sesión válida por máximo 2 horas
            ts = datetime.fromisoformat(data["timestamp"])
            age = (datetime.utcnow() - ts).total_seconds()
            if age > 7200:
                logger.info("Sesión expirada, re-login necesario")
                return False

            for cookie in data["cookies"]:
                self.session.cookies.set(
                    cookie["name"],
                    cookie["value"],
                    domain=cookie.get("domain", ".sellercenter.falabella.com")
                )
            self.session.headers.update(HEADERS_BASE)
            self._logged_in = True
            logger.info("Sesión Falabella cargada desde disco")
            return True
        except Exception as e:
            logger.error(f"Error cargando sesión: {e}")
            return False

    def get(self, path: str, params: dict = None) -> dict:
        """GET a la API interna de Falabella."""
        if not self._logged_in:
            if not self.load_session():
                if not self.login():
                    return {"error": "No autenticado"}

        url = f"{BASE_URL}{path}"
        try:
            r = self.session.get(url, params=params, timeout=15)
            if r.status_code == 401:
                logger.info("Sesión expirada, re-login...")
                self._logged_in = False
                if self.login():
                    r = self.session.get(url, params=params, timeout=15)
                else:
                    return {"error": "Re-login fallido"}
            return r.json()
        except Exception as e:
            logger.error(f"Error GET {path}: {e}")
            return {"error": str(e)}

    def ensure_authenticated(self) -> bool:
        if self._logged_in:
            return True
        if self.load_session():
            return True
        return self.login()
