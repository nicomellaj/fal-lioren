"""Cliente Lioren.cl para emitir boletas desde órdenes Falabella."""
import logging
import requests

logger = logging.getLogger(__name__)

LIOREN_API = "https://www.lioren.cl/api/boletas"


class LiorenClient:
    def __init__(self, jwt_token: str, rut_emisor: str, tipo_dte: int = 39):
        self.jwt = jwt_token
        self.rut_emisor = rut_emisor
        self.tipo_dte = tipo_dte
        self.headers = {
            "Authorization": f"Bearer {self.jwt}",
            "Content-Type": "application/json"
        }

    def emitir_boleta(self, order: dict) -> dict:
        """
        Emite boleta DTE 39 para una orden Falabella delivered.
        Retorna {"folio": X, "pdf_url": "..."} o lanza excepción.
        """
        items = order.get("items", [])
        if not items:
            items = [{"name": "Venta Falabella", "quantity": 1, "unit_price": order.get("total_amount", 0)}]

        detalle = []
        for item in items:
            precio = round(float(item.get("unit_price", 0)))
            qty = int(item.get("quantity", 1))
            if precio <= 0:
                continue
            detalle.append({
                "NmbItem": item.get("name", "Producto")[:80],
                "QtyItem": qty,
                "PrcItem": precio,
            })

        if not detalle:
            raise ValueError("Sin items válidos para emitir boleta")

        payload = {
            "Encabezado": {
                "IdDoc": {
                    "TipoDTE": self.tipo_dte,
                    "Folio": 0,
                },
                "Emisor": {
                    "RUTEmisor": self.rut_emisor,
                },
            },
            "Detalle": detalle,
        }

        r = requests.post(LIOREN_API, json=payload, headers=self.headers, timeout=30)

        if r.status_code not in (200, 201):
            raise Exception(f"Lioren error {r.status_code}: {r.text[:200]}")

        data = r.json()

        folio = (
            data.get("folio") or
            data.get("Folio") or
            data.get("data", {}).get("folio") or
            ""
        )
        pdf_url = (
            data.get("urlPdf") or
            data.get("pdf_url") or
            data.get("data", {}).get("urlPdf") or
            ""
        )

        if not folio:
            raise Exception(f"Lioren no retornó folio: {data}")

        logger.info(f"✅ Boleta emitida — Orden {order['order_id']} — Folio {folio}")
        return {"folio": str(folio), "pdf_url": pdf_url}
