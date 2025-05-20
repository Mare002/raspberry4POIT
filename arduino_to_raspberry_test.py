import serial

ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)

try:
    while True:
        line = ser.readline().decode('utf-8').strip()
        if line:
            print("Received from Arduino:", line)
except KeyboardInterrupt:
    print("Ukoncenie citania.")
finally:
    ser.close()
