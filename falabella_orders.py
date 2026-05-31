"""
Cliente de órdenes Falabella Seller Center.
Solo procesa órdenes en estado 'delivered' para emitir boletas.
"""
import logging
from datetime import datetime, timedelta
from falabella_session import FalabellaSession

logger = logging.getLogger(__name__)

# Estados de Falabella Seller Center
STATUS_DELIVERED = "delivered"
STATUS_MAP = {
    "pending": "Pendiente",
    "ready_to_ship": "Listo para envío",
    "shipped": "Enviado",
    "delivered": "Entregado",
    "canceled": "Cancelado",
    "failed_delivery": "Fallo entrega",
    "returned": "Devuelto",
}


class FalabellaOrdersClient:
    def __init__(self, session: FalabellaSession):
        self.session = session

    def get_delivered_orders(self, days_back: int = 7) -> list:
        """
        Obtiene órdenes en estado 'delivered' de los últimos N días.
        Solo estas órdenes deben generar boleta.
        """
        orders = []

        # Intentar endpoint v1
        try:
            data = self.session.get(
                "/s/order/v1/fetchOrderMetaData",
                params={"status": STATUS_DELIVERED}
            )
            if "errors" not in data:
                logger.info(f"Metadata órdenes: {data}")

            # Buscar el endpoint real de listado
            data = self._fetch_order_list(days_back)
            orders = self._parse_orders(data)
        except Exception as e:
            logger.error(f"Error obteniendo órdenes: {e}")

        # Filtrar solo delivered
        delivered = [o for o in orders if o.get("status") == STATUS_DELIVERED]
        logger.info(f"Órdenes delivered encontradas: {len(delivered)}")
        return delivered

    def _fetch_order_list(self, days_back: int) -> dict:
        """Intenta múltiples endpoints para obtener la lista de órdenes."""
        date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        # Endpoints a probar en orden
        endpoints = [
            f"/s/order/v1/fetchOrderList?status={STATUS_DELIVERED}&limit=50&offset=0",
            f"/s/order/v1/orders?status={STATUS_DELIVERED}&limit=50&offset=0&dateFrom={date_from}",
            f"/s/order/v2/fetchOrderList?status={STATUS_DELIVERED}&limit=50",
            f"/s/order/v1/getOrderList?status={STATUS_DELIVERED}&limit=50",
        ]

        for endpoint in endpoints:
            data = self.session.get(endpoint)
            if "errors" in data:
                err = data["errors"][0].get("code", "")
                if err == "INVALID_ENDPOINT":
                    continue
            # Si llegamos aquí y hay data útil
            if data and "errors" not in data:
                logger.info(f"Endpoint funcional: {endpoint}")
                return data

        logger.warning("No se encontró endpoint de listado, usando HTML scraping")
        return self._scrape_orders_html(days_back)

    def _scrape_orders_html(self, days_back: int) -> dict:
        """Fallback: scraping de la página HTML de órdenes."""
        try:
            from playwright.sync_api import sync_playwright
            import json as json_lib

            orders = []
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()

                # Restaurar cookies
                cookies = []
                for cookie in self.session.session.cookies:
                    cookies.append({
                        "name": cookie.name,
                        "value": cookie.value,
                        "domain": ".sellercenter.falabella.com",
                        "path": "/"
                    })
                context.add_cookies(cookies)

                page = context.new_page()

                # Interceptar llamadas de red
                api_responses = []
                def handle_response(response):
                    if "/s/order/" in response.url and response.status == 200:
                        try:
                            body = response.json()
                            api_responses.append({"url": response.url, "data": body})
                        except Exception:
                            pass

                page.on("response", handle_response)
                page.goto("https://sellercenter.falabella.com/index.php?controller=order&action=viewOrders", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=15000)

                # Esperar que carguen los datos
                import time
                time.sleep(3)

                browser.close()

                if api_responses:
                    logger.info(f"Interceptadas {len(api_responses)} respuestas de API")
                    for resp in api_responses:
                        logger.info(f"URL: {resp['url']}, keys: {list(resp['data'].keys())}")
                    return api_responses[0]["data"] if api_responses else {}

        except Exception as e:
            logger.error(f"Error scraping: {e}")

        return {}

    def _parse_orders(self, data: dict) -> list:
        """Parsea la respuesta de la API a formato estándar."""
        orders = []

        if not data or not isinstance(data, dict):
            return orders

        # Buscar lista de órdenes en diferentes estructuras posibles
        order_list = (
            data.get("data", {}).get("orders", []) or
            data.get("orders", []) or
            data.get("data", []) or
            []
        )

        for o in order_list:
            try:
                order = {
                    "order_id": str(o.get("orderId") or o.get("order_id") or o.get("id", "")),
                    "order_number": str(o.get("orderNumber") or o.get("order_number") or ""),
                    "status": (o.get("status") or o.get("orderStatus") or "").lower(),
                    "buyer_name": self._get_buyer_name(o),
                    "total_amount": float(o.get("price") or o.get("total") or o.get("totalAmount") or 0),
                    "items": self._get_items(o),
                    "created_at": o.get("createdAt") or o.get("created_at") or "",
                    "delivered_at": o.get("deliveredAt") or o.get("delivered_at") or "",
                    "raw": o,
                }
                orders.append(order)
            except Exception as e:
                logger.error(f"Error parseando orden: {e}")

        return orders

    def _get_buyer_name(self, o: dict) -> str:
        first = o.get("customerFirstName") or o.get("firstName") or ""
        last = o.get("customerLastName") or o.get("lastName") or ""
        if first or last:
            return f"{first} {last}".strip()
        return o.get("buyerName") or o.get("buyer_name") or "—"

    def _get_items(self, o: dict) -> list:
        items = o.get("orderItems") or o.get("items") or []
        result = []
        for item in items:
            result.append({
                "name": item.get("name") or item.get("productName") or "Producto",
                "quantity": int(item.get("quantity") or item.get("qty") or 1),
                "unit_price": float(item.get("price") or item.get("unitPrice") or 0),
            })
        if not result:
            total = float(o.get("price") or o.get("total") or 0)
            result = [{"name": "Venta Falabella", "quantity": 1, "unit_price": total}]
        return result
