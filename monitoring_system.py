from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, flash
from datetime import datetime
import threading
import serial
import MySQLdb
import time
import csv
import json
import io

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Globalne premenne
ser = None
read_thread = None
running = False
serial_ready = False

# Lock pre thread-safe databázové operácie
db_lock = threading.Lock()

# Database connection parameters
DB_CONFIG = {
    'host': "localhost",
    'user': "mare",
    'passwd': "rasp4",
    'db': "teplota_db"
}

def get_db_connection():
    """Vytvorí novú databázovú konexiu pre každý thread"""
    return MySQLdb.connect(**DB_CONFIG)

def execute_db_query(query, params=None, fetch_one=False, fetch_all=False):
    """Thread-safe spôsob vykonania databázového dotazu"""
    with db_lock:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            if fetch_one:
                result = cursor.fetchone()
            elif fetch_all:
                result = cursor.fetchall()
            else:
                result = None
                
            conn.commit()
            cursor.close()
            conn.close()
            return result
        except Exception as e:
            print(f"Database error: {e}")
            raise e

# Premenné na uloženie prahových hodnôt
solar_threshold = 25.0
boiler_threshold = 25.0

@app.route('/')
@app.route('/domov')
def index():
    return render_template('domov.html', serial_ready=serial_ready, running=running)

@app.route('/open', methods=['POST'])
def open_connection():
    global ser, serial_ready

    if not serial_ready:
        try:
            ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
            serial_ready = True
            print("Serial port otvoreny.")
        except Exception as e:
            print("Chyba pri otvarani serial portu:", e)
    else:
        print("Serial port uz je otvoreny.")
    
    return redirect(url_for('index'))

@app.route('/start', methods=['POST'])
def start_reading():
    global running, read_thread

    if serial_ready and not running:
        running = True
        read_thread = threading.Thread(target=read_serial)
        read_thread.start()
        print("Citanie spustene.")
    else:
        print("Serial port nie je pripraveny alebo uz bezi.")
    
    return redirect(url_for('index'))

@app.route('/set_parameters', methods=['POST'])
def set_parameters():
    global solar_threshold, boiler_threshold

    try:
        solar_threshold = float(request.form['solar_threshold'])
        boiler_threshold = float(request.form['boiler_threshold'])
        print(f"Nove prahy nastavene: Solar={solar_threshold}, Boiler={boiler_threshold}")
        send_thresholds_to_arduino()
    except Exception as e:
        print("Chyba pri nastavovani parametrov:", e)
    
    return redirect(url_for('index'))

def send_thresholds_to_arduino():
    if ser:
        try:
            command = f"SET,{solar_threshold},{boiler_threshold}\n"
            ser.write(command.encode('utf-8'))
            print("Prahy poslane do Arduino:", command)
        except Exception as e:
            print("Chyba pri posielani prahov:", e)

@app.route('/stop', methods=['POST'])
def stop_reading():
    global running
    if running:
        running = False
        print("Citanie zastavene.")
    else:
        print("Citanie uz je zastavene alebo sa este nezacalo.")
    return redirect(url_for('index'))

@app.route('/close', methods=['POST'])
def close_connection():
    global running, ser, serial_ready
    running = False
    serial_ready = False
    if ser:
        ser.close()
        ser = None
        print("Serial port zatvoreny.")
    return redirect(url_for('index'))
    
def read_serial():
    global running
    while running:
        try:
            line = ser.readline().decode('utf-8').strip()
            if line:
                print("Z Arduino:", line)
                parts = line.split(',')
                if len(parts) == 4:
                    try:
                        solar = float(parts[0])
                        boiler = float(parts[1])
                        valve1 = int(parts[2])
                        valve2 = int(parts[3])

                        query = "INSERT INTO zaznamy (teplota1, teplota2, ventil1, ventil2) VALUES (%s, %s, %s, %s)"
                        execute_db_query(query, (solar, boiler, valve1, valve2))
                        print("Data ulozene.")
                    except Exception as e:
                        print("Chyba pri parsovani alebo vkladani:", e)
                else:
                    print("Zly format dat")
            time.sleep(1)
        except Exception as e:
            print("Chyba pri citani:", e)

