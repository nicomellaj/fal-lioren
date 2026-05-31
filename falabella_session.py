import hashlib
import hmac
import os
from datetime import datetime, timezone
from urllib.parse import quote

import requests
import xmltodict


class FalabellaSession:
    def __init__(self):
        self.api_url = os.environ.get("FALABELLA_API_URL", "https://sellercenter-api.falabella.com")
        self.user_id = os.environ.get("FALABELLA_USER_ID", "")
        self.api_key = os.environ.get("FALABELLA_API_KEY", "")

    def _get_timestamp(self):
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"

    def _generate_signature(self, parameters):
        sorted_keys = sorted(parameters.keys())
        query = "&".join(
            f"{quote(str(k), safe="")}={quote(str(parameters[k]), safe=chr(0))}"
            for k in sorted_keys
        )
        return hmac.new(self.api_key.encode(), query.encode(), hashlib.sha256).hexdigest()

    def get_signed_url(self, action, extra_params=None):
        params = {"Format": "XML", "Timestamp": self._get_timestamp(), "UserID": self.user_id, "Version": "1.0", "Action": action}
        if extra_params:
            params.update(extra_params)
        params["Signature"] = self._generate_signature(params)
        return params

    def api_call(self, action, extra_params=None):
        params = self.get_signed_url(action, extra_params)
        response = requests.get(self.api_url, params=params, timeout=30)
        response.raise_for_status()
        return xmltodict.parse(response.text, force_list=False, attr_prefix="", cdata_key="text")

    def get_orders(self):
        parsed = self.api_call("GetOrders")
        orders = parsed.get("SuccessResponse", {}).get("Body", {}).get("Orders", {}).get("Order", [])
        return orders if isinstance(orders, list) else ([orders] if orders else [])

    def get_order_items(self, order_id):
        parsed = self.api_call("GetOrderItems", {"OrderId": str(order_id)})
        items = parsed.get("SuccessResponse", {}).get("Body", {}).get("OrderItems", {}).get("OrderItem", [])
        return items if isinstance(items, list) else ([items] if items else [])
