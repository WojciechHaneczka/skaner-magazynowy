import os
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
codes = []
first_seen = {}

HTML = r"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Skaner magazynowy</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif}
.wrap{max-width:1050px;margin:auto;padding:20px}
.top{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.box{background:#1e293b;border-radius:16px;padding:18px;margin:15px 0}
#status{font-size:30px;font-weight:bold;text-align:center;padding:30px;border-radius:16px;background:#1e293b}
input,button{width:100%;box-sizing:border-box;font-size:20px;padding:14px;border-radius:12px;border:0}
button{font-weight:700;cursor:pointer}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:15px 0}
.stat{text-align:center;background:#1e293b;padding:15px;border-radius:14px}
.stat b{display:block;font-size:30px}
.ok{background:#15803d!important}
.bad{background:#b91c1c!important}
.bad2{color:#fecaca;font-weight:700}
.tag{display:inline-block;background:#334155;border-radius:999px;padding:8px 12px;font-weight:700}
.change{width:auto;padding:8px 12px;font-size:14px;background:#334155;color:white}
table{width:100%;border-collapse:collapse}
td,th{padding:9px;border-bottom:1px solid #475569;text-align:left;font-size:14px}
h1{margin-bottom:6px}
.overlay{position:fixed;inset:0;background:rgba(2,6,23,.96);display:none;align-items:center;justify-content:center;padding:20px;z-index:100}
.modal{max-width:480px;width:100%;background:#111827;border:1px solid #334155;border-radius:18px;padding:22px}
.modal h2{margin-top:0}
.modal p{color:#cbd5e1}
.modal input{margin:10px 0;background:white;color:#111827}
.modal button{background:#16a34a;color:white}
.section-title{margin:0 0 10px}
@media(max-width:760px){.grid{grid-template-columns:repeat(2,1fr)}}
</style>
</head>
<body>
<div class="wrap">
<div class="top">
  <div>
    <h1>Skaner kodów - wspólna baza</h1>
    <div>Urządzenie: <span class="tag" id="deviceLabel">...</span></div>
  </div>
  <button class="change" onclick="changeDevice()">Zmień nazwę skanera</button>
</div>

<div class="box"><button type="button" onclick="playDuplicateSiren();inp.focus()">Test głośnej syreny (3 sekundy)</button><p>Ustaw głośność multimediów skanera na maksimum.</p></div>
<div id="status">GOTOWY DO SKANOWANIA</div>

<div class="grid">
  <div class="stat"><b id="unique">0</b>unikalne</div>
  <div class="stat"><b id="dup">0</b>duplikaty</div>
  <div class="stat"><b id="total">0</b>wszystkie</div>
  <div class="stat"><b id="mine">0</b>ten skaner</div>
</div>

<div class="box">
  <input id="code" autofocus autocomplete="off" placeholder="Zeskanuj kod i ENTER">
</div>

<div class="box">
  <h3 class="section-title">Aktywność skanerów</h3>
  <table>
    <thead><tr><th>Skaner</th><th>Skany</th><th>Duplikaty</th></tr></thead>
    <tbody id="devices"></tbody>
  </table>
</div>

<div class="box">
  <h3 class="section-title">Ostatnie skany</h3>
  <table>
    <thead><tr><th>Czas</th><th>Kod</th><th>Skaner</th><th>Status</th><th>Pierwszy skan</th></tr></thead>
    <tbody id="rows"></tbody>
  </table>
</div>
</div>

<div class="overlay" id="deviceOverlay">
  <div class="modal">
    <h2>Nazwa urządzenia</h2>
    <p>Wpisz nazwę tego skanera. Zostanie zapamiętana na tym urządzeniu.</p>
    <input id="deviceInput" placeholder="np. SKANER 01" maxlength="40">
    <button onclick="saveDevice()">Zapisz i rozpocznij</button>
  </div>
</div>

<script>
const inp=document.getElementById('code');
const st=document.getElementById('status');
let deviceName = localStorage.getItem('warehouse_device_name') || '';

function normalizeDevice(v){
  return String(v||'').trim().replace(/\s+/g,' ').toUpperCase();
}
function ensureDevice(){
  if(!deviceName){
    document.getElementById('deviceOverlay').style.display='flex';
    setTimeout(()=>document.getElementById('deviceInput').focus(),100);
  } else {
    document.getElementById('deviceLabel').textContent=deviceName;
    inp.focus();
  }
}
function saveDevice(){
  const v=normalizeDevice(document.getElementById('deviceInput').value);
  if(!v) return;
  deviceName=v;
  localStorage.setItem('warehouse_device_name',deviceName);
  document.getElementById('deviceLabel').textContent=deviceName;
  document.getElementById('deviceOverlay').style.display='none';
  inp.focus();
  refresh();
}
function changeDevice(){
  document.getElementById('deviceInput').value=deviceName;
  document.getElementById('deviceOverlay').style.display='flex';
  setTimeout(()=>document.getElementById('deviceInput').focus(),100);
}
let audioContext, activeSiren;
function unlockAudio(){
  try{
    const A=window.AudioContext||window.webkitAudioContext;
    if(!A)return null;
    if(!audioContext||audioContext.state==='closed')audioContext=new A();
    if(audioContext.state==='suspended')audioContext.resume().catch(()=>{});
    return audioContext;
  }catch(e){return null;}
}
document.addEventListener('pointerdown',unlockAudio,true);
document.addEventListener('keydown',unlockAudio,true);
function sound(siren,f=1000,d=0.1){
  const c=unlockAudio();
  if(!c||(!siren&&activeSiren))return;
  try{
    if(siren&&activeSiren){try{activeSiren.stop();}catch(e){}}
    const o=c.createOscillator(),g=c.createGain(),t=c.currentTime;
    if(siren){
      d=3;o.type='sawtooth';
      for(let i=0;i<6;i++){
        o.frequency.setValueAtTime(650,t+i*0.5);
        o.frequency.linearRampToValueAtTime(1550,t+i*0.5+0.25);
        o.frequency.linearRampToValueAtTime(650,t+(i+1)*0.5);
      }
      activeSiren=o;
    }else{o.frequency.value=f;}
    const volume=siren?1:0.25;
    g.gain.setValueAtTime(0,t);
    g.gain.linearRampToValueAtTime(volume,t+0.005);
    g.gain.setValueAtTime(volume,t+d-0.01);
    g.gain.linearRampToValueAtTime(0,t+d);
    o.connect(g);g.connect(c.destination);
    o.onended=()=>{o.disconnect();g.disconnect();if(activeSiren===o)activeSiren=null;};
    o.start(t);o.stop(t+d);
  }catch(e){}
}
function beep(f,d){sound(false,f,d/1000);}
function playDuplicateSiren(){sound(true);}
async function scan(code){
  if(!deviceName){ensureDevice();return}
  let r=await fetch('/scan',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({code,device:deviceName})
  });
  let x=await r.json();
  st.className=x.duplicate?'bad':'ok';
  if(x.duplicate){
    st.innerHTML='DUPLIKAT!<br>'+code+
      '<div style="font-size:15px;margin-top:8px">Pierwszy skan: '+x.first_device+
      ' | '+x.first_time+'</div>';
    playDuplicateSiren();
    if(navigator.vibrate)navigator.vibrate([300,100,300,100,500]);
  }else{
    st.innerHTML='OK ✓<br>'+code;
    beep(1000,100);
  }
  setTimeout(()=>{
    st.className='';
    st.textContent='GOTOWY DO SKANOWANIA';
    inp.focus();
  },x.duplicate?3200:800);
  refresh();
}
inp.addEventListener('keydown',e=>{
  if(e.key==='Enter'){
    let c=inp.value.trim();
    inp.value='';
    if(c)scan(c);
  }
});
async function refresh(){
  let x=await (await fetch('/state')).json();
  document.getElementById('unique').textContent=x.unique;
  document.getElementById('dup').textContent=x.duplicates;
  document.getElementById('total').textContent=x.total;
  const mine = x.device_stats.find(d=>d.device===deviceName);
  document.getElementById('mine').textContent=mine ? mine.total : 0;
  document.getElementById('devices').innerHTML=x.device_stats.map(d=>
    `<tr><td><b>${esc(d.device)}</b></td><td>${d.total}</td><td class="${d.duplicates?'bad2':''}">${d.duplicates}</td></tr>`
  ).join('');
  document.getElementById('rows').innerHTML=x.history.map(v=>
    `<tr><td>${esc(v.time)}</td><td>${esc(v.code)}</td><td><b>${esc(v.device)}</b></td><td class="${v.duplicate?'bad2':''}">${v.duplicate?'DUPLIKAT':'OK'}</td><td>${v.duplicate ? esc(v.first_device+' / '+v.first_time) : '-'}</td></tr>`
  ).join('');
}
function esc(s){
  return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}
ensureDevice();
refresh();
setInterval(refresh,3000);
</script>
</body>
</html>"""

@app.get("/")
def home():
    return render_template_string(HTML)

@app.post("/scan")
def scan():
    from datetime import datetime
    data = request.get_json(silent=True) or {}
    code = str(data.get("code","")).strip()
    device = str(data.get("device","")).strip().upper() or "NIEZNANY"
    if not code:
        return jsonify(error="empty code"), 400

    duplicate = code in first_seen
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not duplicate:
        first_seen[code] = {"device":device,"time":now}

    first = first_seen[code]

    codes.append({
        "code":code,
        "device":device,
        "time":now,
        "duplicate":duplicate,
        "first_device":first["device"],
        "first_time":first["time"],
    })

    if len(codes)>10000:
        del codes[:-10000]

    return jsonify(
        duplicate=duplicate,
        first_device=first["device"],
        first_time=first["time"]
    )

@app.get("/state")
def state():
    stats={}
    for x in codes:
        d=stats.setdefault(x["device"],{"device":x["device"],"total":0,"duplicates":0})
        d["total"]+=1
        if x["duplicate"]:
            d["duplicates"]+=1

    device_stats=sorted(stats.values(),key=lambda x:(-x["total"],x["device"]))

    return jsonify(
        unique=len(first_seen),
        duplicates=sum(1 for x in codes if x["duplicate"]),
        total=len(codes),
        history=list(reversed(codes[-60:])),
        device_stats=device_stats
    )

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT","10000")))