@app.route('/udaje')
@app.route('/realtime_data')
def udaje():
    try:
        query = "SELECT cas, teplota1, teplota2, ventil1, ventil2 FROM zaznamy ORDER BY id DESC LIMIT 20"
        zaznamy = execute_db_query(query, fetch_all=True)
        if zaznamy is None:
            zaznamy = []
    except Exception as e:
        print("Chyba pri nacitani dat z databazy:", e)
        zaznamy = []
    return render_template('realtime_data.html', zaznamy=zaznamy)

def get_teploty():
    try:
        query = "SELECT cas, teplota1, teplota2 FROM zaznamy ORDER BY id DESC LIMIT 100"
        rows = execute_db_query(query, fetch_all=True)
        if rows:
            rows = list(rows)
            rows.reverse()
            return rows
        return []
    except Exception as e:
        print("Chyba v get_teploty:", e)
        return []

@app.route('/api/teploty')
def api_teploty():
    try:
        rows = get_teploty()
        data = {
            "labels": [row[0].strftime('%H:%M:%S') for row in rows],
            "teplota1": [float(row[1]) for row in rows],
            "teplota2": [float(row[2]) for row in rows]
        }
        return jsonify(data)
    except Exception as e:
        print("Chyba pri nacitani dat pre graf:", e)
        return jsonify({})
        
def get_ventily():
    try:
        query = "SELECT cas, ventil1, ventil2 FROM zaznamy ORDER BY id DESC LIMIT 100"
        rows = execute_db_query(query, fetch_all=True)
        if rows:
            rows = list(rows)
            rows.reverse()
            return rows
        return []
    except Exception as e:
        print("Chyba v get_ventily:", e)
        return []

@app.route('/api/ventily')
def api_ventily():
    try:
        rows = get_ventily()
        data = {
            "labels": [row[0].strftime('%H:%M:%S') for row in rows],
            "ventil1": [int(row[1]) for row in rows],
            "ventil2": [int(row[2]) for row in rows]
        }
        return jsonify(data)
    except Exception as e:
        print("Chyba pri načítaní dát pre ventilový graf:", e)
        return jsonify({})

@app.route('/databaza')
@app.route('/data_archive')
def databaza():
    return render_template('data_archive.html')

def get_data_for_date(datum):
    try:
        start = datetime.strptime(datum, "%Y-%m-%d")
        end = start.replace(hour=23, minute=59, second=59)

        query = """
            SELECT cas, teplota1, teplota2, ventil1, ventil2
            FROM zaznamy
            WHERE cas BETWEEN %s AND %s
            ORDER BY cas
        """
        rows = execute_db_query(query, (start, end), fetch_all=True)
        
        if rows:
            return [{
                'cas': row[0].strftime('%H:%M:%S'),
                't1': float(row[1]),
                't2': float(row[2]),
                'v1': int(row[3]),
                'v2': int(row[4])
            } for row in rows]
        return []

    except Exception as e:
        print("Chyba v get_data_for_date:", e)
        return []

def get_data_for_range(start_str, end_str):
    try:
        start = datetime.strptime(start_str, "%Y-%m-%d")
        end = datetime.strptime(end_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59)

        query = """
            SELECT cas, teplota1, teplota2, ventil1, ventil2
            FROM zaznamy
            WHERE cas BETWEEN %s AND %s
            ORDER BY cas
        """
        rows = execute_db_query(query, (start, end), fetch_all=True)
        
        if rows:
            return [{
                'cas': row[0].strftime('%H:%M:%S'),
                't1': float(row[1]),
                't2': float(row[2]),
                'v1': int(row[3]),
                'v2': int(row[4])
            } for row in rows]
        return []

    except Exception as e:
        print("Chyba v get_data_for_range:", e)
        return []

