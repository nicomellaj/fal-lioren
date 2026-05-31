"""
Sesión Falabella via requests + login Keycloak SSO.
Sin Playwright - compatible con Railway sin dependencias de browser.
"""
import json, logging, os, requests
from datetime import datetime

logger = logging.getLogger(__name__)

SESSION_FILE = os.path.join(
    os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", os.path.dirname(os.path.abspath(__file__))),
    "fal_session.json"
)

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

    def login(self):
        try:
            s = self.session
            # 1. GET login page para obtener cookies iniciales
            r = s.get(f"{BASE_URL}/", timeout=15, allow_redirects=True)
            
            # 2. Encontrar URL de login Keycloak
            if "auth/login" in r.url or "keycloak" in r.url:
                login_url = r.url
            else:
                r2 = s.get(f"{BASE_URL}/user/auth/login", timeout=15, allow_redirects=True)
                login_url = r2.url
            
            logger.info(f"Login URL: {login_url}")
            
            # 3. POST credenciales
            login_data = {"username": self.email, "password": self.password}
            r3 = s.post(login_url, data=login_data, timeout=15, allow_redirects=True)
            
            # 4. Verificar login exitoso
            if "auth/login" in r3.url and "error" in r3.text.lower():
                logger.error("Login fallido - credenciales incorrectas")
                return False
            
            self._logged_in = True
            self._save_session()
            logger.info("Login Falabella exitoso")
            return True
        except Exception as e:
            logger.error(f"Error login: {e}")
            return False

    def _save_session(self):
        try:
            cookies = {c.name: c.value for c in self.session.cookies}
            with open(SESSION_FILE, "w") as f:
                json.dump({"cookies": cookies, "ts": datetime.utcnow().isoformat()}, f)
        except Exception as e:
            logger.error(f"Error guardando sesión: {e}")

    def load_session(self):
        try:
            if not os.path.exists(SESSION_FILE):
                return False
            with open(SESSION_FILE) as f:
                data = json.load(f)
            age = (datetime.utcnow() - datetime.fromisoformat(data["ts"])).total_seconds()
            if age > 3600:
                return False
            for k, v in data["cookies"].items():
                self.session.cookies.set(k, v)
            self._logged_in = True
            return True
        except Exception:
            return False

    def ensure_authenticated(self):
        if self._logged_in:
            return True
        if self.load_session():
            return True
        return self.login()

    def get(self, path, params=None):
        if not self.ensure_authenticated():
            return {"error": "No autenticado"}
        url = f"{BASE_URL}{path}"
        try:
            r = self.session.get(url, params=params, timeout=15)
            if r.status_code == 401:
                self._logged_in = False
                if self.login():
                    r = self.session.get(url, params=params, timeout=15)
            return r.json()
        except Exception as e:
            return {"error": str(e)}
