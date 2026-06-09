"""
Cliente de órdenes Falabella.
Usa la API oficial via proxy del API Explorer para obtener órdenes delivered.
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class FalabellaOrdersClient:
    def __init__(self, session):
        self.session = session

    def get_delivered_orders(self, days_back=7):
        """Obtiene órdenes delivered via API oficial de Falabella."""
        date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        
        data = self.session.api_call("GetOrders", {"UpdatedAfter": date_from, "Status": "delivered"})
        logger.info(f"API GetOrders response: {str(data)[:200]}")
        
        orders = self._parse_api_response(data)
        delivered = [o for o in orders if o.get("status","").lower() in ("delivered","entregado")]
        if not delivered:
            delivered = orders

        # Obtener items reales por cada orden
        for order in delivered:
            try:
                items_data = self.session.api_call("GetOrderItems", {"OrderId": order["order_id"]})
                order["items"] = self._parse_order_items(items_data)
            except Exception as e:
                logger.error(f"Error obteniendo items de orden {order['order_id']}: {e}")

        logger.info(f"Órdenes delivered: {len(delivered)}")
        return delivered

    def _parse_order_items(self, data):
        """Parsea items de una orden."""
        items_raw = (
            data.get("SuccessResponse", {}).get("Body", {}).get("OrderItems", {}).get("OrderItem", [])
        )
        if isinstance(items_raw, dict):
            items_raw = [items_raw]
        if not items_raw:
            return []
        result = []
        for item in items_raw:
            result.append({
                "name": item.get("Name", "Producto")[:80],
                "quantity": 1,
                "unit_price": float(item.get("PaidPrice") or item.get("ItemPrice") or 0),
                "sku": item.get("Sku", ""),
            })
        return result

    def _parse_api_response(self, data):
        """Parsea respuesta XML/JSON de la API oficial de Falabella."""
        orders = []
        if not data or "error" in data:
            logger.error(f"Error en respuesta: {data}")
            return orders

        try:
            # Estructura de la API oficial de Falabella
            order_list = (
                data.get("SuccessResponse", {}).get("Body", {}).get("Orders", {}).get("Order", []) or
                data.get("Body", {}).get("Orders", {}).get("Order", []) or
                data.get("Orders", {}).get("Order", []) or
                []
            )
            
            if isinstance(order_list, dict):
                order_list = [order_list]
                
            for o in order_list:
                order = {
                    "order_id": str(o.get("OrderId") or o.get("OrderNumber") or ""),
                    "order_number": str(o.get("OrderNumber") or ""),
                    "status": str(o.get("Status") or o.get("OrderStatus") or "").lower(),
                    "buyer_name": f"{o.get('CustomerFirstName','')} {o.get('CustomerLastName','')}".strip() or "—",
                    "total_amount": float(o.get("Price") or o.get("Total") or 0),
                    "items": [{"name": "Venta Falabella", "quantity": 1, "unit_price": float(o.get("Price") or 0)}],
                    "created_at": o.get("CreatedAt") or "",
                    "delivered_at": o.get("UpdatedAt") or "",
                }
                orders.append(order)
        except Exception as e:
            logger.error(f"Error parseando órdenes: {e}, data={str(data)[:300]}")
        
        return orders
