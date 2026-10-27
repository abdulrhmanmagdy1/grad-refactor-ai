import csv
from datetime import date
from pathlib import Path

from orders.cart import Cart
from orders.catalog import Catalog
from orders.checkout import Checkout
from orders.coupons import CouponBook
from orders.order import OrderBook
from orders.store import connect, export_csv, orders_by_ids, save_order


def test_saved_orders_can_be_read_and_exported(catalog: Catalog, tmp_path: Path) -> None:
    book = OrderBook(catalog)
    checkout = Checkout(book, CouponBook())
    for customer_id in ["c1", "c2"]:
        cart = Cart(customer_id)
        cart.add(catalog.variant("MUG"))
        checkout.place_order(cart, "DE", date(2026, 6, 1))
    conn = connect(tmp_path / "shop.db")
    for order in book.orders.values():
        save_order(conn, order)
    save_order(conn, book.get("ORD-00001"))

    rows = orders_by_ids(conn, ["ORD-00002", "ORD-00001", "ORD-09999"])
    assert rows == [("ORD-00001", "c1", "placed"), ("ORD-00002", "c2", "placed")]
    assert orders_by_ids(conn, []) == []

    target = tmp_path / "orders.csv"
    assert export_csv(conn, target) == 2
    with target.open(newline="", encoding="utf-8") as handle:
        exported = list(csv.DictReader(handle))
    assert exported[0]["total"] == "17.30"
    conn.close()
