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
    
    if request.method == "POST":
        # Check if a measurement is already in progress
        with measurement_lock:
            if measurement_in_progress:
                print("Measurement already in progress - ignoring duplicate request")
                return "A measurement is already in progress. Please wait..."
            
            # Set the flag to indicate measurement is starting
            measurement_in_progress = True
        
        try:
            
            arduino_ip = "http://192.168.75.148/start"
            print(f"Starting new measurement - Sending GET to {arduino_ip}")
            r = requests.get(arduino_ip, timeout=120)

            if r.status_code == 200:
                arduino_data = r.json()
                pressure_data = arduino_data.get("pressure_data")

                if not pressure_data:
                    return "Arduino response does not contain pressure data."

                print(f"Received complete pressure data with {len(pressure_data)} samples")

                # Call internal /analyze_pressure API
                analysis_url = "http://localhost:5000/analyze_pressure"
                analysis_response = requests.post(analysis_url, json={"pressure_data": pressure_data})

                if analysis_response.status_code == 200:
                    result = analysis_response.json()
                    SBP = result["SBP"]
                    DBP = result["DBP"]
                    pulse = result["Pulse"]
                    timestamp = result["timestamp"]

                    # Save to CSV - only once per measurement
                    now = datetime.now()
                    date_str = now.strftime("%Y-%m-%d")
                    time_str = now.strftime("%H:%M:%S")
                    with open(DATA_FILE, "a", newline="") as f:
                        writer = csv.writer(f)
                        writer.writerow([date_str, time_str, SBP, DBP, pulse])

                    print(f"Measurement completed and saved: SBP={SBP}, DBP={DBP}, Pulse={pulse}")
                    
                    # Redirect to prevent duplicate submissions on refresh
                    return redirect(url_for('show_result', sbp=SBP, dbp=DBP, pulse=pulse, timestamp=timestamp))
                else:
                    return f"Error analyzing pressure data: {analysis_response.text}"

            else:
                return f"Failed to trigger Arduino: {r.text}"
                
        except Exception as e:
            print(f"Error contacting Arduino: {e}")
            return f"Error contacting Arduino: {e}"
        
        finally:
            # Always reset the flag when measurement is done (success or failure)
            with measurement_lock:
                measurement_in_progress = False
                print("Measurement flag reset - ready for next measurement")

    return render_template("measure.html")

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
    if not os.path.exists(DATA_FILE):
        return jsonify({"error": "No data file found"}), 404
    
    monthly_data = defaultdict(list)
    
    try:
        with open(DATA_FILE, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Parse date and extract year-month
                date_obj = datetime.strptime(row['Date'], '%Y-%m-%d')
                month_key = date_obj.strftime('%Y-%m')  # Format: 2024-01
                
                monthly_data[month_key].append({
                    'sbp': float(row['SBP']),
                    'dbp': float(row['DBP']),
                    'pulse': int(row['Pulse'])
                })
        
        # Calculate averages for each month
        monthly_averages = []
        for month, readings in monthly_data.items():
            if readings:  # Only process if there are readings
                avg_sbp = sum(r['sbp'] for r in readings) / len(readings)
                avg_dbp = sum(r['dbp'] for r in readings) / len(readings)
                avg_pulse = sum(r['pulse'] for r in readings) / len(readings)
                
                monthly_averages.append({
                    'month': month,
                    'month_name': datetime.strptime(month, '%Y-%m').strftime('%B %Y'),
                    'avg_sbp': round(avg_sbp, 1),
                    'avg_dbp': round(avg_dbp, 1),
                    'avg_pulse': round(avg_pulse, 1),
                    'count': len(readings)
                })
        
        # Sort by month (newest first)
        monthly_averages.sort(key=lambda x: x['month'], reverse=True)
        
        print(f"Calculated averages for {len(monthly_averages)} months")
        return jsonify({"monthly_averages": monthly_averages})
        
    except Exception as e:
        print(f"Error calculating monthly averages: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/daily-averages", methods=["GET"])
def get_daily_averages():
    """API endpoint to get daily averages for a specific period"""
    if not os.path.exists(DATA_FILE):
        return jsonify({"error": "No data file found"}), 404
    
    period = request.args.get('period', 'month')  # 'week' or 'month'
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))  # specific date to center on
    
    try:
        # Parse the reference date
        ref_date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Calculate date range based on period
        if period == 'week':
            # Get start of week (Monday)
            start_date = ref_date - timedelta(days=ref_date.weekday())
            end_date = start_date + timedelta(days=6)
        else:  # month
            # Get start and end of month
            start_date = ref_date.replace(day=1)
            if ref_date.month == 12:
                end_date = start_date.replace(year=ref_date.year + 1, month=1) - timedelta(days=1)
            else:
                end_date = start_date.replace(month=ref_date.month + 1) - timedelta(days=1)
        
        # Read measurements and group by date
        daily_data = defaultdict(list)
        
        with open(DATA_FILE, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                measurement_date = datetime.strptime(row['Date'], '%Y-%m-%d')
                
                # Only include measurements within the date range
                if start_date <= measurement_date <= end_date:
                    daily_data[row['Date']].append({
                        'sbp': float(row['SBP']),
                        'dbp': float(row['DBP']),
                        'pulse': int(row['Pulse']),
                        'time': row['Time']
                    })
        
        # Calculate daily averages
        daily_averages = []
        current_date = start_date
        
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            day_name = current_date.strftime('%A')
            
            if date_str in daily_data:
                readings = daily_data[date_str]
                avg_sbp = sum(r['sbp'] for r in readings) / len(readings)
                avg_dbp = sum(r['dbp'] for r in readings) / len(readings)
                avg_pulse = sum(r['pulse'] for r in readings) / len(readings)
                
                daily_averages.append({
                    'date': date_str,
                    'day_name': day_name,
                    'display_date': current_date.strftime('%m/%d'),
                    'avg_sbp': round(avg_sbp, 1),
                    'avg_dbp': round(avg_dbp, 1),
                    'avg_pulse': round(avg_pulse, 1),
                    'count': len(readings),
                    'readings': readings
                })
            else:
                # Include days with no readings for complete timeline
                daily_averages.append({
                    'date': date_str,
                    'day_name': day_name,
                    'display_date': current_date.strftime('%m/%d'),
                    'avg_sbp': None,
                    'avg_dbp': None,
                    'avg_pulse': None,
                    'count': 0,
                    'readings': []
                })
            
            current_date += timedelta(days=1)
        
        period_name = f"{start_date.strftime('%B %d')} - {end_date.strftime('%B %d, %Y')}"
        
        return jsonify({
            "daily_averages": daily_averages,
            "period": period,
            "period_name": period_name,
            "start_date": start_date.strftime('%Y-%m-%d'),
            "end_date": end_date.strftime('%Y-%m-%d')
        })
        
    except Exception as e:
        print(f"Error calculating daily averages: {e}")
        return jsonify({"error": str(e)}), 500

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