"""Base de datos SQLite para rastrear órdenes Falabella y boletas emitidas."""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(
    os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", os.path.dirname(os.path.abspath(__file__))),
    "fal_boletas.db"
)

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fal_order_id TEXT UNIQUE NOT NULL,
            fal_order_number TEXT,
            buyer_name TEXT,
            total_amount REAL DEFAULT 0,
            status TEXT DEFAULT 'delivered',
            boleta_status TEXT DEFAULT 'pendiente',
            boleta_folio TEXT,
            boleta_pdf_url TEXT,
            pdf_descargado INTEGER DEFAULT 0,
            items_json TEXT,
            created_at TEXT,
            delivered_at TEXT,
            processed_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            message TEXT,
            level TEXT DEFAULT 'info'
        )
    """)
    for col, defn in [("pdf_descargado","INTEGER DEFAULT 0"),("boleta_pdf_url","TEXT"),("delivered_at","TEXT")]:
        try:
            conn.execute(f"ALTER TABLE orders ADD COLUMN {col} {defn}")
        except Exception:
            pass
    conn.commit()
    conn.close()

def get_all_orders():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    emitidas = conn.execute("SELECT COUNT(*) FROM orders WHERE boleta_status='emitida'").fetchone()[0]
    errores = conn.execute("SELECT COUNT(*) FROM orders WHERE boleta_status='error'").fetchone()[0]
    monto = conn.execute("SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE boleta_status='emitida'").fetchone()[0]
    conn.close()
    return {"total": total, "emitidas": emitidas, "errores": errores, "monto_total": monto}

def get_logs(limit=50):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def order_exists(fal_order_id):
    conn = get_conn()
    row = conn.execute("SELECT id FROM orders WHERE fal_order_id=?", (fal_order_id,)).fetchone()
    conn.close()
    return row is not None

def save_order(order):
    import json
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO orders
        (fal_order_id, fal_order_number, buyer_name, total_amount, status, items_json, created_at, delivered_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (order["order_id"], order.get("order_number",""), order.get("buyer_name",""),
          order.get("total_amount",0), order.get("status","delivered"),
          json.dumps(order.get("items",[]), ensure_ascii=False),
          order.get("created_at",""), order.get("delivered_at","")))
    conn.commit()
    conn.close()

def update_boleta(fal_order_id, folio, pdf_url, status="emitida"):
    conn = get_conn()
    conn.execute("UPDATE orders SET boleta_status=?, boleta_folio=?, boleta_pdf_url=?, processed_at=? WHERE fal_order_id=?",
                 (status, folio, pdf_url, datetime.utcnow().isoformat(), fal_order_id))
    conn.commit()
    conn.close()

def mark_error(fal_order_id, msg):
    conn = get_conn()
    conn.execute("UPDATE orders SET boleta_status='error', processed_at=? WHERE fal_order_id=?",
                 (datetime.utcnow().isoformat(), fal_order_id))
    conn.commit()
    conn.close()

def mark_pdf_descargado(fal_order_id):
    conn = get_conn()
    conn.execute("UPDATE orders SET pdf_descargado=1 WHERE fal_order_id=?", (fal_order_id,))
    conn.commit()
    conn.close()

def add_log(message, level="info"):
    conn = get_conn()
    conn.execute("INSERT INTO logs (timestamp, message, level) VALUES (?,?,?)",
                 (datetime.now().strftime("%H:%M"), message, level))
    conn.execute("DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT 200)")
    conn.commit()
    conn.close()

def reset_errors():
    """Elimina órdenes con error para que sean reintentadas."""
    conn = get_conn()
    conn.execute("DELETE FROM orders WHERE boleta_status = 'error'")
    conn.commit()
    return conn.execute("SELECT changes()").fetchone()[0]