@app.route('/data')
def data():
    datum = request.args.get('datum')
    
    if not datum:
        return jsonify({'error': 'Chýba parameter datum'}), 400
    
    try:
        zaznamy = get_data_for_date(datum)
        
        labels = [z['cas'] for z in zaznamy]
        teplota1 = [z['t1'] for z in zaznamy]
        teplota2 = [z['t2'] for z in zaznamy]
        ventil1 = [z['v1'] for z in zaznamy]
        ventil2 = [z['v2'] for z in zaznamy]

        return jsonify({
            'zaznamy': zaznamy,
            'labels': labels,
            'teplota1': teplota1,
            'teplota2': teplota2,
            'ventil1': ventil1,
            'ventil2': ventil2
        })
    except Exception as e:
        print("Chyba pri načítaní dát:", e)
        return jsonify({'error': 'Chyba pri načítaní dát'}), 500
        
@app.route('/data_range')
def data_range():
    start = request.args.get('start')
    end = request.args.get('end')

    if not start or not end:
        return jsonify({'error': 'Chýbajú parametre start alebo end'}), 400
    
    try:
        zaznamy = get_data_for_range(start, end)
        
        labels = [z['cas'] for z in zaznamy]
        teplota1 = [z['t1'] for z in zaznamy]
        teplota2 = [z['t2'] for z in zaznamy]
        ventil1 = [z['v1'] for z in zaznamy]
        ventil2 = [z['v2'] for z in zaznamy]

        return jsonify({
            'zaznamy': zaznamy,
            'labels': labels,
            'teplota1': teplota1,
            'teplota2': teplota2,
            'ventil1': ventil1,
            'ventil2': ventil2
        })
    except Exception as e:
        print("Chyba pri načítaní dát:", e)
        return jsonify({'error': 'Chyba pri načítaní dát'}), 500

@app.route('/api/current_values')
def api_current_values():
    try:
        query = """
            SELECT teplota1, teplota2, ventil1, ventil2, cas 
            FROM zaznamy 
            ORDER BY id DESC LIMIT 1
        """
        row = execute_db_query(query, fetch_one=True)
        
        if row:
            return jsonify({
                'teplota1': float(row[0]),
                'teplota2': float(row[1]),
                'ventil1': int(row[2]),
                'ventil2': int(row[3]),
                'cas': row[4].strftime('%H:%M:%S'),
                'timestamp': row[4].isoformat()
            })
        else:
            return jsonify({
                'teplota1': 0,
                'teplota2': 0,
                'ventil1': 0,
                'ventil2': 0,
                'cas': '00:00:00',
                'timestamp': datetime.now().isoformat()
            })
            
    except Exception as e:
        print("Chyba pri získavaní aktuálnych hodnôt:", e)
        return jsonify({'error': 'Chyba pri načítaní dát'}), 500

@app.route('/api/recent_records')
def api_recent_records():
    try:
        query = """
            SELECT cas, teplota1, teplota2, ventil1, ventil2 
            FROM zaznamy 
            ORDER BY id DESC 
            LIMIT 20
        """
        rows = execute_db_query(query, fetch_all=True)
        
        records = []
        if rows:
            for row in rows:
                records.append({
                    'cas': row[0].strftime('%H:%M:%S'),
                    'teplota1': float(row[1]),
                    'teplota2': float(row[2]),
                    'ventil1': int(row[3]),
                    'ventil2': int(row[4])
                })
        
        return jsonify(records)
        
    except Exception as e:
        print("Chyba pri načítaní najnovších záznamov:", e)
        return jsonify({'error': 'Chyba pri načítaní dát'}), 500

