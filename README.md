![Works with Homie](https://homieiot.github.io/img/homie-logo.png)

# StringNet-Gateway

**Features:** 
- CLI for bridging and setting up USB-StringNet-Devices, which are using [StringNet-Firmware](https://github.com/U2Firestar/StringNet-Firmware).
- Translates between StringNet and MQTT
- - Addition Homie (V4) - Support (backwards-compatible to HomieV3)
- Autostart - useful for long-term application
- Transmission-queues and echo-filtering

**Limitations:**
- One bridge-instance can handle and connect ONE StringNet-Device
- Doesn't support addressing (compared to firmware)
- Communication is Y-wise, so: MQTT (Generic / Homie) <-> USB
- Config must be done in settings.json (no more GUI), which gets generated at first start during a prompt.

**This project builds upon following librarys and therefor special thanks to:**
- Pyserial
- ([Pygubu (+Designer)](https://github.com/alejandroautalan/pygubu-designer) from alejandroautalan @ Github)
- [Eclipse Paho™ MQTT Python Client](https://github.com/eclipse/paho.mqtt.python) from eclipse @ Github
- [Homie4](https://github.com/mjcumming/Homie4) from mjcumming @ Github

**Pre-requisites:**
~~~~
pip install pyserial pygubu paho-mqtt Homie4
~~~~
Note: Use "pip3" on raspberry pi, and recommendedly run this in a venv.

About: Project for Bachelorthesis ("How can classic remote outlets can be connected to openHAB?"), originally supported by UAS Technikum Vienna and 3S-Sedlak

IDE: PyCharm 2024.1.7

Python-Version: 3.12

Versions:
- 1.0.0 - 08.2021 - Hardcoded initial version
- 1.1.0 - 09.2021 - Adding UDP-support
- 2.0.0 - 04.2022 - Introducing dynamic objects solution, removing UDP-support, adding GUI
- 2.0.1 - 12.2022 - X-Server-bug workaround, beautify code
- 2.1.0 - 12.2022 - Fixing X-Server-bug by moving busviewer outputs to commandline
- 2.1.1 - 01.2023 - Adjusting discovery intervalls, beautify github
- 2.1.2+3 -  2023 - Outputs beautified
- 2.2.0 - 12.2023 - Libraries updated + correctly handled, README corrected, files moved, GUI updated
- 3.0.0	- 04.2025 - GUI dropped, connection losses handling improved, split to configurable CLI-subprogramms