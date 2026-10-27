"""Saving orders to SQLite and reading them back for reports."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from orders.order import Order
from orders.utils import CSV_FIELDS, export_orders_csv

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL,
    state TEXT NOT NULL, total TEXT NOT NULL, refunded TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_lines (order_id TEXT NOT NULL, sku TEXT NOT NULL,
    quantity INTEGER NOT NULL, unit_price TEXT NOT NULL);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the database at ``path`` (or ':memory:') and create the tables if needed."""
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def save_order(conn: sqlite3.Connection, order: Order) -> None:
    """Insert or update the order and its lines in one transaction."""
    header = (order.order_id, order.customer_id, order.state, str(order.total), str(order.refunded))
    lines = [(order.order_id, x.sku, x.quantity, str(x.unit_price)) for x in order.lines]
    try:
        with conn:
            conn.execute("INSERT OR REPLACE INTO orders VALUES (?, ?, ?, ?, ?)", header)
            conn.execute("DELETE FROM order_lines WHERE order_id = ?", (order.order_id,))
            conn.executemany("INSERT INTO order_lines VALUES (?, ?, ?, ?)", lines)
    except Exception:
        log.exception("could not save order %s", order.order_id)
        raise


def orders_by_ids(conn: sqlite3.Connection, order_ids: list[str]) -> list[tuple[str, str, str]]:
    """(order_id, customer_id, state) for each of the given ids that exists, by id."""
    if not order_ids:
        return []
    marks = ", ".join("?" for _ in order_ids)
    query = f"SELECT order_id, customer_id, state FROM orders WHERE order_id IN ({marks})"
    rows = conn.execute(query + " ORDER BY order_id", order_ids).fetchall()
    return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]


def export_csv(conn: sqlite3.Connection, path: Path) -> int:
    """Write every saved order to a CSV file at ``path``; returns how many were written."""
    cursor = conn.execute(
        "SELECT order_id, customer_id, state, total, refunded FROM orders ORDER BY order_id"
    )
    rows = (dict(zip(CSV_FIELDS, map(str, row), strict=True)) for row in cursor)
    return export_orders_csv(rows, path)
