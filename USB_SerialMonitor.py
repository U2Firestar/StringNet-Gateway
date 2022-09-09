# Softwarename: USB (UART) - Serial Monitor
import traceback

import serial

## Öffnen der Ethernet-Schnittstelle
device = serial.Serial(
    port="COM7",
    baudrate=115200,
    timeout=.1  # der µC hat 50ms Zeit zum Antworten
)

## Main
while True:
    try:
        line = device.readline().decode("UTF-8")
        if len(line) > 1:
            workBuffer = line
            print(line)  # debug
    except:
        traceback.print_exc()
