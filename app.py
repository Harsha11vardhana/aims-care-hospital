"""
AIMS CARE Hospital — Premium AI Ward Allocation System
Flask Backend · SQLite Database · Real-Time API · Voice AI
"""

from flask import Flask, request, jsonify, send_from_directory, Response
from datetime import datetime, timedelta
import sqlite3, uuid, re, os, random, threading, time

app = Flask(__name__, template_folder=None)
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
    here=os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(here,"index.html")

@app.route("/pwa")
def pwa():
    here=os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(here,"pwa.html")

@app.route("/staff")
def staff():
    here=os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(here,"staff.html")

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
