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
          if s['is_duplicate']: target['duplicates']+=1
        else: target['cartons']+=1
    for pal in pallets:
        if pal['closed_at']:
            b=bucket(pal['closed_at']); p.get(b,outside)['closed']+=1
    rows=[]
    for x in PERIODS:
        v=p[x]; rows.append({'name':x,'cartons':v['cartons'],'duplicates':v['duplicates'],'pallets_touched':len(v['pallets']),'pallets_closed':v['closed']})
    return {
      'date':d,
      'unique':sum(1 for s in scans if not s['is_duplicate']),
      'duplicates':sum(1 for s in scans if s['is_duplicate']),
      'total_scans':len(scans),
      'pallets':{'total':len(pallets),'closed':sum(1 for x in pallets if x['status']=='closed')},
      'periods':rows
    }

HTML='''<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Skaner magazynowy</title><style>
*{box-sizing:border-box}body{margin:0;background:#08111f;color:#fff;font-family:Arial,sans-serif}.wrap{max-width:1300px;margin:auto;padding:16px}.top{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}.muted{color:#9fb0c5}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}button,input{font:inherit}.btn,.tabs button{background:#14243a;color:white;border:1px solid #29405f;border-radius:10px;padding:11px 14px;font-weight:700;cursor:pointer}.tabs .active,.primary{background:#2563eb}.success{background:#15803d}.danger{background:#991b1b}.page{display:none}.page.active{display:block}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.card,.panel{background:#0f1c2e;border:1px solid #263a55;border-radius:14px;padding:15px}.card strong{display:block;font-size:32px;margin-top:5px}.layout{display:grid;grid-template-columns:1.15fr .85fr;gap:12px;margin-top:12px}.pallet{border:2px solid #2563eb;background:#0a1424;border-radius:14px;padding:15px;display:flex;justify-content:space-between;gap:10px}.big{font-size:36px;font-weight:900}.status{margin-top:12px;min-height:110px;display:flex;align-items:center;justify-content:center;flex-direction:column;text-align:center;border-radius:14px;background:#17263b;font-size:28px;font-weight:900;padding:12px}.ok{background:#14532d}.bad{background:#7f1d1d}.warn{background:#78350f}.scan{width:100%;margin-top:10px;padding:16px;border-radius:12px;border:2px solid #355070;background:#07111f;color:#fff;font-size:23px}.actions{display:flex;gap:8px;margin-top:10px}.actions button{flex:1}.periods{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:12px}.period{background:#0b1728;border:1px solid #263a55;border-radius:12px;padding:12px}.period b{font-size:28px}.scroll{max-height:450px;overflow:auto}table{width:100%;border-collapse:collapse}th,td{padding:9px;border-bottom:1px solid #24364f;text-align:left;font-size:13px}.pill{padding:3px 7px;border-radius:999px;font-weight:700}.pill.ok{background:#14532d}.pill.bad{background:#7f1d1d}.pallets{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.pc{background:#0b1728;border:1px solid #263a55;border-radius:12px;padding:12px;cursor:pointer}.modal{position:fixed;inset:0;background:#020617e8;display:none;align-items:center;justify-content:center}.modal>div{background:#0f1c2e;padding:20px;border-radius:14px;width:min(480px,90vw)}.modal input{width:100%;padding:12px;margin:10px 0;background:#07111f;color:#fff;border:1px solid #263a55;border-radius:10px}@media(max-width:800px){.grid,.periods{grid-template-columns:1fr 1fr}.layout{grid-template-columns:1fr}.pallets{grid-template-columns:1fr 1fr}}</style></head><body><div class="wrap">
<div class="top"><div><h1 style="margin:0">SKANER MAGAZYNOWY</h1><div class="muted">Kartony • Palety • Duplikaty • Historia</div></div><div><b id="devLabel">...</b> <button class="btn" onclick="changeDev()">zmień</button></div></div>
<div class="tabs"><button class="active" data-p="scanp">Skanowanie</button><button data-p="palp">Palety</button><button data-p="histp">Historia dni</button><button data-p="repp">Raport</button></div>
<section id="scanp" class="page active"><div class="grid"><div class="card">Kartony<strong id="ku">0</strong></div><div class="card">Palety<strong id="kp">0</strong></div><div class="card">Duplikaty<strong id="kd">0</strong></div><div class="card">Wszystkie skany<strong id="kt">0</strong></div></div><div class="layout"><div class="panel"><div id="active"></div><div id="status" class="status">GOTOWY DO SKANOWANIA</div><input id="code" class="scan" placeholder="Zeskanuj kod EAN i Enter" autocomplete="off"><div class="actions"><button id="start" class="btn success">ROZPOCZNIJ KOLEJNĄ PALETĘ</button><button id="close" class="btn danger">ZAKOŃCZ PALETĘ</button></div></div><div class="panel"><h3>Ostatnie skany</h3><div class="scroll"><table><thead><tr><th>Czas</th><th>Paleta</th><th>Kod</th><th>Status</th></tr></thead><tbody id="rows"></tbody></table></div></div></div><div id="periods" class="periods"></div></section>
<section id="palp" class="page"><div class="panel"><input type="date" id="pdate"><button class="btn" onclick="loadPallets()">Pokaż</button><div id="pcards" class="pallets" style="margin-top:12px"></div><div id="pdetail" style="margin-top:12px"></div></div></section>
<section id="histp" class="page"><div class="panel"><table><thead><tr><th>Data</th><th>Kartony</th><th>Palety</th><th>Duplikaty</th><th>Skany</th></tr></thead><tbody id="days"></tbody></table></div></section>
<section id="repp" class="page"><div class="panel"><input type="date" id="rdate"><button class="btn" onclick="loadReport()">Pokaż</button><button class="btn" onclick="exportCsv()">Eksport CSV</button><div id="rep" style="margin-top:12px"></div></div></section></div>
<div id="modal" class="modal"><div><h2>Nazwa operatora / skanera</h2><input id="dev" placeholder="np. VOVA / SKANER 01"><button class="btn primary" onclick="saveDev()">Zapisz</button></div></div>
<script>
let state=null,device=localStorage.getItem('warehouse_device_name')||'';const q=x=>document.getElementById(x),esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));function changeDev(){q('dev').value=device;q('modal').style.display='flex'}function saveDev(){device=q('dev').value.trim().toUpperCase();if(!device)return;localStorage.setItem('warehouse_device_name',device);q('devLabel').textContent=device;q('modal').style.display='none';q('code').focus()}if(device)q('devLabel').textContent=device;else changeDev();
async function api(u,o){let r=await fetch(u,o),x=await r.json();if(!r.ok)throw Error(x.error||'Błąd');return x}function msg(cls,html,ms=1000){q('status').className='status '+cls;q('status').innerHTML=html;setTimeout(()=>{q('status').className='status';q('status').textContent='GOTOWY DO SKANOWANIA';q('code').focus()},ms)}function beep(f=900,d=.1){try{let c=new(AudioContext||webkitAudioContext)(),o=c.createOscillator();o.frequency.value=f;o.connect(c.destination);o.start();setTimeout(()=>{o.stop();c.close()},d*1000)}catch(e){}}
async function refresh(){state=await api('/api/state');q('ku').textContent=state.unique;q('kp').textContent=state.pallets.total;q('kd').textContent=state.duplicates;q('kt').textContent=state.total_scans;q('start').disabled=!!state.active_pallet;q('close').disabled=!state.active_pallet;q('code').disabled=!state.active_pallet;q('active').innerHTML=state.active_pallet?`<div class="pallet"><div><div class="muted">AKTYWNA PALETA</div><div class="big">PALETA ${state.active_pallet.pallet_no}</div></div><div><div class="muted">KARTONY</div><div class="big">${state.active_pallet.cartons}</div></div></div>`:`<div class="pallet"><div><div class="muted">BRAK AKTYWNEJ PALETY</div><div class="big">Następna: ${state.next_pallet_no}</div></div></div>`;q('rows').innerHTML=state.history.map(v=>`<tr><td>${v.time}</td><td>${v.pallet_no}</td><td>${esc(v.code)}</td><td><span class="pill ${v.duplicate?'bad':'ok'}">${v.duplicate?'DUPLIKAT':'OK'}</span></td></tr>`).join('');q('periods').innerHTML=state.periods.map(p=>`<div class="period"><div>${p.name}</div><b>${p.cartons}</b><div>kartonów</div><div class="muted">Palety: ${p.pallets_touched} | zakończone: ${p.pallets_closed}</div></div>`).join('');if(state.active_pallet)q('code').focus()}
q('start').onclick=async()=>{try{let x=await api('/api/pallet/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device})});msg('ok','PALETA '+x.pallet_no+' ROZPOCZĘTA',700);refresh()}catch(e){msg('warn',esc(e.message),1800)}};q('close').onclick=async()=>{try{let x=await api('/api/pallet/close',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({device})});msg('ok',`PALETA ${x.closed_pallet_no} ZAKOŃCZONA<br><small>${x.cartons} kartonów</small>`,1100);refresh()}catch(e){msg('warn',esc(e.message),1800)}};q('code').addEventListener('keydown',async e=>{if(e.key!=='Enter')return;let c=q('code').value.trim();q('code').value='';if(!c||!state?.active_pallet)return;try{let x=await api('/api/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:c,device,pallet_id:state.active_pallet.id})});if(x.duplicate){msg('bad',`DUPLIKAT<br><small>Paleta ${x.first_pallet_no} • ${x.first_time} • ${x.first_device}</small>`,3000);beep(180,.8);if(navigator.vibrate)navigator.vibrate([300,100,500])}else{msg('ok','OK ✓',600);beep()}refresh()}catch(e){msg('warn',esc(e.message),1800)}});
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.remove('active'));document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));b.classList.add('active');q(b.dataset.p).classList.add('active');if(b.dataset.p==='palp')loadPallets();if(b.dataset.p==='histp')loadDays();if(b.dataset.p==='repp')loadReport()});
async function loadPallets(){let d=q('pdate').value;let x=await api('/api/pallets?date='+d);q('pcards').innerHTML=x.pallets.map(p=>`<div class="pc" onclick="showP(${p.id})"><b>Paleta ${p.pallet_no}</b><div class="big">${p.cartons}</div><div class="muted">kartonów • ${p.status}</div></div>`).join('')||'<div class="muted">Brak palet</div>'}async function showP(id){let x=await api('/api/pallet/'+id);q('pdetail').innerHTML=`<div class="panel"><h3>Paleta ${x.pallet.pallet_no}</h3><table><tr><th>Czas</th><th>Kod</th><th>Operator</th><th>Status</th></tr>${x.scans.map(s=>`<tr><td>${s.time}</td><td>${esc(s.code)}</td><td>${esc(s.device)}</td><td>${s.duplicate?'DUPLIKAT':'OK'}</td></tr>`).join('')}</table></div>`}async function loadDays(){let x=await api('/api/days');q('days').innerHTML=x.days.map(d=>`<tr><td>${d.date}</td><td>${d.unique}</td><td>${d.pallets}</td><td>${d.duplicates}</td><td>${d.total}</td></tr>`).join('')}async function loadReport(){let d=q('rdate').value,x=await api('/api/report?date='+d);q('rep').innerHTML=`<div class="grid"><div class="card">Kartony<strong>${x.unique}</strong></div><div class="card">Palety<strong>${x.pallets.total}</strong></div><div class="card">Duplikaty<strong>${x.duplicates}</strong></div><div class="card">Skany<strong>${x.total_scans}</strong></div></div><div class="periods">${x.periods.map(p=>`<div class="period"><div>${p.name}</div><b>${p.cartons}</b><div>kartonów</div></div>`).join('')}</div>`}function exportCsv(){location.href='/api/export.csv?date='+q('rdate').value}let today=new Date().toISOString().slice(0,10);q('pdate').value=today;q('rdate').value=today;refresh();setInterval(refresh,4000);
</script></body></html>'''


