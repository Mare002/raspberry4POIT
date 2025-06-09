from flask import Flask, render_template, request, redirect, url_for, jsonify
import threading
import serial
import MySQLdb
import time

app = Flask(__name__)

# Globalne premenne
ser = None
read_thread = None
running = False
serial_ready = False

# Pripojenie k databaze
db = MySQLdb.connect(
    host="localhost",
    user="mare",
    passwd="rasp4",
    db="teplota_db"
)
cursor = db.cursor()

#body 1,2,3,9,10

@app.route('/')
def index():
    return render_template('index.html', serial_ready=serial_ready, running=running)
#1
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
#3
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
#2
# Premenné na uloženie prahových hodnôt
solar_threshold = 25.0
boiler_threshold = 25.0

@app.route('/set_parameters', methods=['POST'])
def set_parameters():
    global solar_threshold, boiler_threshold

    try:
        solar_threshold = float(request.form['solar_threshold'])
        boiler_threshold = float(request.form['boiler_threshold'])
        print(f"Nove prahy nastavene: Solar={solar_threshold}, Boiler={boiler_threshold}")
        send_thresholds_to_arduino();
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
#9            
@app.route('/stop', methods=['POST'])
def stop_reading():
    global running
    if running:
        running = False
        print("Citanie zastavene.")
    else:
        print("Citanie uz je zastavene alebo sa este nezacalo.")
    return redirect(url_for('index'))
#10
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

                        sql = "INSERT INTO zaznamy (teplota1, teplota2, ventil1, ventil2) VALUES (%s, %s, %s, %s)"
                        cursor.execute(sql, (solar, boiler, valve1, valve2))
                        db.commit()
                        print("Data ulozene.")
                    except Exception as e:
                        print("Chyba pri parsovani alebo vkladani:", e)
                else:
                    print("Zly format dat")
            time.sleep(1)
        except Exception as e:
            print("Chyba pri citani:", e)

#body 4,5,6
#4
@app.route('/udaje')
def udaje():
    try:
        cursor.execute("SELECT cas, teplota1, teplota2, ventil1, ventil2 FROM zaznamy ORDER BY id DESC LIMIT 20")
        zaznamy = cursor.fetchall()
    except Exception as e:
        print("Chyba pri nacitani dat z databazy:", e)
        zaznamy = []
    return render_template('udaje.html', zaznamy=zaznamy)
#5
def get_teploty():
    try:
        conn = MySQLdb.connect(
            host="localhost",
            user="mare",
            passwd="rasp4",
            db="teplota_db"
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT cas, teplota1, teplota2 FROM zaznamy ORDER BY id DESC LIMIT 100")
            rows = list(cursor.fetchall())
            rows.reverse()
        conn.close()
        return rows
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
        conn = MySQLdb.connect(
            host="localhost",
            user="mare",
            passwd="rasp4",
            db="teplota_db"
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT cas, ventil1, ventil2 FROM zaznamy ORDER BY id DESC LIMIT 100")
            rows = list(cursor.fetchall())
            rows.reverse()
        conn.close()
        return rows
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
def databaza():
    return render_template('databaza.html')






if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)



