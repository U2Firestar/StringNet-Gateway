# GUI for Setup and Bridging of StringNet-Device
This part of the bachelor thesis project (MQTT/Homie-RF433-MHz-Bridge to remote power outlets) is the communcation node between and an MQTT-capable service or smart home system with Service for Homie-V4-convention. 
It's purpose is also to act as API and GUI to send requests and commands via StringNet (own protocoll over UART / USB).
Its' counterpart is [StringNet-RF-APIandGUI](https://github.com/U2Firestar/StringNet-RF-Gateway-Firmware )

Used IDE is: PyCharm Community Edition with Python 3.10

Features: 
- UI and API to setup and control the physically attached USB-Device
- Easily portable
- MQTT-bridge to generically translate between StringNet und MQTT 
-- Implemented transmission-queues and echo-filtering
-	HomieV4 – compatible bridge from and to StringNet
- Autostart - useful for long-term application

This project builds upon following librarys:
- [Pygubu-Designer](https://github.com/alejandroautalan/pygubu-designer) from alejandroautalan @ Github
- [Eclipse Paho™ MQTT Python Client](https://github.com/eclipse/paho.mqtt.python) from eclipse @ Github
- [homie4](https://github.com/mjcumming/Homie4) from mjcumming @ Github (modified)

Therefor special thanks!

Note: It's advised to install "homie" (v4) via pip to get all neccessary packages and then uninstall the package again as homie and Pygubu are already preinstalled in this project.

![Works with Homie](https://github.com/U2Firestar/StringNet-Gateway/blob/main/works-with-homie.png)