@app.get('/')
def home():
    return render_template_string(HTML)


@app.get('/health')
def health():
    return jsonify(ok=True, db=DB_PATH)


@app.post('/api/pallet/start')
def start_pallet():
    data=request.get_json(silent=True) or {}; device=str(data.get('device') or 'NIEZNANY').strip().upper(); d=work_date()
    with db() as c:
        a=active_pallet(c,d)
        if a: return jsonify(error=f"Paleta {a['pallet_no']} jest nadal aktywna"),409
        n=c.execute('SELECT COALESCE(MAX(pallet_no),0)+1 n FROM pallets WHERE work_date=?',(d,)).fetchone()['n']
        cur=c.execute("INSERT INTO pallets(work_date,pallet_no,status,created_at,created_by) VALUES(?,?, 'open', ?, ?)",(d,n,stamp(),device))
        return jsonify(ok=True,pallet_id=cur.lastrowid,pallet_no=n)


@app.post('/api/pallet/close')
def close_pallet():
    data=request.get_json(silent=True) or {}; device=str(data.get('device') or 'NIEZNANY').strip().upper(); d=work_date()
    with db() as c:
        a=active_pallet(c,d)
        if not a: return jsonify(error='Brak aktywnej palety'),409
        n=pallet_count(c,a['id'])
        if n==0: return jsonify(error='Nie można zakończyć pustej palety'),409
        c.execute("UPDATE pallets SET status='closed',closed_at=?,closed_by=? WHERE id=?",(stamp(),device,a['id']))
        return jsonify(ok=True,closed_pallet_no=a['pallet_no'],cartons=n)


