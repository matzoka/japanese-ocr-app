import os
import sqlite3

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "ocr_history.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ocr_records (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            ocr_type    TEXT    NOT NULL,
            pages       INTEGER,
            source_path TEXT,
            ocr_text    TEXT,
            created_date TEXT   NOT NULL,
            created_time TEXT   NOT NULL,
            UNIQUE(title, ocr_type)
        )
    """)
    conn.commit()
    conn.close()


def upsert_record(title, ocr_type, pages, source_path, ocr_text, created_date, created_time):
    conn = _connect()
    existing = conn.execute(
        "SELECT id FROM ocr_records WHERE title = ? AND ocr_type = ?",
        (title, ocr_type)
    ).fetchone()

    if existing:
        conn.execute("""
            UPDATE ocr_records
               SET pages       = ?,
                   source_path = ?,
                   ocr_text    = ?,
                   created_date = ?,
                   created_time = ?
             WHERE id = ?
        """, (pages, source_path, ocr_text, created_date, created_time, existing["id"]))
    else:
        conn.execute("""
            INSERT INTO ocr_records
                (title, ocr_type, pages, source_path, ocr_text, created_date, created_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (title, ocr_type, pages, source_path, ocr_text, created_date, created_time))

    conn.commit()
    conn.close()


def search_records(query=None, limit=200):
    conn = _connect()
    if query:
        q = f"%{query}%"
        rows = conn.execute("""
            SELECT id, title, ocr_type, pages, source_path, created_date, created_time
              FROM ocr_records
             WHERE title LIKE ? OR ocr_text LIKE ?
             ORDER BY created_date DESC, created_time DESC
             LIMIT ?
        """, (q, q, limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT id, title, ocr_type, pages, source_path, created_date, created_time
              FROM ocr_records
             ORDER BY created_date DESC, created_time DESC
             LIMIT ?
        """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_record(record_id):
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM ocr_records WHERE id = ?", (record_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_record(record_id):
    conn = _connect()
    conn.execute("DELETE FROM ocr_records WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
