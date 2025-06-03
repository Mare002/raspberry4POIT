from flask import Flask, render_template, request, redirect, url_for
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

@app.route('/')
def index():
    return render_template('index.html', serial_ready=serial_ready, running=running)

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
