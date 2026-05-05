# IoT Black Box Accident Recorder
### Flask + A7 Thinker GSM + SQLite + PySerial

---

## Overview

A real-time vehicular accident detection and emergency notification system.
The A7 Thinker GSM/GPS chip streams accelerometer and GPS data to this Flask
server. When a crash is detected (G-force ≥ 3.5G), a 20-second safety
countdown begins. If not cancelled by the occupant, SMS alerts are sent to all
registered emergency contacts via the A7's GSM module using AT+CMGS commands
over a serial connection.

---

## Hardware Requirements

| Component        | Detail                                |
|------------------|---------------------------------------|
| A7 Thinker chip  | GSM/GPRS/GPS all-in-one module        |
| USB-UART adapter | CP2102 or CH340 (3.3 V logic)         |
| MPU-6050         | I²C accelerometer (connected to A7)   |
| SIM card         | Any 2G-compatible SIM with SMS plan   |

### Wiring (A7 ↔ Raspberry Pi / Linux host)

```
A7 TX  →  USB-UART RX  →  /dev/ttyUSB0
A7 RX  →  USB-UART TX
A7 GND →  Host GND
A7 VCC →  4.2 V (from LiPo or buck converter)
```

---

## Setup

```bash
# 1. Clone / copy project
cd blackbox/

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Run the server
python app.py
```

Open http://localhost:5000 in your browser.

---

## API Reference

### POST /update_status
Endpoint for the A7 chip firmware to POST sensor readings.

**Request body (JSON):**
```json
{
  "gps": {
    "lat":   28.6139,
    "lon":   77.2090,
    "speed": 60.5
  },
  "gforce": {
    "x":         0.12,
    "y":        -0.08,
    "z":         9.81,
    "magnitude": 9.81
  }
}
```

**Response:**
```json
{
  "status":              "MONITORING",
  "countdown_active":    false,
  "countdown_remaining": 0
}
```

When magnitude ≥ 3.5G, status becomes `"CRASH DETECTED — COUNTDOWN"` and the
20-second SMS countdown thread starts automatically.

---

### GET /api/state
Returns current system state for the frontend polling loop (every 2 s).

**Response:**
```json
{
  "system_status":       "MONITORING",
  "countdown_active":    false,
  "countdown_remaining": 0,
  "last_gps":  { "lat": 28.6139, "lon": 77.2090, "speed": 60.5 },
  "last_gforce": { "x": 0.1, "y": 0.0, "z": 9.8, "magnitude": 9.81 },
  "logs": [ ... ]
}
```

### POST /cancel_countdown
Cancels an active safety countdown (form action from the UI).

### POST /simulate_crash
Triggers a fake crash for development/testing without hardware.

### POST /add_contact
Form action to add an emergency contact.
Fields: `name`, `mobile` (E.164 format recommended, e.g. +919876543210)

### POST /delete_contact/<id>
Removes an emergency contact by database ID.

---

## SMS Format (sent via AT+CMGS)

```
[BLACK BOX ALERT] Crash detected at 2025-07-01 14:32:10 UTC.
G-Force: 4.30G | Speed: 72.0 km/h
Location: 28.613900,77.209000
Maps: https://maps.google.com/?q=28.6139,77.209
```

---

## Database Schema

### incident_logs
| Column     | Type    | Description                              |
|------------|---------|------------------------------------------|
| id         | INTEGER | Auto-increment primary key               |
| timestamp  | TEXT    | UTC timestamp of the event               |
| event_type | TEXT    | CRASH_DETECTED / CRASH_SMS_SENT / etc.   |
| gforce_x/y/z | REAL | Raw axis readings                        |
| magnitude  | REAL    | Vector magnitude in G                    |
| latitude   | REAL    | GPS latitude at time of event            |
| longitude  | REAL    | GPS longitude at time of event           |
| speed      | REAL    | Vehicle speed in km/h                    |
| sms_sent   | INTEGER | Number of SMS successfully delivered     |
| notes      | TEXT    | Human-readable event description         |

### emergency_contacts
| Column | Type    | Description                    |
|--------|---------|--------------------------------|
| id     | INTEGER | Auto-increment primary key     |
| name   | TEXT    | Contact display name           |
| mobile | TEXT    | Phone number (unique)          |
| active | INTEGER | 1 = active, 0 = disabled       |

---

## Configuration

Edit these constants at the top of `app.py`:

| Constant                | Default       | Description                         |
|-------------------------|---------------|-------------------------------------|
| SERIAL_PORT             | /dev/ttyUSB0  | Serial port of A7 chip              |
| BAUD_RATE               | 115200        | Serial baud rate                    |
| CRASH_GFORCE_THRESHOLD  | 3.5           | G-force level to trigger detection  |

---

## Project Structure

```
blackbox/
├── app.py               # Flask application + all backend logic
├── requirements.txt     # Python dependencies
├── blackbox.db          # SQLite database (auto-created on first run)
├── README.md
└── templates/
    └── index.html       # Industrial dark-theme flight recorder UI
```
