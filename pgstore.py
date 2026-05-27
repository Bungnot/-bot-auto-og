"""
pgstore.py - แทนที่การอ่าน/เขียน JSON ไฟล์ด้วย PostgreSQL
ใช้ตาราง kv_store เก็บข้อมูลแบบ key-value
"""
import os
import json
import psycopg2
from psycopg2.extras import Json

DATABASE_URL = os.getenv("DATABASE_URL", "")

def _get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def _init_table():
    """สร้างตารางถ้ายังไม่มี"""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value JSONB,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"PGSTORE INIT ERROR: {e}")

def load(key: str, default=None):
    """โหลดข้อมูลจาก PostgreSQL"""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT value FROM kv_store WHERE key = %s", (key,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return row[0]
        return default
    except Exception as e:
        print(f"PGSTORE LOAD ERROR [{key}]: {e}")
        return default

def save(key: str, data):
    """บันทึกข้อมูลลง PostgreSQL"""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO kv_store (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, updated_at = NOW()
        """, (key, Json(data)))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"PGSTORE SAVE ERROR [{key}]: {e}")
        return False

# สร้างตารางตอน import
_init_table()