@app.post('/api/scan')
def scan():
    data=request.get_json(silent=True) or {}; code=str(data.get('code') or '').strip(); device=str(data.get('device') or 'NIEZNANY').strip().upper(); pid=data.get('pallet_id'); d=work_date()
    if not code: return jsonify(error='Pusty kod'),400
    with db() as c:
        a=active_pallet(c,d)
        if not a: return jsonify(error='Brak aktywnej palety'),409
        if str(a['id'])!=str(pid): return jsonify(error=f"Aktywna jest Paleta {a['pallet_no']}"),409
        first=c.execute('SELECT * FROM scans WHERE work_date=? AND code=? AND is_duplicate=0 ORDER BY id LIMIT 1',(d,code)).fetchone(); dup=first is not None
        c.execute('INSERT INTO scans(work_date,code,pallet_id,pallet_no,device,scanned_at,is_duplicate,duplicate_of_scan_id) VALUES(?,?,?,?,?,?,?,?)',(d,code,a['id'],a['pallet_no'],device,stamp(),1 if dup else 0,first['id'] if first else None))
        if dup: return jsonify(ok=True,duplicate=True,first_pallet_no=first['pallet_no'],first_time=first['scanned_at'].split(' ',1)[1],first_device=first['device'])
        return jsonify(ok=True,duplicate=False,pallet_no=a['pallet_no'])


