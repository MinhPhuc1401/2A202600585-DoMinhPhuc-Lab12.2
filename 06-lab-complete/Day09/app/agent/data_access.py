from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from collections import defaultdict
from langchain_core.tools import tool


class ShoppingDataStore:
    """Student scaffold for mock-data lookup."""

    def __init__(self, json_path: Path) -> None:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.metadata = data.get("metadata", {})
        self.customers = data.get("customers", [])
        self.orders = data.get("orders", [])
        self.vouchers = data.get("vouchers", [])

        # Build indexes for O(1) lookup
        self.customer_by_id = {c["customer_id"]: c for c in self.customers}
        self.order_by_id = {str(o["order_id"]): o for o in self.orders}

        # Index orders by customer_id
        self.orders_by_customer_id_map = defaultdict(list)
        for o in self.orders:
            self.orders_by_customer_id_map[o["customer_id"]].append(o)

        # Index vouchers by customer_id
        self.vouchers_by_customer_id_map = defaultdict(list)
        for v in self.vouchers:
            if "customer_id" in v:
                self.vouchers_by_customer_id_map[v["customer_id"]].append(v)

    def get_customer_by_id(self, customer_id: str) -> dict[str, Any]:
        if customer_id not in self.customer_by_id:
            return {"status": "not_found", "customer_id": customer_id}
        return {"status": "ok", "customer": self.customer_by_id[customer_id]}

    def get_orders_by_customer_id(self, customer_id: str, limit: int = 10) -> dict[str, Any]:
        if customer_id not in self.customer_by_id:
            return {"status": "not_found", "customer_id": customer_id}
        orders = self.orders_by_customer_id_map.get(customer_id, [])
        # Sort by creation date descending (newest first)
        sorted_orders = sorted(orders, key=lambda o: o.get("created_at", ""), reverse=True)
        return {"status": "ok", "orders": sorted_orders[:limit]}

    def get_order_detail_by_order_id(self, order_id: str) -> dict[str, Any]:
        oid = str(order_id).strip()
        if oid not in self.order_by_id:
            return {"status": "not_found", "order_id": order_id}
        return {"status": "ok", "order": self.order_by_id[oid]}

    def get_vouchers_by_customer_id(
        self,
        customer_id: str,
        only_active: bool = False,
    ) -> dict[str, Any]:
        if customer_id not in self.customer_by_id:
            return {"status": "not_found", "customer_id": customer_id}
        vouchers = self.vouchers_by_customer_id_map.get(customer_id, [])
        if only_active:
            vouchers = [v for v in vouchers if v.get("status") in ("active", "restored")]
        return {"status": "ok", "vouchers": vouchers}


def build_data_tools(store: ShoppingDataStore) -> list:
    @tool
    def get_customer_by_id(customer_id: str) -> str:
        """Tra cứu thông tin chi tiết của khách hàng dựa trên customer_id (ví dụ: 'C001').
        Trả về hạng thành viên (tier), thông tin liên hệ, hạn mức voucher (quota) và trạng thái tài khoản.
        """
        res = store.get_customer_by_id(customer_id)
        return json.dumps(res, ensure_ascii=False)

    @tool
    def get_orders_by_customer_id(customer_id: str, limit: int = 10) -> str:
        """Tra cứu danh sách đơn hàng gần đây của một khách hàng dựa trên customer_id (ví dụ: 'C001').
        """
        res = store.get_orders_by_customer_id(customer_id, limit)
        return json.dumps(res, ensure_ascii=False)

    @tool
    def get_order_detail_by_order_id(order_id: str) -> str:
        """Tra cứu thông tin chi tiết của một đơn hàng dựa trên order_id (ví dụ: '1971', '2058').
        Trả về trạng thái đơn hàng (order_status), ngày tạo, ngày giao dự kiến (estimated_delivery),
        danh sách sản phẩm (items), voucher đã áp dụng và hạn chót đổi trả (eligible_for_return_until).
        """
        res = store.get_order_detail_by_order_id(order_id)
        return json.dumps(res, ensure_ascii=False)

    @tool
    def get_vouchers_by_customer_id(customer_id: str, only_active: bool = False) -> str:
        """Tra cứu danh sách mã giảm giá (vouchers) của một khách hàng dựa trên customer_id (ví dụ: 'C001').
        Có thể lọc chỉ lấy các voucher còn hiệu lực (chưa sử dụng, chưa hết hạn) bằng cách đặt only_active=True.
        """
        res = store.get_vouchers_by_customer_id(customer_id, only_active)
        return json.dumps(res, ensure_ascii=False)

    return [get_customer_by_id, get_orders_by_customer_id, get_order_detail_by_order_id, get_vouchers_by_customer_id]
