import csv
import io
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date, time

from flask import Flask, Response, jsonify, render_template_string, request

app = Flask(__name__)

DB_PATH = os.environ.get("SCANNER_DB_PATH", os.path.join(os.path.dirname(__file__), "data", "scanner.db"))
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def now_local():
    # Serwer Render może pracować w UTC, dlatego aplikacja używa strefy Europe/Warsaw.
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Warsaw"))
    except Exception:
        return datetime.now()


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_date TEXT NOT NULL,
                pallet_no INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                closed_at TEXT,
                created_by TEXT NOT NULL,
                closed_by TEXT,
                UNIQUE(work_date, pallet_no)
            );

            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_date TEXT NOT NULL,
                code TEXT NOT NULL,
                pallet_id INTEGER NOT NULL,
                pallet_no INTEGER NOT NULL,
                device TEXT NOT NULL,
                scanned_at TEXT NOT NULL,
                is_duplicate INTEGER NOT NULL DEFAULT 0,
                duplicate_of_scan_id INTEGER,
                FOREIGN KEY(pallet_id) REFERENCES pallets(id),
                FOREIGN KEY(duplicate_of_scan_id) REFERENCES scans(id)
            );

            CREATE INDEX IF NOT EXISTS idx_scans_date_code ON scans(work_date, code);
            CREATE INDEX IF NOT EXISTS idx_scans_date_time ON scans(work_date, scanned_at);
            CREATE INDEX IF NOT EXISTS idx_scans_pallet ON scans(pallet_id);
            """
        )


init_db()


def norm_device(v):
    return " ".join(str(v or "").strip().upper().split()) or "NIEZNANY"


def norm_code(v):
    return str(v or "").strip()


def work_date_str():
    return now_local().date().isoformat()


def ts(dt=None):
    return (dt or now_local()).strftime("%Y-%m-%d %H:%M:%S")


def bucket_for(dt):
    t = dt.time().replace(microsecond=0)
    if time(6, 0) <= t < time(8, 1):