@app.get('/api/state')
def state():
    d=work_date()
    with db() as c:
        r=report(c,d); a=active_pallet(c,d); nxt=c.execute('SELECT COALESCE(MAX(pallet_no),0)+1 n FROM pallets WHERE work_date=?',(d,)).fetchone()['n']; hist=c.execute('SELECT * FROM scans WHERE work_date=? ORDER BY id DESC LIMIT 80',(d,)).fetchall()
        r['active_pallet']={'id':a['id'],'pallet_no':a['pallet_no'],'cartons':pallet_count(c,a['id'])} if a else None; r['next_pallet_no']=nxt; r['history']=[{'time':x['scanned_at'].split(' ',1)[1],'pallet_no':x['pallet_no'],'code':x['code'],'device':x['device'],'duplicate':bool(x['is_duplicate'])} for x in hist]
        return jsonify(r)


@app.get('/api/pallets')
def pallets():
    d=request.args.get('date') or work_date()
    with db() as c:
        rows=c.execute('SELECT * FROM pallets WHERE work_date=? ORDER BY pallet_no',(d,)).fetchall(); return jsonify(date=d,pallets=[{'id':p['id'],'pallet_no':p['pallet_no'],'status':p['status'],'cartons':pallet_count(c,p['id'])} for p in rows])


@app.get('/api/pallet/<int:pid>')
def pallet_detail(pid):
    with db() as c:
        p=c.execute('SELECT * FROM pallets WHERE id=?',(pid,)).fetchone()
        if not p: return jsonify(error='Nie znaleziono palety'),404
        s=c.execute('SELECT * FROM scans WHERE pallet_id=? ORDER BY id',(pid,)).fetchall(); return jsonify(pallet={'id':p['id'],'pallet_no':p['pallet_no'],'status':p['status'],'cartons':pallet_count(c,pid)},scans=[{'time':x['scanned_at'].split(' ',1)[1],'code':x['code'],'device':x['device'],'duplicate':bool(x['is_duplicate'])} for x in s])


@app.get('/api/days')
def days():
    with db() as c:
        dates=[x['work_date'] for x in c.execute('SELECT work_date FROM pallets UNION SELECT work_date FROM scans ORDER BY work_date DESC').fetchall()]; out=[]
        for d in dates:
            r=report(c,d); out.append({'date':d,'unique':r['unique'],'pallets':r['pallets']['total'],'duplicates':r['duplicates'],'total':r['total_scans']})
        return jsonify(days=out)


@app.get('/api/report')
def report_api():
    d=request.args.get('date') or work_date()
    with db() as c: return jsonify(report(c,d))


@app.get('/api/export.csv')
def export_csv():
    d=request.args.get('date') or work_date()
    with db() as c: rows=c.execute('SELECT * FROM scans WHERE work_date=? ORDER BY id',(d,)).fetchall()
    out=io.StringIO(); w=csv.writer(out,delimiter=';'); w.writerow(['Data','Godzina','Paleta','Kod EAN','Operator/Skaner','Status'])
