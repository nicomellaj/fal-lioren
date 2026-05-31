"""Cliente Lioren.cl para emitir boletas desde ordenes Falabella."""
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

LIOREN_API = "https://www.lioren.cl/api/boletas"


class LiorenClient:
    def __init__(self, jwt_token: str, rut_emisor: str, tipo_dte: int = 39):
        self.jwt = jwt_token
        self.rut_emisor = rut_emisor
        self.tipo_dte = tipo_dte
        self.headers = {
            "Authorization": f"Bearer {self.jwt}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def emitir_boleta(self, order: dict) -> dict:
        items = order.get("items", [])
        if not items:
            items = [{"name": "Venta Falabella", "quantity": 1, "unit_price": order.get("total_amount", 0)}]

        detalles = []
        for item in items:
            precio = round(float(item.get("unit_price", 0)))
            qty = int(item.get("quantity", 1))
            if precio <= 0:
                continue
            detalles.append({
                "nombre": item.get("name", "Producto")[:80],
                "cantidad": qty,
                "precio": precio,
                "exento": False,
            })

        if not detalles:
            raise ValueError("Sin items validos para emitir boleta")

        payload = {
            "emisor": {
                "tipodoc": str(self.tipo_dte),
                "servicio": 3,
                "fecha": datetime.now().strftime("%Y-%m-%d"),
            },
            "receptor": {
                "rut": "66666666-6",
                "rs": "Consumidor Final",
            },
            "detalles": detalles,
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
            raise Exception(f"Lioren no retorno folio: {data}")

        logger.info(f"Boleta emitida Orden {order['order_id']} Folio {folio}")
        return {"folio": str(folio), "pdf_url": pdf_url}
