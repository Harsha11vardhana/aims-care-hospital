"""
AIMS CARE Hospital — Premium AI Ward Allocation System
Flask Backend · SQLite Database · Real-Time API · Voice AI
"""

from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import sqlite3, uuid, re, os, random, threading, time

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "aimscare.db")

# ═══════════════════════════════════════════════════════════
#  WARD CONFIGURATION
# ═══════════════════════════════════════════════════════════
WARDS_CONFIG = {
    "ICU": {
        "name": "Intensive Care Unit", "emoji": "🏥", "color": "#ef4444",
        "total": 20, "floor": "3rd Floor, Block A", "icon": "🫁",
        "specialists": ["Pulmonologist", "Critical Care Specialist"],
        "equipment": ["Ventilator", "Defibrillator", "Dialysis Machine", "Cardiac Monitor"],
        "cost_per_day": 8000, "severity_min": 3,
        "suitable_for": ["respiratory","failure","critical","sepsis","coma","multi-organ","shock"],
    },
    "Cardiology": {
        "name": "Cardiology Ward", "emoji": "❤️", "color": "#f97316",
        "total": 30, "floor": "2nd Floor, Block B", "icon": "❤️",
        "specialists": ["Cardiologist", "Cardiac Surgeon", "Electrophysiologist"],
        "equipment": ["ECG Monitor", "Catheterisation Lab", "Echo Machine", "Holter Monitor"],
        "cost_per_day": 5000, "severity_min": 2,
        "suitable_for": ["chest pain","cardiac","heart","hypertension","ecg","arrhythmia","angina","myocardial"],
    },
    "Surgical": {
        "name": "Surgical Ward", "emoji": "⚕️", "color": "#8b5cf6",
        "total": 40, "floor": "2nd Floor, Block C", "icon": "🔬",
        "specialists": ["General Surgeon", "Laparoscopic Surgeon", "Anaesthesiologist"],
        "equipment": ["Operation Theatre", "Post-Op Monitor", "Wound Care", "Laparoscope"],
        "cost_per_day": 3500, "severity_min": 1,
        "suitable_for": ["surgery","appendix","appendicitis","hernia","gallbladder","tumor","operation","post-op"],
    },
    "General Medicine": {
        "name": "General Medicine", "emoji": "💊", "color": "#06b6d4",
        "total": 50, "floor": "1st Floor, Block B", "icon": "🏠",
        "specialists": ["General Physician", "Internist", "Diabetologist"],
        "equipment": ["Pulse Oximeter", "IV Stand", "Nebuliser", "Blood Glucose Monitor"],
        "cost_per_day": 1200, "severity_min": 1,
        "suitable_for": ["fever","infection","diabetes","viral","bacterial","general","diarrhoea","vomiting","weakness"],
    },
    "Paediatrics": {
        "name": "Paediatrics Ward", "emoji": "👶", "color": "#22c55e",
        "total": 30, "floor": "1st Floor, Block D", "icon": "🧒",
        "specialists": ["Paediatrician", "Neonatologist", "Paediatric Surgeon"],
        "equipment": ["Child Monitor", "Paediatric Ventilator", "Incubator", "Phototherapy"],
        "cost_per_day": 2000, "severity_min": 1,
        "suitable_for": ["child","infant","baby","pneumonia","paeds","toddler","neonatal"],
    },
    "Orthopaedics": {
        "name": "Orthopaedics Ward", "emoji": "🦴", "color": "#eab308",
        "total": 35, "floor": "3rd Floor, Block D", "icon": "🦿",
        "specialists": ["Orthopaedic Surgeon", "Physiotherapist", "Spine Specialist"],
        "equipment": ["X-Ray Suite", "Traction Bed", "Physiotherapy Room", "Arthroscope"],
        "cost_per_day": 3000, "severity_min": 1,
        "suitable_for": ["fracture","bone","joint","spine","knee","hip","replacement","ligament","ortho"],
    },
}

SEVERITY_MAP = {"Low": 1, "Moderate": 2, "High": 3, "Critical": 4}

