"""
Servicio de sincronización Falabella → Lioren.
Solo emite boletas para órdenes en estado DELIVERED.
"""
import logging
from database import (
    add_log, order_exists, save_order,
    update_boleta, mark_error
)
from falabella_session import FalabellaSession
from falabella_orders import FalabellaOrdersClient
from lioren_client import LiorenClient

logger = logging.getLogger(__name__)


class SyncService:
    def __init__(self, config: dict):
        self.config = config
        self._session = None

    def _get_session(self) -> FalabellaSession:
        if self._session is None:
            self._session = FalabellaSession(
                self.config.get("fal_email", ""),
                self.config.get("fal_password", "")
            )
        return self._session

    def sync(self) -> dict:
        """
        Sincroniza órdenes delivered de Falabella y emite boletas.
        Retorna resumen {"procesadas": N, "emitidas": N, "errores": N}.
        """
        add_log("🔄 Iniciando sincronización Falabella → Lioren")
        result = {"procesadas": 0, "emitidas": 0, "errores": 0}

        # Validar config
        if not self.config.get("fal_email"):
            add_log("❌ Falta email de Falabella", "error")
            return result
        if not self.config.get("lioren_jwt"):
            add_log("❌ Falta JWT de Lioren", "error")
            return result

        # Obtener sesión Falabella
        session = self._get_session()
        if not session.ensure_authenticated():
            add_log("❌ No se pudo autenticar en Falabella", "error")
            return result

        # Obtener órdenes delivered
        orders_client = FalabellaOrdersClient(session)
        days_back = int(self.config.get("dias_atras", 7))
        delivered_orders = orders_client.get_delivered_orders(days_back=days_back)

        add_log(f"📦 {len(delivered_orders)} órdenes delivered encontradas")

        if not delivered_orders:
            add_log("✅ Sincronización completada — Sin órdenes nuevas")
            return result

        # Cliente Lioren
        lioren = LiorenClient(
            jwt_token=self.config["lioren_jwt"],
            rut_emisor=self.config.get("rut_emisor", ""),
            tipo_dte=int(self.config.get("tipo_dte", 39))
        )

        # Procesar cada orden delivered
        for order in delivered_orders:
            order_id = order["order_id"]
            result["procesadas"] += 1

            # Skip si ya procesada
            if order_exists(order_id):
                logger.debug(f"Orden {order_id} ya existe, saltando")
                continue

            # Guardar en BD
            save_order(order)

            # Emitir boleta
            try:
                boleta = lioren.emitir_boleta(order)
                update_boleta(order_id, boleta["folio"], boleta["pdf_url"])
                add_log(
                    f"✅ Boleta emitida — Orden {order_id} — "
                    f"Folio {boleta['folio']} — ${order['total_amount']:,.0f}"
                )
                result["emitidas"] += 1
            except Exception as e:
                mark_error(order_id, str(e))
                add_log(f"❌ Error orden {order_id}: {e}", "error")
                result["errores"] += 1

        add_log(
            f"✅ Sync completada — {result['emitidas']} boletas emitidas, "
            f"{result['errores']} errores"
        )
        return result
