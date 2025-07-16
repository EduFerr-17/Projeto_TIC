from flask import Flask, render_template, request, redirect, url_for, jsonify, Request
import numpy as np
import os
import csv
from datetime import datetime, timedelta
from bp_calc import Blood_Pressure
import requests
import time
import threading
from collections import defaultdict


app = Flask(__name__)

# Path to save measurement history
DATA_FILE = "measurements.csv"

# Lock to prevent concurrent measurements
measurement_lock = threading.Lock()
measurement_in_progress = False

# Ensure the CSV file exists with headers
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Time", "Patient", "SBP", "DBP", "Pulse"])


@app.route("/")
def home():
    return render_template("home.html")

@app.route("/receive", methods=["POST"])
def receive_data():
    try:
        data = request.get_json()
        print("Received JSON:", data)  # Debug print

        SBP = float(data.get("SBP", 0))
        DBP = float(data.get("DBP", 0))
        pulse = int(data.get("Pulse", 0))

        print(f"Parsed SBP: {SBP}, DBP: {DBP}, Pulse: {pulse}")  # Debug print

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

        # Save to CSV
        with open(DATA_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([date_str, time_str, SBP, DBP, pulse])

        print(f"Saved data at {timestamp}")  # Debug print
        return jsonify({"status": "success", "timestamp": timestamp}), 200

    except Exception as e:
        print(f"Error receiving data: {e}")  # Debug print
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route("/measure", methods=["GET", "POST"])
def measure():
    global measurement_in_progress

    message = None

    if request.method == "POST":
        with measurement_lock:
            if measurement_in_progress:
                message = "A measurement is already in progress. Please wait..."
                return render_template("measure.html", message=message)
            measurement_in_progress = True

        try:
            # Replace with your Arduino's actual IP and endpoint
            arduino_ip = "http://192.168.75.148/start"
            print(f"Starting new measurement - Sending GET to {arduino_ip}")
            r = requests.get(arduino_ip, timeout=120)

            if r.status_code == 200:
                arduino_data = r.json()
                # Check for low pressure status
                if arduino_data.get("status") == "low_pressure":
                    message = "Pressure too low. Please inflate the cuff and try again."
                    measurement_in_progress = False
                    return render_template("measure.html", message=message)
                
                if arduino_data.get("status") == "high_pressure":
                    message = "Pressure too high. Please desinflate the cuff and try again."
                    measurement_in_progress = False
                    return render_template("measure.html", message=message)

                pressure_data = arduino_data.get("pressure_data")
                if not pressure_data:
                    message = "Arduino response does not contain pressure data."
                    measurement_in_progress = False
                    return render_template("measure.html", message=message)

                # Analyze pressure data
                SBP, DBP, pulse, timestamp = Blood_Pressure(pressure_data)

                # Save measurement to CSV
                now = datetime.now()
                date_str = now.strftime("%Y-%m-%d")
                time_str = now.strftime("%H:%M:%S")
                patient_name = request.form.get("patient_name", "Unknown")

                with open(DATA_FILE, "a", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow([date_str, time_str, patient_name, SBP, DBP, pulse])

                measurement_in_progress = False

                # Redirect to result page
                return redirect(url_for("show_result", sbp=SBP, dbp=DBP, pulse=pulse, timestamp=timestamp))

            else:
                message = "Failed to communicate with Arduino. Please try again."
                measurement_in_progress = False
                return render_template("measure.html", message=message)

        except Exception as e:
            print(f"Error during measurement: {e}")
            message = "An error occurred during measurement. Please try again."
            measurement_in_progress = False
            return render_template("measure.html", message=message)

    return render_template("measure.html", message=message)

@app.route("/result")
def show_result():
    # Get parameters from URL
    sbp = request.args.get('sbp', type=float)
    dbp = request.args.get('dbp', type=float)
    pulse = request.args.get('pulse', type=int)
    timestamp = request.args.get('timestamp')
    
    return render_template("result.html", SBP=sbp, DBP=dbp, pulse=pulse, timestamp=timestamp)

@app.route("/calendar")
def calendar():
    measurements = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                event = {
                    "title": f"SBP: {row['SBP']} | DBP: {row['DBP']} | Pulse: {row['Pulse']}",
                    "start": f"{row['Date']}T{row['Time']}",
                    "extendedProps": {
                        "SBP": row['SBP'],
                        "DBP": row['DBP'],
                        "Pulse": row['Pulse'],
                        "Date": row['Date'],
                        "Time": row['Time']
                    }
                }
                measurements.append(event)

    return render_template("calendar.html", measurements=measurements)

@app.route("/analyze_pressure", methods=["POST"])
def analyze_pressure():
    print("Request received")

    try:
        data = request.get_json()
        print("JSON data parsed successfully")
    except Exception as e:
        print("Error parsing JSON:", e)
        return jsonify({"error": "Invalid JSON format"}), 400

    pressure_data = data.get("pressure_data")
    if not pressure_data:
        print("No pressure_data found in JSON")
        return jsonify({"error": "No pressure_data provided"}), 400

    print(f"Received pressure_data of length: {len(pressure_data)}")

    try:
        pressure_data = np.array(pressure_data)
        print("Converted pressure_data to NumPy array")

        SBP, DBP, pulse, timestamp = Blood_Pressure(pressure_data)
        print(f"SBP: {SBP}, DBP: {DBP}, Pulse: {pulse}, Time: {timestamp}")

        return jsonify({
            "SBP": SBP,
            "DBP": DBP,
            "Pulse": pulse,
            "timestamp": timestamp
        }), 200

    except Exception as e:
        print("Error during analysis:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/measurements", methods=["GET"])
def get_measurements():
    """API endpoint to get all measurements as JSON"""
    measurements = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    measurements.append({
                        "date": row['Date'],
                        "time": row['Time'],
                        "patient": row["Patient"],
                        "sbp": float(row['SBP']),
                        "dbp": float(row['DBP']),
                        "pulse": int(row['Pulse'])
                    })
            print(f"Found {len(measurements)} measurements in CSV")
        except Exception as e:
            print(f"Error reading measurements: {e}")
            return jsonify({"error": str(e)}), 500
    else:
        print("CSV file does not exist")
    
    return jsonify({"measurements": measurements})

@app.route("/api/monthly-averages", methods=["GET"])
def get_monthly_averages():
    """API endpoint to calculate monthly averages"""
    patient = request.args.get("patient", "")
    data = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if patient and row["Patient"] != patient:
                    continue
                data.append(row)
    # Group by month
    from collections import defaultdict
    import calendar
    monthly = defaultdict(list)
    for row in data:
        month = row["Date"][:7]  # YYYY-MM
        monthly[month].append(row)
    result = []
    for month, rows in sorted(monthly.items()):
        sbps = [float(r["SBP"]) for r in rows]
        dbps = [float(r["DBP"]) for r in rows]
        pulses = [int(r["Pulse"]) for r in rows]
        count = len(rows)
        year, m = month.split('-')
        month_name = f"{calendar.month_name[int(m)]} {year}"
        result.append({
            "month": month,
            "month_name": month_name,
            "avg_sbp": round(sum(sbps)/count, 1) if count else 0,
            "avg_dbp": round(sum(dbps)/count, 1) if count else 0,
            "avg_pulse": round(sum(pulses)/count, 1) if count else 0,
            "count": count
        })
    return jsonify({"monthly_averages": result})


@app.route("/api/daily-averages", methods=["GET"])
def daily_averages():
    """API endpoint to get daily averages for a period, with optional patient filter"""
    import datetime
    from collections import defaultdict

    patient = request.args.get("patient", "")
    period = request.args.get("period", "month")
    date_str = request.args.get("date", datetime.date.today().isoformat())
    try:
        base_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        base_date = datetime.date.today()

    # Determine date range
    if period == "week":
        start_date = base_date - datetime.timedelta(days=base_date.weekday())
        end_date = start_date + datetime.timedelta(days=6)
        period_name = "This Week"
    else:  # month
        start_date = base_date.replace(day=1)
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year+1, month=1, day=1) - datetime.timedelta(days=1)
        else:
            end_date = start_date.replace(month=start_date.month+1, day=1) - datetime.timedelta(days=1)
        period_name = "This Month"

    # Read and filter data
    data = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if patient and row["Patient"] != patient:
                    continue
                try:
                    row_date = datetime.datetime.strptime(row["Date"], "%Y-%m-%d").date()
                except Exception:
                    continue
                if start_date <= row_date <= end_date:
                    data.append(row)

    # Group by day
    daily = defaultdict(list)
    for row in data:
        daily[row["Date"]].append(row)

    # Prepare output for each day in range
    result = []
    for i in range((end_date - start_date).days + 1):
        day = start_date + datetime.timedelta(days=i)
        day_str = day.isoformat()
        rows = daily.get(day_str, [])
        count = len(rows)
        sbps = [float(r["SBP"]) for r in rows]
        dbps = [float(r["DBP"]) for r in rows]
        pulses = [int(r["Pulse"]) for r in rows]
        result.append({
            "date": day_str,
            "display_date": day.strftime("%d/%m"),
            "day_name": day.strftime("%A"),
            "avg_sbp": round(sum(sbps)/count, 1) if count else None,
            "avg_dbp": round(sum(dbps)/count, 1) if count else None,
            "avg_pulse": round(sum(pulses)/count, 1) if count else None,
            "count": count
        })
    return jsonify({"daily_averages": result, "period": period_name})

@app.route("/debug/csv")
def debug_csv():
    """Debug route to check what's in the CSV file"""
    if not os.path.exists(DATA_FILE):
        return f"CSV file {DATA_FILE} does not exist"
    
    try:
        with open(DATA_FILE, "r") as f:
            content = f.read()
            lines = content.split('\n')
            
        return f"""
        <h2>CSV File Debug Info</h2>
        <p><strong>File:</strong> {DATA_FILE}</p>
        <p><strong>File size:</strong> {os.path.getsize(DATA_FILE)} bytes</p>
        <p><strong>Number of lines:</strong> {len(lines)}</p>
        <p><strong>Content:</strong></p>
        <pre>{content}</pre>
        """
    except Exception as e:
        return f"Error reading CSV: {e}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)