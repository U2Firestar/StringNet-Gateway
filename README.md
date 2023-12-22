![Works with Homie](https://github.com/U2Firestar/StringNet-Gateway/blob/main/assets/works-with-homie.png)

# StringNet-Gateway

**Features:** 
- GUI for bridging and setting up USB-StringNet-Devices using [StringNet-Firmware](https://github.com/U2Firestar/StringNet-Firmware).
- Translate between StringNet and MQTT / HomieV4
- - Homie (V4) - Support (backwards-compatible to HomieV3)
- Autostart - useful for long-term application
- Transmission-queues and echo-filtering

**Limitations:**
- One instance can handle ONE StringNet-Device
- Doesn't support addressing (compared to firmware)

**This project builds upon following librarys and therefor special thanks to:**
- [Pygubu (+Designer)](https://github.com/alejandroautalan/pygubu-designer) from alejandroautalan @ Github
- [Eclipse Paho™ MQTT Python Client](https://github.com/eclipse/paho.mqtt.python) from eclipse @ Github
- [homie4](https://github.com/mjcumming/Homie4) from mjcumming @ Github (--> [forked for app](https://github.com/U2Firestar/Homie4StringNet))

**Pre-requisites (eventually use "pip3" on raspberry):**
~~~~
pip install pygubu
~~~~
~~~~
pip install paho-mqtt
~~~~
~~~~
pip install git+https://github.com/U2Firestar/Homie4StringNet.git@master
~~~~
_Make sure to uninstall homie4 beforehand!_


About: Project for Bachelorthesis, originally supported by UAS Technikum Vienna and 3S-Sedlak

IDE: PyCharm

Python-Version: 3.10

Versions:
- 1.0.0 - 08.2021 - Hardcoded initial version
- 1.1.0 - 09.2021 - Adding UDP-support
- 2.0.0 - 04.2022 - Introducing dynamic objects solution, removing UDP-support, adding GUI
- 2.0.1 - 12.2022 - X-Server-bug workaround, beautify code
- 2.1.0 - 12.2022 - Fixing X-Server-bug by moving busviewer outputs to commandline
- 2.1.1 - 01.2023 - Adjusting discovery intervalls, beautify github
- 2.1.2+3 -  2023 - Outputs beautified
- 2.2.0 - 12.2023 - Libraries updated, README simplified