import os
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
codes = []
seen = set()

HTML = '''<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Skaner magazynowy</title>
<style>
body{margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif}
.wrap{max-width:850px;margin:auto;padding:20px}
.box{background:#1e293b;border-radius:16px;padding:20px;margin:15px 0}
#status{font-size:30px;font-weight:bold;text-align:center;padding:30px;border-radius:16px;background:#1e293b}
input{width:100%;box-sizing:border-box;font-size:22px;padding:15px;border-radius:12px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:15px 0}
.stat{text-align:center;background:#1e293b;padding:15px;border-radius:14px}.stat b{display:block;font-size:30px}
.ok{background:#15803d!important}.bad{background:#b91c1c!important}
table{width:100%;border-collapse:collapse}td,th{padding:9px;border-bottom:1px solid #475569;text-align:left}
</style></head>
<body><div class="wrap">
<h1>Skaner kodów - wspólna baza</h1>
<div id="status">GOTOWY DO SKANOWANIA</div>
<div class="grid"><div class="stat"><b id="unique">0</b>unikalne</div><div class="stat"><b id="dup">0</b>duplikaty</div><div class="stat"><b id="total">0</b>wszystkie</div></div>
<div class="box"><input id="code" autofocus autocomplete="off" placeholder="Zeskanuj kod i ENTER"></div>
<div class="box"><table><thead><tr><th>Kod</th><th>Status</th></tr></thead><tbody id="rows"></tbody></table></div>
</div>
<script>
const inp=document.getElementById('code'), st=document.getElementById('status');
function beep(f,d){try{let c=new(AudioContext||webkitAudioContext)(),o=c.createOscillator();o.frequency.value=f;o.connect(c.destination);o.start();setTimeout(()=>{o.stop();c.close()},d)}catch(e){}}
async function scan(code){
 let r=await fetch('/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});
 let x=await r.json();
 st.className=x.duplicate?'bad':'ok';
 st.innerHTML=(x.duplicate?'DUPLIKAT!':'OK ✓')+'<br>'+code;
 if(x.duplicate){beep(180,600);if(navigator.vibrate)navigator.vibrate([300,100,500])}else beep(1000,100);
 setTimeout(()=>{st.className='';st.textContent='GOTOWY DO SKANOWANIA';inp.focus()},x.duplicate?2200:800);
 refresh();
}
inp.addEventListener('keydown',e=>{if(e.key==='Enter'){let c=inp.value.trim();inp.value='';if(c)scan(c)}});
async function refresh(){
 let x=await (await fetch('/state')).json();
 unique.textContent=x.unique;dup.textContent=x.duplicates;total.textContent=x.total;
 rows.innerHTML=x.history.map(v=>`<tr><td>${v.code}</td><td>${v.duplicate?'DUPLIKAT':'OK'}</td></tr>`).join('');
}
refresh();setInterval(refresh,3000);
</script></body></html>'''

@app.get("/")
def home():
    return render_template_string(HTML)

@app.post("/scan")
def scan():
    data = request.get_json(silent=True) or {}
    code = str(data.get("code","")).strip()
    duplicate = code in seen
    seen.add(code)
    codes.append({"code":code,"duplicate":duplicate})
    if len(codes) > 10000:
        del codes[:-10000]
    return jsonify(duplicate=duplicate)

@app.get("/state")
def state():
    return jsonify(
        unique=len(seen),
        duplicates=sum(1 for x in codes if x["duplicate"]),
        total=len(codes),
        history=list(reversed(codes[-50:]))
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","10000")))
