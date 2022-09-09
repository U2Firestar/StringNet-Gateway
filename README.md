# StringNet-RF-APIandGUI
This part of the bachelor thesis project (MQTT/Homie-RF433-MHz-Bridge to remote power outlets) is the communcation node between https://github.com/U2Firestar/StringNet-RF-Gateway-Firmware and an MQTT-capable service or smart home system with Service for Homie-V4-convention. 
It's purpose is also to act as API and GUI to send requests and commands via StringNet (own protocoll over UART / USB).

Used IDE is: PyCharm Community Edition with Python 3.10

Features: 
- UI and API to setup and control the physically attached USB-Device
- Easily portable
- MQTT-bridge to generically translate between StringNet und MQTT 
-- Implemented transmission-queues and echo-filtering
-	HomieV4 – compatible bridge from and to StringNet

This project builds upon following librarys:
- Pygubu-Designer from alejandroautalan @ Github: https://github.com/alejandroautalan/pygubu-designer
- Eclipse Paho™ MQTT Python Client from eclipse @ Github: https://github.com/eclipse/paho.mqtt.python
- homie4 from mjcumming @ Github: https://github.com/mjcumming/Homie4

Therefor special thanks!
