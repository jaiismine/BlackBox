"""
IoT Black Box Accident Recorder - Flask Backend
A7 Thinker GSM Chip Integration via PySerial
"""

import sqlite3
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

app = Flask(__name__)
DB_PATH = "blackbox.db"

SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE   = 115200

system_status       = "STANDBY"
countdown_active    = False
countdown_remaining = 0
last_gps    = {"lat": 0.0, "lon": 0.0, "speed": 0.0}
last_gforce = {"x": 0.0, "y": 0.0, "z": 0.0, "magnitude": 0.0}
CRASH_GFORCE_THRESHOLD = 3.5

@app.context_processor
def inject_now():
    return {"now": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS incident_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            gforce_x REAL, gforce_y REAL, gforce_z REAL, magnitude REAL,
            latitude REAL, longitude REAL, speed REAL,
            sms_sent INTEGER DEFAULT 0,
            notes TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS emergency_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            mobile TEXT NOT NULL UNIQUE,
            active INTEGER DEFAULT 1
        )
    """)
    c.execute("SELECT COUNT(*) FROM emergency_contacts")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO emergency_contacts (name, mobile) VALUES (?, ?)",
                  ("Emergency Contact 1", "+911234567890"))
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def open_serial():
    if not SERIAL_AVAILABLE:
        return None
    try:
        return serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
    except Exception as e:
        app.logger.warning(f"[SERIAL] {e}")
        return None

def send_at_command(ser, command, delay=1.0):
    ser.write((command + "\r\n").encode())
    time.sleep(delay)
    return ser.read_all().decode(errors="ignore")

def send_sms(mobile_number, message):
    """Send SMS via A7 Thinker chip using AT+CMGS command over PySerial."""
    ser = open_serial()
    if ser is None:
        app.logger.error("[SMS] Serial port unavailable.")
        return False
    try:
        send_at_command(ser, "AT+CMGF=1", delay=0.5)
        ser.write(f'AT+CMGS="{mobile_number}"\r\n'.encode())
        time.sleep(0.5)
        ser.write((message + "\x1A").encode())
        time.sleep(3)
        response = ser.read_all().decode(errors="ignore")
        ser.close()
        return "+CMGS" in response
    except Exception as e:
        app.logger.error(f"[SMS] Exception: {e}")
        try: ser.close()
        except: pass
        return False

def log_incident(event_type, gforce, gps, sms_sent=0, notes=""):
    conn = get_db()
    conn.execute("""
        INSERT INTO incident_logs
            (timestamp, event_type, gforce_x, gforce_y, gforce_z, magnitude,
             latitude, longitude, speed, sms_sent, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        event_type,
        gforce.get("x",0), gforce.get("y",0), gforce.get("z",0),
        gforce.get("magnitude",0),
        gps.get("lat",0), gps.get("lon",0), gps.get("speed",0),
        sms_sent, notes
    ))
    conn.commit()
    conn.close()

def safety_countdown_and_sms(gforce_snapshot, gps_snapshot):
    global system_status, countdown_active, countdown_remaining
    countdown_active = True
    system_status = "CRASH DETECTED — COUNTDOWN"

    for i in range(20, 0, -1):
        if not countdown_active:
            system_status = "COUNTDOWN CANCELLED"
            log_incident("COUNTDOWN_CANCELLED", gforce_snapshot, gps_snapshot,
                         notes="Operator cancelled countdown.")
            return
        countdown_remaining = i
        time.sleep(1)

    countdown_active    = False
    countdown_remaining = 0
    system_status       = "SMS DISPATCHING"

    conn     = get_db()
    contacts = conn.execute(
        "SELECT name, mobile FROM emergency_contacts WHERE active=1"
    ).fetchall()
    conn.close()

    mag = gforce_snapshot.get("magnitude", 0)
    lat = gps_snapshot.get("lat", 0)
    lon = gps_snapshot.get("lon", 0)
    spd = gps_snapshot.get("speed", 0)
    ts  = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    message = (
        f"[BLACK BOX ALERT] Crash detected at {ts}.\n"
        f"G-Force: {mag:.2f}G | Speed: {spd:.1f} km/h\n"
        f"Location: {lat:.6f},{lon:.6f}\n"
        f"Maps: https://maps.google.com/?q={lat},{lon}"
    )

    sms_ok = sum(1 for c in contacts if send_sms(c["mobile"], message))
    log_incident("CRASH_SMS_SENT", gforce_snapshot, gps_snapshot,
                 sms_sent=sms_ok,
                 notes=f"SMS dispatched to {sms_ok}/{len(contacts)} contacts.")
    system_status = f"SMS SENT TO {sms_ok} CONTACT(S)"