@app.route('/export_csv')
def export_csv():
    datum = request.args.get('datum')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    try:
        if datum:
            zaznamy = get_data_for_date(datum)
            filename_date = datum
        elif start_date and end_date:
            zaznamy = get_data_for_range(start_date, end_date)
            filename_date = f"{start_date}_to_{end_date}"
        else:
            return "Chýbajú parametre", 400
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Cas', 'Teplota1', 'Teplota2', 'Ventil1', 'Ventil2'])
        
        for zaznam in zaznamy:
            writer.writerow([
                zaznam['cas'],
                zaznam['t1'],
                zaznam['t2'],
                zaznam['v1'],
                zaznam['v2']
            ])
        
        mem = io.BytesIO()
        mem.write(output.getvalue().encode('utf-8'))
        mem.seek(0)
        output.close()
        
        filename = f"teploty_{filename_date}.csv"
        
        return send_file(
            mem,
            as_attachment=True,
            download_name=filename,
            mimetype='text/csv'
        )
        
    except Exception as e:
        print("Chyba pri exporte CSV:", e)
        return f"Chyba pri exporte: {str(e)}", 500

@app.route('/export_json')
def export_json():
    datum = request.args.get('datum')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    try:
        if datum:
            zaznamy = get_data_for_date(datum)
            filename_date = datum
        elif start_date and end_date:
            zaznamy = get_data_for_range(start_date, end_date)
            filename_date = f"{start_date}_to_{end_date}"
        else:
            return "Chýbajú parametre", 400
        
        data = {
            "export_time": datetime.now().isoformat(),
            "export_date_range": filename_date,
            "records_count": len(zaznamy),
            "data": zaznamy
        }
        
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        mem = io.BytesIO()
        mem.write(json_str.encode('utf-8'))
        mem.seek(0)
        
        filename = f"teploty_{filename_date}.json"
        
        return send_file(
            mem,
            as_attachment=True,
            download_name=filename,
            mimetype='application/json'
        )
        
    except Exception as e:
        print("Chyba pri exporte JSON:", e)
        return f"Chyba pri exporte: {str(e)}", 500

@app.route('/import_csv', methods=['POST'])
def import_csv():
    if 'file' not in request.files:
        flash('Nebol vybratý súbor')
        return redirect(url_for('databaza'))
    
    file = request.files['file']
    if file.filename == '':
        flash('Nebol vybratý súbor')
        return redirect(url_for('databaza'))
    
    if file and file.filename.endswith('.csv'):
        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_input = csv.reader(stream)
            
            next(csv_input)  # Skip header
            
            imported_count = 0
            for row in csv_input:
                if len(row) >= 5:
                    cas_str = row[0]
                    if len(cas_str) <= 8:
                        today = datetime.now().strftime('%Y-%m-%d')
                        cas = datetime.strptime(f"{today} {cas_str}", '%Y-%m-%d %H:%M:%S')
                    else:
                        cas = datetime.strptime(cas_str, '%Y-%m-%d %H:%M:%S')
                    
                    teplota1 = float(row[1])
                    teplota2 = float(row[2])
                    ventil1 = 1 if str(row[3]).lower() in ['1', 'true', 'zapnuté', 'zapnute'] else 0
                    ventil2 = 1 if str(row[4]).lower() in ['1', 'true', 'zapnuté', 'zapnute'] else 0
                    
                    query = """
                        INSERT INTO zaznamy (cas, teplota1, teplota2, ventil1, ventil2) 
                        VALUES (%s, %s, %s, %s, %s)
                    """
                    execute_db_query(query, (cas, teplota1, teplota2, ventil1, ventil2))
                    imported_count += 1
            
            flash(f'Úspešne importované {imported_count} záznamov')
            
        except Exception as e:
            print("Chyba pri importe CSV:", e)
            flash(f'Chyba pri importe: {str(e)}')
    else:
        flash('Podporované sú iba CSV súbory')
    
    return redirect(url_for('databaza'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
