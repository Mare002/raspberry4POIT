import serial
import MySQLdb

# Pripojenie k databaze
db = MySQLdb.connect(
    host="localhost",
    user="mare",
    passwd="rasp4",
    db="teplota_db"
)
cursor = db.cursor()

# Otvorenie serial portu
ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)

try:
    while True:
        line = ser.readline().decode('utf-8').strip()
        if line:
            print("Received from Arduino:", line)

            # Rozdelime hodnoty podla ciarky
            parts = line.split(',')
            if len(parts) == 4:
                try:
                    solar = float(parts[0])
                    boiler = float(parts[1])
                    valve1 = int(parts[2])
                    valve2 = int(parts[3])

                    # SQL prikaz na vlozenie dat
                    sql = "INSERT INTO zaznamy (teplota1, teplota2, ventil1, ventil2) VALUES (%s, %s, %s, %s)"
                    cursor.execute(sql, (solar, boiler, valve1, valve2))
                    db.commit()
                    print("Data inserted into DB")
                except Exception as e:
                    print("Chyba pri parsovani alebo vkladani do DB:", e)
            else:
                print("Nespravny format dat")

except KeyboardInterrupt:
    print("Ukoncenie citania.")
finally:
    ser.close()
    cursor.close()
    db.close()