@app.route("/")
def index():
    conn     = get_db()
    logs     = conn.execute("SELECT * FROM incident_logs ORDER BY id DESC LIMIT 50").fetchall()
    contacts = conn.execute("SELECT * FROM emergency_contacts ORDER BY id").fetchall()
    conn.close()
    return render_template("index.html",
                           logs=logs, contacts=contacts,
                           system_status=system_status,
                           countdown_active=countdown_active,
                           countdown_remaining=countdown_remaining,
                           last_gps=last_gps, last_gforce=last_gforce)

@app.route("/update_status", methods=["POST"])
def update_status():
    """A7 Thinker chip POSTs GPS + G-force data here."""
    global system_status, countdown_active, last_gps, last_gforce
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400
    gps    = data.get("gps",    {})
    gforce = data.get("gforce", {})
    last_gps.update(gps)
    last_gforce.update(gforce)
    magnitude = gforce.get("magnitude", 0)
    if magnitude >= CRASH_GFORCE_THRESHOLD and not countdown_active:
        log_incident("CRASH_DETECTED", gforce, gps,
                     notes=f"G-Force threshold breached: {magnitude:.2f}G")
        threading.Thread(target=safety_countdown_and_sms,
                         args=(dict(gforce), dict(gps)), daemon=True).start()
    elif not countdown_active:
        system_status = "MONITORING"
    return jsonify({"status": system_status,
                    "countdown_active": countdown_active,
                    "countdown_remaining": countdown_remaining})

@app.route("/cancel_countdown", methods=["POST"])
def cancel_countdown():
    global countdown_active
    countdown_active = False
    return redirect(url_for("index"))

@app.route("/add_contact", methods=["POST"])
def add_contact():
    name   = request.form.get("name",   "").strip()
    mobile = request.form.get("mobile", "").strip()
    if name and mobile:
        conn = get_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO emergency_contacts (name, mobile) VALUES (?, ?)",
                (name, mobile))
            conn.commit()
        except Exception as e:
            app.logger.error(f"[DB] {e}")
        conn.close()
    return redirect(url_for("index"))

@app.route("/delete_contact/<int:cid>", methods=["POST"])
def delete_contact(cid):
    conn = get_db()
    conn.execute("DELETE FROM emergency_contacts WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return redirect(url_for("index"))

@app.route("/api/state")
def api_state():
    """Polling endpoint for frontend real-time updates."""
    conn = get_db()
    logs = conn.execute("SELECT * FROM incident_logs ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    return jsonify({
        "system_status":       system_status,
        "countdown_active":    countdown_active,
        "countdown_remaining": countdown_remaining,
        "last_gps":            last_gps,
        "last_gforce":         last_gforce,
        "logs":                [dict(r) for r in logs]
    })

@app.route("/simulate_crash", methods=["POST"])
def simulate_crash():
    """Dev endpoint: trigger a fake crash without hardware."""
    global countdown_active
    fake_gforce = {"x": 2.1, "y": -3.8, "z": 1.2, "magnitude": 4.3}
    fake_gps    = {"lat": 28.6139, "lon": 77.2090, "speed": 72.0}
    if not countdown_active:
        log_incident("CRASH_DETECTED", fake_gforce, fake_gps,
                     notes="SIMULATED crash event via web UI.")
        threading.Thread(target=safety_countdown_and_sms,
                         args=(fake_gforce, fake_gps), daemon=True).start()
    return redirect(url_for("index"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
