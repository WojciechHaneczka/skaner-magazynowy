import os, sqlite3, csv, io
from datetime import datetime, time
from contextlib import contextmanager
from flask import Flask, request, jsonify, render_template_string, Response

app = Flask(__name__)
DB_PATH = os.environ.get('SCANNER_DB_PATH') or '/tmp/scanner.db'


def now_local():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo('Europe/Warsaw'))
    except Exception:
        return datetime.now()


def stamp(dt=None):
    return (dt or now_local()).strftime('%Y-%m-%d %H:%M:%S')


def work_date():
    return now_local().date().isoformat()


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS pallets(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          work_date TEXT NOT NULL,
          pallet_no INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'open',
          created_at TEXT NOT NULL,
          closed_at TEXT,
          created_by TEXT,
          closed_by TEXT,
          UNIQUE(work_date,pallet_no)
        );
        CREATE TABLE IF NOT EXISTS scans(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          work_date TEXT NOT NULL,
          code TEXT NOT NULL,
          pallet_id INTEGER NOT NULL,
          pallet_no INTEGER NOT NULL,
          device TEXT NOT NULL,
          scanned_at TEXT NOT NULL,
          is_duplicate INTEGER NOT NULL DEFAULT 0,
          duplicate_of_scan_id INTEGER
        );
        CREATE INDEX IF NOT EXISTS ix_scans_date_code ON scans(work_date,code);
        CREATE INDEX IF NOT EXISTS ix_scans_pallet ON scans(pallet_id);
        ''')


init_db()


def bucket(ts):
    t=datetime.strptime(ts,'%Y-%m-%d %H:%M:%S').time()
    if time(6,0)<=t<=time(8,0,59): return '06:00–08:00'
    if time(8,1)<=t<=time(10,0,59): return '08:01–10:00'
    if time(10,1)<=t<=time(12,0,59): return '10:01–12:00'
    if time(12,1)<=t<=time(13,30,59): return '12:01–13:30'
    return 'Poza zakresem'

PERIODS=['06:00–08:00','08:01–10:00','10:01–12:00','12:01–13:30']


def active_pallet(c,d):
    return c.execute("SELECT * FROM pallets WHERE work_date=? AND status='open' ORDER BY pallet_no DESC LIMIT 1",(d,)).fetchone()


def pallet_count(c,pid):
    return c.execute('SELECT COUNT(*) n FROM scans WHERE pallet_id=? AND is_duplicate=0',(pid,)).fetchone()['n']


def report(c,d):
    scans=c.execute('SELECT * FROM scans WHERE work_date=? ORDER BY id',(d,)).fetchall()
    pallets=c.execute('SELECT * FROM pallets WHERE work_date=? ORDER BY pallet_no',(d,)).fetchall()
    p={x:{'name':x,'cartons':0,'duplicates':0,'pallets':set(),'closed':0} for x in PERIODS}
    outside={'name':'Poza zakresem','cartons':0,'duplicates':0,'pallets':set(),'closed':0}
    for s in scans:
        b=bucket(s['scanned_at']); target=p.get(b,outside); target['pallets'].add(s['pallet_id'])