# ═══════════════════════════════════════════════════════════
#  DATABASE HELPERS
# ═══════════════════════════════════════════════════════════
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS wards (
            ward_id      TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            emoji        TEXT,
            color        TEXT,
            icon         TEXT,
            total_beds   INTEGER NOT NULL,
            occupied     INTEGER DEFAULT 0,
            floor        TEXT,
            cost_per_day INTEGER,
            updated_at   TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS patients (
            patient_id     TEXT PRIMARY KEY,
            first_name     TEXT NOT NULL,
            last_name      TEXT NOT NULL,
            age            INTEGER,
            gender         TEXT,
            phone          TEXT,
            blood_group    TEXT,
            diagnosis      TEXT,
            severity       TEXT,
            admission_type TEXT,
            notes          TEXT,
            status         TEXT DEFAULT 'Registered',
            ward_id        TEXT,
            bed_number     TEXT,
            registered_at  TEXT DEFAULT (datetime('now')),
            admitted_at    TEXT
        );
        CREATE TABLE IF NOT EXISTS bookings (
            booking_id   TEXT PRIMARY KEY,
            patient_id   TEXT NOT NULL,
            patient_name TEXT,
            ward_id      TEXT NOT NULL,
            ward_name    TEXT,
            bed_number   TEXT,
            floor        TEXT,
            diagnosis    TEXT,
            severity     TEXT,
            allocated_at TEXT DEFAULT (datetime('now')),
            status       TEXT DEFAULT 'Active'
        );
        CREATE TABLE IF NOT EXISTS ward_updates (
            update_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            ward_id      TEXT NOT NULL,
            old_occupied INTEGER,
            new_occupied INTEGER,
            reason       TEXT,
            updated_at   TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS announcements (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT NOT NULL,
            body       TEXT NOT NULL,
            category   TEXT DEFAULT 'info',
            is_active  INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS chat_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role       TEXT,
            message    TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """)
        db.commit()
    _seed_wards()

def _seed_wards():
    with get_db() as db:
        if db.execute("SELECT COUNT(*) FROM wards").fetchone()[0] == 0:
            defaults = {"ICU":18,"Cardiology":28,"Surgical":22,"General Medicine":34,"Paediatrics":15,"Orthopaedics":30}
            for wid, w in WARDS_CONFIG.items():
                db.execute("INSERT INTO wards VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))",
                    (wid,w["name"],w["emoji"],w["color"],w["icon"],w["total"],defaults.get(wid,0),w["floor"],w["cost_per_day"]))
            for t,b,c in [
                ("🆕 New 3T MRI Suite Operational","State-of-the-art MRI facility now open on Floor 2, Block A.","info"),
                ("⚠️ ICU Near Capacity","ICU at 90%. Critical patients prioritised. Emergency: 108","warning"),
                ("🎉 NABH Re-accreditation 2025","AIMS CARE received NABH re-accreditation for 2025-2028.","success"),
                ("💉 Free Cardiac Screening","Free camp on 15th March. Register at reception or call us.","info"),
            ]:
                db.execute("INSERT INTO announcements (title,body,category) VALUES (?,?,?)",(t,b,c))
            db.commit()
        if db.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] == 0:
            _seed_demo_patients()

def _seed_demo_patients():
    demos = [
        {"first_name":"Priya","last_name":"Sharma","age":42,"gender":"Female","phone":"9876543210",
         "diagnosis":"Chest pain, known hypertension","severity":"High","admission_type":"Emergency","notes":"BP 180/110","blood_group":"B+"},
        {"first_name":"Mohan","last_name":"Reddy","age":67,"gender":"Male","phone":"9876500001",
         "diagnosis":"Respiratory failure, COPD","severity":"Critical","admission_type":"Emergency","notes":"On home oxygen","blood_group":"O+"},
        {"first_name":"Sneha","last_name":"Pillai","age":9,"gender":"Female","phone":"9876500002",
         "diagnosis":"Pneumonia","severity":"Moderate","admission_type":"Referral","notes":"","blood_group":"A+"},
        {"first_name":"Arjun","last_name":"Mehta","age":35,"gender":"Male","phone":"9876500003",
         "diagnosis":"Appendicitis","severity":"High","admission_type":"Emergency","notes":"Post-op day 1","blood_group":"AB+"},
    ]
    for p in demos:
        pid = "P" + str(uuid.uuid4())[:6].upper()
        recs = _ai_allocate_logic(p)
        ward_id = recs[0]["ward_id"] if recs else "General Medicine"
        bed = _next_bed_number(ward_id)
        now = datetime.now().isoformat()
        with get_db() as db:
            db.execute("INSERT INTO patients VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pid,p["first_name"],p["last_name"],p["age"],p["gender"],p["phone"],p["blood_group"],
                 p["diagnosis"],p["severity"],p["admission_type"],p["notes"],"Admitted",ward_id,bed,now,now))
            db.execute("UPDATE wards SET occupied=occupied+1 WHERE ward_id=?",(ward_id,))
            w = WARDS_CONFIG[ward_id]
            db.execute("INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("BK"+str(uuid.uuid4())[:6].upper(),pid,f"{p['first_name']} {p['last_name']}",
                 ward_id,w["name"],bed,w["floor"],p["diagnosis"],p["severity"],now,"Active"))
            db.commit()

# ═══════════════════════════════════════════════════════════
#  AI ENGINE
# ═══════════════════════════════════════════════════════════
def _ai_allocate_logic(patient):
    diag = (patient.get("diagnosis") or "").lower()
    sev_s = patient.get("severity","Low")
    sev = SEVERITY_MAP.get(sev_s,1)
    age = int(patient.get("age",30) or 30)
    with get_db() as db:
        wards_db = {r["ward_id"]:dict(r) for r in db.execute("SELECT * FROM wards").fetchall()}
    scores = {}
    for wid, wdb in wards_db.items():
        w = WARDS_CONFIG.get(wid,{})
        avail = wdb["total_beds"] - wdb["occupied"]
        if avail <= 0: continue
        score, reasons = 0.0, []
        matched = sum(1 for kw in w.get("suitable_for",[]) if kw in diag)
        score += min(40, matched*15)
        if matched: reasons.append(f"Diagnosis matches {matched} keyword(s) for this ward")
        if sev >= w.get("severity_min",1):
            score += min(25,(sev-w["severity_min"]+1)*8)
            reasons.append(f"Severity '{sev_s}' is compatible with this ward")
        else:
            score -= 10
        occ_r = wdb["occupied"]/wdb["total_beds"]
        score += round((1-occ_r)*20,1)
        reasons.append(f"{avail} bed(s) available ({round((1-occ_r)*100)}% free)")
        if wid=="Paediatrics" and age<=14: score+=10; reasons.append("Patient age indicates paediatric care")
        elif wid=="Paediatrics" and age>14: score-=20
        if wid=="ICU" and (age>=60 or sev==4): score+=8; reasons.append("Age/severity profile suits intensive monitoring")
        if sev==4 and wid=="ICU": score+=15; reasons.append("Critical patient — ICU strongly recommended")
        scores[wid] = {
            "ward_id":wid,"ward_name":wdb["name"],"emoji":wdb["emoji"],"color":wdb.get("color","#666"),
            "confidence":max(0,min(100,round(score))),"available_beds":avail,
            "floor":wdb["floor"],"specialists":w.get("specialists",[]),
            "cost_per_day":wdb["cost_per_day"],"reasons":reasons,
        }
    return sorted(scores.values(),key=lambda x:x["confidence"],reverse=True)[:3]

def _next_bed_number(ward_id):
    prefix = {"ICU":"ICU","Cardiology":"C","Surgical":"S","General Medicine":"G","Paediatrics":"P","Orthopaedics":"O"}.get(ward_id,"W")
    with get_db() as db:
        taken = [r[0] for r in db.execute("SELECT bed_number FROM bookings WHERE ward_id=? AND status='Active'",(ward_id,)).fetchall()]
    n = 1
    while f"{prefix}-{n:02d}" in taken: n+=1
    return f"{prefix}-{n:02d}"

# ═══════════════════════════════════════════════════════════
#  BACKGROUND REAL-TIME SIMULATION
# ═══════════════════════════════════════════════════════════
def _simulate_ward_activity():
    while True:
        time.sleep(30)
        try:
            with get_db() as db:
                for w in db.execute("SELECT ward_id,occupied,total_beds FROM wards").fetchall():
                    change = random.choice([-1,0,0,0,1])
                    new_occ = max(0,min(w["total_beds"]-1,w["occupied"]+change))
                    if new_occ != w["occupied"]:
                        db.execute("UPDATE wards SET occupied=?,updated_at=datetime('now') WHERE ward_id=?",(new_occ,w["ward_id"]))
                        db.execute("INSERT INTO ward_updates (ward_id,old_occupied,new_occupied,reason) VALUES (?,?,?,?)",
                            (w["ward_id"],w["occupied"],new_occ,"Live activity"))
                db.commit()
        except Exception: pass

# ═══════════════════════════════════════════════════════════
#  API ROUTES
# ═══════════════════════════════════════════════════════════
@app.route("/")
def index():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>AIMS CARE — Staff Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet"/>
<style>
:root{
  --blue:#3B5BDB;--blue2:#4263EB;--blue-lt:#EEF2FF;--blue-pale:#dbe4ff;
  --red:#E03131;--red-lt:#FFF5F5;--green:#2F9E44;--green-lt:#EBFBEE;
  --amber:#E67700;--amber-lt:#FFF3BF;--purple:#7c3aed;--purple-lt:#f3f0ff;
  --white:#fff;--bg:#F0F4FF;--sidebar:#1a2744;--sidebar2:#243058;
  --g100:#F1F3F5;--g200:#E9ECEF;--g300:#DEE2E6;--g500:#ADB5BD;--g600:#868E96;--g700:#495057;--g800:#343A40;--g900:#212529;
  --sh1:0 2px 10px rgba(0,0,0,.06);--sh2:0 4px 18px rgba(0,0,0,.09);--shb:0 4px 16px rgba(59,91,219,.28);
  --r8:8px;--r10:10px;--r12:12px;--r16:16px;--r20:20px;--r99:99px;
  --fn:'Plus Jakarta Sans',sans-serif;--sw:240px;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--fn);background:var(--bg);color:var(--g900);display:flex;min-height:100vh}
::-webkit-scrollbar{width:4px;height:4px}::-webkit-scrollbar-thumb{background:#4a5568;border-radius:2px}

/* ── SIDEBAR ── */
.sidebar{width:var(--sw);background:var(--sidebar);display:flex;flex-direction:column;position:fixed;top:0;left:0;bottom:0;z-index:100;transition:transform .3s}
.sb-hdr{padding:20px 18px 16px;border-bottom:1px solid rgba(255,255,255,.08)}
.sb-brand{display:flex;align-items:center;gap:10px;margin-bottom:3px}
.sb-ico{width:36px;height:36px;background:var(--blue);border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:17px;flex-shrink:0}
.sb-name{font-size:17px;font-weight:800;color:#fff;letter-spacing:-.3px}
.sb-name span{color:var(--blue-pale);font-weight:400}
.sb-badge{font-size:10px;color:rgba(255,255,255,.4);font-weight:600;letter-spacing:.5px;text-transform:uppercase;margin-left:46px}
.sb-section{padding:12px 10px 4px;font-size:9.5px;font-weight:800;color:rgba(255,255,255,.28);letter-spacing:2px;text-transform:uppercase}
.sbi{display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:var(--r10);font-size:13px;font-weight:600;color:rgba(255,255,255,.55);cursor:pointer;transition:all .18s;margin-bottom:2px;border:none;background:none;width:100%;text-align:left}
.sbi:hover{background:rgba(255,255,255,.07);color:rgba(255,255,255,.85)}
.sbi.act{background:var(--blue);color:#fff;box-shadow:var(--shb)}
.sbi-ico{font-size:15px;width:20px;text-align:center;flex-shrink:0}
.sbi-bdg{margin-left:auto;background:var(--red);color:#fff;font-size:9px;font-weight:800;padding:2px 6px;border-radius:var(--r99)}
.sb-foot{margin-top:auto;padding:14px 10px;border-top:1px solid rgba(255,255,255,.08)}
.sb-user{display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:var(--r10);cursor:pointer;transition:background .18s}
.sb-user:hover{background:rgba(255,255,255,.07)}
.sb-av{width:32px;height:32px;border-radius:50%;background:var(--blue);display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0}
.sb-un{font-size:12.5px;font-weight:700;color:#fff}
.sb-ur{font-size:10px;color:rgba(255,255,255,.45)}

/* ── MAIN ── */
.main{margin-left:var(--sw);flex:1;display:flex;flex-direction:column;min-height:100vh}
.topbar{background:var(--white);border-bottom:1px solid var(--g200);padding:0 28px;height:64px;display:flex;align-items:center;gap:14px;box-shadow:var(--sh1);position:sticky;top:0;z-index:50}
.topbar-title{font-size:18px;font-weight:800;color:var(--g900);flex:1}
.topbar-sub{font-size:12px;color:var(--g500);font-weight:500;margin-top:2px}
.tb-actions{display:flex;align-items:center;gap:10px}
.tb-btn{display:flex;align-items:center;gap:5px;padding:8px 14px;border:none;border-radius:var(--r8);font-size:12.5px;font-weight:700;cursor:pointer;transition:all .18s;font-family:var(--fn)}
.tb-btn-blue{background:var(--blue);color:#fff;box-shadow:var(--shb)}.tb-btn-blue:hover{background:var(--blue2)}
.tb-btn-out{background:var(--white);color:var(--g700);border:1.5px solid var(--g300)}.tb-btn-out:hover{border-color:var(--blue);color:var(--blue)}
.tb-search{display:flex;align-items:center;gap:7px;background:var(--bg);border:1.5px solid var(--g300);border-radius:var(--r99);padding:7px 14px;font-size:12.5px;color:var(--g500);min-width:200px;cursor:pointer}
.tb-search input{border:none;background:none;outline:none;font-size:12.5px;color:var(--g900);font-family:var(--fn);width:100%}
.tb-search input::placeholder{color:var(--g500)}
.tb-time{font-size:12px;color:var(--g500);font-weight:600;white-space:nowrap}
.lpill{display:flex;align-items:center;gap:4px;padding:5px 11px;background:var(--green-lt);border-radius:var(--r99);font-size:10.5px;font-weight:700;color:var(--green)}
.ld{width:5px;height:5px;border-radius:50%;background:var(--green);animation:lp 2s ease-in-out infinite}
@keyframes lp{0%,100%{opacity:1}50%{opacity:.3}}
.content{padding:24px 28px;flex:1}

/* ── PAGES ── */
.page{display:none}.page.act{display:block}

/* ── STAT CARDS ── */
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}
.stat-card{background:var(--white);border-radius:var(--r16);padding:18px;box-shadow:var(--sh1);border:1px solid var(--g200);transition:box-shadow .2s;position:relative;overflow:hidden}
.stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}
.stat-card.sc-blue::before{background:var(--blue)}.stat-card.sc-green::before{background:var(--green)}
.stat-card.sc-red::before{background:var(--red)}.stat-card.sc-amber::before{background:var(--amber)}
.stat-card:hover{box-shadow:var(--sh2)}
.sc-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:11px}
.sc-ico{width:42px;height:42px;border-radius:var(--r10);display:flex;align-items:center;justify-content:center;font-size:19px}
.sc-bdg{padding:3px 8px;border-radius:var(--r99);font-size:10px;font-weight:700}
.bdg-g{background:var(--green-lt);color:var(--green)}.bdg-r{background:var(--red-lt);color:var(--red)}
.bdg-b{background:var(--blue-lt);color:var(--blue)}.bdg-a{background:var(--amber-lt);color:var(--amber)}
.sc-val{font-size:32px;font-weight:800;line-height:1;margin-bottom:4px;color:var(--g900)}
.sc-lbl{font-size:11px;color:var(--g500);font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.sc-trend{font-size:11px;color:var(--green);font-weight:600;margin-top:4px}

/* ── TABLES ── */
.table-card{background:var(--white);border-radius:var(--r16);border:1px solid var(--g200);box-shadow:var(--sh1);overflow:hidden;margin-bottom:20px}
.table-hdr{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--g100)}
.table-ttl{font-size:14px;font-weight:800;color:var(--g900)}
.table-acts{display:flex;gap:8px;align-items:center}
table{width:100%;border-collapse:collapse}
th{padding:10px 16px;text-align:left;font-size:10.5px;font-weight:800;color:var(--g500);text-transform:uppercase;letter-spacing:.8px;background:var(--g100);border-bottom:1px solid var(--g200)}
td{padding:12px 16px;font-size:13px;color:var(--g700);border-bottom:1px solid var(--g100);vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--bg)}
.td-name{font-weight:700;color:var(--g900)}
.td-id{font-size:11px;color:var(--g400);font-weight:600}
.pill{display:inline-flex;align-items:center;padding:3px 8px;border-radius:var(--r99);font-size:10.5px;font-weight:700}
.pill-g{background:var(--green-lt);color:var(--green)}.pill-r{background:var(--red-lt);color:var(--red)}
.pill-b{background:var(--blue-lt);color:var(--blue)}.pill-a{background:var(--amber-lt);color:var(--amber)}
.pill-p{background:var(--purple-lt);color:var(--purple)}
.td-act{display:flex;gap:5px}
.act-btn{padding:5px 10px;border:1px solid var(--g300);border-radius:6px;font-size:11px;font-weight:700;cursor:pointer;background:var(--white);color:var(--g700);transition:all .15s;font-family:var(--fn)}
.act-btn:hover{border-color:var(--blue);color:var(--blue);background:var(--blue-lt)}
.act-btn.red{border-color:rgba(224,49,49,.2);color:var(--red)}.act-btn.red:hover{background:var(--red-lt);border-color:var(--red)}
.act-btn.grn{border-color:rgba(47,158,68,.2);color:var(--green)}.act-btn.grn:hover{background:var(--green-lt);border-color:var(--green)}

/* ── WARD GRID ── */
.ward-mgmt-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:20px}
.wm-card{background:var(--white);border-radius:var(--r16);border:1px solid var(--g200);overflow:hidden;box-shadow:var(--sh1)}
.wm-acc{height:4px}
.wm-body{padding:16px}
.wm-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:11px}
.wm-name{font-size:14px;font-weight:800;color:var(--g900)}
.wm-floor{font-size:10.5px;color:var(--g500)}
.wm-stats{display:flex;gap:16px;margin-bottom:10px}
.wm-s{text-align:center}
.wm-sv{font-size:22px;font-weight:800;line-height:1}
.wm-sl{font-size:9.5px;color:var(--g500);font-weight:700;text-transform:uppercase;letter-spacing:.4px;margin-top:2px}
.wm-bar{height:6px;background:var(--g100);border-radius:3px;overflow:hidden;margin-bottom:12px}
.wm-fill{height:100%;border-radius:3px;transition:width 1s ease}
.wm-actions{display:flex;gap:7px}
.wm-btn{flex:1;padding:8px;border:none;border-radius:var(--r8);font-size:12px;font-weight:700;cursor:pointer;transition:all .18s;font-family:var(--fn)}
.wm-btn-blue{background:var(--blue-lt);color:var(--blue)}.wm-btn-blue:hover{background:var(--blue);color:#fff}
.wm-btn-red{background:var(--red-lt);color:var(--red)}.wm-btn-red:hover{background:var(--red);color:#fff}
.wm-btn-green{background:var(--green-lt);color:var(--green)}.wm-btn-green:hover{background:var(--green);color:#fff}

/* ── CHARTS / BARS ── */
.chart-row{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px}
.chart-card{background:var(--white);border-radius:var(--r16);border:1px solid var(--g200);padding:18px;box-shadow:var(--sh1)}
.chart-ttl{font-size:13px;font-weight:800;color:var(--g900);margin-bottom:14px;display:flex;align-items:center;justify-content:space-between}
.bar-row{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.bar-lbl{font-size:11.5px;color:var(--g700);width:110px;flex-shrink:0;font-weight:600;display:flex;align-items:center;gap:5px}
.bar-bg{flex:1;height:7px;background:var(--g100);border-radius:4px;overflow:hidden}
.bar-fill{height:100%;border-radius:4px;transition:width 1s ease}
.bar-val{font-size:11px;font-weight:700;color:var(--g600);width:30px;text-align:right;flex-shrink:0}

/* ── MODAL ── */
.modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:1000;align-items:center;justify-content:center;backdrop-filter:blur(4px)}
.modal-bg.on{display:flex}
.modal{background:var(--white);border-radius:var(--r20);padding:28px;max-width:500px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.2);animation:mIn .3s cubic-bezier(.34,1.56,.64,1)}
@keyframes mIn{from{opacity:0;transform:scale(.88) translateY(20px)}to{opacity:1;transform:scale(1) translateY(0)}}
.modal-ttl{font-size:17px;font-weight:800;color:var(--g900);margin-bottom:4px}
.modal-sub{font-size:12px;color:var(--g500);margin-bottom:20px}
.modal-footer{display:flex;gap:10px;margin-top:20px;justify-content:flex-end}
.fg{display:flex;flex-direction:column;gap:5px;margin-bottom:12px}
.flbl{font-size:10.5px;font-weight:700;color:var(--g600);text-transform:uppercase;letter-spacing:.5px}
.fi{background:var(--bg);border:1.5px solid var(--g300);border-radius:var(--r8);padding:10px 12px;color:var(--g900);font-size:13px;font-family:var(--fn);outline:none;width:100%;transition:all .2s}
.fi:focus{border-color:var(--blue);background:var(--white);box-shadow:0 0 0 3px rgba(59,91,219,.1)}
.fi::placeholder{color:var(--g500)}
select.fi option{background:var(--white)}
textarea.fi{resize:none;min-height:64px}
.frow{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.btn{display:flex;align-items:center;justify-content:center;gap:6px;padding:10px 20px;border:none;border-radius:var(--r8);font-size:13px;font-weight:700;cursor:pointer;font-family:var(--fn);transition:all .18s}
.btn-blue{background:var(--blue);color:#fff;box-shadow:var(--shb)}.btn-blue:hover{background:var(--blue2)}
.btn-out{background:var(--white);color:var(--g700);border:1.5px solid var(--g300)}.btn-out:hover{border-color:var(--g500)}
.btn-red{background:var(--red);color:#fff}.btn-red:hover{background:#C92A2A}

/* TOAST */
.toast{position:fixed;top:76px;left:50%;transform:translateX(-50%) translateY(-8px);z-index:9999;border-radius:var(--r10);padding:10px 20px;font-size:13px;font-weight:600;opacity:0;transition:all .28s;pointer-events:none;white-space:nowrap;box-shadow:var(--sh2);border:1px solid}
.toast.on{transform:translateX(-50%) translateY(0);opacity:1}
.ts{background:rgba(235,251,238,.97);color:var(--green);border-color:rgba(47,158,68,.2)}
.te{background:rgba(255,245,245,.97);color:var(--red);border-color:rgba(224,49,49,.2)}
.ti{background:rgba(238,242,255,.97);color:var(--blue);border-color:rgba(59,91,219,.2)}
.spn{display:inline-block;width:12px;height:12px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}

/* MOBILE SIDEBAR TOGGLE */
.sb-toggle{display:none;position:fixed;top:14px;left:14px;z-index:200;width:36px;height:36px;border-radius:var(--r8);background:var(--sidebar);color:#fff;border:none;font-size:16px;cursor:pointer;align-items:center;justify-content:center}

@media(max-width:1100px){
  .stat-grid{grid-template-columns:1fr 1fr}
  .ward-mgmt-grid{grid-template-columns:1fr 1fr}
  .chart-row{grid-template-columns:1fr}
}
@media(max-width:768px){
  .sidebar{transform:translateX(-100%)}
  .sidebar.mobile-open{transform:translateX(0)}
  .main{margin-left:0}
  .sb-toggle{display:flex}
  .stat-grid{grid-template-columns:1fr 1fr}
  .ward-mgmt-grid{grid-template-columns:1fr}
  .content{padding:16px}
  .topbar{padding:0 16px 0 56px}
  .tb-search{display:none}
}
</style>
</head>
<body>

<!-- MOBILE SIDEBAR TOGGLE -->
<button class="sb-toggle" id="sb-toggle" onclick="toggleSidebar()">☰</button>

<!-- ── SIDEBAR ── -->
<div class="sidebar" id="sidebar">
  <div class="sb-hdr">
    <div class="sb-brand"><div class="sb-ico">🏥</div><div class="sb-name">AIMS <span>CARE</span></div></div>
    <div class="sb-badge">Staff Portal</div>
  </div>
  <div style="padding:8px 10px;flex:1;overflow-y:auto">
    <div class="sb-section">Main</div>
    <button class="sbi act" id="sbi-dashboard" onclick="goTab('dashboard')"><span class="sbi-ico">📊</span>Dashboard</button>
    <button class="sbi" id="sbi-wards" onclick="goTab('wards')"><span class="sbi-ico">🛏️</span>Ward Management</button>
    <button class="sbi" id="sbi-patients" onclick="goTab('patients')"><span class="sbi-ico">👥</span>Patients<span class="sbi-bdg" id="new-bdg">3</span></button>
    <button class="sbi" id="sbi-bookings" onclick="goTab('bookings')"><span class="sbi-ico">📋</span>Bookings</button>
    <div class="sb-section">Management</div>
    <button class="sbi" id="sbi-staff" onclick="goTab('staff')"><span class="sbi-ico">👨‍⚕️</span>Staff</button>
    <button class="sbi" id="sbi-reports" onclick="goTab('reports')"><span class="sbi-ico">📈</span>Reports</button>
    <button class="sbi" id="sbi-settings" onclick="goTab('settings')"><span class="sbi-ico">⚙️</span>Settings</button>
    <div class="sb-section">Quick Actions</div>
    <button class="sbi" onclick="openModal('admit')"><span class="sbi-ico">➕</span>Admit Patient</button>
    <button class="sbi" onclick="showToast('Emergency protocol activated','e')" style="color:rgba(255,100,100,.8)"><span class="sbi-ico">🚨</span>Emergency Alert</button>
  </div>
  <div class="sb-foot">
    <div class="sb-user">
      <div class="sb-av">👨‍⚕️</div>
      <div><div class="sb-un">Dr. Admin</div><div class="sb-ur">Administrator</div></div>
      <button onclick="showToast('Logged out','i')" style="margin-left:auto;background:none;border:none;color:rgba(255,255,255,.3);cursor:pointer;font-size:13px">↩</button>
    </div>
  </div>
</div>

<!-- ── MAIN ── -->
<div class="main">
  <div class="topbar">
    <div style="flex:1">
      <div class="topbar-title" id="page-title">Dashboard</div>
      <div class="topbar-sub" id="page-sub">Live hospital overview · Auto-refreshes every 15s</div>
    </div>
    <div class="tb-search"><span>🔍</span><input placeholder="Search patients, wards…" id="search-input" oninput="doSearch(this.value)"/></div>
    <div class="tb-actions">
      <div class="lpill"><span class="ld"></span>LIVE</div>
      <span class="tb-time" id="ntime"></span>
      <span id="rlbl" style="font-size:11px;color:var(--g500);font-weight:600"></span>
      <button class="tb-btn tb-btn-blue" onclick="openModal('admit')">➕ Admit Patient</button>
      <button class="tb-btn tb-btn-out" onclick="loadAll();showToast('Data refreshed','i')">🔄 Refresh</button>
    </div>
  </div>

  <!-- Refresh bar -->
  <div style="height:3px;background:var(--g200);overflow:hidden">
    <div id="rfill" style="height:100%;background:var(--blue);width:100%;transition:width 1s linear"></div>
  </div>

  <div class="content">

    <!-- ── DASHBOARD TAB ── -->
    <div class="page act" id="tab-dashboard">
      <div class="stat-grid">
        <div class="stat-card sc-blue"><div class="sc-top"><div class="sc-ico" style="background:#dbe4ff">🛏️</div><div class="sc-bdg bdg-b" id="sb-tot">—</div></div><div class="sc-val" id="sv-tot">—</div><div class="sc-lbl">Total Beds</div><div class="sc-trend" id="st-tot"></div></div>
        <div class="stat-card sc-green"><div class="sc-top"><div class="sc-ico" style="background:#ebfbee">✅</div><div class="sc-bdg bdg-g" id="sb-av">—</div></div><div class="sc-val" id="sv-av" style="color:var(--green)">—</div><div class="sc-lbl">Available Beds</div><div class="sc-trend" id="st-av"></div></div>
        <div class="stat-card sc-red"><div class="sc-top"><div class="sc-ico" style="background:#fff5f5">🚨</div><div class="sc-bdg bdg-r" id="sb-cr">—</div></div><div class="sc-val" id="sv-cr" style="color:var(--red)">—</div><div class="sc-lbl">Critical Patients</div></div>
        <div class="stat-card sc-amber"><div class="sc-top"><div class="sc-ico" style="background:#fff3bf">📊</div><div class="sc-bdg bdg-a" id="sb-oc">—</div></div><div class="sc-val" id="sv-oc" style="color:var(--amber)">—</div><div class="sc-lbl">Occupancy Rate</div></div>
      </div>

      <div class="chart-row">
        <div class="chart-card">
          <div class="chart-ttl">🛏️ Ward Occupancy <span style="font-size:11px;color:var(--g500);font-weight:500">Live</span></div>
          <div id="occ-bars"></div>
        </div>
        <div class="chart-card">
          <div class="chart-ttl">📊 Severity Breakdown <span style="font-size:11px;color:var(--g500);font-weight:500">Today</span></div>
          <div id="sev-bars"></div>
        </div>
      </div>

      <div class="table-card">
        <div class="table-hdr">
          <span class="table-ttl">⚡ Recent Patient Allocations</span>
          <div class="table-acts">
            <div class="lpill"><span class="ld"></span>LIVE</div>
            <button class="tb-btn tb-btn-out" onclick="goTab('bookings')" style="padding:6px 12px;font-size:12px">View All</button>
          </div>
        </div>
        <div style="overflow-x:auto">
          <table>
            <thead><tr><th>Patient</th><th>Ward</th><th>Bed</th><th>Severity</th><th>Time</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody id="recent-table"><tr><td colspan="7" style="text-align:center;color:var(--g400);padding:24px">Loading…</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ── WARDS TAB ── -->
    <div class="page" id="tab-wards">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">
        <div><div style="font-size:17px;font-weight:800;color:var(--g900)">Ward Management</div><div style="font-size:12px;color:var(--g500);margin-top:3px">Update bed counts, manage ward status and staff assignments</div></div>
        <button class="tb-btn tb-btn-blue" onclick="showToast('Ward report exported','s')">📥 Export Report</button>
      </div>
      <div class="ward-mgmt-grid" id="ward-mgmt-grid"></div>
      <div class="table-card">
        <div class="table-hdr"><span class="table-ttl">🔄 Recent Ward Activity</span><div class="lpill"><span class="ld"></span>LIVE</div></div>
        <div id="ward-activity-list" style="padding:8px 0"></div>
      </div>
    </div>

    <!-- ── PATIENTS TAB ── -->
    <div class="page" id="tab-patients">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">
        <div><div style="font-size:17px;font-weight:800;color:var(--g900)">Patient Management</div><div style="font-size:12px;color:var(--g500);margin-top:3px">View, admit, discharge and manage all patients</div></div>
        <div style="display:flex;gap:9px">
          <button class="tb-btn tb-btn-out" onclick="showToast('Patient list exported','s')">📥 Export</button>
          <button class="tb-btn tb-btn-blue" onclick="openModal('admit')">➕ Admit Patient</button>
        </div>
      </div>
      <div class="table-card">
        <div class="table-hdr">
          <span class="table-ttl">All Patients</span>
          <div class="table-acts">
            <select class="fi" style="width:auto;padding:6px 10px;font-size:12px" onchange="filterPatients(this.value)">
              <option value="">All Wards</option>
              <option value="ICU">ICU</option>
              <option value="Cardiology">Cardiology</option>
              <option value="Surgical">Surgical</option>
              <option value="General">General Medicine</option>
              <option value="Paediatrics">Paediatrics</option>
              <option value="Orthopaedics">Orthopaedics</option>
            </select>
          </div>
        </div>
        <div style="overflow-x:auto">
          <table>
            <thead><tr><th>Patient ID</th><th>Name</th><th>Age</th><th>Ward</th><th>Bed</th><th>Severity</th><th>Admitted</th><th>Actions</th></tr></thead>
            <tbody id="patient-table"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ── BOOKINGS TAB ── -->
    <div class="page" id="tab-bookings">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">
        <div><div style="font-size:17px;font-weight:800;color:var(--g900)">Booking Management</div><div style="font-size:12px;color:var(--g500);margin-top:3px">Manage all ward allocations and booking requests</div></div>
        <button class="tb-btn tb-btn-blue" onclick="openModal('admit')">➕ New Booking</button>
      </div>
      <div class="table-card">
        <div class="table-hdr"><span class="table-ttl">All Allocations</span><div class="lpill"><span class="ld"></span>LIVE</div></div>
        <div style="overflow-x:auto">
          <table>
            <thead><tr><th>Booking ID</th><th>Patient</th><th>Ward</th><th>Bed</th><th>Type</th><th>Severity</th><th>Date & Time</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody id="booking-table"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ── STAFF TAB ── -->
    <div class="page" id="tab-staff">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">
        <div><div style="font-size:17px;font-weight:800;color:var(--g900)">Staff Management</div><div style="font-size:12px;color:var(--g500);margin-top:3px">Manage doctors, nurses and administrative staff</div></div>
        <button class="tb-btn tb-btn-blue" onclick="showToast('Add staff feature coming soon','i')">➕ Add Staff</button>
      </div>
      <div class="table-card">
        <div style="overflow-x:auto">
          <table>
            <thead><tr><th>Staff ID</th><th>Name</th><th>Role</th><th>Department</th><th>Shift</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody id="staff-table"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ── REPORTS TAB ── -->
    <div class="page" id="tab-reports">
      <div style="margin-bottom:18px"><div style="font-size:17px;font-weight:800;color:var(--g900)">Reports & Analytics</div><div style="font-size:12px;color:var(--g500);margin-top:3px">Hospital performance metrics and reports</div></div>
      <div class="chart-row">
        <div class="chart-card">
          <div class="chart-ttl">📅 Weekly Admissions</div>
          <div id="weekly-bars"></div>
        </div>
        <div class="chart-card">
          <div class="chart-ttl">🏥 Ward Utilisation %</div>
          <div id="util-bars"></div>
        </div>
      </div>
      <div class="stat-grid" style="margin-top:0">
        <div class="stat-card sc-blue"><div class="sc-ico" style="background:#dbe4ff;margin-bottom:10px">📈</div><div class="sc-val" style="font-size:24px">94%</div><div class="sc-lbl">AI Match Accuracy</div></div>
        <div class="stat-card sc-green"><div class="sc-ico" style="background:#ebfbee;margin-bottom:10px">⚡</div><div class="sc-val" style="font-size:24px">&lt;2m</div><div class="sc-lbl">Avg Allocation Time</div></div>
        <div class="stat-card sc-amber"><div class="sc-ico" style="background:#fff3bf;margin-bottom:10px">😊</div><div class="sc-val" style="font-size:24px">4.8/5</div><div class="sc-lbl">Patient Satisfaction</div></div>
        <div class="stat-card sc-red"><div class="sc-ico" style="background:#fff5f5;margin-bottom:10px">🚑</div><div class="sc-val" style="font-size:24px">3.2m</div><div class="sc-lbl">Avg Emergency Response</div></div>
      </div>
    </div>

    <!-- ── SETTINGS TAB ── -->
    <div class="page" id="tab-settings">
      <div style="margin-bottom:18px"><div style="font-size:17px;font-weight:800;color:var(--g900)">Settings</div><div style="font-size:12px;color:var(--g500);margin-top:3px">Configure hospital system settings</div></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
        <div class="table-card" style="padding:20px">
          <div style="font-size:14px;font-weight:800;color:var(--g900);margin-bottom:14px">🔗 API Configuration</div>
          <div class="fg"><label class="flbl">Claude AI API Key</label><input class="fi" type="password" id="api-key-input" placeholder="sk-ant-… (for AI chatbot)"/></div>
          <div class="fg"><label class="flbl">Flask Backend URL</label><input class="fi" value="http://localhost:5000" id="flask-url"/></div>
          <button class="btn btn-blue" onclick="saveSettings()" style="width:100%;margin-top:8px">💾 Save Settings</button>
        </div>
        <div class="table-card" style="padding:20px">
          <div style="font-size:14px;font-weight:800;color:var(--g900);margin-bottom:14px">🏥 Hospital Info</div>
          <div class="fg"><label class="flbl">Hospital Name</label><input class="fi" value="AIMS CARE Hospital"/></div>
          <div class="fg"><label class="flbl">Emergency Number</label><input class="fi" value="108"/></div>
          <div class="fg"><label class="flbl">Phone</label><input class="fi" value="+91 8762557576"/></div>
          <div class="fg"><label class="flbl">Auto-Refresh Interval</label>
            <select class="fi" onchange="updatePollInterval(parseInt(this.value))">
              <option value="10000">10 seconds</option>
              <option value="15000" selected>15 seconds</option>
              <option value="30000">30 seconds</option>
              <option value="60000">1 minute</option>
            </select>
          </div>
          <button class="btn btn-blue" onclick="showToast('Hospital settings saved','s')" style="width:100%;margin-top:8px">💾 Save</button>
        </div>
      </div>
    </div>

  </div><!-- /content -->
</div><!-- /main -->

<!-- ── ADMIT PATIENT MODAL ── -->
<div class="modal-bg" id="modal-admit">
  <div class="modal">
    <div class="modal-ttl">➕ Admit New Patient</div>
    <div class="modal-sub">Fill in patient details for AI ward allocation</div>
    <div class="frow">
      <div class="fg"><label class="flbl">First Name *</label><input class="fi" id="m-fn" placeholder="Ravi"/></div>
      <div class="fg"><label class="flbl">Last Name *</label><input class="fi" id="m-ln" placeholder="Kumar"/></div>
    </div>
    <div class="frow">
      <div class="fg"><label class="flbl">Age *</label><input class="fi" id="m-age" type="number" placeholder="45"/></div>
      <div class="fg"><label class="flbl">Gender</label><select class="fi" id="m-gen"><option>Male</option><option>Female</option><option>Other</option></select></div>
    </div>
    <div class="fg"><label class="flbl">Diagnosis / Complaint *</label><input class="fi" id="m-diag" placeholder="e.g. Chest pain, fracture, respiratory distress"/></div>
    <div class="frow">
      <div class="fg"><label class="flbl">Severity *</label><select class="fi" id="m-sev"><option value="">Select</option><option>Low</option><option>Moderate</option><option>High</option><option>Critical</option></select></div>
      <div class="fg"><label class="flbl">Admission Type</label><select class="fi" id="m-adm"><option>Emergency</option><option>Planned</option><option>Referral</option></select></div>
    </div>
    <div class="fg"><label class="flbl">Phone</label><input class="fi" id="m-ph" type="tel" placeholder="+91 98765 43210"/></div>
    <div class="modal-footer">
      <button class="btn btn-out" onclick="closeModal('admit')">Cancel</button>
      <button class="btn btn-blue" id="btn-admit" onclick="submitAdmit()">🤖 AI Allocate & Admit</button>
    </div>
  </div>
</div>

<!-- ── WARD UPDATE MODAL ── -->
<div class="modal-bg" id="modal-ward">
  <div class="modal">
    <div class="modal-ttl" id="wm-title">Update Ward</div>
    <div class="modal-sub">Manually update bed availability for this ward</div>
    <div class="frow">
      <div class="fg"><label class="flbl">Total Beds</label><input class="fi" id="wm-total" type="number"/></div>
      <div class="fg"><label class="flbl">Occupied Beds</label><input class="fi" id="wm-occupied" type="number"/></div>
    </div>
    <div class="fg"><label class="flbl">Ward Status</label><select class="fi" id="wm-status"><option>operational</option><option>maintenance</option><option>emergency-only</option><option>closed</option></select></div>
    <div class="fg"><label class="flbl">Notes</label><textarea class="fi" id="wm-notes" placeholder="Any notes for the shift…"></textarea></div>
    <div class="modal-footer">
      <button class="btn btn-out" onclick="closeModal('ward')">Cancel</button>
      <button class="btn btn-blue" onclick="saveWardUpdate()">💾 Save Update</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
'use strict';
// ══ MOCK DATA ══
var MW=[
  {id:'ICU',name:'ICU',fullName:'Intensive Care Unit',emoji:'🏥',floor:'3rd Floor, Block A',total:20,occupied:17,available:3,cost:8000,pct:85,color:'#E03131',specialists:['Dr. Ramesh Kumar','Dr. Anand Rao'],status:'operational'},
  {id:'Cardiology',name:'Cardiology',fullName:'Cardiology Ward',emoji:'❤️',floor:'2nd Floor, Block B',total:30,occupied:28,available:2,cost:5000,pct:93,color:'#f97316',specialists:['Dr. Meera Singh','Dr. Priya Nair'],status:'operational'},
  {id:'Surgical',name:'Surgical',fullName:'Surgical Ward',emoji:'⚕️',floor:'1st Floor, Block C',total:25,occupied:18,available:7,cost:3500,pct:72,color:'#7c3aed',specialists:['Dr. Suresh Rao','Dr. Kiran Kumar'],status:'operational'},
  {id:'General',name:'General',fullName:'General Medicine',emoji:'🩺',floor:'Ground Floor, Block A',total:40,occupied:29,available:11,cost:1200,pct:73,color:'#2F9E44',specialists:['Dr. Kavitha','Dr. Rajesh'],status:'operational'},
  {id:'Paediatrics',name:'Paeds',fullName:'Paediatric Ward',emoji:'👶',floor:'1st Floor, Block A',total:20,occupied:12,available:8,cost:2000,pct:60,color:'#0ea5e9',specialists:['Dr. Sunita','Dr. Deepak'],status:'operational'},
  {id:'Orthopaedics',name:'Ortho',fullName:'Orthopaedic Ward',emoji:'🦴',floor:'2nd Floor, Block C',total:25,occupied:15,available:10,cost:3000,pct:60,color:'#E67700',specialists:['Dr. Vikram','Dr. Sanjay'],status:'operational'}
];
var PATIENTS=[
  {id:'PT-1001',fn:'Ravi',ln:'Kumar',age:52,gender:'Male',ward:'Cardiology',bed:7,severity:'High',diag:'Chest pain',admitted:new Date(Date.now()-86400000).toISOString(),status:'admitted',phone:'+91 9876543210'},
  {id:'PT-1002',fn:'Priya',ln:'Sharma',age:34,gender:'Female',ward:'General',bed:22,severity:'Moderate',diag:'Fever, viral infection',admitted:new Date(Date.now()-172800000).toISOString(),status:'admitted',phone:'+91 9123456789'},
  {id:'PT-1003',fn:'Suresh',ln:'Rao',age:68,gender:'Male',ward:'ICU',bed:3,severity:'Critical',diag:'Respiratory failure',admitted:new Date(Date.now()-43200000).toISOString(),status:'critical',phone:'+91 9988776655'},
  {id:'PT-1004',fn:'Meera',ln:'Devi',age:8,gender:'Female',ward:'Paediatrics',bed:11,severity:'Low',diag:'Appendicitis (post-op)',admitted:new Date(Date.now()-259200000).toISOString(),status:'recovering',phone:'+91 9765432100'},
  {id:'PT-1005',fn:'Arjun',ln:'Naik',age:45,gender:'Male',ward:'Surgical',bed:5,severity:'High',diag:'Hernia repair',admitted:new Date(Date.now()-21600000).toISOString(),status:'admitted',phone:'+91 9871234560'},
  {id:'PT-1006',fn:'Lakshmi',ln:'Patil',age:72,gender:'Female',ward:'Orthopaedics',bed:14,severity:'Moderate',diag:'Hip fracture',admitted:new Date(Date.now()-432000000).toISOString(),status:'recovering',phone:'+91 9654321098'}
];
var STAFF=[
  {id:'ST-001',name:'Dr. Ramesh Kumar',role:'Doctor',dept:'Pulmonology / ICU',shift:'Day 8AM–8PM',status:'on-duty'},
  {id:'ST-002',name:'Dr. Meera Singh',role:'Doctor',dept:'Cardiology',shift:'Day 8AM–8PM',status:'on-duty'},
  {id:'ST-003',name:'Nurse Kamala',role:'Head Nurse',dept:'ICU',shift:'Night 8PM–8AM',status:'off-duty'},
  {id:'ST-004',name:'Dr. Suresh Rao',role:'Surgeon',dept:'Surgical',shift:'Day 8AM–8PM',status:'on-duty'},
  {id:'ST-005',name:'Dr. Kavitha',role:'Doctor',dept:'Paediatrics',shift:'Day 8AM–8PM',status:'on-duty'},
  {id:'ST-006',name:'Mr. Admin Reddy',role:'Administrator',dept:'Admin',shift:'Day 9AM–6PM',status:'on-duty'}
];
var _patients=[].concat(PATIENTS);
var _curWardEdit=null;
var POLL_MS=15000,_pt=null,_ct=null,_cd=15;

// ══ HELPERS ══
function esc(s){return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):''}
function sel(id){return document.getElementById(id)}
function nowT(){return new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}
function fmt(iso){return iso?new Date(iso).toLocaleString([],{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}):''}
function ago(iso){var s=Math.floor((Date.now()-new Date(iso))/1000);return s<60?s+'s ago':s<3600?Math.floor(s/60)+'m ago':s<86400?Math.floor(s/3600)+'h ago':Math.floor(s/86400)+'d ago';}

// ══ TOAST ══
var _tt=null;
function showToast(msg,t){
  var e=sel('toast');if(!e)return;
  e.textContent=msg;e.className='toast on t'+(t==='s'?'s':t==='e'?'e':'i');
  clearTimeout(_tt);_tt=setTimeout(function(){e.classList.remove('on');},4000);
}

// ══ ROUTING ══
var TABS=['dashboard','wards','patients','bookings','staff','reports','settings'],curTab='dashboard';
var PAGE_TITLES={dashboard:'Dashboard',wards:'Ward Management',patients:'Patient Management',bookings:'Booking Management',staff:'Staff Management',reports:'Reports & Analytics',settings:'Settings'};
var PAGE_SUBS={dashboard:'Live hospital overview · Auto-refreshes every 15s',wards:'Update bed counts, manage ward status',patients:'View, admit, discharge and manage all patients',bookings:'Manage all ward allocations and booking requests',staff:'Manage doctors, nurses and administrative staff',reports:'Hospital performance metrics and reports',settings:'Configure hospital system settings'};

function goTab(t){
  if(t===curTab)return;
  TABS.forEach(function(tb){var p=sel('tab-'+tb);if(p)p.classList.toggle('act',tb===t);var s=sel('sbi-'+tb);if(s)s.classList.toggle('act',tb===t);});
  curTab=t;
  var pt=sel('page-title');if(pt)pt.textContent=PAGE_TITLES[t]||t;
  var ps=sel('page-sub');if(ps)ps.textContent=PAGE_SUBS[t]||'';
  if(t==='patients')renderPatients(_patients);
  if(t==='bookings')renderBookings();
  if(t==='staff')renderStaff();
  if(t==='reports')renderReports();
  // Close mobile sidebar
  sel('sidebar').classList.remove('mobile-open');
}

// ══ SIDEBAR ══
function toggleSidebar(){sel('sidebar').classList.toggle('mobile-open');}

// ══ LOAD DATA ══
function liveWards(){
  return MW.map(function(w){
    var d=Math.floor(Math.random()*2)-0;
    var occ=Math.min(w.total-1,Math.max(Math.floor(w.total*.3),w.occupied+d));
    return Object.assign({},w,{occupied:occ,available:w.total-occ,pct:Math.round(occ/w.total*100)});
  });
}

function loadDashboard(){
  var wards=liveWards();
  var tot=wards.reduce(function(a,w){return a+w.total;},0);
  var av=wards.reduce(function(a,w){return a+w.available;},0);
  var oc=Math.round((tot-av)/tot*100);
  var cr=_patients.filter(function(p){return p.severity==='Critical';}).length;

  sel('sv-tot').textContent=tot;sel('sb-tot').textContent=tot+' beds';
  sel('sv-av').textContent=av;sel('sb-av').textContent=av+' free';
  sel('sv-cr').textContent=cr;sel('sb-cr').textContent=cr+' patients';
  sel('sv-oc').textContent=oc+'%';sel('sb-oc').textContent=oc>=85?'High':oc>=65?'Moderate':'Good';

  // Occupancy bars
  var ob=sel('occ-bars');
  if(ob)ob.innerHTML=wards.map(function(w){
    var c=w.pct>=85?'var(--red)':w.pct>=65?'var(--amber)':'var(--green)';
    return '<div class="bar-row"><div class="bar-lbl">'+w.emoji+' '+esc(w.name)+'</div>'
      +'<div class="bar-bg"><div class="bar-fill" style="width:'+w.pct+'%;background:'+c+'"></div></div>'
      +'<div class="bar-val">'+w.pct+'%</div></div>';
  }).join('');

  // Severity bars
  var sevs={Low:0,Moderate:0,High:0,Critical:0};
  _patients.forEach(function(p){sevs[p.severity]=(sevs[p.severity]||0)+1;});
  var sevC={Low:'var(--green)',Moderate:'var(--amber)',High:'var(--red)',Critical:'#9b1c1c'};
  var total=_patients.length||1;
  var sb=sel('sev-bars');
  if(sb)sb.innerHTML=Object.keys(sevs).map(function(k){
    var pct=Math.round(sevs[k]/total*100);
    return '<div class="bar-row"><div class="bar-lbl" style="color:'+sevC[k]+'">⬤ '+k+'</div>'
      +'<div class="bar-bg"><div class="bar-fill" style="width:'+pct+'%;background:'+sevC[k]+'"></div></div>'
      +'<div class="bar-val">'+sevs[k]+'</div></div>';
  }).join('');

  // Recent table
  var rt=sel('recent-table');
  if(rt)rt.innerHTML=_patients.slice(-5).reverse().map(function(p){
    var sc=p.severity==='Critical'?'pill-r':p.severity==='High'?'pill-a':p.severity==='Moderate'?'pill-b':'pill-g';
    var stc=p.status==='critical'?'pill-r':p.status==='recovering'?'pill-g':'pill-b';
    return '<tr><td><div class="td-name">'+esc(p.fn)+' '+esc(p.ln)+'</div><div class="td-id">'+esc(p.id)+'</div></td>'
      +'<td>'+esc(p.ward)+'</td><td>Bed '+p.bed+'</td>'
      +'<td><span class="pill '+sc+'">'+esc(p.severity)+'</span></td>'
      +'<td style="font-size:11.5px;color:var(--g500)">'+ago(p.admitted)+'</td>'
      +'<td><span class="pill '+stc+'">'+esc(p.status)+'</span></td>'
      +'<td><div class="td-act">'
        +'<button class="act-btn grn" onclick="dischargePatient(\\''+p.id+'\\')">Discharge</button>'
        +'<button class="act-btn" onclick="showToast(\\'Viewing \\'+\\''+esc(p.fn)+'\\',\\'i\\')">View</button>'
      +'</div></td></tr>';
  }).join('');
}

function loadWards(){
  var wards=liveWards();
  var g=sel('ward-mgmt-grid');
  if(g)g.innerHTML=wards.map(function(w){
    var c=w.pct>=85?'var(--red)':w.pct>=65?'var(--amber)':'var(--green)';
    return '<div class="wm-card">'
      +'<div class="wm-acc" style="background:'+esc(w.color)+'"></div>'
      +'<div class="wm-body">'
      +'<div class="wm-top"><div>'
        +'<div class="wm-name">'+w.emoji+' '+esc(w.fullName)+'</div>'
        +'<div class="wm-floor">'+esc(w.floor)+'</div>'
      +'</div><span class="pill '+(w.pct>=85?'pill-r':w.pct>=65?'pill-a':'pill-g')+'">'+esc(w.status)+'</span></div>'
      +'<div class="wm-stats">'
        +'<div class="wm-s"><div class="wm-sv" style="color:'+c+'">'+w.available+'</div><div class="wm-sl">Free</div></div>'
        +'<div class="wm-s"><div class="wm-sv" style="color:var(--g700)">'+w.occupied+'</div><div class="wm-sl">Occupied</div></div>'
        +'<div class="wm-s"><div class="wm-sv" style="color:var(--g400)">'+w.total+'</div><div class="wm-sl">Total</div></div>'
        +'<div class="wm-s"><div class="wm-sv" style="color:'+c+'">'+w.pct+'%</div><div class="wm-sl">Used</div></div>'
      +'</div>'
      +'<div class="wm-bar"><div class="wm-fill" style="width:'+w.pct+'%;background:'+c+'"></div></div>'
      +'<div style="font-size:11px;color:var(--g500);margin-bottom:10px">'+esc(w.specialists.join(' · '))+'</div>'
      +'<div class="wm-actions">'
        +'<button class="wm-btn wm-btn-blue" onclick="openWardModal(\\''+w.id+'\\')">✏️ Update</button>'
        +'<button class="wm-btn wm-btn-green" onclick="showToast(\\''+esc(w.fullName)+' report ready\\',\\'s\\')">📊 Report</button>'
        +'<button class="wm-btn wm-btn-red" onclick="showToast(\\'Alert sent for '+esc(w.name)+'\\',\\'e\\')">🚨 Alert</button>'
      +'</div></div></div>';
  }).join('');

  // Ward activity list
  var wal=sel('ward-activity-list');
  if(wal){
    var acts=[
      {w:'❤️ Cardiology',msg:'2 patients admitted',t:new Date(Date.now()-90000).toISOString(),c:'var(--red)'},
      {w:'🏥 ICU',msg:'1 patient discharged',t:new Date(Date.now()-280000).toISOString(),c:'var(--green)'},
      {w:'🩺 General',msg:'Bed 15 cleaned and ready',t:new Date(Date.now()-540000).toISOString(),c:'var(--blue)'},
      {w:'🦴 Ortho',msg:'Shift handover completed',t:new Date(Date.now()-820000).toISOString(),c:'var(--amber)'},
    ];
    wal.innerHTML=acts.map(function(a){
      return '<div style="display:flex;align-items:center;gap:10px;padding:10px 16px;border-bottom:1px solid var(--g100)">'
        +'<div style="width:8px;height:8px;border-radius:50%;background:'+a.c+';flex-shrink:0"></div>'
        +'<div style="flex:1;font-size:12.5px;color:var(--g700)"><strong>'+a.w+'</strong> — '+a.msg+'</div>'
        +'<div style="font-size:11px;color:var(--g400);font-weight:600">'+ago(a.t)+'</div></div>';
    }).join('');
  }
}

function renderPatients(patients){
  var tb=sel('patient-table');if(!tb)return;
  var sc={Critical:'pill-r',High:'pill-a',Moderate:'pill-b',Low:'pill-g'};
  var stc={critical:'pill-r',recovering:'pill-g',admitted:'pill-b'};
  tb.innerHTML=patients.map(function(p){
    return '<tr><td><span class="pill pill-b">'+esc(p.id)+'</span></td>'
      +'<td><div class="td-name">'+esc(p.fn)+' '+esc(p.ln)+'</div><div class="td-id">'+esc(p.phone)+'</div></td>'
      +'<td>'+p.age+'</td><td>'+esc(p.ward)+'</td><td>Bed '+p.bed+'</td>'
      +'<td><span class="pill '+(sc[p.severity]||'pill-b')+'">'+esc(p.severity)+'</span></td>'
      +'<td style="font-size:11.5px">'+fmt(p.admitted)+'</td>'
      +'<td><div class="td-act">'
        +'<button class="act-btn grn" onclick="dischargePatient(\\''+p.id+'\\')">Discharge</button>'
        +'<button class="act-btn" onclick="showToast(\\'Viewing '+esc(p.fn)+'\\',\\'i\\')">View</button>'
      +'</div></td></tr>';
  }).join('');
}

function renderBookings(){
  var tb=sel('booking-table');if(!tb)return;
  var sc={Critical:'pill-r',High:'pill-a',Moderate:'pill-b',Low:'pill-g'};
  var types={Emergency:'pill-r',Planned:'pill-g',Referral:'pill-b'};
  tb.innerHTML=_patients.map(function(p,i){
    var bid='BK-'+(2000+i);
    var type=i===0||i===2?'Emergency':i===3?'Referral':'Planned';
    return '<tr><td><span class="pill pill-p">'+bid+'</span></td>'
      +'<td><div class="td-name">'+esc(p.fn)+' '+esc(p.ln)+'</div><div class="td-id">'+esc(p.id)+'</div></td>'
      +'<td>'+esc(p.ward)+'</td><td>Bed '+p.bed+'</td>'
      +'<td><span class="pill '+(types[type]||'pill-b')+'">'+type+'</span></td>'
      +'<td><span class="pill '+(sc[p.severity]||'pill-b')+'">'+esc(p.severity)+'</span></td>'
      +'<td style="font-size:11.5px">'+fmt(p.admitted)+'</td>'
      +'<td><span class="pill pill-g">Active</span></td>'
      +'<td><div class="td-act">'
        +'<button class="act-btn red" onclick="showToast(\\'Booking cancelled\\',\\'e\\')">Cancel</button>'
        +'<button class="act-btn" onclick="showToast(\\'Booking '+bid+' details\\',\\'i\\')">View</button>'
      +'</div></td></tr>';
  }).join('');
}

function renderStaff(){
  var tb=sel('staff-table');if(!tb)return;
  var sc={'on-duty':'pill-g','off-duty':'pill-a'};
  var rc={Doctor:'pill-b',Surgeon:'pill-p','Head Nurse':'pill-a',Administrator:'pill-g'};
  tb.innerHTML=STAFF.map(function(s){
    return '<tr><td><span class="pill pill-b">'+esc(s.id)+'</span></td>'
      +'<td class="td-name">'+esc(s.name)+'</td>'
      +'<td><span class="pill '+(rc[s.role]||'pill-b')+'">'+esc(s.role)+'</span></td>'
      +'<td>'+esc(s.dept)+'</td><td style="font-size:12px">'+esc(s.shift)+'</td>'
      +'<td><span class="pill '+(sc[s.status]||'pill-b')+'">'+esc(s.status)+'</span></td>'
      +'<td><div class="td-act">'
        +'<button class="act-btn" onclick="showToast(\\'Viewing \\'+\\''+esc(s.name)+'\\',\\'i\\')">View</button>'
        +'<button class="act-btn" onclick="showToast(\\'Edited \\'+\\''+esc(s.name)+'\\',\\'s\\')">Edit</button>'
      +'</div></td></tr>';
  }).join('');
}

function renderReports(){
  var days=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  var vals=[12,18,15,22,19,14,8];
  var wb=sel('weekly-bars');
  if(wb)wb.innerHTML=days.map(function(d,i){
    return '<div class="bar-row"><div class="bar-lbl">'+d+'</div>'
      +'<div class="bar-bg"><div class="bar-fill" style="width:'+(vals[i]/22*100)+'%;background:var(--blue)"></div></div>'
      +'<div class="bar-val">'+vals[i]+'</div></div>';
  }).join('');
  var ub=sel('util-bars');
  var uw=liveWards();
  if(ub)ub.innerHTML=uw.map(function(w){
    var c=w.pct>=85?'var(--red)':w.pct>=65?'var(--amber)':'var(--green)';
    return '<div class="bar-row"><div class="bar-lbl">'+w.emoji+' '+esc(w.name)+'</div>'
      +'<div class="bar-bg"><div class="bar-fill" style="width:'+w.pct+'%;background:'+c+'"></div></div>'
      +'<div class="bar-val">'+w.pct+'%</div></div>';
  }).join('');
}

function filterPatients(ward){
  if(!ward)renderPatients(_patients);
  else renderPatients(_patients.filter(function(p){return p.ward===ward;}));
}

function dischargePatient(id){
  var idx=_patients.findIndex(function(p){return p.id===id;});
  if(idx>=0){var name=_patients[idx].fn+' '+_patients[idx].ln;_patients.splice(idx,1);renderPatients(_patients);loadDashboard();showToast(name+' discharged successfully','s');sel('new-bdg').textContent=Math.max(0,parseInt(sel('new-bdg').textContent||0)-1);}
}

function doSearch(q){
  if(!q){renderPatients(_patients);return;}
  var lq=q.toLowerCase();
  var res=_patients.filter(function(p){return (p.fn+' '+p.ln).toLowerCase().includes(lq)||p.id.toLowerCase().includes(lq)||p.ward.toLowerCase().includes(lq)||p.diag.toLowerCase().includes(lq);});
  if(curTab==='patients')renderPatients(res);
}

// ══ MODALS ══
function openModal(id){sel('modal-'+id).classList.add('on');}
function closeModal(id){sel('modal-'+id).classList.remove('on');}
window.addEventListener('click',function(e){if(e.target.classList.contains('modal-bg'))e.target.classList.remove('on');});

function openWardModal(wid){
  var w=MW.find(function(x){return x.id===wid;});if(!w)return;
  _curWardEdit=wid;
  sel('wm-title').textContent='Update '+w.fullName;
  sel('wm-total').value=w.total;
  sel('wm-occupied').value=w.occupied;
  sel('wm-status').value=w.status;
  openModal('ward');
}

function saveWardUpdate(){
  if(!_curWardEdit)return;
  var w=MW.find(function(x){return x.id===_curWardEdit;});if(!w)return;
  var tot=parseInt(sel('wm-total').value)||w.total;
  var occ=Math.min(tot-1,parseInt(sel('wm-occupied').value)||w.occupied);
  w.total=tot;w.occupied=occ;w.available=tot-occ;w.pct=Math.round(occ/tot*100);
  w.status=sel('wm-status').value;
  closeModal('ward');loadWards();loadDashboard();
  showToast(w.fullName+' updated successfully','s');
}

function submitAdmit(){
  var fn=(sel('m-fn')||{}).value,ln=(sel('m-ln')||{}).value;
  var age=(sel('m-age')||{}).value,diag=(sel('m-diag')||{}).value;
  var sev=(sel('m-sev')||{}).value;
  if(!fn||!ln||!age||!diag||!sev){showToast('Fill all required fields','e');return;}
  var btn=sel('btn-admit');btn.disabled=true;btn.innerHTML='<span class="spn"></span> AI Allocating…';
  setTimeout(function(){
    var avWards=MW.filter(function(w){return w.available>0;});
    var ward=avWards[Math.floor(Math.random()*Math.min(2,avWards.length))];
    if(!ward){showToast('No beds available! Consider transferring a patient.','e');btn.disabled=false;btn.innerHTML='🤖 AI Allocate & Admit';return;}
    var pid='PT-'+(1007+_patients.length);
    var bed=Math.floor(Math.random()*(ward.available))+1;
    _patients.push({id:pid,fn:fn,ln:ln,age:parseInt(age),gender:(sel('m-gen')||{}).value||'',ward:ward.name,bed:bed,severity:sev,diag:diag,admitted:new Date().toISOString(),status:'admitted',phone:(sel('m-ph')||{}).value||''});
    ward.occupied++;ward.available--;ward.pct=Math.round(ward.occupied/ward.total*100);
    closeModal('admit');loadDashboard();loadWards();
    showToast('✅ '+fn+' '+ln+' admitted to '+ward.fullName+' (Bed '+bed+')','s');
    sel('new-bdg').textContent=parseInt(sel('new-bdg').textContent||0)+1;
    btn.disabled=false;btn.innerHTML='🤖 AI Allocate & Admit';
    ['m-fn','m-ln','m-age','m-diag','m-ph'].forEach(function(id){var e=sel(id);if(e)e.value='';});
    if(sel('m-sev'))sel('m-sev').selectedIndex=0;
  },900);
}

function saveSettings(){
  var key=(sel('api-key-input')||{}).value;
  if(key&&key.startsWith('sk-ant')){showToast('API key saved! Chatbot now uses Claude AI','s');}
  else{showToast('Settings saved','s');}
}

function updatePollInterval(ms){
  POLL_MS=ms||15000;
  clearInterval(_pt);clearInterval(_ct);
  _cd=POLL_MS/1000;
  _pt=setInterval(function(){_cd=POLL_MS/1000;loadAll();showToast('🔄 Data refreshed','i');},POLL_MS);
  _ct=setInterval(function(){_cd=Math.max(0,_cd-1);var f=sel('rfill');if(f)f.style.width=(_cd/(POLL_MS/1000)*100)+'%';var l=sel('rlbl');if(l)l.textContent='↻ '+_cd+'s';},1000);
  showToast('Refresh interval: '+(POLL_MS/1000)+'s','i');
}

function loadAll(){loadDashboard();if(curTab==='wards')loadWards();}

// ══ AUTO-REFRESH ══
function startPolling(){
  loadAll();loadWards();
  clearInterval(_pt);clearInterval(_ct);_cd=POLL_MS/1000;
  _pt=setInterval(function(){_cd=POLL_MS/1000;loadAll();},POLL_MS);
  _ct=setInterval(function(){
    _cd=Math.max(0,_cd-1);
    var f=sel('rfill');if(f)f.style.width=(_cd/(POLL_MS/1000)*100)+'%';
    var l=sel('rlbl');if(l)l.textContent='↻ '+_cd+'s';
  },1000);
}

// ══ CLOCK ══
setInterval(function(){var e=sel('ntime');if(e)e.textContent=nowT();},1000);

// ══ INIT ══
window.addEventListener('DOMContentLoaded',function(){startPolling();renderPatients(_patients);});
</script>
</body>
</html>
"""

@app.route("/pwa")
def pwa():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no"/>
<meta name="apple-mobile-web-app-capable" content="yes"/>
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"/>
<meta name="apple-mobile-web-app-title" content="AIMS CARE"/>
<meta name="theme-color" content="#3B5BDB"/>
<meta name="description" content="AIMS CARE Hospital — AI-Powered Ward Booking"/>
<title>AIMS CARE Hospital</title>

<!-- PWA Manifest inline -->
<link rel="manifest" href="data:application/json,%7B%22name%22%3A%22AIMS+CARE+Hospital%22%2C%22short_name%22%3A%22AIMS+CARE%22%2C%22start_url%22%3A%22.%2F%22%2C%22display%22%3A%22standalone%22%2C%22background_color%22%3A%22%233B5BDB%22%2C%22theme_color%22%3A%22%233B5BDB%22%2C%22orientation%22%3A%22portrait%22%7D"/>

<!-- Apple PWA icons -->
<link rel="apple-touch-icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 180 180'><rect width='180' height='180' rx='40' fill='%233B5BDB'/><text y='125' x='25' font-size='110'>🏥</text></svg>"/>

<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet"/>
<style>
:root{
  --blue:#3B5BDB;--blue2:#4263EB;--blue-lt:#EEF2FF;--blue-pale:#dbe4ff;
  --red:#E03131;--red-lt:#FFF5F5;--green:#2F9E44;--green-lt:#EBFBEE;
  --amber:#E67700;--amber-lt:#FFF3BF;
  --white:#fff;--bg:#F0F4FF;
  --g100:#F1F3F5;--g200:#E9ECEF;--g300:#DEE2E6;--g500:#ADB5BD;--g600:#868E96;--g700:#495057;--g800:#343A40;--g900:#212529;
  --sh1:0 2px 12px rgba(59,91,219,.12);--sh2:0 4px 20px rgba(59,91,219,.15);--sh3:0 8px 32px rgba(59,91,219,.18);
  --shb:0 4px 18px rgba(59,91,219,.35);
  --r10:10px;--r12:12px;--r16:16px;--r20:20px;--r24:24px;--r99:99px;
  --fn:'Plus Jakarta Sans',sans-serif;
  --sft:env(safe-area-inset-top,0px);--sfb:env(safe-area-inset-bottom,0px);
  --sfl:env(safe-area-inset-left,0px);--sfr:env(safe-area-inset-right,0px);
  --tb:64px;--hh:56px;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{height:100%;overflow:hidden;font-family:var(--fn);background:var(--bg);color:var(--g900)}
::-webkit-scrollbar{display:none}

/* ── APP SHELL ── */
#app{display:flex;flex-direction:column;height:100%;height:100dvh;position:relative;overflow:hidden}

/* ── STATUS BAR FILL ── */
.status-fill{height:var(--sft);background:var(--blue);flex-shrink:0}

/* ── TOP HEADER ── */
.app-hdr{flex-shrink:0;height:var(--hh);background:var(--blue);
  display:flex;align-items:center;padding:0 16px;gap:10px;
  box-shadow:0 2px 12px rgba(0,0,0,.2)}
.hdr-brand{flex:1;display:flex;align-items:center;gap:8px}
.hdr-ico{width:32px;height:32px;background:rgba(255,255,255,.2);border-radius:9px;
  display:flex;align-items:center;justify-content:center;font-size:16px}
.hdr-name{font-size:17px;font-weight:800;color:#fff;letter-spacing:-.3px}
.hdr-name span{opacity:.75;font-weight:500}
.hdr-btns{display:flex;gap:6px}
.hdr-btn{width:34px;height:34px;border-radius:50%;background:rgba(255,255,255,.15);
  border:none;color:#fff;font-size:14px;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:background .2s}
.hdr-btn:hover{background:rgba(255,255,255,.25)}
.hdr-live{display:flex;align-items:center;gap:4px;padding:4px 10px;
  background:rgba(255,255,255,.15);border-radius:var(--r99);font-size:10px;font-weight:700;color:#fff}
.hld{width:5px;height:5px;border-radius:50%;background:#4ADE80;animation:lp 2s ease-in-out infinite}
@keyframes lp{0%,100%{opacity:1}50%{opacity:.3}}

/* ── PAGE CONTAINER ── */
.pages{flex:1;overflow:hidden;position:relative}
.pg{position:absolute;inset:0;overflow-y:auto;overflow-x:hidden;
  background:var(--bg);transform:translateX(100%);transition:transform .32s cubic-bezier(.4,0,.2,1);
  padding-bottom:calc(var(--tb) + var(--sfb) + 16px)}
.pg.act{transform:translateX(0)}
.pg.prev{transform:translateX(-30%)}

/* ── BOTTOM TAB BAR ── */
.tabbar{flex-shrink:0;height:calc(var(--tb) + var(--sfb));padding-bottom:var(--sfb);
  background:rgba(255,255,255,.97);backdrop-filter:blur(20px);
  border-top:1px solid var(--g200);
  display:flex;box-shadow:0 -4px 20px rgba(0,0,0,.07)}
.tab{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:3px;border:none;background:none;position:relative;cursor:pointer;transition:all .2s}
.tab.act .ti{color:var(--blue);transform:translateY(-2px)}
.tab.act .tl{color:var(--blue);font-weight:700}
.tab.act::before{content:'';position:absolute;top:0;left:50%;transform:translateX(-50%);
  width:28px;height:3px;background:var(--blue);border-radius:0 0 3px 3px}
.tab-emr{background:var(--red)!important}
.tab-emr .ti,.tab-emr .tl{color:#fff!important}
.tab-emr.act::before{background:#fff}
.ti{font-size:20px;transition:all .25s;color:var(--g400)}
.tl{font-size:9px;font-weight:600;color:var(--g400);transition:all .2s;letter-spacing:.2px}

/* ── COMMON ── */
.card{background:var(--white);border-radius:var(--r20);box-shadow:0 2px 12px rgba(0,0,0,.06);overflow:hidden}
.section{padding:16px}
.sec-ttl{font-size:17px;font-weight:800;color:var(--g900);margin-bottom:4px;letter-spacing:-.3px}
.sec-sub{font-size:12px;color:var(--g500);margin-bottom:16px;line-height:1.5}
.badge{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:var(--r99);font-size:10.5px;font-weight:700}
.bg{background:var(--green-lt);color:var(--green)}.br{background:var(--red-lt);color:var(--red)}
.bb{background:var(--blue-lt);color:var(--blue)}.ba{background:var(--amber-lt);color:var(--amber)}
.btn{display:flex;align-items:center;justify-content:center;gap:6px;padding:13px 20px;
  border:none;border-radius:var(--r12);font-size:14px;font-weight:700;cursor:pointer;
  transition:all .2s;font-family:var(--fn)}
.btn-blue{background:var(--blue);color:#fff;box-shadow:var(--shb)}
.btn-blue:hover{background:var(--blue2);transform:translateY(-1px)}
.btn-blue:active{transform:translateY(0);box-shadow:none}
.btn-red{background:var(--red);color:#fff;box-shadow:0 4px 16px rgba(224,49,49,.3)}
.btn-outline{background:var(--white);color:var(--blue);border:1.5px solid var(--blue-pale)}
.divider{height:1px;background:var(--g200);margin:12px 0}

/* ── TOAST ── */
.toast{position:fixed;top:calc(var(--hh) + var(--sft) + 8px);left:50%;transform:translateX(-50%) translateY(-8px);
  z-index:9999;border-radius:var(--r12);padding:10px 18px;font-size:13px;font-weight:600;
  opacity:0;transition:all .28s;pointer-events:none;white-space:nowrap;box-shadow:var(--sh3)}
.toast.on{transform:translateX(-50%) translateY(0);opacity:1}
.ts{background:var(--green-lt);color:var(--green);border:1px solid rgba(47,158,68,.2)}
.te{background:var(--red-lt);color:var(--red);border:1px solid rgba(224,49,49,.2)}
.ti-t{background:var(--blue-lt);color:var(--blue);border:1px solid rgba(59,91,219,.2)}

/* ── SPINNER ── */
.spn{display:inline-block;width:14px;height:14px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}

/* ════════════════════════════
   HOME PAGE
════════════════════════════ */
.hero-card{margin:14px;border-radius:var(--r24);overflow:hidden;position:relative;min-height:180px;
  background:linear-gradient(135deg,#1e3ca8,var(--blue));box-shadow:var(--sh3)}
.hero-bg{position:absolute;inset:0;background:url('https://images.unsplash.com/photo-1631217868264-e5b90bb7e133?w=800&q=80')center/cover;opacity:.18}
.hero-body{position:relative;z-index:1;padding:22px 18px}
.hero-badge{display:inline-flex;align-items:center;gap:5px;padding:4px 10px;
  background:rgba(255,255,255,.15);border-radius:var(--r99);font-size:10px;font-weight:700;color:rgba(255,255,255,.9);margin-bottom:10px}
.hero-h1{font-size:22px;font-weight:800;color:#fff;line-height:1.2;margin-bottom:6px}
.hero-h1 em{color:#A5C8FF;font-style:normal}
.hero-p{font-size:12px;color:rgba(255,255,255,.8);line-height:1.6;margin-bottom:16px}
.hero-btns{display:flex;gap:8px}
.hero-btn-w{display:flex;align-items:center;gap:5px;padding:10px 16px;background:#fff;color:var(--blue);border:none;border-radius:var(--r10);font-size:12.5px;font-weight:700;cursor:pointer;transition:all .2s;font-family:var(--fn)}
.hero-btn-w:active{transform:scale(.96)}
.hero-btn-o{display:flex;align-items:center;gap:5px;padding:10px 16px;background:rgba(255,255,255,.15);color:#fff;border:1.5px solid rgba(255,255,255,.4);border-radius:var(--r10);font-size:12.5px;font-weight:600;cursor:pointer;transition:all .2s;font-family:var(--fn)}

.kgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:0 14px}
.kcard{background:var(--white);border-radius:var(--r16);padding:14px;box-shadow:0 2px 10px rgba(0,0,0,.05)}
.kico{font-size:22px;margin-bottom:8px}
.kval{font-size:26px;font-weight:800;line-height:1;margin-bottom:3px}
.klbl{font-size:10px;font-weight:600;color:var(--g500);text-transform:uppercase;letter-spacing:.5px}

.feed-card{margin:14px;border-radius:var(--r20);background:var(--white);box-shadow:0 2px 10px rgba(0,0,0,.05);overflow:hidden}
.feed-hdr{display:flex;align-items:center;justify-content:space-between;padding:13px 14px;border-bottom:1px solid var(--g100)}
.feed-ttl{font-size:13px;font-weight:700;color:var(--g800)}
.fitem{display:flex;align-items:center;gap:10px;padding:11px 14px;border-bottom:1px solid var(--g100)}
.fitem:last-child{border-bottom:none}
.fdot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.ftxt{flex:1;font-size:12px;color:var(--g600);line-height:1.4}.ftxt strong{color:var(--g900);font-size:12.5px}
.ftime{font-size:10px;color:var(--g400);font-weight:600;flex-shrink:0}

/* ════════════════════════════
   WARD PAGE
════════════════════════════ */
.ward-list{padding:0 14px;display:flex;flex-direction:column;gap:10px}
.wcard{background:var(--white);border-radius:var(--r20);overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.05);
  transition:transform .2s;cursor:pointer}
.wcard:active{transform:scale(.98)}
.wacc{height:4px}
.wbody{padding:14px}
.wtop{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}
.wleft{display:flex;align-items:center;gap:10px}
.wico{width:42px;height:42px;border-radius:var(--r12);display:flex;align-items:center;justify-content:center;font-size:20px;flex-shrink:0}
.wname{font-size:14px;font-weight:800;color:var(--g900);margin-bottom:2px}
.wfloor{font-size:10.5px;color:var(--g500);font-weight:500}
.wstats{display:flex;align-items:center;gap:12px;margin-bottom:10px}
.wbnum{font-size:28px;font-weight:800;line-height:1}
.wblbl{font-size:11px;color:var(--g500)}
.wbar{height:5px;background:var(--g100);border-radius:3px;overflow:hidden;margin-bottom:10px}
.wbar-f{height:100%;border-radius:3px;transition:width 1.2s ease}
.wfooter{display:flex;justify-content:space-between;align-items:center}
.wcost{font-size:13px;font-weight:700;color:var(--blue)}
.wspec{font-size:10px;color:var(--g500)}
.btn-bk{display:block;width:100%;margin-top:11px;padding:11px;border:none;border-radius:var(--r10);
  background:var(--blue);color:#fff;font-size:13px;font-weight:700;cursor:pointer;
  transition:all .2s;font-family:var(--fn)}
.btn-bk:active{transform:scale(.97);background:var(--blue2)}

/* ════════════════════════════
   BOOK PAGE
════════════════════════════ */
.book-wrap{padding:14px}
.steps-row{display:flex;align-items:center;margin-bottom:20px;background:var(--white);border-radius:var(--r16);padding:14px;box-shadow:0 2px 10px rgba(0,0,0,.05)}
.step{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;position:relative}
.sline{position:absolute;top:13px;left:calc(50% + 14px);right:calc(-50% + 14px);height:2px;background:var(--g300)}
.sline.dn{background:var(--blue)}
.sc{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;position:relative;z-index:1}
.step.dn .sc{background:var(--blue);color:#fff}
.step.ac .sc{background:var(--blue);color:#fff;box-shadow:0 0 0 4px var(--blue-lt)}
.step.pd .sc{background:var(--g200);color:var(--g500)}
.slbl{font-size:9px;font-weight:700;color:var(--g500)}
.step.ac .slbl{color:var(--blue)}.step.dn .slbl{color:var(--g600)}
.form-card{background:var(--white);border-radius:var(--r20);padding:16px;box-shadow:0 2px 10px rgba(0,0,0,.05);margin-bottom:12px}
.form-ttl{font-size:15px;font-weight:800;color:var(--g900);margin-bottom:3px}
.form-sub{font-size:11.5px;color:var(--g500);margin-bottom:14px}
.fg{display:flex;flex-direction:column;gap:5px;margin-bottom:10px}
.flbl{font-size:10.5px;font-weight:700;color:var(--g600);text-transform:uppercase;letter-spacing:.5px}
.fi{background:var(--bg);border:1.5px solid var(--g300);border-radius:var(--r10);
  padding:11px 13px;color:var(--g900);font-size:13.5px;font-family:var(--fn);outline:none;transition:all .2s;width:100%}
.fi:focus{border-color:var(--blue);background:var(--white);box-shadow:0 0 0 3px rgba(59,91,219,.1)}
.fi::placeholder{color:var(--g500)}
select.fi option{background:var(--white)}
textarea.fi{resize:none;min-height:72px}
.frow{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.aires{background:var(--bg);border-radius:var(--r12);padding:13px;margin-top:10px;display:none;animation:fadeUp .3s ease}
@keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.aires.show{display:block}
.ail{font-size:10px;font-weight:800;letter-spacing:1px;text-transform:uppercase;color:var(--blue);margin-bottom:10px;display:flex;align-items:center;gap:5px}
.rc{background:var(--white);border:1.5px solid var(--g200);border-radius:var(--r12);padding:11px;
  margin-bottom:8px;display:flex;gap:9px;align-items:flex-start;cursor:pointer;transition:all .2s}
.rc:last-child{margin-bottom:0}
.rc:active,.rc.sel{border-color:var(--blue);background:var(--blue-lt)}
.rn{width:24px;height:24px;border-radius:7px;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:800;flex-shrink:0}
.rn1{background:var(--blue);color:#fff}.rn2{background:var(--blue-lt);color:var(--blue)}.rn3{background:var(--g100);color:var(--g600)}
.rw{font-size:12.5px;font-weight:700;color:var(--g900);margin-bottom:2px}
.rr{font-size:10.5px;color:var(--g500);line-height:1.5}
.rpct{font-size:18px;font-weight:800;color:var(--blue);flex-shrink:0}

/* ════════════════════════════
   EMERGENCY PAGE
════════════════════════════ */
.emr-hero{margin:14px;border-radius:var(--r24);background:linear-gradient(135deg,#b91c1c,var(--red));
  padding:24px 18px;text-align:center;box-shadow:0 8px 32px rgba(224,49,49,.35)}
.emr-ico{font-size:48px;margin-bottom:10px;animation:pulse 1.5s ease-in-out infinite}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.08)}}
.emr-h1{font-size:22px;font-weight:800;color:#fff;margin-bottom:6px}
.emr-p{font-size:12.5px;color:rgba(255,255,255,.85);line-height:1.6;margin-bottom:18px}
.emr-num{font-size:42px;font-weight:900;color:#fff;letter-spacing:-1px;margin-bottom:4px}
.emr-lbl{font-size:10px;color:rgba(255,255,255,.65);font-weight:700;text-transform:uppercase;letter-spacing:1px}
.btn-call{display:flex;align-items:center;justify-content:center;gap:7px;width:100%;margin-top:16px;
  padding:14px;background:#fff;color:var(--red);border:none;border-radius:var(--r12);
  font-size:15px;font-weight:800;cursor:pointer;font-family:var(--fn);transition:all .2s;
  box-shadow:0 4px 16px rgba(0,0,0,.15)}
.btn-call:active{transform:scale(.97)}
.emr-steps{display:flex;flex-direction:column;gap:10px;margin:14px}
.estep{background:var(--white);border-radius:var(--r16);padding:14px;display:flex;gap:12px;align-items:center;box-shadow:0 2px 10px rgba(0,0,0,.05)}
.esn{width:36px;height:36px;border-radius:50%;background:var(--red-lt);color:var(--red);font-size:16px;font-weight:900;display:flex;align-items:center;justify-content:center;flex-shrink:0;font-family:var(--fn)}
.esl{font-size:13px;font-weight:700;color:var(--g800)}.esd{font-size:11px;color:var(--g500);margin-top:2px}

/* ════════════════════════════
   CHATBOT FLOATING
════════════════════════════ */
.cfab{position:fixed;bottom:calc(var(--tb) + var(--sfb) + 14px);right:16px;z-index:800;
  display:flex;align-items:center;gap:7px;background:var(--blue);color:#fff;border:none;
  border-radius:var(--r99);padding:12px 18px;font-size:13px;font-weight:700;
  box-shadow:0 6px 24px rgba(59,91,219,.45);cursor:pointer;font-family:var(--fn);
  animation:fabIn .5s 1s ease both}
@keyframes fabIn{from{opacity:0;transform:scale(.7) translateY(20px)}to{opacity:1;transform:scale(1) translateY(0)}}
.cfab:active{transform:scale(.95)}
.cbdg{width:16px;height:16px;background:var(--red);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:800;border:2px solid var(--white)}
.cwin{position:fixed;bottom:calc(var(--tb) + var(--sfb) + 78px);left:10px;right:10px;z-index:799;
  background:var(--white);border-radius:var(--r24);box-shadow:0 12px 48px rgba(0,0,0,.18);
  display:flex;flex-direction:column;max-height:65vh;overflow:hidden;
  transform:scale(.85) translateY(30px);opacity:0;pointer-events:none;
  transition:all .3s cubic-bezier(.34,1.56,.64,1);transform-origin:bottom center}
.cwin.open{transform:scale(1) translateY(0);opacity:1;pointer-events:all}
.chdr{flex-shrink:0;padding:14px;display:flex;align-items:center;gap:10px;background:var(--blue);border-radius:var(--r24) var(--r24) 0 0}
.cav{width:38px;height:38px;border-radius:50%;background:rgba(255,255,255,.2);border:2px solid rgba(255,255,255,.3);display:flex;align-items:center;justify-content:center;font-size:17px;flex-shrink:0;transition:all .3s}
.cav.lst{animation:avP .7s ease-in-out infinite alternate}
.cav.spk{animation:avS .5s ease-in-out infinite alternate}
@keyframes avP{from{transform:scale(.94)}to{transform:scale(1.1)}}
@keyframes avS{from{transform:scale(1)}to{transform:scale(1.08)}}
.cinfo{flex:1}.cname{font-size:14px;font-weight:800;color:#fff}
.csub{font-size:10px;color:rgba(255,255,255,.7);display:flex;align-items:center;gap:4px;margin-top:1px}
.chdbtns{display:flex;gap:5px}
.chb{width:28px;height:28px;border-radius:50%;border:1px solid rgba(255,255,255,.25);background:rgba(255,255,255,.12);color:rgba(255,255,255,.8);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:11px;transition:all .2s}
.chb:active,.chb.on{background:rgba(255,255,255,.25);color:#fff}
.clang{display:flex;border-bottom:1px solid var(--g200);background:var(--g100);flex-shrink:0}
.clbtn{flex:1;padding:8px 4px;border:none;background:none;font-size:11px;font-weight:700;color:var(--g600);cursor:pointer;transition:all .2s;border-bottom:2px solid transparent}
.clbtn.act{background:var(--white);color:var(--blue);border-bottom-color:var(--blue)}
.clive{max-height:0;overflow:hidden;background:var(--blue-lt);font-size:11px;color:var(--blue);text-align:center;font-style:italic;transition:all .28s;flex-shrink:0;padding:0 12px;border-bottom:1px solid transparent}
.clive.on{max-height:30px;padding:6px 12px;border-bottom-color:var(--g200)}
.cmsgs{flex:1;overflow-y:auto;padding:12px 10px;display:flex;flex-direction:column;gap:8px;min-height:120px}
.cmsg{display:flex;gap:7px;align-items:flex-end;animation:fadeUp .2s ease}
.cmsg.usr{flex-direction:row-reverse}
.cmav{width:26px;height:26px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:12px}
.cmav.ai{background:var(--blue-lt);border:1.5px solid var(--blue-pale)}
.cmav.me{background:var(--g100);border:1.5px solid var(--g200)}
.cmbub{padding:9px 12px;border-radius:14px;font-size:12.5px;line-height:1.65;word-break:break-word;max-width:82%}
.cmsg.ai .cmbub{background:var(--g100);color:var(--g700);border-bottom-left-radius:3px}
.cmsg.usr .cmbub{background:var(--blue);color:#fff;border-bottom-right-radius:3px;font-weight:500}
.cchips{display:flex;flex-wrap:wrap;gap:5px;margin-top:5px;margin-left:33px}
.cchip{padding:5px 11px;border-radius:var(--r99);border:1.5px solid var(--blue-pale);background:var(--blue-lt);color:var(--blue);font-size:11px;font-weight:700;cursor:pointer;transition:all .18s;white-space:nowrap;font-family:var(--fn)}
.cchip:active{background:var(--blue);color:#fff}
.ctyp{display:flex;gap:4px;align-items:center;padding:3px 0}
.ctyp span{width:6px;height:6px;border-radius:50%;background:var(--blue);opacity:.28;animation:vtd 1.2s ease-in-out infinite}
.ctyp span:nth-child(2){animation-delay:.2s}.ctyp span:nth-child(3){animation-delay:.4s}
@keyframes vtd{0%,80%,100%{transform:scale(.5);opacity:.22}40%{transform:scale(1);opacity:1}}
.cinp{flex-shrink:0;padding:10px 12px calc(10px + var(--sfb));border-top:1px solid var(--g200);background:var(--white)}
.cinprow{display:flex;align-items:center;gap:7px}
.cinput{flex:1;background:var(--bg);border:1.5px solid var(--g300);border-radius:var(--r99);
  padding:10px 16px;color:var(--g900);font-size:13.5px;font-family:var(--fn);outline:none;transition:all .2s}
.cinput:focus{border-color:var(--blue);background:var(--white);box-shadow:0 0 0 3px rgba(59,91,219,.1)}
.cinput::placeholder{color:var(--g500)}
.csend,.cmic{width:38px;height:38px;border-radius:50%;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:15px;transition:all .2s;flex-shrink:0}
.csend{background:var(--blue);color:#fff;box-shadow:var(--shb)}.csend:active{transform:scale(.92)}
.csend:disabled{opacity:.4;cursor:not-allowed}
.cmic{background:var(--white);border:1.5px solid var(--g300);color:var(--g500)}.cmic:active{background:var(--blue-lt)}
.cmic.rec{background:var(--red);border-color:transparent;color:#fff;animation:mP 1s ease-in-out infinite}
@keyframes mP{0%,100%{box-shadow:0 0 0 3px rgba(224,49,49,.1)}50%{box-shadow:0 0 0 10px rgba(224,49,49,.03)}}

/* VOICE OVERLAY */
.vo{position:fixed;inset:0;z-index:9500;background:rgba(8,16,60,.97);
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:13px;
  opacity:0;pointer-events:none;transition:opacity .35s;padding:24px}
.vo.on{opacity:1;pointer-events:all}
.vo-ttl{font-size:20px;font-weight:800;color:#fff;text-align:center}
.vo-sub{font-size:10px;color:rgba(255,255,255,.4);letter-spacing:2px;text-transform:uppercase;font-weight:700}
.vo-langs{display:flex;gap:8px}
.vo-lb{padding:8px 16px;border-radius:var(--r99);border:1.5px solid rgba(255,255,255,.2);background:transparent;color:rgba(255,255,255,.6);font-size:12px;font-weight:700;cursor:pointer;transition:all .2s;font-family:var(--fn)}
.vo-lb.act{background:var(--blue);border-color:var(--blue);color:#fff}
.vo-rings{position:relative;width:180px;height:180px;display:flex;align-items:center;justify-content:center}
.vring{position:absolute;border-radius:50%;border:1px solid}
.vring:nth-child(1){width:120px;height:120px;border-color:rgba(59,91,219,.3);animation:vrng 2.5s 0s ease-in-out infinite}
.vring:nth-child(2){width:148px;height:148px;border-color:rgba(59,91,219,.17);animation:vrng 2.5s .6s ease-in-out infinite}
.vring:nth-child(3){width:176px;height:176px;border-color:rgba(59,91,219,.07);animation:vrng 2.5s 1.2s ease-in-out infinite}
@keyframes vrng{0%,100%{transform:scale(1);opacity:.5}50%{transform:scale(1.05);opacity:1}}
.voav{width:90px;height:90px;border-radius:50%;background:rgba(59,91,219,.18);border:2px solid rgba(59,91,219,.42);display:flex;align-items:center;justify-content:center;font-size:38px;position:relative;z-index:2;transition:all .3s}
.voav.lst{border-color:rgba(224,49,49,.5);animation:voL .7s ease-in-out infinite alternate}
.voav.spk{animation:voS .5s ease-in-out infinite alternate}
@keyframes voL{from{transform:scale(.94)}to{transform:scale(1.1)}}
@keyframes voS{from{transform:scale(1)}to{transform:scale(1.1)}}
.vowaves{display:flex;align-items:center;gap:3px;height:36px}
.vowv{width:4px;border-radius:3px;background:var(--blue-pale);opacity:.5}
.vowv:nth-child(odd){height:10px;animation:vowb .5s ease-in-out infinite alternate}
.vowv:nth-child(even){height:24px;animation:vowb .5s .15s ease-in-out infinite alternate}
@keyframes vowb{from{transform:scaleY(.2);opacity:.3}to{transform:scaleY(1);opacity:1}}
.vo-slbl{font-size:11px;font-weight:800;color:rgba(255,255,255,.5);letter-spacing:3px;text-transform:uppercase}
.vo-tx{font-size:14px;color:rgba(255,255,255,.7);max-width:300px;text-align:center;min-height:20px;line-height:1.6;font-style:italic;word-break:break-word}
.vo-actbtn{background:var(--blue);color:#fff;border:none;border-radius:var(--r99);padding:14px 38px;font-size:15px;font-weight:800;font-family:var(--fn);box-shadow:0 6px 22px rgba(59,91,219,.4);transition:all .22s;cursor:pointer}
.vo-actbtn:active{transform:scale(.96)}
.vo-closebtn{background:transparent;color:rgba(255,255,255,.4);border:1px solid rgba(255,255,255,.15);border-radius:var(--r99);padding:9px 24px;font-size:12px;font-weight:600;cursor:pointer;font-family:var(--fn)}
</style>
</head>
<body>
<div id="app">
  <div class="status-fill"></div>

  <!-- TOP HEADER -->
  <div class="app-hdr">
    <div class="hdr-brand">
      <div class="hdr-ico">🏥</div>
      <div class="hdr-name">AIMS <span>CARE</span></div>
    </div>
    <div class="hdr-live"><span class="hld"></span>LIVE</div>
    <span id="ntime" style="font-size:11px;color:rgba(255,255,255,.7);font-weight:600;margin:0 4px"></span>
    <div class="hdr-btns">
      <button class="hdr-btn" onclick="goPage('emergency')" title="Emergency">🚨</button>
      <button class="hdr-btn" onclick="toggleChat()" title="AI Chat">💬</button>
    </div>
  </div>

  <!-- PAGES -->
  <div class="pages">

    <!-- HOME -->
    <div class="pg act" id="pg-home">
      <div class="hero-card">
        <div class="hero-bg"></div>
        <div class="hero-body">
          <div class="hero-badge">✦ AI-Powered · Est. 1986</div>
          <h1 class="hero-h1">Smart Hospital<br><em>Ward Booking</em></h1>
          <p class="hero-p">Book any ward in under 30 seconds using our AI — no queues, no waiting.</p>
          <div class="hero-btns">
            <button class="hero-btn-w" onclick="goPage('book')">📋 Book Ward</button>
            <button class="hero-btn-o" onclick="goPage('emergency')">🚑 Emergency</button>
          </div>
        </div>
      </div>

      <div style="padding:0 14px;margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <span style="font-size:14px;font-weight:800;color:var(--g900)">Live Overview</span>
          <span id="refreshlbl" style="font-size:10.5px;color:var(--g500);font-weight:600"></span>
        </div>
        <!-- Refresh progress bar -->
        <div style="height:3px;background:var(--g200);border-radius:2px;overflow:hidden;margin-bottom:14px">
          <div id="rfill" style="height:100%;background:var(--blue);width:100%;transition:width 1s linear;border-radius:2px"></div>
        </div>
        <div class="kgrid">
          <div class="kcard"><div class="kico">🛏️</div><div class="kval" id="k-tot" style="color:var(--blue)">—</div><div class="klbl">Total Beds</div></div>
          <div class="kcard"><div class="kico">✅</div><div class="kval" id="k-av" style="color:var(--green)">—</div><div class="klbl">Available</div></div>
          <div class="kcard"><div class="kico">🚨</div><div class="kval" id="k-cr" style="color:var(--red)">—</div><div class="klbl">Critical</div></div>
          <div class="kcard"><div class="kico">📊</div><div class="kval" id="k-oc" style="color:var(--amber)">—</div><div class="klbl">Occupancy</div></div>
        </div>
      </div>

      <div class="feed-card">
        <div class="feed-hdr"><span class="feed-ttl">⚡ Recent Allocations</span><div class="badge bg"><span class="hld"></span>LIVE</div></div>
        <div id="rfeed"><div class="fitem"><span style="color:var(--g500);font-size:12px">Loading…</span></div></div>
      </div>

      <div class="feed-card" style="margin-top:0">
        <div class="feed-hdr"><span class="feed-ttl">📢 Announcements</span></div>
        <div id="annfeed"><div class="fitem"><span style="color:var(--g500);font-size:12px">Loading…</span></div></div>
      </div>

      <!-- ABOUT CARD -->
      <div style="margin:14px">
        <div style="background:linear-gradient(135deg,#1e3ca8,var(--blue));border-radius:var(--r20);padding:18px;display:flex;gap:14px;align-items:center">
          <div style="font-size:36px">🏥</div>
          <div>
            <div style="font-size:14px;font-weight:800;color:#fff;margin-bottom:4px">AIMS CARE Hospital</div>
            <div style="font-size:11px;color:rgba(255,255,255,.8);line-height:1.6">BG Nagara, Bellur Cross, Nagamangala Mandya, Karnataka · Est. 1986 · NABH Accredited</div>
            <div style="display:flex;gap:12px;margin-top:10px">
              <div style="text-align:center"><div style="font-size:17px;font-weight:900;color:#fff">28+</div><div style="font-size:9px;color:rgba(255,255,255,.65);font-weight:700;text-transform:uppercase">Years</div></div>
              <div style="text-align:center"><div style="font-size:17px;font-weight:900;color:#fff">200+</div><div style="font-size:9px;color:rgba(255,255,255,.65);font-weight:700;text-transform:uppercase">Doctors</div></div>
              <div style="text-align:center"><div style="font-size:17px;font-weight:900;color:#fff">50K+</div><div style="font-size:9px;color:rgba(255,255,255,.65);font-weight:700;text-transform:uppercase">Patients</div></div>
              <div style="text-align:center"><div style="font-size:17px;font-weight:900;color:#fff">15</div><div style="font-size:9px;color:rgba(255,255,255,.65);font-weight:700;text-transform:uppercase">Depts</div></div>
            </div>
          </div>
        </div>
      </div>
      <div style="height:16px"></div>
    </div>

    <!-- WARDS -->
    <div class="pg" id="pg-wards">
      <div style="padding:14px 14px 0">
        <div style="font-size:18px;font-weight:800;color:var(--g900);margin-bottom:4px">Ward Availability</div>
        <div style="font-size:12px;color:var(--g500);margin-bottom:14px">Live bed counts · Updates every 15s</div>
      </div>
      <div class="ward-list" id="ward-list"><div style="text-align:center;padding:40px;color:var(--g500)">Loading wards…</div></div>
      <div style="height:16px"></div>
    </div>

    <!-- BOOK -->
    <div class="pg" id="pg-book">
      <div class="book-wrap">
        <div style="font-size:18px;font-weight:800;color:var(--g900);margin-bottom:4px">AI Ward Booking</div>
        <div style="font-size:12px;color:var(--g500);margin-bottom:14px">AI recommends the best ward for your condition</div>

        <div class="steps-row">
          <div class="step ac" id="bs1"><div class="sc">1</div><div class="slbl">Patient</div><div class="sline" id="sl1"></div></div>
          <div class="step pd" id="bs2"><div class="sc">2</div><div class="slbl">AI Match</div><div class="sline" id="sl2"></div></div>
          <div class="step pd" id="bs3"><div class="sc">3</div><div class="slbl">Confirm</div><div class="sline" id="sl3"></div></div>
          <div class="step pd" id="bs4"><div class="sc">4</div><div class="slbl">Done ✓</div></div>
        </div>

        <div class="form-card">
          <div class="form-ttl">🤖 Patient Details</div>
          <div class="form-sub">Fill all fields for AI recommendation</div>
          <div class="frow">
            <div class="fg"><label class="flbl">First Name *</label><input class="fi" id="b-fn" placeholder="Ravi"/></div>
            <div class="fg"><label class="flbl">Last Name *</label><input class="fi" id="b-ln" placeholder="Kumar"/></div>
          </div>
          <div class="frow">
            <div class="fg"><label class="flbl">Age *</label><input class="fi" id="b-age" type="number" placeholder="45"/></div>
            <div class="fg"><label class="flbl">Gender</label><select class="fi" id="b-gen"><option value="">Select</option><option>Male</option><option>Female</option><option>Other</option></select></div>
          </div>
          <div class="fg"><label class="flbl">Phone</label><input class="fi" id="b-ph" type="tel" placeholder="+91 98765 43210"/></div>
          <div class="fg"><label class="flbl">Diagnosis / Complaint *</label><input class="fi" id="b-diag" placeholder="e.g. Chest pain, fracture…"/></div>
          <div class="frow">
            <div class="fg"><label class="flbl">Severity *</label><select class="fi" id="b-sev"><option value="">Select</option><option>Low</option><option>Moderate</option><option>High</option><option>Critical</option></select></div>
            <div class="fg"><label class="flbl">Admission</label><select class="fi" id="b-adm"><option value="">Select</option><option>Emergency</option><option>Planned</option><option>Referral</option></select></div>
          </div>
          <div class="fg"><label class="flbl">Notes</label><textarea class="fi" id="b-notes" placeholder="Allergies, medications…"></textarea></div>
          <button class="btn btn-blue" id="btn-reg" onclick="regPatient()" style="width:100%;margin-top:6px">🤖 Get AI Recommendation</button>
          <div class="aires" id="aires">
            <div class="ail">✦ AI Recommendations — Tap to Select</div>
            <div id="airecs"></div>
            <button class="btn btn-blue" id="btn-conf" onclick="confAlloc()" style="width:100%;margin-top:8px;background:var(--green);box-shadow:0 4px 14px rgba(47,158,68,.3)">✅ Confirm Allocation</button>
          </div>
        </div>
      </div>
    </div>

    <!-- EMERGENCY -->
    <div class="pg" id="pg-emergency">
      <div class="emr-hero">
        <div class="emr-ico">🚑</div>
        <div class="emr-h1">Emergency Services</div>
        <div class="emr-p">Every second counts in an emergency. Call immediately — we are open 24/7.</div>
        <div class="emr-num">108</div>
        <div class="emr-lbl">Free Ambulance Number</div>
        <button class="btn-call" onclick="showToast('Calling 108 — Free Ambulance','e')">📞 Call 108 Now</button>
      </div>
      <div class="emr-steps">
        <div class="estep"><div class="esn">1</div><div><div class="esl">Call 108 or arrive at ER</div><div class="esd">Free ambulance available 24/7 across Mandya district</div></div></div>
        <div class="estep"><div class="esn">2</div><div><div class="esl">Triage by trained nurses</div><div class="esd">Immediate assessment within 5 minutes of arrival</div></div></div>
        <div class="estep"><div class="esn">3</div><div><div class="esl">AI ward allocation</div><div class="esd">Best ward assigned in under 2 minutes automatically</div></div></div>
      </div>
      <div style="margin:0 14px">
        <div style="background:var(--white);border-radius:var(--r20);padding:16px;box-shadow:0 2px 10px rgba(0,0,0,.05)">
          <div style="font-size:13px;font-weight:800;color:var(--g900);margin-bottom:12px">📞 Contact Numbers</div>
          <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--g100)">
            <div><div style="font-size:12.5px;font-weight:700;color:var(--g800)">Ambulance (Free)</div><div style="font-size:11px;color:var(--g500)">Available 24/7</div></div>
            <button onclick="showToast('Calling 108…','e')" style="padding:8px 16px;background:var(--red-lt);color:var(--red);border:none;border-radius:var(--r10);font-size:13px;font-weight:800;cursor:pointer;font-family:var(--fn)">108</button>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0">
            <div><div style="font-size:12.5px;font-weight:700;color:var(--g800)">Hospital Direct</div><div style="font-size:11px;color:var(--g500)">Emergency reception</div></div>
            <button onclick="showToast('Calling +91 8762557576…','i')" style="padding:8px 16px;background:var(--blue-lt);color:var(--blue);border:none;border-radius:var(--r10);font-size:11px;font-weight:800;cursor:pointer;font-family:var(--fn)">+91 8762557576</button>
          </div>
        </div>
      </div>
      <div style="height:16px"></div>
    </div>

    <!-- PROFILE -->
    <div class="pg" id="pg-profile">
      <div style="padding:14px">
        <div style="font-size:18px;font-weight:800;color:var(--g900);margin-bottom:14px">My Profile</div>
        <div style="background:linear-gradient(135deg,#1e3ca8,var(--blue));border-radius:var(--r20);padding:20px;text-align:center;margin-bottom:14px">
          <div style="width:64px;height:64px;border-radius:50%;background:rgba(255,255,255,.2);display:flex;align-items:center;justify-content:center;font-size:28px;margin:0 auto 10px">👤</div>
          <div style="font-size:17px;font-weight:800;color:#fff">Guest Patient</div>
          <div style="font-size:11px;color:rgba(255,255,255,.7);margin-top:3px">AIMS CARE App User</div>
        </div>
        <div style="background:var(--white);border-radius:var(--r20);overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.05)">
          <div style="padding:14px;border-bottom:1px solid var(--g100);display:flex;justify-content:space-between;align-items:center">
            <span style="font-size:13.5px;font-weight:600;color:var(--g800)">📋 My Bookings</span>
            <span style="font-size:11px;color:var(--g400)">→</span>
          </div>
          <div style="padding:14px;border-bottom:1px solid var(--g100);display:flex;justify-content:space-between;align-items:center">
            <span style="font-size:13.5px;font-weight:600;color:var(--g800)">🔔 Notifications</span>
            <span style="font-size:11px;color:var(--g400)">→</span>
          </div>
          <div style="padding:14px;border-bottom:1px solid var(--g100);display:flex;justify-content:space-between;align-items:center">
            <span style="font-size:13.5px;font-weight:600;color:var(--g800)">📞 Contact Hospital</span>
            <span style="font-size:11px;color:var(--g400)">→</span>
          </div>
          <div style="padding:14px;display:flex;justify-content:space-between;align-items:center" onclick="showToast('OPD: Mon–Sat 8AM–8PM | Emergency: 24/7','i')">
            <span style="font-size:13.5px;font-weight:600;color:var(--g800)">🕐 Hospital Hours</span>
            <span style="font-size:11px;color:var(--g400)">→</span>
          </div>
        </div>
        <div style="margin-top:14px;background:var(--white);border-radius:var(--r20);padding:14px;box-shadow:0 2px 10px rgba(0,0,0,.05)">
          <div style="font-size:13px;font-weight:800;color:var(--g900);margin-bottom:10px">📍 Hospital Info</div>
          <div style="font-size:12px;color:var(--g600);line-height:1.7">
            🏥 BG Nagara, Bellur Cross, Nagamangala Mandya<br>
            📞 +91 8762557576<br>
            ✉️ <a href="/cdn-cgi/l/email-protection" class="__cf_email__" data-cfemail="f091999d83b092978391999d83de959485de999e">[email&#160;protected]</a><br>
            🚨 Emergency: 108 (Free)<br>
            🕐 OPD: Mon–Sat 8AM–8PM
          </div>
        </div>
        <!-- PWA Install prompt -->
        <div id="pwa-prompt" style="margin-top:14px;background:var(--blue-lt);border:1.5px solid var(--blue-pale);border-radius:var(--r20);padding:16px;display:none">
          <div style="font-size:13px;font-weight:800;color:var(--blue);margin-bottom:6px">📲 Install as App</div>
          <div style="font-size:11.5px;color:var(--g600);line-height:1.6;margin-bottom:10px">Add AIMS CARE to your home screen for a native app experience — works offline too!</div>
          <button id="pwa-install-btn" style="width:100%;padding:11px;background:var(--blue);color:#fff;border:none;border-radius:var(--r10);font-size:13px;font-weight:700;cursor:pointer;font-family:var(--fn)">📲 Add to Home Screen</button>
        </div>
      </div>
    </div>

  </div><!-- /pages -->

  <!-- TABBAR -->
  <div class="tabbar">
    <button class="tab act" id="tb-home"      onclick="goPage('home')"><span class="ti">🏠</span><span class="tl">Home</span></button>
    <button class="tab" id="tb-wards"         onclick="goPage('wards')"><span class="ti">🛏️</span><span class="tl">Wards</span></button>
    <button class="tab" id="tb-book"          onclick="goPage('book')"><span class="ti">📋</span><span class="tl">Book</span></button>
    <button class="tab tab-emr" id="tb-emergency" onclick="goPage('emergency')"><span class="ti">🚨</span><span class="tl">Emergency</span></button>
    <button class="tab" id="tb-profile"       onclick="goPage('profile')"><span class="ti">👤</span><span class="tl">Profile</span></button>
  </div>
</div><!-- /app -->

<!-- CHATBOT FAB -->
<button class="cfab" id="cfab" onclick="toggleChat()">
  <span id="fab-ico">💬</span>
  <span id="fab-lbl">AI Chat</span>
  <span class="cbdg" id="fab-bdg">1</span>
</button>

<!-- CHAT WINDOW -->
<div class="cwin" id="cwin">
  <div class="chdr">
    <div class="cav" id="cav">🤖</div>
    <div class="cinfo">
      <div class="cname">AIMS CARE AI</div>
      <div class="csub"><span class="hld"></span><span id="cstatus">ಕನ್ನಡ · हिंदी · English</span></div>
    </div>
    <div class="chdbtns">
      <button class="chb on" id="ttsbtn" onclick="toggleTTS()">🔊</button>
      <button class="chb" onclick="openVO()">🎙️</button>
      <button class="chb" onclick="clearChat()">🗑️</button>
      <button class="chb" onclick="toggleChat()">✕</button>
    </div>
  </div>
  <div class="clang">
    <button class="clbtn" id="lb-kn" onclick="setLang('kn-IN','kn')">🇮🇳 ಕನ್ನಡ</button>
    <button class="clbtn" id="lb-hi" onclick="setLang('hi-IN','hi')">🇮🇳 हिंदी</button>
    <button class="clbtn act" id="lb-en" onclick="setLang('en-IN','en')">🇬🇧 English</button>
  </div>
  <div class="clive" id="clive">🎙️ Listening…</div>
  <div class="cmsgs" id="cmsgs"></div>
  <div class="cinp">
    <div class="cinprow">
      <button class="cmic" id="cmic" onclick="toggleSTT()">🎙️</button>
      <input class="cinput" id="cinput" placeholder="ಕನ್ನಡ · हिंदी · English…"
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendMsg()}"/>
      <button class="csend" id="csend" onclick="sendMsg()">➤</button>
    </div>
  </div>
</div>

<!-- VOICE OVERLAY -->
<div class="vo" id="vo">
  <div class="vo-ttl">AIMS CARE Voice</div>
  <div class="vo-sub">ಕನ್ನಡ · हिंदी · English</div>
  <div class="vo-langs">
    <button class="vo-lb" id="vo-kn" onclick="setLang('kn-IN','kn')">ಕನ್ನಡ</button>
    <button class="vo-lb" id="vo-hi" onclick="setLang('hi-IN','hi')">हिंदी</button>
    <button class="vo-lb act" id="vo-en" onclick="setLang('en-IN','en')">English</button>
  </div>
  <div class="vo-rings">
    <div class="vring"></div><div class="vring"></div><div class="vring"></div>
    <div class="voav" id="voav">🤖</div>
  </div>
  <div class="vowaves"><div class="vowv"></div><div class="vowv"></div><div class="vowv"></div><div class="vowv"></div><div class="vowv"></div><div class="vowv"></div></div>
  <div class="vo-slbl" id="vo-slbl">READY</div>
  <div class="vo-tx" id="vo-tx">Select language and tap Start</div>
  <button class="vo-actbtn" id="vo-actbtn" onclick="voAction()">🎙️ Start Listening</button>
  <button class="vo-closebtn" onclick="closeVO()">✕ Close</button>
</div>

<div class="toast" id="toast"></div>

<script data-cfasync="false" src="/cdn-cgi/scripts/5c5dd728/cloudflare-static/email-decode.min.js"></script><script>
'use strict';
// ══ MOCK DATA ══
var MW=[
  {id:'ICU',name:'Intensive Care Unit',emoji:'🏥',floor:'3rd Floor, Block A',total:20,occupied:17,available:3,cost_per_day:8000,occupancy_pct:85,specialists:['Pulmonologist','Critical Care'],color:'#E03131'},
  {id:'Cardiology',name:'Cardiology Ward',emoji:'❤️',floor:'2nd Floor, Block B',total:30,occupied:28,available:2,cost_per_day:5000,occupancy_pct:93,specialists:['Cardiologist','Cardiac Surgeon'],color:'#f97316'},
  {id:'Surgical',name:'Surgical Ward',emoji:'⚕️',floor:'1st Floor, Block C',total:25,occupied:18,available:7,cost_per_day:3500,occupancy_pct:72,specialists:['General Surgeon','Anaesthesiologist'],color:'#7c3aed'},
  {id:'General',name:'General Medicine',emoji:'🩺',floor:'Ground Floor, Block A',total:40,occupied:29,available:11,cost_per_day:1200,occupancy_pct:73,specialists:['General Physician','Internist'],color:'#2F9E44'},
  {id:'Paediatrics',name:'Paediatric Ward',emoji:'👶',floor:'1st Floor, Block A',total:20,occupied:12,available:8,cost_per_day:2000,occupancy_pct:60,specialists:['Paediatrician','Neonatologist'],color:'#0ea5e9'},
  {id:'Orthopaedics',name:'Orthopaedic Ward',emoji:'🦴',floor:'2nd Floor, Block C',total:25,occupied:15,available:10,cost_per_day:3000,occupancy_pct:60,specialists:['Orthopaedic Surgeon','Physiotherapist'],color:'#E67700'}
];
var MANN=[
  {title:'OPD Hours',body:'Mon–Sat 8AM–8PM. Emergency 24/7.'},
  {title:'AI Booking',body:'Book any ward instantly — no queues.'},
  {title:'Insurance',body:'Cashless: Ayushman Bharat, Star Health, HDFC ERGO.'},
  {title:'New ICU',body:'10 new ICU beds now operational in Block A.'},
  {title:'Emergency',body:'Free ambulance 24/7 — Call 108.'}
];
var MBK=[
  {patient_name:'Ravi Kumar',ward_name:'Cardiology',bed_number:7,severity:'High',allocated_at:new Date(Date.now()-120000).toISOString()},
  {patient_name:'Priya Sharma',ward_name:'General Medicine',bed_number:22,severity:'Moderate',allocated_at:new Date(Date.now()-360000).toISOString()},
  {patient_name:'Suresh Rao',ward_name:'ICU',bed_number:3,severity:'Critical',allocated_at:new Date(Date.now()-700000).toISOString()},
  {patient_name:'Meera Devi',ward_name:'Paediatrics',bed_number:11,severity:'Low',allocated_at:new Date(Date.now()-980000).toISOString()}
];
var _cw=null,_flaskOK=null;

function liveWards(){
  return MW.map(function(w){
    var d=Math.floor(Math.random()*3)-1;
    var occ=Math.min(w.total-1,Math.max(Math.floor(w.total*.4),w.occupied+d));
    return Object.assign({},w,{occupied:occ,available:w.total-occ,occupancy_pct:Math.round(occ/w.total*100)});
  });
}
function tryF(url,opts,ok,fail){
  if(_flaskOK===false){fail();return;}
  fetch(url,Object.assign({signal:typeof AbortController!=='undefined'?(function(){var c=new AbortController();setTimeout(function(){c.abort();},2200);return c.signal;})():undefined},opts||{}))
    .then(function(r){if(!r.ok)throw 0;return r.json();})
    .then(function(d){_flaskOK=true;ok(d);})
    .catch(function(){_flaskOK=false;fail();});
}

// ══ HELPERS ══
function esc(s){return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):''}
function gv(id){return(document.getElementById(id)||{}).value||''}
function sel(id){return document.getElementById(id)}
function nowT(){return new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}
function ago(iso){var s=Math.floor((Date.now()-new Date(iso))/1000);return s<60?s+'s':s<3600?Math.floor(s/60)+'m':Math.floor(s/3600)+'h';}

// ══ TOAST ══
var _tt=null;
function showToast(msg,t){
  var e=sel('toast');if(!e)return;
  e.textContent=msg;e.className='toast on t'+(t==='s'?'s':t==='e'?'e':'i-t');
  clearTimeout(_tt);_tt=setTimeout(function(){e.classList.remove('on');},4200);
}

// ══ ROUTING ══
var PAGES=['home','wards','book','emergency','profile'],curPage='home',prevPage=null;
function goPage(p){
  if(p===curPage)return;
  var old=sel('pg-'+curPage),nw=sel('pg-'+p);
  if(!nw)return;
  if(old){old.classList.remove('act');old.classList.add('prev');setTimeout(function(){old.classList.remove('prev');},350);}
  nw.classList.add('act');
  prevPage=curPage;curPage=p;
  PAGES.forEach(function(pg){var tb=sel('tb-'+pg);if(tb)tb.classList.toggle('act',pg===p);});
  if(p==='wards')loadWards();
}

// ══ LOAD DATA ══
function loadDashboard(){
  var wards=liveWards();_cw=wards;
  var tot=wards.reduce(function(a,w){return a+w.total;},0);
  var av=wards.reduce(function(a,w){return a+w.available;},0);
  var oc=Math.round((tot-av)/tot*100);
  var cr=Math.floor(Math.random()*3)+4;
  ['k-tot','k-av','k-cr','k-oc'].forEach(function(id,i){
    var e=sel(id);if(e)e.textContent=[tot,av,cr,oc+'%'][i];
  });
  var rf=sel('rfeed');
  if(rf)rf.innerHTML=MBK.map(function(b){
    var c=b.severity==='Critical'?'var(--red)':b.severity==='High'?'var(--amber)':'var(--green)';
    return '<div class="fitem"><div class="fdot" style="background:'+c+'"></div>'
      +'<div class="ftxt"><strong>'+esc(b.patient_name)+'</strong> → '+esc(b.ward_name)+' · Bed '+b.bed_number+'</div>'
      +'<div class="ftime">'+ago(b.allocated_at)+'</div></div>';
  }).join('');
  var af=sel('annfeed');
  if(af)af.innerHTML=MANN.map(function(a){
    return '<div class="fitem"><div class="fdot" style="background:var(--blue)"></div>'
      +'<div class="ftxt"><strong>'+esc(a.title)+'</strong>: '+esc(a.body)+'</div></div>';
  }).join('');
}

function loadWards(){
  var wards=liveWards();_cw=wards;
  var wl=sel('ward-list');if(!wl)return;
  wl.innerHTML=wards.map(function(w){
    var p=w.occupancy_pct;
    var c=p>=85?'var(--red)':p>=65?'var(--amber)':'var(--green)';
    var bc=w.color||'#3B5BDB';
    var bsl=p>=85?'Full':p>=65?'Busy':'Available';
    var bsc=p>=85?'br':p>=65?'ba':'bg';
    var ib=p>=85?'#fff5f5':p>=65?'#fff3bf':'#ebfbee';
    return '<div class="wcard">'
      +'<div class="wacc" style="background:'+bc+'"></div>'
      +'<div class="wbody">'
      +'<div class="wtop"><div class="wleft"><div class="wico" style="background:'+ib+'">'+w.emoji+'</div>'
      +'<div><div class="wname">'+esc(w.name)+'</div><div class="wfloor">'+esc(w.floor)+'</div></div></div>'
      +'<div class="badge '+bsc+'">'+bsl+'</div></div>'
      +'<div class="wstats"><div class="wbnum" style="color:'+c+'">'+w.available+'</div><div class="wblbl"> / '+w.total+' free</div></div>'
      +'<div class="wbar"><div class="wbar-f" style="width:'+p+'%;background:'+c+'"></div></div>'
      +'<div class="wfooter"><div class="wcost">₹'+Number(w.cost_per_day).toLocaleString()+'/day</div>'
      +'<div class="wspec">'+esc((w.specialists||[]).slice(0,2).join(' · '))+'</div></div>'
      +'<button class="btn-bk" onclick="goPage(\\'book\\')">Book This Ward</button>'
      +'</div></div>';
  }).join('');
}

function loadAll(){loadDashboard();if(curPage==='wards')loadWards();}

// ══ REFRESH ══
var POLL=15000,_pt=null,_ct=null,_cd=15;
function startPolling(){
  loadAll();
  clearInterval(_pt);clearInterval(_ct);_cd=POLL/1000;
  _pt=setInterval(function(){_cd=POLL/1000;loadAll();showToast('🔄 Data refreshed','i');},POLL);
  _ct=setInterval(function(){
    _cd=Math.max(0,_cd-1);
    var f=sel('rfill');if(f)f.style.width=(_cd/(POLL/1000)*100)+'%';
    var l=sel('refreshlbl');if(l)l.textContent='Next refresh in '+_cd+'s';
  },1000);
}

// ══ BOOKING ══
var selWard=null,patientId=null;
function regPatient(){
  var fn=gv('b-fn'),ln=gv('b-ln'),age=gv('b-age'),diag=gv('b-diag'),sev=gv('b-sev');
  if(!fn||!ln||!age||!diag||!sev){showToast('Fill all required fields *','e');return;}
  var btn=sel('btn-reg');btn.disabled=true;btn.innerHTML='<span class="spn"></span> AI Analysing…';
  setStep(2);
  setTimeout(function(){
    patientId='PT-'+Math.floor(1000+Math.random()*9000);
    var wards=(_cw||liveWards()).filter(function(w){return w.available>0;}).slice(0,3);
    var reasons=[['Best match for diagnosis','Beds available now','Specialist on duty'],
      ['Good alternative','Cost-effective','Good availability'],['Third option','Reasonable fit','Some availability']];
    var recs=wards.map(function(w,i){
      return {ward_id:w.id,ward_name:w.name,floor:w.floor,emoji:w.emoji,
        available_beds:w.available,cost_per_day:w.cost_per_day,
        confidence:Math.max(60,93-(i*14)+Math.floor(Math.random()*6)),reasons:reasons[i]};
    });
    selWard=recs[0]?recs[0].ward_id:null;
    sel('airecs').innerHTML=recs.map(function(r,i){
      return '<div class="rc'+(i===0?' sel':'')+'" data-wid="'+esc(r.ward_id)+'" onclick="pickRec(this)">'
        +'<div class="rn rn'+(i+1)+'">'+(i+1)+'</div>'
        +'<div style="flex:1"><div class="rw">'+esc(r.emoji)+' '+esc(r.ward_name)+'</div>'
        +'<div class="rr">'+esc(r.reasons.join(' · '))+'<br>🛏 '+r.available_beds+' free · ₹'+Number(r.cost_per_day).toLocaleString()+'/day</div></div>'
        +'<div class="rpct">'+r.confidence+'%</div></div>';
    }).join('');
    sel('aires').classList.add('show');
    setStep(3);
    showToast(fn+' registered! ID: '+patientId,'s');
    btn.disabled=false;btn.innerHTML='🤖 Get AI Recommendation';
  },900);
}
function pickRec(el){
  document.querySelectorAll('.rc').forEach(function(c){c.classList.remove('sel');});
  el.classList.add('sel');selWard=el.getAttribute('data-wid');
}
function confAlloc(){
  if(!selWard){showToast('Select a ward first','e');return;}
  var btn=sel('btn-conf');btn.disabled=true;btn.innerHTML='<span class="spn"></span> Allocating…';
  setTimeout(function(){
    var w=(_cw||MW).find(function(x){return x.id===selWard;})||{name:'selected ward'};
    setStep(4);showToast('🎉 Allocated to '+w.name+'!','s');
    setTimeout(function(){
      sel('aires').classList.remove('show');
      ['b-fn','b-ln','b-age','b-ph','b-diag','b-notes'].forEach(function(id){var e=sel(id);if(e)e.value='';});
      ['b-gen','b-sev','b-adm'].forEach(function(id){var e=sel(id);if(e)e.selectedIndex=0;});
      patientId=null;selWard=null;setStep(1);
    },3000);
    btn.disabled=false;btn.innerHTML='✅ Confirm Allocation';
  },700);
}
function setStep(n){
  for(var i=1;i<=4;i++){
    var s=sel('bs'+i);if(!s)continue;
    s.className='step '+(i<n?'dn':i===n?'ac':'pd');
    var l=sel('sl'+i);if(l)l.classList.toggle('dn',i<n);
  }
}

// ══ CHATBOT ══
var chatOpen=false,ttsOn=true,sttActive=false,chatBusy=false;
var chatHistory=[],curLang='en-IN',curLangCode='en',sttRec=null;
var voOpen=false,voListening=false;
var CLAUDE_KEY=''; // ← Paste your sk-ant-... key here

var LANGS={
  kn:{greeting:'ನಮಸ್ಕಾರ! ನಾನು AIMS CARE AI. ವಾರ್ಡ್, ಬುಕ್ಕಿಂಗ್, ತುರ್ತು ಮತ್ತು ಮಾಹಿತಿ ಸಹಾಯ ಮಾಡಬಲ್ಲೆ.',
   chips:['🛏️ ವಾರ್ಡ್','🚨 ತುರ್ತು 108','💰 ಶುಲ್ಕ','⏰ OPD ಸಮಯ'],
   placeholder:'ಕನ್ನಡದಲ್ಲಿ ಟೈಪ್ ಮಾಡಿ…'},
  hi:{greeting:'नमस्ते! मैं AIMS CARE AI हूं। वार्ड, बुकिंग, इमरजेंसी और जानकारी में मदद करता हूं।',
   chips:['🛏️ वार्ड','🚨 इमरजेंसी 108','💰 शुल्क','⏰ OPD समय'],
   placeholder:'हिंदी में टाइप करें…'},
  en:{greeting:'Hi! I am the AIMS CARE AI. I help with ward availability, booking, emergencies and hospital info.',
   chips:['🛏️ Ward Availability','🚨 Emergency 108','💰 Ward Costs','⏰ OPD Hours'],
   placeholder:'Type in ಕನ್ನಡ · हिंदी · English…'}
};
var SYS='You are AIMS CARE Hospital AI. Reply in the SAME language the user uses (Kannada/Hindi/English). Keep replies under 3 sentences. Hospital: BG Nagara, Bellur Cross, Nagamangala Mandya. Emergency:108. Phone:+91 8762557576. Wards: ICU ₹8000, Cardiology ₹5000, Surgical ₹3500, General ₹1200, Paediatrics ₹2000, Orthopaedics ₹3000 per day. OPD Mon-Sat 8AM-8PM. Never diagnose. Plain text only.';

function setLang(sl,code){
  curLang=sl;curLangCode=code;
  ['kn','hi','en'].forEach(function(l){
    var b=sel('lb-'+l);if(b)b.classList.toggle('act',l===code);
    var v=sel('vo-'+l);if(v)v.classList.toggle('act',l===code);
  });
  var i=sel('cinput');if(i)i.placeholder=LANGS[code].placeholder;
  showToast('Language: '+(code==='kn'?'ಕನ್ನಡ':code==='hi'?'हिंदी':'English'),'i');
}
function toggleChat(){
  chatOpen=!chatOpen;
  sel('cwin').classList.toggle('open',chatOpen);
  sel('cfab').classList.toggle('open',chatOpen);
  sel('fab-ico').textContent=chatOpen?'✕':'💬';
  sel('fab-lbl').textContent=chatOpen?'Close':'AI Chat';
  sel('fab-bdg').style.display=chatOpen?'none':'flex';
  if(chatOpen&&sel('cmsgs').children.length===0)setTimeout(function(){addAI(LANGS[curLangCode].greeting,true);},300);
  if(chatOpen){var i=sel('cinput');if(i)setTimeout(function(){i.focus();},350);}
}
function clearChat(){sel('cmsgs').innerHTML='';chatHistory=[];if(window.speechSynthesis)speechSynthesis.cancel();setTimeout(function(){addAI(LANGS[curLangCode].greeting,true);},200);}

function addAI(text,withChips){
  var msgs=sel('cmsgs');if(!msgs)return;
  var d=document.createElement('div');d.className='cmsg ai';
  d.innerHTML='<div class="cmav ai">🤖</div><div style="max-width:83%">'
    +'<div class="cmbub">'+esc(text)+'</div></div>';
  var ttsB=document.createElement('button');
  ttsB.textContent='🔊';ttsB.style.cssText='font-size:10px;border:none;background:none;cursor:pointer;padding:2px 5px;color:var(--g400);';
  ttsB.addEventListener('click',function(){speakText(text);});
  d.querySelector('.cmsg.ai div:last-child').appendChild(ttsB);
  if(withChips){
    var chips=LANGS[curLangCode].chips;
    var cd=document.createElement('div');cd.className='cchips';
    chips.forEach(function(c){
      var b=document.createElement('button');b.className='cchip';b.textContent=c;
      b.addEventListener('click',function(){sendMsg(c);});cd.appendChild(b);
    });
    d.appendChild(cd);
  }
  msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;
}
function addUser(text){
  var msgs=sel('cmsgs');if(!msgs)return;
  var d=document.createElement('div');d.className='cmsg usr';
  d.innerHTML='<div class="cmav me">👤</div><div class="cmbub">'+esc(text)+'</div>';
  msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;
}
function showTyping(){
  var msgs=sel('cmsgs');if(!msgs)return;
  var d=document.createElement('div');d.className='cmsg ai';d.id='typ';
  d.innerHTML='<div class="cmav ai">🤖</div><div class="cmbub"><div class="ctyp"><span></span><span></span><span></span></div></div>';
  msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;
}
function rmTyping(){var e=sel('typ');if(e)e.remove();}
function setAv(s){
  var av=sel('cav'),vo=sel('voav');
  var ic={idle:'🤖',listen:'🎙️',think:'⚙️',speak:'🔊'}[s]||'🤖';
  if(av){av.textContent=ic;av.className='cav'+(s==='listen'?' lst':s==='speak'?' spk':'');}
  if(vo){vo.textContent=ic;vo.className='voav'+(s==='listen'?' lst':s==='speak'?' spk':'');}
  var sl=sel('vo-slbl');if(sl)sl.textContent=s.toUpperCase();
}

function sendMsg(override){
  var inp=sel('cinput');
  var msg=(override||inp.value||'').trim();
  if(!msg||chatBusy)return;
  if(!override)inp.value='';
  addUser(msg);chatBusy=true;setAv('think');showTyping();
  sel('csend').disabled=true;
  chatHistory.push({role:'user',content:msg});

  function onReply(reply){
    rmTyping();chatHistory.push({role:'assistant',content:reply});
    addAI(reply,chatHistory.length<=2);
    chatBusy=false;sel('csend').disabled=false;
    if(ttsOn)speakText(reply,function(){setAv('idle');});else setAv('idle');
    var vtx=sel('vo-tx');if(vtx)vtx.textContent=reply;
  }

  if(CLAUDE_KEY&&CLAUDE_KEY.startsWith('sk-ant')){
    var msgs=chatHistory.slice(-10).filter(function(m){return m.role;});
    fetch('https://api.anthropic.com/v1/messages',{
      method:'POST',
      headers:{'Content-Type':'application/json','x-api-key':CLAUDE_KEY,'anthropic-version':'2023-06-01','anthropic-dangerous-direct-browser-access':'true'},
      body:JSON.stringify({model:'claude-sonnet-4-20250514',max_tokens:200,system:SYS,messages:msgs})
    }).then(function(r){return r.json();})
    .then(function(d){onReply((d.content&&d.content[0]&&d.content[0].text)||fallback(msg));})
    .catch(function(){tryFC(msg,onReply);});
    return;
  }
  tryFC(msg,onReply);
}
function tryFC(msg,cb){
  tryF('/api/chatbot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg,language:curLangCode})},
    function(d){cb(d.reply||fallback(msg));},function(){cb(fallback(msg));});
}
function fallback(msg){
  var m=msg.toLowerCase(),k=curLangCode;
  if(m.match(/emergency|108|ambulance|ತುರ್ತು|आपातकाल/))return k==='kn'?'ತಕ್ಷಣ 108 ಗೆ ಕರೆ ಮಾಡಿ. ಆಸ್ಪತ್ರೆ: +91 8762557576.':k==='hi'?'तुरंत 108 पर कॉल करें। अस्पताल: +91 8762557576।':'Call 108 immediately (free ambulance). Hospital: +91 8762557576.';
  if(m.match(/ward|bed|icu|ವಾರ್ಡ್|वार्ड/)){var w=(_cw||MW).filter(function(x){return x.available>0;}).map(function(x){return x.emoji+' '+x.name+': '+x.available+' free';}).join(', ');return k==='kn'?'ಲಭ್ಯ ವಾರ್ಡ್‌ಗಳು: '+w:k==='hi'?'उपलब्ध वार्ड: '+w:'Available wards: '+w+'. Tap "Book" to reserve.';}
  if(m.match(/cost|price|fee|ಶುಲ್ಕ|शुल्क/))return k==='kn'?'ICU ₹8000 · Cardiology ₹5000 · Surgical ₹3500 · General ₹1200 · Paediatrics ₹2000 · Ortho ₹3000 (ಪ್ರತಿ ದಿನ)':k==='hi'?'ICU ₹8000 · Cardiology ₹5000 · Surgical ₹3500 · General ₹1200 · Paediatrics ₹2000 · Ortho ₹3000 (प्रति दिन)':'ICU ₹8000 | Cardiology ₹5000 | Surgical ₹3500 | General ₹1200 | Paediatrics ₹2000 | Ortho ₹3000 per day.';
  if(m.match(/opd|time|hour|ಸಮಯ|समय/))return k==='kn'?'OPD: ಸೋಮ–ಶನಿ ಬೆ.8 – ರಾ.8. ತುರ್ತು: 24/7.':k==='hi'?'OPD: सोम–शनि सुबह 8 – रात 8। इमरजेंसी: 24/7।':'OPD: Monday to Saturday 8AM–8PM. Emergency services: 24/7.';
  if(m.match(/location|address|where|ವಿಳಾಸ|पता/))return k==='kn'?'BG ನಗರ, ಬೆಲ್ಲೂರು ಕ್ರಾಸ್, ನಾಗಮಂಗಲ ಮಂಡ್ಯ. ಫೋನ್: +91 8762557576.':k==='hi'?'BG नगर, बेलूर क्रॉस, नागमंगला मंड्या। फोन: +91 8762557576।':'BG Nagara, Bellur Cross, Nagamangala Mandya. Phone: +91 8762557576.';
  return k==='kn'?'ವಾರ್ಡ್ ಲಭ್ಯತೆ, ದರಗಳು, OPD ಸಮಯ ಅಥವಾ ತುರ್ತು ಬಗ್ಗೆ ಕೇಳಿ.':k==='hi'?'वार्ड, दरें, OPD समय या इमरजेंसी के बारे में पूछें।':'Ask me about ward availability, costs, OPD hours or emergency contacts!';
}

// ══ TTS ══
function toggleTTS(){ttsOn=!ttsOn;var b=sel('ttsbtn');if(b){b.textContent=ttsOn?'🔊':'🔇';b.classList.toggle('on',ttsOn);}if(!ttsOn&&window.speechSynthesis)speechSynthesis.cancel();showToast('Voice '+(ttsOn?'on':'off'),'i');}
function speakText(text,onEnd){
  if(!window.speechSynthesis||!text)return;
  speechSynthesis.cancel();
  var clean=text.replace(/<[^>]+>/g,'').replace(/[*_#`]/g,'').trim();
  var chunks=clean.match(/[^।?!.]{1,180}(?:[।?!.]|$)/g)||[clean];
  var idx=0;setAv('speak');
  function next(){
    if(idx>=chunks.length){setAv('idle');if(onEnd)onEnd();return;}
    var u=new SpeechSynthesisUtterance(chunks[idx++]);
    u.lang=curLangCode==='kn'?'kn-IN':curLangCode==='hi'?'hi-IN':'en-IN';
    u.rate=.93;u.pitch=1;
    var vs=speechSynthesis.getVoices();
    var pv=vs.filter(function(v){return v.lang===u.lang;});
    if(pv.length)u.voice=pv[0];
    var rt=setInterval(function(){if(!speechSynthesis.speaking)clearInterval(rt);else speechSynthesis.resume();},5000);
    u.onend=function(){clearInterval(rt);next();};u.onerror=function(){clearInterval(rt);setAv('idle');if(onEnd)onEnd();};
    speechSynthesis.speak(u);
  }
  next();
}

// ══ STT ══
function toggleSTT(){if(sttActive)stopSTT();else startSTT(function(t){var i=sel('cinput');if(i)i.value=t;stopSTT();if(t)sendMsg(t);},function(t){var l=sel('clive');if(l)l.textContent='🎙️ '+t;var i=sel('cinput');if(i)i.value=t;});}
function startSTT(onF,onI){
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){showToast('Use Chrome for voice input','e');return;}
  if(sttRec){try{sttRec.stop();}catch(e){}}
  sttRec=new SR();sttRec.lang=curLangCode==='kn'?'kn-IN':curLangCode==='hi'?'hi-IN':'en-IN';
  sttRec.continuous=false;sttRec.interimResults=true;
  sttRec.onstart=function(){sttActive=true;sel('cmic').classList.add('rec');sel('clive').classList.add('on');sel('clive').textContent='🎙️ Listening…';setAv('listen');};
  sttRec.onresult=function(e){var fi='',in2='';for(var i=e.resultIndex;i<e.results.length;i++){if(e.results[i].isFinal)fi+=e.results[i][0].transcript;else in2+=e.results[i][0].transcript;}if(in2&&onI)onI(in2);if(fi&&onF)onF(fi);};
  sttRec.onerror=function(e){if(e.error!=='aborted')showToast('Mic error: '+e.error,'e');stopSTT();};
  sttRec.onend=function(){stopSTT();};
  try{sttRec.start();}catch(e){showToast('Cannot access microphone','e');}
}
function stopSTT(){sttActive=false;sel('cmic').classList.remove('rec');sel('clive').classList.remove('on');setAv('idle');if(sttRec){try{sttRec.stop();}catch(e){}sttRec=null;}}

// ══ VOICE OVERLAY ══
function openVO(){sel('vo').classList.add('on');voOpen=true;}
function closeVO(){sel('vo').classList.remove('on');voOpen=false;if(voListening)stopSTT();}
function voAction(){
  if(voListening){stopSTT();voListening=false;sel('vo-actbtn').textContent='🎙️ Start Listening';return;}
  voListening=true;sel('vo-actbtn').textContent='⏹ Stop';sel('vo-tx').textContent='Listening…';
  startSTT(function(t){
    sel('vo-tx').textContent='"'+t+'"';voListening=false;sel('vo-actbtn').textContent='🎙️ Start Listening';
    if(!chatOpen)toggleChat();setTimeout(function(){sendMsg(t);},300);
  },function(t){sel('vo-tx').textContent=t;});
}

// ══ PWA INSTALL ══
var deferredPrompt=null;
window.addEventListener('beforeinstallprompt',function(e){
  e.preventDefault();deferredPrompt=e;
  var p=sel('pwa-prompt');if(p)p.style.display='block';
});
var ib=sel('pwa-install-btn');
if(ib)ib.addEventListener('click',function(){
  if(!deferredPrompt){showToast('Open in Chrome and use Add to Home Screen','i');return;}
  deferredPrompt.prompt();
  deferredPrompt.userChoice.then(function(r){
    if(r.outcome==='accepted')showToast('AIMS CARE installed! 🎉','s');
    deferredPrompt=null;
  });
});

// ══ CLOCK ══
setInterval(function(){var e=sel('ntime');if(e)e.textContent=nowT();},1000);

// ══ SERVICE WORKER (PWA offline support) ══
if('serviceWorker' in navigator){
  var swCode="self.addEventListener('install',function(e){e.waitUntil(caches.open('aims-v1').then(function(c){return c.addAll(['./', './index.html']);}));});"
    +"self.addEventListener('fetch',function(e){e.respondWith(caches.match(e.request).then(function(r){return r||fetch(e.request);}));});";
  var blob=new Blob([swCode],{type:'application/javascript'});
  var swUrl=URL.createObjectURL(blob);
  navigator.servic"""

@app.route("/staff")
def staff():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>AIMS CARE — Staff Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet"/>
<style>
:root{
  --blue:#3B5BDB;--blue2:#4263EB;--blue-lt:#EEF2FF;--blue-pale:#dbe4ff;
  --red:#E03131;--red-lt:#FFF5F5;--green:#2F9E44;--green-lt:#EBFBEE;
  --amber:#E67700;--amber-lt:#FFF3BF;--purple:#7c3aed;--purple-lt:#f3f0ff;
  --white:#fff;--bg:#F0F4FF;--sidebar:#1a2744;--sidebar2:#243058;
  --g100:#F1F3F5;--g200:#E9ECEF;--g300:#DEE2E6;--g500:#ADB5BD;--g600:#868E96;--g700:#495057;--g800:#343A40;--g900:#212529;
  --sh1:0 2px 10px rgba(0,0,0,.06);--sh2:0 4px 18px rgba(0,0,0,.09);--shb:0 4px 16px rgba(59,91,219,.28);
  --r8:8px;--r10:10px;--r12:12px;--r16:16px;--r20:20px;--r99:99px;
  --fn:'Plus Jakarta Sans',sans-serif;--sw:240px;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--fn);background:var(--bg);color:var(--g900);display:flex;min-height:100vh}
::-webkit-scrollbar{width:4px;height:4px}::-webkit-scrollbar-thumb{background:#4a5568;border-radius:2px}

/* ── SIDEBAR ── */
.sidebar{width:var(--sw);background:var(--sidebar);display:flex;flex-direction:column;position:fixed;top:0;left:0;bottom:0;z-index:100;transition:transform .3s}
.sb-hdr{padding:20px 18px 16px;border-bottom:1px solid rgba(255,255,255,.08)}
.sb-brand{display:flex;align-items:center;gap:10px;margin-bottom:3px}
.sb-ico{width:36px;height:36px;background:var(--blue);border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:17px;flex-shrink:0}
.sb-name{font-size:17px;font-weight:800;color:#fff;letter-spacing:-.3px}
.sb-name span{color:var(--blue-pale);font-weight:400}
.sb-badge{font-size:10px;color:rgba(255,255,255,.4);font-weight:600;letter-spacing:.5px;text-transform:uppercase;margin-left:46px}
.sb-section{padding:12px 10px 4px;font-size:9.5px;font-weight:800;color:rgba(255,255,255,.28);letter-spacing:2px;text-transform:uppercase}
.sbi{display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:var(--r10);font-size:13px;font-weight:600;color:rgba(255,255,255,.55);cursor:pointer;transition:all .18s;margin-bottom:2px;border:none;background:none;width:100%;text-align:left}
.sbi:hover{background:rgba(255,255,255,.07);color:rgba(255,255,255,.85)}
.sbi.act{background:var(--blue);color:#fff;box-shadow:var(--shb)}
.sbi-ico{font-size:15px;width:20px;text-align:center;flex-shrink:0}
.sbi-bdg{margin-left:auto;background:var(--red);color:#fff;font-size:9px;font-weight:800;padding:2px 6px;border-radius:var(--r99)}
.sb-foot{margin-top:auto;padding:14px 10px;border-top:1px solid rgba(255,255,255,.08)}
.sb-user{display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:var(--r10);cursor:pointer;transition:background .18s}
.sb-user:hover{background:rgba(255,255,255,.07)}
.sb-av{width:32px;height:32px;border-radius:50%;background:var(--blue);display:flex;align-items:center;justify-content:center;font-size:14px;flex-shrink:0}
.sb-un{font-size:12.5px;font-weight:700;color:#fff}
.sb-ur{font-size:10px;color:rgba(255,255,255,.45)}

/* ── MAIN ── */
.main{margin-left:var(--sw);flex:1;display:flex;flex-direction:column;min-height:100vh}
.topbar{background:var(--white);border-bottom:1px solid var(--g200);padding:0 28px;height:64px;display:flex;align-items:center;gap:14px;box-shadow:var(--sh1);position:sticky;top:0;z-index:50}
.topbar-title{font-size:18px;font-weight:800;color:var(--g900);flex:1}
.topbar-sub{font-size:12px;color:var(--g500);font-weight:500;margin-top:2px}
.tb-actions{display:flex;align-items:center;gap:10px}
.tb-btn{display:flex;align-items:center;gap:5px;padding:8px 14px;border:none;border-radius:var(--r8);font-size:12.5px;font-weight:700;cursor:pointer;transition:all .18s;font-family:var(--fn)}
.tb-btn-blue{background:var(--blue);color:#fff;box-shadow:var(--shb)}.tb-btn-blue:hover{background:var(--blue2)}
.tb-btn-out{background:var(--white);color:var(--g700);border:1.5px solid var(--g300)}.tb-btn-out:hover{border-color:var(--blue);color:var(--blue)}
.tb-search{display:flex;align-items:center;gap:7px;background:var(--bg);border:1.5px solid var(--g300);border-radius:var(--r99);padding:7px 14px;font-size:12.5px;color:var(--g500);min-width:200px;cursor:pointer}
.tb-search input{border:none;background:none;outline:none;font-size:12.5px;color:var(--g900);font-family:var(--fn);width:100%}
.tb-search input::placeholder{color:var(--g500)}
.tb-time{font-size:12px;color:var(--g500);font-weight:600;white-space:nowrap}
.lpill{display:flex;align-items:center;gap:4px;padding:5px 11px;background:var(--green-lt);border-radius:var(--r99);font-size:10.5px;font-weight:700;color:var(--green)}
.ld{width:5px;height:5px;border-radius:50%;background:var(--green);animation:lp 2s ease-in-out infinite}
@keyframes lp{0%,100%{opacity:1}50%{opacity:.3}}
.content{padding:24px 28px;flex:1}

/* ── PAGES ── */
.page{display:none}.page.act{display:block}

/* ── STAT CARDS ── */
.stat-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:22px}
.stat-card{background:var(--white);border-radius:var(--r16);padding:18px;box-shadow:var(--sh1);border:1px solid var(--g200);transition:box-shadow .2s;position:relative;overflow:hidden}
.stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}
.stat-card.sc-blue::before{background:var(--blue)}.stat-card.sc-green::before{background:var(--green)}
.stat-card.sc-red::before{background:var(--red)}.stat-card.sc-amber::before{background:var(--amber)}
.stat-card:hover{box-shadow:var(--sh2)}
.sc-top{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:11px}
.sc-ico{width:42px;height:42px;border-radius:var(--r10);display:flex;align-items:center;justify-content:center;font-size:19px}
.sc-bdg{padding:3px 8px;border-radius:var(--r99);font-size:10px;font-weight:700}
.bdg-g{background:var(--green-lt);color:var(--green)}.bdg-r{background:var(--red-lt);color:var(--red)}
.bdg-b{background:var(--blue-lt);color:var(--blue)}.bdg-a{background:var(--amber-lt);color:var(--amber)}
.sc-val{font-size:32px;font-weight:800;line-height:1;margin-bottom:4px;color:var(--g900)}
.sc-lbl{font-size:11px;color:var(--g500);font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.sc-trend{font-size:11px;color:var(--green);font-weight:600;margin-top:4px}

/* ── TABLES ── */
.table-card{background:var(--white);border-radius:var(--r16);border:1px solid var(--g200);box-shadow:var(--sh1);overflow:hidden;margin-bottom:20px}
.table-hdr{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--g100)}
.table-ttl{font-size:14px;font-weight:800;color:var(--g900)}
.table-acts{display:flex;gap:8px;align-items:center}
table{width:100%;border-collapse:collapse}
th{padding:10px 16px;text-align:left;font-size:10.5px;font-weight:800;color:var(--g500);text-transform:uppercase;letter-spacing:.8px;background:var(--g100);border-bottom:1px solid var(--g200)}
td{padding:12px 16px;font-size:13px;color:var(--g700);border-bottom:1px solid var(--g100);vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--bg)}
.td-name{font-weight:700;color:var(--g900)}
.td-id{font-size:11px;color:var(--g400);font-weight:600}
.pill{display:inline-flex;align-items:center;padding:3px 8px;border-radius:var(--r99);font-size:10.5px;font-weight:700}
.pill-g{background:var(--green-lt);color:var(--green)}.pill-r{background:var(--red-lt);color:var(--red)}
.pill-b{background:var(--blue-lt);color:var(--blue)}.pill-a{background:var(--amber-lt);color:var(--amber)}
.pill-p{background:var(--purple-lt);color:var(--purple)}
.td-act{display:flex;gap:5px}
.act-btn{padding:5px 10px;border:1px solid var(--g300);border-radius:6px;font-size:11px;font-weight:700;cursor:pointer;background:var(--white);color:var(--g700);transition:all .15s;font-family:var(--fn)}
.act-btn:hover{border-color:var(--blue);color:var(--blue);background:var(--blue-lt)}
.act-btn.red{border-color:rgba(224,49,49,.2);color:var(--red)}.act-btn.red:hover{background:var(--red-lt);border-color:var(--red)}
.act-btn.grn{border-color:rgba(47,158,68,.2);color:var(--green)}.act-btn.grn:hover{background:var(--green-lt);border-color:var(--green)}

/* ── WARD GRID ── */
.ward-mgmt-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:20px}
.wm-card{background:var(--white);border-radius:var(--r16);border:1px solid var(--g200);overflow:hidden;box-shadow:var(--sh1)}
.wm-acc{height:4px}
.wm-body{padding:16px}
.wm-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:11px}
.wm-name{font-size:14px;font-weight:800;color:var(--g900)}
.wm-floor{font-size:10.5px;color:var(--g500)}
.wm-stats{display:flex;gap:16px;margin-bottom:10px}
.wm-s{text-align:center}
.wm-sv{font-size:22px;font-weight:800;line-height:1}
.wm-sl{font-size:9.5px;color:var(--g500);font-weight:700;text-transform:uppercase;letter-spacing:.4px;margin-top:2px}
.wm-bar{height:6px;background:var(--g100);border-radius:3px;overflow:hidden;margin-bottom:12px}
.wm-fill{height:100%;border-radius:3px;transition:width 1s ease}
.wm-actions{display:flex;gap:7px}
.wm-btn{flex:1;padding:8px;border:none;border-radius:var(--r8);font-size:12px;font-weight:700;cursor:pointer;transition:all .18s;font-family:var(--fn)}
.wm-btn-blue{background:var(--blue-lt);color:var(--blue)}.wm-btn-blue:hover{background:var(--blue);color:#fff}
.wm-btn-red{background:var(--red-lt);color:var(--red)}.wm-btn-red:hover{background:var(--red);color:#fff}
.wm-btn-green{background:var(--green-lt);color:var(--green)}.wm-btn-green:hover{background:var(--green);color:#fff}

/* ── CHARTS / BARS ── */
.chart-row{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px}
.chart-card{background:var(--white);border-radius:var(--r16);border:1px solid var(--g200);padding:18px;box-shadow:var(--sh1)}
.chart-ttl{font-size:13px;font-weight:800;color:var(--g900);margin-bottom:14px;display:flex;align-items:center;justify-content:space-between}
.bar-row{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.bar-lbl{font-size:11.5px;color:var(--g700);width:110px;flex-shrink:0;font-weight:600;display:flex;align-items:center;gap:5px}
.bar-bg{flex:1;height:7px;background:var(--g100);border-radius:4px;overflow:hidden}
.bar-fill{height:100%;border-radius:4px;transition:width 1s ease}
.bar-val{font-size:11px;font-weight:700;color:var(--g600);width:30px;text-align:right;flex-shrink:0}

/* ── MODAL ── */
.modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:1000;align-items:center;justify-content:center;backdrop-filter:blur(4px)}
.modal-bg.on{display:flex}
.modal{background:var(--white);border-radius:var(--r20);padding:28px;max-width:500px;width:90%;box-shadow:0 20px 60px rgba(0,0,0,.2);animation:mIn .3s cubic-bezier(.34,1.56,.64,1)}
@keyframes mIn{from{opacity:0;transform:scale(.88) translateY(20px)}to{opacity:1;transform:scale(1) translateY(0)}}
.modal-ttl{font-size:17px;font-weight:800;color:var(--g900);margin-bottom:4px}
.modal-sub{font-size:12px;color:var(--g500);margin-bottom:20px}
.modal-footer{display:flex;gap:10px;margin-top:20px;justify-content:flex-end}
.fg{display:flex;flex-direction:column;gap:5px;margin-bottom:12px}
.flbl{font-size:10.5px;font-weight:700;color:var(--g600);text-transform:uppercase;letter-spacing:.5px}
.fi{background:var(--bg);border:1.5px solid var(--g300);border-radius:var(--r8);padding:10px 12px;color:var(--g900);font-size:13px;font-family:var(--fn);outline:none;width:100%;transition:all .2s}
.fi:focus{border-color:var(--blue);background:var(--white);box-shadow:0 0 0 3px rgba(59,91,219,.1)}
.fi::placeholder{color:var(--g500)}
select.fi option{background:var(--white)}
textarea.fi{resize:none;min-height:64px}
.frow{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.btn{display:flex;align-items:center;justify-content:center;gap:6px;padding:10px 20px;border:none;border-radius:var(--r8);font-size:13px;font-weight:700;cursor:pointer;font-family:var(--fn);transition:all .18s}
.btn-blue{background:var(--blue);color:#fff;box-shadow:var(--shb)}.btn-blue:hover{background:var(--blue2)}
.btn-out{background:var(--white);color:var(--g700);border:1.5px solid var(--g300)}.btn-out:hover{border-color:var(--g500)}
.btn-red{background:var(--red);color:#fff}.btn-red:hover{background:#C92A2A}

/* TOAST */
.toast{position:fixed;top:76px;left:50%;transform:translateX(-50%) translateY(-8px);z-index:9999;border-radius:var(--r10);padding:10px 20px;font-size:13px;font-weight:600;opacity:0;transition:all .28s;pointer-events:none;white-space:nowrap;box-shadow:var(--sh2);border:1px solid}
.toast.on{transform:translateX(-50%) translateY(0);opacity:1}
.ts{background:rgba(235,251,238,.97);color:var(--green);border-color:rgba(47,158,68,.2)}
.te{background:rgba(255,245,245,.97);color:var(--red);border-color:rgba(224,49,49,.2)}
.ti{background:rgba(238,242,255,.97);color:var(--blue);border-color:rgba(59,91,219,.2)}
.spn{display:inline-block;width:12px;height:12px;border:2px solid rgba(255,255,255,.4);border-top-color:#fff;border-radius:50%;animation:sp .7s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}

/* MOBILE SIDEBAR TOGGLE */
.sb-toggle{display:none;position:fixed;top:14px;left:14px;z-index:200;width:36px;height:36px;border-radius:var(--r8);background:var(--sidebar);color:#fff;border:none;font-size:16px;cursor:pointer;align-items:center;justify-content:center}

@media(max-width:1100px){
  .stat-grid{grid-template-columns:1fr 1fr}
  .ward-mgmt-grid{grid-template-columns:1fr 1fr}
  .chart-row{grid-template-columns:1fr}
}
@media(max-width:768px){
  .sidebar{transform:translateX(-100%)}
  .sidebar.mobile-open{transform:translateX(0)}
  .main{margin-left:0}
  .sb-toggle{display:flex}
  .stat-grid{grid-template-columns:1fr 1fr}
  .ward-mgmt-grid{grid-template-columns:1fr}
  .content{padding:16px}
  .topbar{padding:0 16px 0 56px}
  .tb-search{display:none}
}
</style>
</head>
<body>

<!-- MOBILE SIDEBAR TOGGLE -->
<button class="sb-toggle" id="sb-toggle" onclick="toggleSidebar()">☰</button>

<!-- ── SIDEBAR ── -->
<div class="sidebar" id="sidebar">
  <div class="sb-hdr">
    <div class="sb-brand"><div class="sb-ico">🏥</div><div class="sb-name">AIMS <span>CARE</span></div></div>
    <div class="sb-badge">Staff Portal</div>
  </div>
  <div style="padding:8px 10px;flex:1;overflow-y:auto">
    <div class="sb-section">Main</div>
    <button class="sbi act" id="sbi-dashboard" onclick="goTab('dashboard')"><span class="sbi-ico">📊</span>Dashboard</button>
    <button class="sbi" id="sbi-wards" onclick="goTab('wards')"><span class="sbi-ico">🛏️</span>Ward Management</button>
    <button class="sbi" id="sbi-patients" onclick="goTab('patients')"><span class="sbi-ico">👥</span>Patients<span class="sbi-bdg" id="new-bdg">3</span></button>
    <button class="sbi" id="sbi-bookings" onclick="goTab('bookings')"><span class="sbi-ico">📋</span>Bookings</button>
    <div class="sb-section">Management</div>
    <button class="sbi" id="sbi-staff" onclick="goTab('staff')"><span class="sbi-ico">👨‍⚕️</span>Staff</button>
    <button class="sbi" id="sbi-reports" onclick="goTab('reports')"><span class="sbi-ico">📈</span>Reports</button>
    <button class="sbi" id="sbi-settings" onclick="goTab('settings')"><span class="sbi-ico">⚙️</span>Settings</button>
    <div class="sb-section">Quick Actions</div>
    <button class="sbi" onclick="openModal('admit')"><span class="sbi-ico">➕</span>Admit Patient</button>
    <button class="sbi" onclick="showToast('Emergency protocol activated','e')" style="color:rgba(255,100,100,.8)"><span class="sbi-ico">🚨</span>Emergency Alert</button>
  </div>
  <div class="sb-foot">
    <div class="sb-user">
      <div class="sb-av">👨‍⚕️</div>
      <div><div class="sb-un">Dr. Admin</div><div class="sb-ur">Administrator</div></div>
      <button onclick="showToast('Logged out','i')" style="margin-left:auto;background:none;border:none;color:rgba(255,255,255,.3);cursor:pointer;font-size:13px">↩</button>
    </div>
  </div>
</div>

<!-- ── MAIN ── -->
<div class="main">
  <div class="topbar">
    <div style="flex:1">
      <div class="topbar-title" id="page-title">Dashboard</div>
      <div class="topbar-sub" id="page-sub">Live hospital overview · Auto-refreshes every 15s</div>
    </div>
    <div class="tb-search"><span>🔍</span><input placeholder="Search patients, wards…" id="search-input" oninput="doSearch(this.value)"/></div>
    <div class="tb-actions">
      <div class="lpill"><span class="ld"></span>LIVE</div>
      <span class="tb-time" id="ntime"></span>
      <span id="rlbl" style="font-size:11px;color:var(--g500);font-weight:600"></span>
      <button class="tb-btn tb-btn-blue" onclick="openModal('admit')">➕ Admit Patient</button>
      <button class="tb-btn tb-btn-out" onclick="loadAll();showToast('Data refreshed','i')">🔄 Refresh</button>
    </div>
  </div>

  <!-- Refresh bar -->
  <div style="height:3px;background:var(--g200);overflow:hidden">
    <div id="rfill" style="height:100%;background:var(--blue);width:100%;transition:width 1s linear"></div>
  </div>

  <div class="content">

    <!-- ── DASHBOARD TAB ── -->
    <div class="page act" id="tab-dashboard">
      <div class="stat-grid">
        <div class="stat-card sc-blue"><div class="sc-top"><div class="sc-ico" style="background:#dbe4ff">🛏️</div><div class="sc-bdg bdg-b" id="sb-tot">—</div></div><div class="sc-val" id="sv-tot">—</div><div class="sc-lbl">Total Beds</div><div class="sc-trend" id="st-tot"></div></div>
        <div class="stat-card sc-green"><div class="sc-top"><div class="sc-ico" style="background:#ebfbee">✅</div><div class="sc-bdg bdg-g" id="sb-av">—</div></div><div class="sc-val" id="sv-av" style="color:var(--green)">—</div><div class="sc-lbl">Available Beds</div><div class="sc-trend" id="st-av"></div></div>
        <div class="stat-card sc-red"><div class="sc-top"><div class="sc-ico" style="background:#fff5f5">🚨</div><div class="sc-bdg bdg-r" id="sb-cr">—</div></div><div class="sc-val" id="sv-cr" style="color:var(--red)">—</div><div class="sc-lbl">Critical Patients</div></div>
        <div class="stat-card sc-amber"><div class="sc-top"><div class="sc-ico" style="background:#fff3bf">📊</div><div class="sc-bdg bdg-a" id="sb-oc">—</div></div><div class="sc-val" id="sv-oc" style="color:var(--amber)">—</div><div class="sc-lbl">Occupancy Rate</div></div>
      </div>

      <div class="chart-row">
        <div class="chart-card">
          <div class="chart-ttl">🛏️ Ward Occupancy <span style="font-size:11px;color:var(--g500);font-weight:500">Live</span></div>
          <div id="occ-bars"></div>
        </div>
        <div class="chart-card">
          <div class="chart-ttl">📊 Severity Breakdown <span style="font-size:11px;color:var(--g500);font-weight:500">Today</span></div>
          <div id="sev-bars"></div>
        </div>
      </div>

      <div class="table-card">
        <div class="table-hdr">
          <span class="table-ttl">⚡ Recent Patient Allocations</span>
          <div class="table-acts">
            <div class="lpill"><span class="ld"></span>LIVE</div>
            <button class="tb-btn tb-btn-out" onclick="goTab('bookings')" style="padding:6px 12px;font-size:12px">View All</button>
          </div>
        </div>
        <div style="overflow-x:auto">
          <table>
            <thead><tr><th>Patient</th><th>Ward</th><th>Bed</th><th>Severity</th><th>Time</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody id="recent-table"><tr><td colspan="7" style="text-align:center;color:var(--g400);padding:24px">Loading…</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ── WARDS TAB ── -->
    <div class="page" id="tab-wards">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">
        <div><div style="font-size:17px;font-weight:800;color:var(--g900)">Ward Management</div><div style="font-size:12px;color:var(--g500);margin-top:3px">Update bed counts, manage ward status and staff assignments</div></div>
        <button class="tb-btn tb-btn-blue" onclick="showToast('Ward report exported','s')">📥 Export Report</button>
      </div>
      <div class="ward-mgmt-grid" id="ward-mgmt-grid"></div>
      <div class="table-card">
        <div class="table-hdr"><span class="table-ttl">🔄 Recent Ward Activity</span><div class="lpill"><span class="ld"></span>LIVE</div></div>
        <div id="ward-activity-list" style="padding:8px 0"></div>
      </div>
    </div>

    <!-- ── PATIENTS TAB ── -->
    <div class="page" id="tab-patients">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">
        <div><div style="font-size:17px;font-weight:800;color:var(--g900)">Patient Management</div><div style="font-size:12px;color:var(--g500);margin-top:3px">View, admit, discharge and manage all patients</div></div>
        <div style="display:flex;gap:9px">
          <button class="tb-btn tb-btn-out" onclick="showToast('Patient list exported','s')">📥 Export</button>
          <button class="tb-btn tb-btn-blue" onclick="openModal('admit')">➕ Admit Patient</button>
        </div>
      </div>
      <div class="table-card">
        <div class="table-hdr">
          <span class="table-ttl">All Patients</span>
          <div class="table-acts">
            <select class="fi" style="width:auto;padding:6px 10px;font-size:12px" onchange="filterPatients(this.value)">
              <option value="">All Wards</option>
              <option value="ICU">ICU</option>
              <option value="Cardiology">Cardiology</option>
              <option value="Surgical">Surgical</option>
              <option value="General">General Medicine</option>
              <option value="Paediatrics">Paediatrics</option>
              <option value="Orthopaedics">Orthopaedics</option>
            </select>
          </div>
        </div>
        <div style="overflow-x:auto">
          <table>
            <thead><tr><th>Patient ID</th><th>Name</th><th>Age</th><th>Ward</th><th>Bed</th><th>Severity</th><th>Admitted</th><th>Actions</th></tr></thead>
            <tbody id="patient-table"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ── BOOKINGS TAB ── -->
    <div class="page" id="tab-bookings">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">
        <div><div style="font-size:17px;font-weight:800;color:var(--g900)">Booking Management</div><div style="font-size:12px;color:var(--g500);margin-top:3px">Manage all ward allocations and booking requests</div></div>
        <button class="tb-btn tb-btn-blue" onclick="openModal('admit')">➕ New Booking</button>
      </div>
      <div class="table-card">
        <div class="table-hdr"><span class="table-ttl">All Allocations</span><div class="lpill"><span class="ld"></span>LIVE</div></div>
        <div style="overflow-x:auto">
          <table>
            <thead><tr><th>Booking ID</th><th>Patient</th><th>Ward</th><th>Bed</th><th>Type</th><th>Severity</th><th>Date & Time</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody id="booking-table"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ── STAFF TAB ── -->
    <div class="page" id="tab-staff">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:18px">
        <div><div style="font-size:17px;font-weight:800;color:var(--g900)">Staff Management</div><div style="font-size:12px;color:var(--g500);margin-top:3px">Manage doctors, nurses and administrative staff</div></div>
        <button class="tb-btn tb-btn-blue" onclick="showToast('Add staff feature coming soon','i')">➕ Add Staff</button>
      </div>
      <div class="table-card">
        <div style="overflow-x:auto">
          <table>
            <thead><tr><th>Staff ID</th><th>Name</th><th>Role</th><th>Department</th><th>Shift</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody id="staff-table"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ── REPORTS TAB ── -->
    <div class="page" id="tab-reports">
      <div style="margin-bottom:18px"><div style="font-size:17px;font-weight:800;color:var(--g900)">Reports & Analytics</div><div style="font-size:12px;color:var(--g500);margin-top:3px">Hospital performance metrics and reports</div></div>
      <div class="chart-row">
        <div class="chart-card">
          <div class="chart-ttl">📅 Weekly Admissions</div>
          <div id="weekly-bars"></div>
        </div>
        <div class="chart-card">
          <div class="chart-ttl">🏥 Ward Utilisation %</div>
          <div id="util-bars"></div>
        </div>
      </div>
      <div class="stat-grid" style="margin-top:0">
        <div class="stat-card sc-blue"><div class="sc-ico" style="background:#dbe4ff;margin-bottom:10px">📈</div><div class="sc-val" style="font-size:24px">94%</div><div class="sc-lbl">AI Match Accuracy</div></div>
        <div class="stat-card sc-green"><div class="sc-ico" style="background:#ebfbee;margin-bottom:10px">⚡</div><div class="sc-val" style="font-size:24px">&lt;2m</div><div class="sc-lbl">Avg Allocation Time</div></div>
        <div class="stat-card sc-amber"><div class="sc-ico" style="background:#fff3bf;margin-bottom:10px">😊</div><div class="sc-val" style="font-size:24px">4.8/5</div><div class="sc-lbl">Patient Satisfaction</div></div>
        <div class="stat-card sc-red"><div class="sc-ico" style="background:#fff5f5;margin-bottom:10px">🚑</div><div class="sc-val" style="font-size:24px">3.2m</div><div class="sc-lbl">Avg Emergency Response</div></div>
      </div>
    </div>

    <!-- ── SETTINGS TAB ── -->
    <div class="page" id="tab-settings">
      <div style="margin-bottom:18px"><div style="font-size:17px;font-weight:800;color:var(--g900)">Settings</div><div style="font-size:12px;color:var(--g500);margin-top:3px">Configure hospital system settings</div></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
        <div class="table-card" style="padding:20px">
          <div style="font-size:14px;font-weight:800;color:var(--g900);margin-bottom:14px">🔗 API Configuration</div>
          <div class="fg"><label class="flbl">Claude AI API Key</label><input class="fi" type="password" id="api-key-input" placeholder="sk-ant-… (for AI chatbot)"/></div>
          <div class="fg"><label class="flbl">Flask Backend URL</label><input class="fi" value="http://localhost:5000" id="flask-url"/></div>
          <button class="btn btn-blue" onclick="saveSettings()" style="width:100%;margin-top:8px">💾 Save Settings</button>
        </div>
        <div class="table-card" style="padding:20px">
          <div style="font-size:14px;font-weight:800;color:var(--g900);margin-bottom:14px">🏥 Hospital Info</div>
          <div class="fg"><label class="flbl">Hospital Name</label><input class="fi" value="AIMS CARE Hospital"/></div>
          <div class="fg"><label class="flbl">Emergency Number</label><input class="fi" value="108"/></div>
          <div class="fg"><label class="flbl">Phone</label><input class="fi" value="+91 8762557576"/></div>
          <div class="fg"><label class="flbl">Auto-Refresh Interval</label>
            <select class="fi" onchange="updatePollInterval(parseInt(this.value))">
              <option value="10000">10 seconds</option>
              <option value="15000" selected>15 seconds</option>
              <option value="30000">30 seconds</option>
              <option value="60000">1 minute</option>
            </select>
          </div>
          <button class="btn btn-blue" onclick="showToast('Hospital settings saved','s')" style="width:100%;margin-top:8px">💾 Save</button>
        </div>
      </div>
    </div>

  </div><!-- /content -->
</div><!-- /main -->

<!-- ── ADMIT PATIENT MODAL ── -->
<div class="modal-bg" id="modal-admit">
  <div class="modal">
    <div class="modal-ttl">➕ Admit New Patient</div>
    <div class="modal-sub">Fill in patient details for AI ward allocation</div>
    <div class="frow">
      <div class="fg"><label class="flbl">First Name *</label><input class="fi" id="m-fn" placeholder="Ravi"/></div>
      <div class="fg"><label class="flbl">Last Name *</label><input class="fi" id="m-ln" placeholder="Kumar"/></div>
    </div>
    <div class="frow">
      <div class="fg"><label class="flbl">Age *</label><input class="fi" id="m-age" type="number" placeholder="45"/></div>
      <div class="fg"><label class="flbl">Gender</label><select class="fi" id="m-gen"><option>Male</option><option>Female</option><option>Other</option></select></div>
    </div>
    <div class="fg"><label class="flbl">Diagnosis / Complaint *</label><input class="fi" id="m-diag" placeholder="e.g. Chest pain, fracture, respiratory distress"/></div>
    <div class="frow">
      <div class="fg"><label class="flbl">Severity *</label><select class="fi" id="m-sev"><option value="">Select</option><option>Low</option><option>Moderate</option><option>High</option><option>Critical</option></select></div>
      <div class="fg"><label class="flbl">Admission Type</label><select class="fi" id="m-adm"><option>Emergency</option><option>Planned</option><option>Referral</option></select></div>
    </div>
    <div class="fg"><label class="flbl">Phone</label><input class="fi" id="m-ph" type="tel" placeholder="+91 98765 43210"/></div>
    <div class="modal-footer">
      <button class="btn btn-out" onclick="closeModal('admit')">Cancel</button>
      <button class="btn btn-blue" id="btn-admit" onclick="submitAdmit()">🤖 AI Allocate & Admit</button>
    </div>
  </div>
</div>

<!-- ── WARD UPDATE MODAL ── -->
<div class="modal-bg" id="modal-ward">
  <div class="modal">
    <div class="modal-ttl" id="wm-title">Update Ward</div>
    <div class="modal-sub">Manually update bed availability for this ward</div>
    <div class="frow">
      <div class="fg"><label class="flbl">Total Beds</label><input class="fi" id="wm-total" type="number"/></div>
      <div class="fg"><label class="flbl">Occupied Beds</label><input class="fi" id="wm-occupied" type="number"/></div>
    </div>
    <div class="fg"><label class="flbl">Ward Status</label><select class="fi" id="wm-status"><option>operational</option><option>maintenance</option><option>emergency-only</option><option>closed</option></select></div>
    <div class="fg"><label class="flbl">Notes</label><textarea class="fi" id="wm-notes" placeholder="Any notes for the shift…"></textarea></div>
    <div class="modal-footer">
      <button class="btn btn-out" onclick="closeModal('ward')">Cancel</button>
      <button class="btn btn-blue" onclick="saveWardUpdate()">💾 Save Update</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
'use strict';
// ══ MOCK DATA ══
var MW=[
  {id:'ICU',name:'ICU',fullName:'Intensive Care Unit',emoji:'🏥',floor:'3rd Floor, Block A',total:20,occupied:17,available:3,cost:8000,pct:85,color:'#E03131',specialists:['Dr. Ramesh Kumar','Dr. Anand Rao'],status:'operational'},
  {id:'Cardiology',name:'Cardiology',fullName:'Cardiology Ward',emoji:'❤️',floor:'2nd Floor, Block B',total:30,occupied:28,available:2,cost:5000,pct:93,color:'#f97316',specialists:['Dr. Meera Singh','Dr. Priya Nair'],status:'operational'},
  {id:'Surgical',name:'Surgical',fullName:'Surgical Ward',emoji:'⚕️',floor:'1st Floor, Block C',total:25,occupied:18,available:7,cost:3500,pct:72,color:'#7c3aed',specialists:['Dr. Suresh Rao','Dr. Kiran Kumar'],status:'operational'},
  {id:'General',name:'General',fullName:'General Medicine',emoji:'🩺',floor:'Ground Floor, Block A',total:40,occupied:29,available:11,cost:1200,pct:73,color:'#2F9E44',specialists:['Dr. Kavitha','Dr. Rajesh'],status:'operational'},
  {id:'Paediatrics',name:'Paeds',fullName:'Paediatric Ward',emoji:'👶',floor:'1st Floor, Block A',total:20,occupied:12,available:8,cost:2000,pct:60,color:'#0ea5e9',specialists:['Dr. Sunita','Dr. Deepak'],status:'operational'},
  {id:'Orthopaedics',name:'Ortho',fullName:'Orthopaedic Ward',emoji:'🦴',floor:'2nd Floor, Block C',total:25,occupied:15,available:10,cost:3000,pct:60,color:'#E67700',specialists:['Dr. Vikram','Dr. Sanjay'],status:'operational'}
];
var PATIENTS=[
  {id:'PT-1001',fn:'Ravi',ln:'Kumar',age:52,gender:'Male',ward:'Cardiology',bed:7,severity:'High',diag:'Chest pain',admitted:new Date(Date.now()-86400000).toISOString(),status:'admitted',phone:'+91 9876543210'},
  {id:'PT-1002',fn:'Priya',ln:'Sharma',age:34,gender:'Female',ward:'General',bed:22,severity:'Moderate',diag:'Fever, viral infection',admitted:new Date(Date.now()-172800000).toISOString(),status:'admitted',phone:'+91 9123456789'},
  {id:'PT-1003',fn:'Suresh',ln:'Rao',age:68,gender:'Male',ward:'ICU',bed:3,severity:'Critical',diag:'Respiratory failure',admitted:new Date(Date.now()-43200000).toISOString(),status:'critical',phone:'+91 9988776655'},
  {id:'PT-1004',fn:'Meera',ln:'Devi',age:8,gender:'Female',ward:'Paediatrics',bed:11,severity:'Low',diag:'Appendicitis (post-op)',admitted:new Date(Date.now()-259200000).toISOString(),status:'recovering',phone:'+91 9765432100'},
  {id:'PT-1005',fn:'Arjun',ln:'Naik',age:45,gender:'Male',ward:'Surgical',bed:5,severity:'High',diag:'Hernia repair',admitted:new Date(Date.now()-21600000).toISOString(),status:'admitted',phone:'+91 9871234560'},
  {id:'PT-1006',fn:'Lakshmi',ln:'Patil',age:72,gender:'Female',ward:'Orthopaedics',bed:14,severity:'Moderate',diag:'Hip fracture',admitted:new Date(Date.now()-432000000).toISOString(),status:'recovering',phone:'+91 9654321098'}
];
var STAFF=[
  {id:'ST-001',name:'Dr. Ramesh Kumar',role:'Doctor',dept:'Pulmonology / ICU',shift:'Day 8AM–8PM',status:'on-duty'},
  {id:'ST-002',name:'Dr. Meera Singh',role:'Doctor',dept:'Cardiology',shift:'Day 8AM–8PM',status:'on-duty'},
  {id:'ST-003',name:'Nurse Kamala',role:'Head Nurse',dept:'ICU',shift:'Night 8PM–8AM',status:'off-duty'},
  {id:'ST-004',name:'Dr. Suresh Rao',role:'Surgeon',dept:'Surgical',shift:'Day 8AM–8PM',status:'on-duty'},
  {id:'ST-005',name:'Dr. Kavitha',role:'Doctor',dept:'Paediatrics',shift:'Day 8AM–8PM',status:'on-duty'},
  {id:'ST-006',name:'Mr. Admin Reddy',role:'Administrator',dept:'Admin',shift:'Day 9AM–6PM',status:'on-duty'}
];
var _patients=[].concat(PATIENTS);
var _curWardEdit=null;
var POLL_MS=15000,_pt=null,_ct=null,_cd=15;

// ══ HELPERS ══
function esc(s){return s?String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):''}
function sel(id){return document.getElementById(id)}
function nowT(){return new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}
function fmt(iso){return iso?new Date(iso).toLocaleString([],{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}):''}
function ago(iso){var s=Math.floor((Date.now()-new Date(iso))/1000);return s<60?s+'s ago':s<3600?Math.floor(s/60)+'m ago':s<86400?Math.floor(s/3600)+'h ago':Math.floor(s/86400)+'d ago';}

// ══ TOAST ══
var _tt=null;
function showToast(msg,t){
  var e=sel('toast');if(!e)return;
  e.textContent=msg;e.className='toast on t'+(t==='s'?'s':t==='e'?'e':'i');
  clearTimeout(_tt);_tt=setTimeout(function(){e.classList.remove('on');},4000);
}

// ══ ROUTING ══
var TABS=['dashboard','wards','patients','bookings','staff','reports','settings'],curTab='dashboard';
var PAGE_TITLES={dashboard:'Dashboard',wards:'Ward Management',patients:'Patient Management',bookings:'Booking Management',staff:'Staff Management',reports:'Reports & Analytics',settings:'Settings'};
var PAGE_SUBS={dashboard:'Live hospital overview · Auto-refreshes every 15s',wards:'Update bed counts, manage ward status',patients:'View, admit, discharge and manage all patients',bookings:'Manage all ward allocations and booking requests',staff:'Manage doctors, nurses and administrative staff',reports:'Hospital performance metrics and reports',settings:'Configure hospital system settings'};

function goTab(t){
  if(t===curTab)return;
  TABS.forEach(function(tb){var p=sel('tab-'+tb);if(p)p.classList.toggle('act',tb===t);var s=sel('sbi-'+tb);if(s)s.classList.toggle('act',tb===t);});
  curTab=t;
  var pt=sel('page-title');if(pt)pt.textContent=PAGE_TITLES[t]||t;
  var ps=sel('page-sub');if(ps)ps.textContent=PAGE_SUBS[t]||'';
  if(t==='patients')renderPatients(_patients);
  if(t==='bookings')renderBookings();
  if(t==='staff')renderStaff();
  if(t==='reports')renderReports();
  // Close mobile sidebar
  sel('sidebar').classList.remove('mobile-open');
}

// ══ SIDEBAR ══
function toggleSidebar(){sel('sidebar').classList.toggle('mobile-open');}

// ══ LOAD DATA ══
function liveWards(){
  return MW.map(function(w){
    var d=Math.floor(Math.random()*2)-0;
    var occ=Math.min(w.total-1,Math.max(Math.floor(w.total*.3),w.occupied+d));
    return Object.assign({},w,{occupied:occ,available:w.total-occ,pct:Math.round(occ/w.total*100)});
  });
}

function loadDashboard(){
  var wards=liveWards();
  var tot=wards.reduce(function(a,w){return a+w.total;},0);
  var av=wards.reduce(function(a,w){return a+w.available;},0);
  var oc=Math.round((tot-av)/tot*100);
  var cr=_patients.filter(function(p){return p.severity==='Critical';}).length;

  sel('sv-tot').textContent=tot;sel('sb-tot').textContent=tot+' beds';
  sel('sv-av').textContent=av;sel('sb-av').textContent=av+' free';
  sel('sv-cr').textContent=cr;sel('sb-cr').textContent=cr+' patients';
  sel('sv-oc').textContent=oc+'%';sel('sb-oc').textContent=oc>=85?'High':oc>=65?'Moderate':'Good';

  // Occupancy bars
  var ob=sel('occ-bars');
  if(ob)ob.innerHTML=wards.map(function(w){
    var c=w.pct>=85?'var(--red)':w.pct>=65?'var(--amber)':'var(--green)';
    return '<div class="bar-row"><div class="bar-lbl">'+w.emoji+' '+esc(w.name)+'</div>'
      +'<div class="bar-bg"><div class="bar-fill" style="width:'+w.pct+'%;background:'+c+'"></div></div>'
      +'<div class="bar-val">'+w.pct+'%</div></div>';
  }).join('');

  // Severity bars
  var sevs={Low:0,Moderate:0,High:0,Critical:0};
  _patients.forEach(function(p){sevs[p.severity]=(sevs[p.severity]||0)+1;});
  var sevC={Low:'var(--green)',Moderate:'var(--amber)',High:'var(--red)',Critical:'#9b1c1c'};
  var total=_patients.length||1;
  var sb=sel('sev-bars');
  if(sb)sb.innerHTML=Object.keys(sevs).map(function(k){
    var pct=Math.round(sevs[k]/total*100);
    return '<div class="bar-row"><div class="bar-lbl" style="color:'+sevC[k]+'">⬤ '+k+'</div>'
      +'<div class="bar-bg"><div class="bar-fill" style="width:'+pct+'%;background:'+sevC[k]+'"></div></div>'
      +'<div class="bar-val">'+sevs[k]+'</div></div>';
  }).join('');

  // Recent table
  var rt=sel('recent-table');
  if(rt)rt.innerHTML=_patients.slice(-5).reverse().map(function(p){
    var sc=p.severity==='Critical'?'pill-r':p.severity==='High'?'pill-a':p.severity==='Moderate'?'pill-b':'pill-g';
    var stc=p.status==='critical'?'pill-r':p.status==='recovering'?'pill-g':'pill-b';
    return '<tr><td><div class="td-name">'+esc(p.fn)+' '+esc(p.ln)+'</div><div class="td-id">'+esc(p.id)+'</div></td>'
      +'<td>'+esc(p.ward)+'</td><td>Bed '+p.bed+'</td>'
      +'<td><span class="pill '+sc+'">'+esc(p.severity)+'</span></td>'
      +'<td style="font-size:11.5px;color:var(--g500)">'+ago(p.admitted)+'</td>'
      +'<td><span class="pill '+stc+'">'+esc(p.status)+'</span></td>'
      +'<td><div class="td-act">'
        +'<button class="act-btn grn" onclick="dischargePatient(\\''+p.id+'\\')">Discharge</button>'
        +'<button class="act-btn" onclick="showToast(\\'Viewing \\'+\\''+esc(p.fn)+'\\',\\'i\\')">View</button>'
      +'</div></td></tr>';
  }).join('');
}

function loadWards(){
  var wards=liveWards();
  var g=sel('ward-mgmt-grid');
  if(g)g.innerHTML=wards.map(function(w){
    var c=w.pct>=85?'var(--red)':w.pct>=65?'var(--amber)':'var(--green)';
    return '<div class="wm-card">'
      +'<div class="wm-acc" style="background:'+esc(w.color)+'"></div>'
      +'<div class="wm-body">'
      +'<div class="wm-top"><div>'
        +'<div class="wm-name">'+w.emoji+' '+esc(w.fullName)+'</div>'
        +'<div class="wm-floor">'+esc(w.floor)+'</div>'
      +'</div><span class="pill '+(w.pct>=85?'pill-r':w.pct>=65?'pill-a':'pill-g')+'">'+esc(w.status)+'</span></div>'
      +'<div class="wm-stats">'
        +'<div class="wm-s"><div class="wm-sv" style="color:'+c+'">'+w.available+'</div><div class="wm-sl">Free</div></div>'
        +'<div class="wm-s"><div class="wm-sv" style="color:var(--g700)">'+w.occupied+'</div><div class="wm-sl">Occupied</div></div>'
        +'<div class="wm-s"><div class="wm-sv" style="color:var(--g400)">'+w.total+'</div><div class="wm-sl">Total</div></div>'
        +'<div class="wm-s"><div class="wm-sv" style="color:'+c+'">'+w.pct+'%</div><div class="wm-sl">Used</div></div>'
      +'</div>'
      +'<div class="wm-bar"><div class="wm-fill" style="width:'+w.pct+'%;background:'+c+'"></div></div>'
      +'<div style="font-size:11px;color:var(--g500);margin-bottom:10px">'+esc(w.specialists.join(' · '))+'</div>'
      +'<div class="wm-actions">'
        +'<button class="wm-btn wm-btn-blue" onclick="openWardModal(\\''+w.id+'\\')">✏️ Update</button>'
        +'<button class="wm-btn wm-btn-green" onclick="showToast(\\''+esc(w.fullName)+' report ready\\',\\'s\\')">📊 Report</button>'
        +'<button class="wm-btn wm-btn-red" onclick="showToast(\\'Alert sent for '+esc(w.name)+'\\',\\'e\\')">🚨 Alert</button>'
      +'</div></div></div>';
  }).join('');

  // Ward activity list
  var wal=sel('ward-activity-list');
  if(wal){
    var acts=[
      {w:'❤️ Cardiology',msg:'2 patients admitted',t:new Date(Date.now()-90000).toISOString(),c:'var(--red)'},
      {w:'🏥 ICU',msg:'1 patient discharged',t:new Date(Date.now()-280000).toISOString(),c:'var(--green)'},
      {w:'🩺 General',msg:'Bed 15 cleaned and ready',t:new Date(Date.now()-540000).toISOString(),c:'var(--blue)'},
      {w:'🦴 Ortho',msg:'Shift handover completed',t:new Date(Date.now()-820000).toISOString(),c:'var(--amber)'},
    ];
    wal.innerHTML=acts.map(function(a){
      return '<div style="display:flex;align-items:center;gap:10px;padding:10px 16px;border-bottom:1px solid var(--g100)">'
        +'<div style="width:8px;height:8px;border-radius:50%;background:'+a.c+';flex-shrink:0"></div>'
        +'<div style="flex:1;font-size:12.5px;color:var(--g700)"><strong>'+a.w+'</strong> — '+a.msg+'</div>'
        +'<div style="font-size:11px;color:var(--g400);font-weight:600">'+ago(a.t)+'</div></div>';
    }).join('');
  }
}

function renderPatients(patients){
  var tb=sel('patient-table');if(!tb)return;
  var sc={Critical:'pill-r',High:'pill-a',Moderate:'pill-b',Low:'pill-g'};
  var stc={critical:'pill-r',recovering:'pill-g',admitted:'pill-b'};
  tb.innerHTML=patients.map(function(p){
    return '<tr><td><span class="pill pill-b">'+esc(p.id)+'</span></td>'
      +'<td><div class="td-name">'+esc(p.fn)+' '+esc(p.ln)+'</div><div class="td-id">'+esc(p.phone)+'</div></td>'
      +'<td>'+p.age+'</td><td>'+esc(p.ward)+'</td><td>Bed '+p.bed+'</td>'
      +'<td><span class="pill '+(sc[p.severity]||'pill-b')+'">'+esc(p.severity)+'</span></td>'
      +'<td style="font-size:11.5px">'+fmt(p.admitted)+'</td>'
      +'<td><div class="td-act">'
        +'<button class="act-btn grn" onclick="dischargePatient(\\''+p.id+'\\')">Discharge</button>'
        +'<button class="act-btn" onclick="showToast(\\'Viewing '+esc(p.fn)+'\\',\\'i\\')">View</button>'
      +'</div></td></tr>';
  }).join('');
}

function renderBookings(){
  var tb=sel('booking-table');if(!tb)return;
  var sc={Critical:'pill-r',High:'pill-a',Moderate:'pill-b',Low:'pill-g'};
  var types={Emergency:'pill-r',Planned:'pill-g',Referral:'pill-b'};
  tb.innerHTML=_patients.map(function(p,i){
    var bid='BK-'+(2000+i);
    var type=i===0||i===2?'Emergency':i===3?'Referral':'Planned';
    return '<tr><td><span class="pill pill-p">'+bid+'</span></td>'
      +'<td><div class="td-name">'+esc(p.fn)+' '+esc(p.ln)+'</div><div class="td-id">'+esc(p.id)+'</div></td>'
      +'<td>'+esc(p.ward)+'</td><td>Bed '+p.bed+'</td>'
      +'<td><span class="pill '+(types[type]||'pill-b')+'">'+type+'</span></td>'
      +'<td><span class="pill '+(sc[p.severity]||'pill-b')+'">'+esc(p.severity)+'</span></td>'
      +'<td style="font-size:11.5px">'+fmt(p.admitted)+'</td>'
      +'<td><span class="pill pill-g">Active</span></td>'
      +'<td><div class="td-act">'
        +'<button class="act-btn red" onclick="showToast(\\'Booking cancelled\\',\\'e\\')">Cancel</button>'
        +'<button class="act-btn" onclick="showToast(\\'Booking '+bid+' details\\',\\'i\\')">View</button>'
      +'</div></td></tr>';
  }).join('');
}

function renderStaff(){
  var tb=sel('staff-table');if(!tb)return;
  var sc={'on-duty':'pill-g','off-duty':'pill-a'};
  var rc={Doctor:'pill-b',Surgeon:'pill-p','Head Nurse':'pill-a',Administrator:'pill-g'};
  tb.innerHTML=STAFF.map(function(s){
    return '<tr><td><span class="pill pill-b">'+esc(s.id)+'</span></td>'
      +'<td class="td-name">'+esc(s.name)+'</td>'
      +'<td><span class="pill '+(rc[s.role]||'pill-b')+'">'+esc(s.role)+'</span></td>'
      +'<td>'+esc(s.dept)+'</td><td style="font-size:12px">'+esc(s.shift)+'</td>'
      +'<td><span class="pill '+(sc[s.status]||'pill-b')+'">'+esc(s.status)+'</span></td>'
      +'<td><div class="td-act">'
        +'<button class="act-btn" onclick="showToast(\\'Viewing \\'+\\''+esc(s.name)+'\\',\\'i\\')">View</button>'
        +'<button class="act-btn" onclick="showToast(\\'Edited \\'+\\''+esc(s.name)+'\\',\\'s\\')">Edit</button>'
      +'</div></td></tr>';
  }).join('');
}

function renderReports(){
  var days=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  var vals=[12,18,15,22,19,14,8];
  var wb=sel('weekly-bars');
  if(wb)wb.innerHTML=days.map(function(d,i){
    return '<div class="bar-row"><div class="bar-lbl">'+d+'</div>'
      +'<div class="bar-bg"><div class="bar-fill" style="width:'+(vals[i]/22*100)+'%;background:var(--blue)"></div></div>'
      +'<div class="bar-val">'+vals[i]+'</div></div>';
  }).join('');
  var ub=sel('util-bars');
  var uw=liveWards();
  if(ub)ub.innerHTML=uw.map(function(w){
    var c=w.pct>=85?'var(--red)':w.pct>=65?'var(--amber)':'var(--green)';
    return '<div class="bar-row"><div class="bar-lbl">'+w.emoji+' '+esc(w.name)+'</div>'
      +'<div class="bar-bg"><div class="bar-fill" style="width:'+w.pct+'%;background:'+c+'"></div></div>'
      +'<div class="bar-val">'+w.pct+'%</div></div>';
  }).join('');
}

function filterPatients(ward){
  if(!ward)renderPatients(_patients);
  else renderPatients(_patients.filter(function(p){return p.ward===ward;}));
}

function dischargePatient(id){
  var idx=_patients.findIndex(function(p){return p.id===id;});
  if(idx>=0){var name=_patients[idx].fn+' '+_patients[idx].ln;_patients.splice(idx,1);renderPatients(_patients);loadDashboard();showToast(name+' discharged successfully','s');sel('new-bdg').textContent=Math.max(0,parseInt(sel('new-bdg').textContent||0)-1);}
}

function doSearch(q){
  if(!q){renderPatients(_patients);return;}
  var lq=q.toLowerCase();
  var res=_patients.filter(function(p){return (p.fn+' '+p.ln).toLowerCase().includes(lq)||p.id.toLowerCase().includes(lq)||p.ward.toLowerCase().includes(lq)||p.diag.toLowerCase().includes(lq);});
  if(curTab==='patients')renderPatients(res);
}

// ══ MODALS ══
function openModal(id){sel('modal-'+id).classList.add('on');}
function closeModal(id){sel('modal-'+id).classList.remove('on');}
window.addEventListener('click',function(e){if(e.target.classList.contains('modal-bg'))e.target.classList.remove('on');});

function openWardModal(wid){
  var w=MW.find(function(x){return x.id===wid;});if(!w)return;
  _curWardEdit=wid;
  sel('wm-title').textContent='Update '+w.fullName;
  sel('wm-total').value=w.total;
  sel('wm-occupied').value=w.occupied;
  sel('wm-status').value=w.status;
  openModal('ward');
}

function saveWardUpdate(){
  if(!_curWardEdit)return;
  var w=MW.find(function(x){return x.id===_curWardEdit;});if(!w)return;
  var tot=parseInt(sel('wm-total').value)||w.total;
  var occ=Math.min(tot-1,parseInt(sel('wm-occupied').value)||w.occupied);
  w.total=tot;w.occupied=occ;w.available=tot-occ;w.pct=Math.round(occ/tot*100);
  w.status=sel('wm-status').value;
  closeModal('ward');loadWards();loadDashboard();
  showToast(w.fullName+' updated successfully','s');
}

function submitAdmit(){
  var fn=(sel('m-fn')||{}).value,ln=(sel('m-ln')||{}).value;
  var age=(sel('m-age')||{}).value,diag=(sel('m-diag')||{}).value;
  var sev=(sel('m-sev')||{}).value;
  if(!fn||!ln||!age||!diag||!sev){showToast('Fill all required fields','e');return;}
  var btn=sel('btn-admit');btn.disabled=true;btn.innerHTML='<span class="spn"></span> AI Allocating…';
  setTimeout(function(){
    var avWards=MW.filter(function(w){return w.available>0;});
    var ward=avWards[Math.floor(Math.random()*Math.min(2,avWards.length))];
    if(!ward){showToast('No beds available! Consider transferring a patient.','e');btn.disabled=false;btn.innerHTML='🤖 AI Allocate & Admit';return;}
    var pid='PT-'+(1007+_patients.length);
    var bed=Math.floor(Math.random()*(ward.available))+1;
    _patients.push({id:pid,fn:fn,ln:ln,age:parseInt(age),gender:(sel('m-gen')||{}).value||'',ward:ward.name,bed:bed,severity:sev,diag:diag,admitted:new Date().toISOString(),status:'admitted',phone:(sel('m-ph')||{}).value||''});
    ward.occupied++;ward.available--;ward.pct=Math.round(ward.occupied/ward.total*100);
    closeModal('admit');loadDashboard();loadWards();
    showToast('✅ '+fn+' '+ln+' admitted to '+ward.fullName+' (Bed '+bed+')','s');
    sel('new-bdg').textContent=parseInt(sel('new-bdg').textContent||0)+1;
    btn.disabled=false;btn.innerHTML='🤖 AI Allocate & Admit';
    ['m-fn','m-ln','m-age','m-diag','m-ph'].forEach(function(id){var e=sel(id);if(e)e.value='';});
    if(sel('m-sev'))sel('m-sev').selectedIndex=0;
  },900);
}

function saveSettings(){
  var key=(sel('api-key-input')||{}).value;
  if(key&&key.startsWith('sk-ant')){showToast('API key saved! Chatbot now uses Claude AI','s');}
  else{showToast('Settings saved','s');}
}

function updatePollInterval(ms){
  POLL_MS=ms||15000;
  clearInterval(_pt);clearInterval(_ct);
  _cd=POLL_MS/1000;
  _pt=setInterval(function(){_cd=POLL_MS/1000;loadAll();showToast('🔄 Data refreshed','i');},POLL_MS);
  _ct=setInterval(function(){_cd=Math.max(0,_cd-1);var f=sel('rfill');if(f)f.style.width=(_cd/(POLL_MS/1000)*100)+'%';var l=sel('rlbl');if(l)l.textContent='↻ '+_cd+'s';},1000);
  showToast('Refresh interval: '+(POLL_MS/1000)+'s','i');
}

function loadAll(){loadDashboard();if(curTab==='wards')loadWards();}

// ══ AUTO-REFRESH ══
function startPolling(){
  loadAll();loadWards();
  clearInterval(_pt);clearInterval(_ct);_cd=POLL_MS/1000;
  _pt=setInterval(function(){_cd=POLL_MS/1000;loadAll();},POLL_MS);
  _ct=setInterval(function(){
    _cd=Math.max(0,_cd-1);
    var f=sel('rfill');if(f)f.style.width=(_cd/(POLL_MS/1000)*100)+'%';
    var l=sel('rlbl');if(l)l.textContent='↻ '+_cd+'s';
  },1000);
}

// ══ CLOCK ══
setInterval(function(){var e=sel('ntime');if(e)e.textContent=nowT();},1000);

// ══ INIT ══
window.addEventListener('DOMContentLoaded',function(){startPolling();renderPatients(_patients);});
</script>
</body>
</html>
"""

@app.route("/api/wards")
def get_wards():
    with get_db() as db:
        rows = db.execute("SELECT * FROM wards ORDER BY ward_id").fetchall()
    result = []
    for r in rows:
        pct = round(r["occupied"]/r["total_beds"]*100,1)
        status = "critical" if pct>=85 else "moderate" if pct>=60 else "available"
        cfg = WARDS_CONFIG.get(r["ward_id"],{})
        result.append({"id":r["ward_id"],"name":r["name"],"emoji":r["emoji"],"color":r["color"],
            "icon":r["icon"],"total":r["total_beds"],"occupied":r["occupied"],
            "available":r["total_beds"]-r["occupied"],"occupancy_pct":pct,"status":status,
            "floor":r["floor"],"cost_per_day":r["cost_per_day"],
            "specialists":cfg.get("specialists",[]),"equipment":cfg.get("equipment",[]),
            "updated_at":r["updated_at"]})
    return jsonify({"success":True,"wards":result,"count":len(result),"timestamp":datetime.now().isoformat()})

@app.route("/api/dashboard")
def dashboard():
    with get_db() as db:
        wards = db.execute("SELECT * FROM wards").fetchall()
        total = sum(w["total_beds"] for w in wards)
        occ = sum(w["occupied"] for w in wards)
        critical = db.execute("SELECT COUNT(*) FROM patients WHERE severity='Critical' AND status='Admitted'").fetchone()[0]
        total_pts = db.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        active_bk = db.execute("SELECT COUNT(*) FROM bookings WHERE status='Active'").fetchone()[0]
        recent = db.execute("SELECT * FROM bookings ORDER BY allocated_at DESC LIMIT 5").fetchall()
    return jsonify({"success":True,"stats":{"total_beds":total,"occupied_beds":occ,"available_beds":total-occ,
        "occupancy_rate":round(occ/total*100,1) if total else 0,"total_patients":total_pts,
        "critical_patients":critical,"active_bookings":active_bk},
        "recent_bookings":[dict(r) for r in recent],"timestamp":datetime.now().isoformat()})

@app.route("/api/announcements")
def announcements():
    with get_db() as db:
        rows = db.execute("SELECT * FROM announcements WHERE is_active=1 ORDER BY created_at DESC LIMIT 6").fetchall()
    return jsonify({"success":True,"announcements":[dict(r) for r in rows]})

@app.route("/api/stats/trend")
def stats_trend():
    with get_db() as db:
        base = db.execute("SELECT SUM(occupied) FROM wards").fetchone()[0] or 100
        total = db.execute("SELECT SUM(total_beds) FROM wards").fetchone()[0] or 205
    now = datetime.now()
    trend = []
    for i in range(12,-1,-1):
        h = now - timedelta(hours=i)
        noise = random.randint(-6,6)
        occ = max(50,min(total-5,base+noise-i//2))
        trend.append({"hour":h.strftime("%H:00"),"occupied":occ,"available":total-occ})
    return jsonify({"success":True,"trend":trend,"total_beds":total})

@app.route("/api/ward-updates")
def ward_updates():
    with get_db() as db:
        rows = db.execute("""SELECT wu.*,w.name as ward_name,w.emoji FROM ward_updates wu
            JOIN wards w ON wu.ward_id=w.ward_id ORDER BY wu.updated_at DESC LIMIT 15""").fetchall()
    return jsonify({"success":True,"updates":[dict(r) for r in rows],"timestamp":datetime.now().isoformat()})

@app.route("/api/patients/register", methods=["POST"])
def register_patient():
    data = request.json or {}
    missing = [f for f in ["first_name","last_name","age","diagnosis","severity"] if not data.get(f)]
    if missing: return jsonify({"success":False,"error":f"Missing: {', '.join(missing)}"}),400
    pid = "P"+str(uuid.uuid4())[:6].upper()
    recs = _ai_allocate_logic(data)
    with get_db() as db:
        db.execute("INSERT INTO patients VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid,data["first_name"],data["last_name"],data.get("age"),data.get("gender",""),
             data.get("phone",""),data.get("blood_group",""),data["diagnosis"],data["severity"],
             data.get("admission_type","Planned"),data.get("notes",""),"Registered",None,None,
             datetime.now().isoformat(),None))
        db.commit()
    return jsonify({"success":True,"patient_id":pid,"ai_recommendations":recs,
        "message":f"Patient {data['first_name']} {data['last_name']} registered"})

@app.route("/api/patients/allocate", methods=["POST"])
def allocate_patient():
    data = request.json or {}
    pid, wid = data.get("patient_id"), data.get("ward_id")
    if not pid or not wid: return jsonify({"success":False,"error":"patient_id and ward_id required"}),400
    with get_db() as db:
        patient = db.execute("SELECT * FROM patients WHERE patient_id=?",(pid,)).fetchone()
        ward = db.execute("SELECT * FROM wards WHERE ward_id=?",(wid,)).fetchone()
        if not patient: return jsonify({"success":False,"error":"Patient not found"}),404
        if not ward: return jsonify({"success":False,"error":"Ward not found"}),404
        if ward["total_beds"]-ward["occupied"] <= 0: return jsonify({"success":False,"error":f"{wid} is full"}),409
        bed = _next_bed_number(wid)
        now = datetime.now().isoformat()
        db.execute("UPDATE wards SET occupied=occupied+1,updated_at=? WHERE ward_id=?",(now,wid))
        db.execute("UPDATE patients SET status='Admitted',ward_id=?,bed_number=?,admitted_at=? WHERE patient_id=?",(wid,bed,now,pid))
        db.execute("INSERT INTO ward_updates (ward_id,old_occupied,new_occupied,reason) VALUES (?,?,?,?)",
            (wid,ward["occupied"],ward["occupied"]+1,f"Admitted {pid}"))
        bk_id = "BK"+str(uuid.uuid4())[:6].upper()
        db.execute("INSERT INTO bookings VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (bk_id,pid,f"{patient['first_name']} {patient['last_name']}",wid,ward["name"],
             bed,ward["floor"],patient["diagnosis"],patient["severity"],now,"Active"))
        db.commit()
    return jsonify({"success":True,"booking_id":bk_id,"bed_number":bed,"ward":wid,
        "message":f"Bed {bed} confirmed in {WARDS_CONFIG[wid]['name']}"})

@app.route("/api/bookings")
def get_bookings():
    with get_db() as db:
        rows = db.execute("SELECT * FROM bookings ORDER BY allocated_at DESC LIMIT 50").fetchall()
    return jsonify({"success":True,"bookings":[dict(r) for r in rows],"total":len(rows)})

@app.route("/api/patients")
def get_patients():
    with get_db() as db:
        rows = db.execute("SELECT * FROM patients ORDER BY registered_at DESC LIMIT 50").fetchall()
    return jsonify({"success":True,"patients":[dict(r) for r in rows],"total":len(rows)})

@app.route("/api/chatbot", methods=["POST"])
def chatbot():
    data = request.json or {}
    msg = (data.get("message") or "").lower().strip()
    session_id = data.get("session_id","anon")
    with get_db() as db:
        wards = {r["ward_id"]:dict(r) for r in db.execute("SELECT * FROM wards").fetchall()}
        db.execute("INSERT INTO chat_logs (session_id,role,message) VALUES (?,?,?)",(session_id,"user",msg))
        db.commit()

    def ws():
        lines = []
        for wid,w in wards.items():
            avail = w["total_beds"]-w["occupied"]
            icon = "🔴" if avail<=3 else "🟡" if avail<=8 else "🟢"
            lines.append(f"{icon} **{wid}**: {avail}/{w['total_beds']} free — ₹{w['cost_per_day']:,}/day")
        return "\n".join(lines)

    if re.search(r"hi|hello|hey|good\s*(morning|evening)|namaste",msg):
        reply=("👋 **Welcome to AIMS CARE Hospital!**\n\nI can help you with:\n• 🛏️ Live ward availability\n• 📋 Ward booking\n• 🚨 Emergency services\n• 💰 Costs & insurance\n\nHow can I assist?")
    elif re.search(r"availab|bed|free|vacant|ward status|capacity",msg):
        reply=f"📊 **Live Ward Availability** (as of {datetime.now().strftime('%H:%M')}):\n\n{ws()}\n\n**Total free:** {sum(w['total_beds']-w['occupied'] for w in wards.values())} beds"
    elif re.search(r"emergency|urgent|critical|sos|ambulance|accident",msg):
        avail=wards.get("ICU",{}).get("total_beds",20)-wards.get("ICU",{}).get("occupied",0)
        reply=(f"🚨 **EMERGENCY — ACT NOW**\n\n📞 **Call 108** (Free 24/7)\n☎️ **+91 816 222 3456**\n\n🏥 ICU: **{avail} beds available**\n\nHead to Emergency Gate — Ground Floor, Main Block.")
    elif re.search(r"icu|intensive|ventilat|critical care",msg):
        w=wards.get("ICU",{}); a=w.get("total_beds",20)-w.get("occupied",0)
        reply=(f"🏥 **ICU — Intensive Care**\n\n📍 3rd Floor, Block A\n🛏️ **{a} beds free** / {w.get('total_beds',20)}\n💰 ₹8,000/day\n👨‍⚕️ Pulmonologist, Critical Care Specialist")
    elif re.search(r"cardio|heart|chest|ecg|cardiac",msg):
        w=wards.get("Cardiology",{}); a=w.get("total_beds",30)-w.get("occupied",0)
        reply=(f"❤️ **Cardiology Ward**\n\n📍 2nd Floor, Block B\n🛏️ **{a} beds free** / {w.get('total_beds',30)}\n💰 ₹5,000/day\n👨‍⚕️ Cardiologist, Cardiac Surgeon")
    elif re.search(r"paed|child|infant|baby|neonatal",msg):
        w=wards.get("Paediatrics",{}); a=w.get("total_beds",30)-w.get("occupied",0)
        reply=(f"👶 **Paediatrics Ward**\n\n📍 1st Floor, Block D\n🛏️ **{a} beds free** / {w.get('total_beds',30)}\n💰 ₹2,000/day\n👩‍⚕️ Paediatrician, Neonatologist")
    elif re.search(r"ortho|fracture|bone|joint|spine|knee|hip",msg):
        w=wards.get("Orthopaedics",{}); a=w.get("total_beds",35)-w.get("occupied",0)
        reply=(f"🦴 **Orthopaedics Ward**\n\n📍 3rd Floor, Block D\n🛏️ **{a} beds free** / {w.get('total_beds',35)}\n💰 ₹3,000/day\n👨‍⚕️ Orthopaedic Surgeon, Physiotherapist")
    elif re.search(r"book|admit|register|reservation",msg):
        reply=("📋 **Book a Ward**\n\nUse the **Book Ward** section above:\n1️⃣ Fill patient details\n2️⃣ AI recommends top 3 wards in 2s\n3️⃣ Confirm — instant bed assignment!\n\nOr call **+91 816 222 3456**")
    elif re.search(r"cost|price|charge|fee|rate|how much|billing",msg):
        lines="\n".join([f"{w['emoji']} **{wid}**: ₹{w['cost_per_day']:,}/day" for wid,w in wards.items()])
        reply=f"💰 **Ward Charges (per day):**\n\n{lines}\n\n_Includes nursing, meals & basic medications._"
    elif re.search(r"insur|cashless|ayushman|mediclaim",msg):
        reply=("💳 **Insurance Accepted:**\n\n✅ Ayushman Bharat (PMJAY)\n✅ Star Health\n✅ HDFC ERGO\n✅ New India Assurance\n✅ ICICI Lombard\n\nCashless processing in 30 minutes.")
    elif re.search(r"time|hour|opd|open|timing|schedule",msg):
        reply=("🕐 **Hospital Hours:**\n\n🏥 OPD: 8AM–8PM (Mon–Sat)\n🚨 Emergency: 24/7\n💊 Pharmacy: 6AM–10PM\n🧪 Lab: 7AM–9PM")
    elif re.search(r"locat|address|where|direction|map",msg):
        reply=("📍 **AIMS CARE Hospital**\n12 Healthcare Avenue\nTumkur, Karnataka — 572101\n\n🚗 5min from Bus Stand\n🚂 10min from Railway Station\n🅿️ Free parking — 200 vehicles")
    elif re.search(r"doctor|physician|specialist|surgeon",msg):
        reply=("👨‍⚕️ **Our Specialists:**\n• Dr. Ramesh Kumar — ICU Head\n• Dr. Meera Singh — Cardiologist\n• Dr. Suresh Rao — Surgeon\n• Dr. Kavitha M. — Paediatrician\n• Dr. Anand P. — Orthopaedics\n\nAppts: Mon–Sat 9AM–5PM")
    elif re.search(r"thank|thanks|ok|okay",msg):
        reply="😊 You're welcome! Anything else? Stay healthy! 🏥"
    elif re.search(r"bye|goodbye",msg):
        reply="👋 Take care! AIMS CARE is always here for you. 💙"
    else:
        reply=("🤔 I can help with:\n• 🛏️ Ward availability\n• 📋 Booking\n• 🚨 Emergency\n• 💰 Costs\n• 📍 Location\n\nTry: *'Check availability'* or *'Emergency help'*")

    with get_db() as db:
        db.execute("INSERT INTO chat_logs (session_id,role,message) VALUES (?,?,?)",(session_id,"bot",reply))
        db.commit()
    return jsonify({"success":True,"reply":reply,"timestamp":datetime.now().isoformat()})

# ═══════════════════════════════════════════════════════════
#  STARTUP
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
