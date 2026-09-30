        cartons = get_pallet_carton_count(conn, active["id"])
        if cartons == 0:
            return jsonify(error="Nie można zakończyć pustej palety. Zeskanuj co najmniej jeden karton."), 409
        conn.execute("UPDATE pallets SET status='closed', closed_at=?, closed_by=? WHERE id=?", (ts(), device, active["id"]))
        return jsonify(ok=True, closed_pallet_no=active["pallet_no"], cartons=cartons, next_pallet_no=active["pallet_no"]+1)


@app.post("/api/scan")
def scan_api():
    data = request.get_json(silent=True) or {}
    code = norm_code(data.get("code"))
    device = norm_device(data.get("device"))
    pallet_id = data.get("pallet_id")
    if not code:
        return jsonify(error="Pusty kod"), 400
    if len(code) > 128:
        return jsonify(error="Kod jest zbyt długi"), 400
    d = work_date_str()
    n = now_local()
    n_ts = ts(n)
    with db() as conn:
        active = get_active_pallet(conn, d)
        if not active:
            return jsonify(error="Brak aktywnej palety"), 409
        if str(active["id"]) != str(pallet_id):
            return jsonify(error=f"Aktywna jest Paleta {active['pallet_no']}. Odśwież ekran."), 409

        first = conn.execute(
            "SELECT * FROM scans WHERE work_date=? AND code=? AND is_duplicate=0 ORDER BY id LIMIT 1", (d, code)
        ).fetchone()
        duplicate = first is not None
        cur = conn.execute(
            "INSERT INTO scans(work_date,code,pallet_id,pallet_no,device,scanned_at,is_duplicate,duplicate_of_scan_id) VALUES(?,?,?,?,?,?,?,?)",
            (d, code, active["id"], active["pallet_no"], device, n_ts, 1 if duplicate else 0, first["id"] if first else None),
        )
        cartons = get_pallet_carton_count(conn, active["id"])
        if duplicate:
            return jsonify(
                ok=True, duplicate=True, scan_id=cur.lastrowid,
                first_pallet_no=first["pallet_no"], first_time=row_time_text(first["scanned_at"]), first_device=first["device"],
                pallet_no=active["pallet_no"], pallet_cartons=cartons,
            )
        return jsonify(ok=True, duplicate=False, scan_id=cur.lastrowid, pallet_no=active["pallet_no"], pallet_cartons=cartons)


@app.get("/api/state")
def state_api():
    d = work_date_str()
    with db() as conn:
        rep = report_for_date(conn, d)
        active = get_active_pallet(conn, d)
        if active:
            active_obj = {
                "id": active["id"], "pallet_no": active["pallet_no"],
                "created_time": row_time_text(active["created_at"]),
                "cartons": get_pallet_carton_count(conn, active["id"]),
            }
        else:
            active_obj = None
        hist = conn.execute(
            "SELECT code,pallet_no,device,scanned_at,is_duplicate FROM scans WHERE work_date=? ORDER BY id DESC LIMIT 80", (d,)
        ).fetchall()
        next_no = conn.execute("SELECT COALESCE(MAX(pallet_no),0)+1 n FROM pallets WHERE work_date=?", (d,)).fetchone()["n"]
        rep.update({
            "active_pallet": active_obj,
            "next_pallet_no": next_no,
            "history": [{"code": r["code"], "pallet_no": r["pallet_no"], "device": r["device"], "time": row_time_text(r["scanned_at"]), "duplicate": bool(r["is_duplicate"])} for r in hist],
        })
        return jsonify(rep)


@app.get("/api/pallets")
def pallets_api():
    d = request.args.get("date") or work_date_str()
    with db() as conn:
        rows = conn.execute("SELECT * FROM pallets WHERE work_date=? ORDER BY pallet_no", (d,)).fetchall()
        out = []
        for p in rows:
            out.append({
                "id": p["id"], "pallet_no": p["pallet_no"], "status": p["status"],
                "cartons": get_pallet_carton_count(conn, p["id"]),
                "duplicates": conn.execute("SELECT COUNT(*) c FROM scans WHERE pallet_id=? AND is_duplicate=1", (p["id"],)).fetchone()["c"],
            })
        return jsonify(date=d, pallets=out)


@app.get("/api/pallet/<int:pallet_id>")
def pallet_api(pallet_id):
    with db() as conn:
        p = conn.execute("SELECT * FROM pallets WHERE id=?", (pallet_id,)).fetchone()
        if not p:
            return jsonify(error="Nie znaleziono palety"), 404
        rows = conn.execute("SELECT * FROM scans WHERE pallet_id=? ORDER BY id", (pallet_id,)).fetchall()
        return jsonify(
            pallet={"id": p["id"], "pallet_no": p["pallet_no"], "work_date": p["work_date"], "status": p["status"], "cartons": sum(1 for r in rows if not r["is_duplicate"])},
            scans=[{"code": r["code"], "time": row_time_text(r["scanned_at"]), "device": r["device"], "duplicate": bool(r["is_duplicate"])} for r in rows],
        )


@app.get("/api/days")
def days_api():
    with db() as conn:
        dates = [r["work_date"] for r in conn.execute("SELECT work_date FROM pallets UNION SELECT work_date FROM scans ORDER BY work_date DESC LIMIT 120").fetchall()]
        return jsonify(days=[{"date": d, **{k: report_for_date(conn, d)[k] for k in ["unique", "duplicates", "total_scans"]}, "pallets": report_for_date(conn, d)["pallets"]["total"], "total": report_for_date(conn, d)["total_scans"]} for d in dates])


@app.get("/api/report")
def report_api():
    d = request.args.get("date") or work_date_str()
    with db() as conn:
        return jsonify(report_for_date(conn, d))


@app.get("/api/export.csv")
def export_csv():
    d = request.args.get("date") or work_date_str()
    with db() as conn:
        rows = conn.execute("SELECT * FROM scans WHERE work_date=? ORDER BY id", (d,)).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';', lineterminator='\n')
    w.writerow(["Data", "Godzina", "Paleta", "Kod EAN", "Operator/Skaner", "Status"])
    for r in rows:
        w.writerow([r["work_date"], row_time_text(r["scanned_at"]), r["pallet_no"], r["code"], r["device"], "DUPLIKAT" if r["is_duplicate"] else "OK"])
    data = '\ufeff' + buf.getvalue()
    return Response(data, mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="skaner_{d}.csv"'})


@app.get("/health")
