# GUI for Setup and Bridging of StringNet-Device
This part of the bachelor thesis project (RF-Bridge between a Smart Home and remote power outlets, over MQTT/Homie) is the communcation node for MQTT-capable service like a smart home system supporting the Homie-V4-convention. It's purpose is provice a GUI for seting up and bridging requests / commands to a StringNet (own protocoll over UART / USB) - Device.
Its' counterpart is [StringNet-Firmware](https://github.com/U2Firestar/StringNet-Firmware).

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
-- pygubu
-- pygubu-designer
- [homie4](https://github.com/mjcumming/Homie4) from mjcumming @ Github (modified)
-- netifaces (within homie)
-- [Eclipse Paho™ MQTT Python Client](https://github.com/eclipse/paho.mqtt.python) from eclipse @ Github

Therefor special thanks!

Note: It's advised to install "homie" (v4) via pip to get all neccessary packages and then (only) uninstall "homie" again as it and Pygubu are locally within modified(!) in this project.

To install on Raspberry:
	<YOUR_MAINPATH> = /home/pi/Desktop/StringNet-Gateway ... keep attention to eventually necessary quotation marks
	
	=> Command for etc/rc.local
		sudo -H -u pi lxterminal -e "python3 <YOUR_MAINPATH>" &

	=> For eventuall crashes do a restarting run.sh with
		while true; do python3 <YOUR_MAINPATH>/mainapp.py; sleep 5; done	

![Works with Homie](https://github.com/U2Firestar/StringNet-Gateway/blob/main/works-with-homie.png)
