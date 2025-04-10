## Special thanks and credits to:
# - Pyserial
# - Eclipse Paho™ MQTT Python Client from eclipse @ Github: https://github.com/eclipse/paho.mqtt.python
# - Homie4 from mjcumming @ Github: https://github.com/mjcumming/Homie4

aboutprogramm_bridge = "-----------\n\
Software: StringNet-Gateway\n\
Purpose: Serial bridging between StringNet and MQTT\n\
Version: 3.0.0 05.04.2025\n\
Author: Emil Sedlacek (U2Firestar, Firestar)\n\
Originally supported by: UAS Technikum Vienna and 3S-Sedlak\n\
Note: See README and source-Files of firmware for more info!\n\
Make options in settings file!\n\
-----------\
"

aboutprogramm_programmer = "-----------\n\
Software: StringNet-programmer\n\
Purpose: Interactive programmer for StringNet device\n\
Version: 3.0.0 05.04.2025\n\
Author: Emil Sedlacek (U2Firestar, Firestar)\n\
Originally supported by: UAS Technikum Vienna and 3S-Sedlak\n\
Note: See README and source-Files of firmware for more info!\n\
Make options in settings file!\n\
-----------\
"

## Imports
# SYSTEM
import serial

# Dataformat
import time
import json

# LOGGING
import traceback
import logging

logger = logging.getLogger(__name__)  # SET for getting HOMIE too

logging.basicConfig(
    level=logging.INFO,
    format='[ %(filename)s:%(lineno)s in %(funcName)s() @ %(asctime)s ] %(message)s',
    datefmt='%m/%d/%Y %I:%M:%S %p'
)

# MQTT / HOMIE
import paho.mqtt.client as mqtt

from homie.device_switch import Device_Switch
from homie.node.node_switch import Node_Switch

## StringNet Functions and Definitions
GLOBAL_USB_SEND_QUERY = []  # Needed between MainApp & Homie-Implementation - Buffers all StringNet-packages that shall be sent

# Commands which get filtered both ways as they are systemcommands, so "STATUS" is not included
COMMANDS = ["FORMAT", "LIFESIGN", "NETMODE", "DISCOVER", "CREATE", "DELETE", "NAME", "PIN", "TYPE",
            "ONSEQUENCE", "OFFSEQUENCE", "PROTOCOLL", "PULSLENGTH", "RF_TX_REP"]
SUBCOMMANDS = ["TELLALL", "TELLDEV", "TELLGPIO", "TELLRF", "SETDEV", "SETGPIO", "SETRF"]
STN_STATES = ["ON", "SilentON", "OFF", "SilentOFF", "TOGGLE", "SilentTOGGLE", "STATUS"]  # Standard Name States


# Generic Objects and Classes for StringNet-Data-Processing
class StringNetObject:
    def __init__(self, Dev, InfoObject, Valstr, Valnum):
        self.Dev = Dev
        self.InfoObject = InfoObject
        self.Val_str = Valstr
        self.Val_num = Valnum


class StringNetPackage:
    def __init__(self, COM, SUBCOM, Val_num, Val_str):
        self.Com = COM
        self.Subcom = SUBCOM
        self.Val_num = Val_num
        self.Val_str = Val_str


# Extraction and check of StringNetPackage
def checkAndExtractStNPackage(line):
    # Validity-Check + check whether bridge should react # {LIGHT1;ON}
    if isinstance(line, str) and len(line) > len("{;}") and '{' in line and ';' in line and '}' in line:
        # Consistency-check
        tmp = ['{', ';', '}']
        x = -1  # Position start with 0

        for char in tmp:
            position = line.find(char)
            if position == -1 or position <= x:  # if there is none of those characters or the order is wrong
                return None
            else:
                x = position
        return line[line.find("{"): line.find("}") + 1]  # Extract StringNetpackage
    else:
        return None


def convert2StNPackage(line):
    # Split String into useful format
    line = line.replace("{", "")
    line = line.replace("}", "")
    stringNetPackage = line.split(';')

    # Prepair for separation
    i = 1
    command = ""
    subcommand = ""
    Val_num = 0  # Standard Error-Num
    Val_str = ""

    # Iterate through all Objects of given one Package and extact value
    for object in stringNetPackage:
        if i == 1:
            command = object
        elif i == 2:
            subcommand = object
        elif i == 3:
            if len(object) > 0:
                Val_num = int(object)
        elif i == 4:
            Val_str = object
        elif i >= 5:
            logger.error("Too many objects in StringNetPackage!")
            break
        i = i + 1

    logger.debug(StringNetPackage(command, subcommand, Val_num, Val_str))
    logger.debug(len(stringNetPackage))

    return StringNetPackage(command, subcommand, Val_num, Val_str)


# Globally needed StringNet-Package Wrapper
def convert2sendablePackage(COM, SUBCOM, VAL_NUM, VAL_STR):
    return "{" + str(COM) + ";" + str(SUBCOM) + ";" + str(VAL_NUM) + ";" + str(VAL_STR) + "}"


# Helper for String-Conversion of Booleans
def convertBool2String(self, boolVal):
    if boolVal == "false" or boolVal == False:
        return "OFF"
    elif boolVal == "true" or boolVal == True:
        return "ON"
    else:
        return "NaN"


## MQTT-based Network-Objects and Functions
# Threaded subcribe-Event for generic-mqtt. Filters and conditionally Buffers to USB-TX-Query
def genericMQTT_on_message(client, userdata, message):
    global GLOBAL_USB_SEND_QUERY
    logger.debug("Incomming Generic-MQTT-Topic: " + message.topic + " with message: ",
                 str(message.payload.decode("utf-8")))

    # Filter for Echos between MQTT-Server <- Bridge -> Arduino
    if "/STATUS" in message.topic:
        logger.warning("Ignored: " + str(message.topic) + " and message: " + str(message.payload.decode("utf-8")))
        return

    # convert MQTT-Strcuture to Stringnet:  root/xyz payload  --> {xyz;payload}
    workBuffer = message.topic.split('/')
    i = 1
    command = ""
    for object in workBuffer:
        if i == 1:
            pass  # not further interesting - contains root
        elif i == 2:
            command = object  # contains xyz
        # Check if the positions are correct: If there are postions after - they are ignored!
        elif i >= 3:
            logger.warning("Too many objects in workBuffer as StringNetPackage!")
            break
        i = i + 1

    # Wrapp the Package
    workBuffer = convert2sendablePackage(command, message.payload.decode("utf-8"), "", "")

    # Eliminate double-sending
    if workBuffer not in GLOBAL_USB_SEND_QUERY:
        GLOBAL_USB_SEND_QUERY.append(workBuffer)
        logger.info("Querying: " + str(workBuffer))


# Wrapper to match Homie-Librarys Needs
def nicefy2HomieID(string):
    # Follow Homie-Conventions
    forbidden = "!:;',@#/_$ "

    string = string.lower()
    for char in forbidden:
        string = string.replace(char, "")

    return string


## Modifcations in HOMIEV4-Implementation
class STN_Device_Switch(Device_Switch):  # Basically fully modified
    def __init__(
            self, device_id=None, device_name="Switch Device", homie_settings=None, mqtt_settings=None
    ):
        super().__init__(device_id, device_name, homie_settings, mqtt_settings)

        self.TOPIC_BUFFER = []
        self.STATE_BUFFER = []

    def update_switch(self, onoff, node_id):  # sends updates to clients
        self.get_node(node_id).update_switch(onoff)  # pick out node needed to be updated --> set_switch()
        logger.debug("Switch Update {}".format(onoff))

    def set_switch(self, onoff):  # received commands from clients
        # First: Check coherence of Buffers from device_base.py
        if len(self.TOPIC_BUFFER) == 0 or len(self.STATE_BUFFER) == 0:
            logger.error("Error in causal query for Homie with\nTopicBuffer: " + str(
                self.TOPIC_BUFFER) + ", State Buffer: " + str(self.STATE_BUFFER))

        if len(self.TOPIC_BUFFER) != len(self.STATE_BUFFER):
            logger.warning("There is an inconsistence between buffers!")

        global GLOBAL_USB_SEND_QUERY
        iteration = 0

        # loops through whole selfmade homie-topic-state-buffer
        for topic, state in zip(self.TOPIC_BUFFER, self.STATE_BUFFER):
            topic = topic.replace("switch", "", 1)  # Always in it and confuses following node-check

            # Check if a stored node is namend within the topic
            for node in self.nodes:
                logger.debug(str(topic) + str(node) + str(state) + str(onoff))
                if node in topic:
                    workBuffer = convert2sendablePackage(self.nodes[node].name, onoff, "",
                                                         "")  # convert2sendablePackage-function needs to be known before import!

                    # Eliminate double-sending
                    if workBuffer not in GLOBAL_USB_SEND_QUERY:
                        GLOBAL_USB_SEND_QUERY.append(workBuffer)
                        logger.info("Querying 2 USB: " + workBuffer)

                    # Free topic-state-pair
                    self.TOPIC_BUFFER.pop(iteration)
                    self.STATE_BUFFER.pop(iteration)
                    iteration = iteration - 1
            iteration = iteration + 1

        Device_Switch.set_switch(self, onoff)

    def createNewNode(self, node_id, node_name):
        self.add_node(Node_Switch(self, id=node_id, name=node_name, set_switch=self.set_switch))
        self.subscribe_topics()  # always resubribe if a new node is added

    def mqtt_on_message(self, topic, payload, retain, qos):
        self.TOPIC_BUFFER.append(topic)
        self.STATE_BUFFER.append(payload)

        super().mqtt_on_message(topic, payload, retain, qos)


## Main Class of the complete UI
class rf_gateway:
    # Building and Init of UI
    def __init__(self, master=None):
        self.mode = None
        self.enableMQTTbridge = False
        self.enableHomieBridge = False

        # USB - Interaction
        self.StringNetPackageBuffer = []  # Holds received Packages from USB to Filter-Interpret Objects
        self.StringNetSendListBuffer = []  # Holds Que of Packages to be sent
        self.StringNetInteractionObjectBuffer = []  # Holds interactable Objects besides System-Commands
        self.StringNetInteractionNumValsBuffer = [0,
                                                  60000]  # Holds numbers of interactable Objects besides System-Commands

        self.USB_CON = None
        self.USB_PORT = None
        self.USB_BAUDRATE = None
        self.USB_TIMEOUT = None
        self.USB_HOST_NAME = None
        self.USB_SINGLEBUFFER_SIZE = 200

        # MQTT-Generic
        self.MQTT_BROKER_IP = None
        self.MQTT_BROKER_PORT = None
        self.MQTT_HOMEPATH = None
        self.MQTT_TIMEOUT = None
        self.MQTT_QOS = None

        self.MQTT_CON = None

        # MQTT-Homie - Interaction
        self.HOMIE_MQTT_SETTINGS = {
            "MQTT_BROKER": self.MQTT_BROKER_IP,
            "MQTT_PORT": self.MQTT_BROKER_PORT,
            "MQTT_SHARE_CLIENT": True  # limited ressources and many "devices" == objects!
            # The root is /homie
        }
        self.HOMIE_SWITCH_DEVICES = None  # stores many nodes in it

        self.DISCOVER_INTERVAL = 60 * 60  # in seconds
        self.LAST_DISCOVER = time.time() - self.DISCOVER_INTERVAL  # force first discovery

        logger.info("Stringnet-Gateway Init complete!")

    def OpenSettingsFile(self):
        path = "settings.json"
        logger.info("Checking on: " + path)

        try:
            # Open File
            file = open(path, encoding='utf-8')

            # parse JSON to data-Object
            data = json.load(file)

            # Close File
            file.close()

            # Load information, return true if valid
            self.mode = data["mode"]
            self.enableMQTTbridge = data["enableMQTTbridge"]
            self.enableHomieBridge = data["enableHomieBridge"]
            self.USB_PORT = data["USB_PORT"]
            self.USB_BAUDRATE = data["USB_BAUDRATE"]
            self.USB_TIMEOUT = data["USB_TIMEOUT"]
            self.USB_HOST_NAME = data["USB_HOST_NAME"]
            self.MQTT_BROKER_IP = data["MQTT_BROKER_IP"]
            self.MQTT_BROKER_PORT = data["MQTT_BROKER_PORT"]
            self.MQTT_HOMEPATH = data["MQTT_HOMEPATH"]
            self.MQTT_TIMEOUT = data["MQTT_TIMEOUT"]
            self.MQTT_QOS = data["MQTT_QOS"]

            self.HOMIE_MQTT_SETTINGS = {
                "MQTT_BROKER": self.MQTT_BROKER_IP,
                "MQTT_PORT": self.MQTT_BROKER_PORT,
                "MQTT_SHARE_CLIENT": True  # limited ressources and many "devices" == objects!
                # The root is /homie
            }

            return True

        except:
            logger.error("Settings not correct! Will create/overwrite with non-runable stockvalues!")
            self.ResetSettings()
            self.StoreSettings()
            exit(2)  # early exit

    def ResetSettings(self):
        ## Load all stock-settings to UI
        # Setup Vars
        self.enableMQTTbridge = False
        self.enableHomieBridge = False

        while True:
            logger.error("\nYou may choose which MODE the Settings shall up into!\n"
                  "1 - BRIDGE\n"
                  "2 - PROGRAMMER")
            choice = input("\nPlease choose: ")
            if choice == "1":
                self.mode = "BRIDGE"
                break
            elif choice == "2":
                self.mode = "PROGRAMMER"
                break

        self.USB_PORT = "COMx or /dev/ttyUSB0"
        self.USB_BAUDRATE = 115200
        self.USB_TIMEOUT = .1  # for Buffer-Receiv and Busy-Waiting
        self.USB_HOST_NAME = "stringNet"
        self.MQTT_BROKER_IP = "127.0.0.1 or other"
        self.MQTT_BROKER_PORT = 1883
        self.MQTT_HOMEPATH = self.USB_HOST_NAME + "/"  # HARDCODED
        self.MQTT_TIMEOUT = 60  # Keeps Connection open for x Sec. # HARDCODED
        self.MQTT_QOS = 1  # 0: fire and forget, 1: at least once, 2: make sure once

    def StoreSettings(self):
        try:
            path = "settings.json"

            # Open Settingsfile - if present
            file = open(path, "w")

            # Pack all data to JSON-compatible format
            data = {
                "mode": self.mode,
                "enableMQTTbridge": self.enableMQTTbridge,
                "enableHomieBridge": self.enableHomieBridge,
                "USB_HOST_NAME": self.USB_HOST_NAME,
                "USB_PORT": self.USB_PORT,
                "USB_BAUDRATE": self.USB_BAUDRATE,
                "USB_TIMEOUT": self.USB_TIMEOUT,
                "MQTT_BROKER_IP": self.MQTT_BROKER_IP,
                "MQTT_BROKER_PORT": self.MQTT_BROKER_PORT,
                "MQTT_HOMEPATH": self.MQTT_HOMEPATH,
                "MQTT_TIMEOUT": self.MQTT_TIMEOUT,
                "MQTT_QOS": self.MQTT_QOS
            }

            # Write to File
            json.dump(data, file)

            # Close File
            file.close()

            # Tell sucess
            logger.info("Settingsfile successfully saved to: " + path)
        except:
            logger.error("Saving settingsfile saved to: " + path + " failed!")

    #################### USB #######################
    def testUSBConn(self):
        if self.USB_CON is not None and not self.USB_CON.is_open:
            self.try2closeUSBConnection()

        try:
            self.USB_CON = serial.Serial(
                port=self.USB_PORT,
                baudrate=self.USB_BAUDRATE,
                timeout=self.USB_TIMEOUT
            )
            time.sleep(5)
            if self.USB_CON.is_open:
                logger.info("Establishing USB-Connection was successful!")

                # Say hello to USB
                for i in range(5):
                    testMsg = "{LIFESIGN;TELLDEV}"
                    try:
                        logger.debug("Sending testwise:" + str(testMsg))
                        self.USB_CON.write(testMsg.encode("UTF-8"))
                        time.sleep(1)  # wait for it
                        logger.debug("Answer was:" + str(self.USB_CON.readline().decode("UTF-8")))
                    except:
                        # logger.debug(traceback.print_exc()) # DEBUG-SPAM
                        logger.debug("Garbage received! But its fine.")

                return True
        except:
            logger.debug(traceback.print_exc())  # DEBUG-SPAM

        logger.error("Unable to setup USB-Connection!")
        return False

    def processUSBSendBuffer(self):  # Returns whether Package was successfully sent
        global GLOBAL_USB_SEND_QUERY

        if len(GLOBAL_USB_SEND_QUERY) > 0:
            try:
                self.USB_CON.write(GLOBAL_USB_SEND_QUERY[0].encode("UTF-8"))
                logger.debug("USB-TX: " + str(GLOBAL_USB_SEND_QUERY[0]))
                GLOBAL_USB_SEND_QUERY.pop(0)
                return True
            except:
                logger.debug(traceback.print_exc())
                logger.error("USB-Send-Error!")

        return False

    def try2closeUSBConnection(self):
        try:
            self.USB_CON.close()
            logger.info("USB-Connection closed!")
        except:
            logger.warning("No USB-Connection closable!")

    # MQTT-based
    def testMQTTConn(self):
        if self.enableMQTTbridge:
            if self.MQTT_CON is not None and not self.MQTT_CON.is_connected:
                self.try2closeMQTTConnection()

            try:
                self.MQTT_CON = mqtt.Client()
                self.MQTT_CON.on_message = genericMQTT_on_message
                self.MQTT_CON.connect(host=self.MQTT_BROKER_IP, port=self.MQTT_BROKER_PORT, keepalive=self.MQTT_TIMEOUT)
                self.MQTT_CON.loop_start()
                self.MQTT_CON.subscribe(topic=(self.MQTT_HOMEPATH + "#"),
                                        qos=self.MQTT_QOS)  # Subscribe to set root-topic
                logger.info("Init of Generic MQTT-Bridge successfull! (path: " + self.MQTT_HOMEPATH + "#)")

            except:
                logger.debug(traceback.print_exc())
                logger.error("Failed to init Generic MQTT-Bridge!")

        if self.enableHomieBridge:
            if self.HOMIE_SWITCH_DEVICES is not None:
                self.HOMIE_SWITCH_DEVICES.close()

            try:
                # Follow Homie-Conventions
                devName = self.MQTT_HOMEPATH.replace("/", "")
                devID = nicefy2HomieID(devName)
                self.HOMIE_SWITCH_DEVICES = STN_Device_Switch(
                    device_id=devID,
                    device_name=devName,
                    mqtt_settings=self.HOMIE_MQTT_SETTINGS
                )

            except:
                logger.debug(traceback.print_exc())
                logger.error("Failed to init Homie!")

            logger.info("Init of Homie MQTT-Bridge successfull!")

        if (self.MQTT_CON is not None and self.MQTT_CON.is_connected()) or (self.HOMIE_SWITCH_DEVICES is not None):
            return True
        else:
            logger.error("No MQTT-Option to init!")
            return False

    def try2closeMQTTConnection(self):
        if self.enableMQTTbridge:
            try:
                self.MQTT_CON.loop_stop()  # stops network loop
                self.MQTT_CON.disconnect()  # disconnect gracefully
                logger.info("MQTT-Connection closed!")
            except:
                logger.warning("No MQTT-Connection closable!")

        if self.enableHomieBridge:
            try:
                self.HOMIE_SWITCH_DEVICES.close()
            except:
                logger.warning("No Homie-Devices closable!")

    def EstablishConnections(self):
        # Retest Connections
        connectCtr = 0
        while not self.testUSBConn() and not self.testMQTTConn():
            connectCtr += 1
            if connectCtr > 10:
                logger.error("Unable to establish all connections on try #" + str(connectCtr))
            time.sleep(5)
            # yes, endless!

    def getLine(self):
        if self.USB_CON is None or not self.USB_CON.is_open:
            self.testUSBConn()
            time.sleep(1)
            return None

        if self.USB_CON.inWaiting == 0:
            return None

        try:
            line = self.USB_CON.readline().decode("utf-8")
        except UnicodeError:  # filter empty lines
            return None
        except Exception:  # common USB error
            logger.debug(traceback.print_exc())
            logger.error("Trying to regain connection...")
            self.try2closeUSBConnection()
            time.sleep(1)
            self.testUSBConn()
            return None  # early return

        # Check and Process
        try:
            line = checkAndExtractStNPackage(line)
        except:
            logger.debug(traceback.print_exc())
            logger.error("Error while reading! ")
            line = None

        if line is None or line == "":
            logger.debug("Probably nothing to read.")
            return None

        return line

    def receiveUSB(self):
        line = self.getLine()
        if line is None:
            return

        # Convert and Check for it not being a sys-command
        logger.debug("USB-RX: " + str(line))
        strNPackage = convert2StNPackage(line)
        isValid = True
        for COMMAND in COMMANDS:  # Only Object - no sys - commands shall pass
            if COMMAND == strNPackage.Com:
                isValid = False
                break

        if not isValid:
            return

        # Trigger Publish-Events
        if self.enableMQTTbridge:  # Filters
            # Packing and Sending Package
            try:
                topic = self.MQTT_HOMEPATH + strNPackage.Com + "/" + strNPackage.Subcom
                message = strNPackage.Val_str
                self.MQTT_CON.publish(topic, message, self.MQTT_QOS)

                logger.info("GenericMQTT-TX: " + str(line) + "\t" + str(topic) + " " + str(message))
            except:
                logger.debug(traceback.print_exc())
                logger.error("Error while sending Generic MQTT-Paket!")
                self.try2closeMQTTConnection()
                time.sleep(1)
                self.testMQTTConn()

        if not self.enableHomieBridge:
            return

        # Make Name-Command storeable for Homie and find device in RAM
        if strNPackage.Com == "NAME":  #
            strNPackage.Com = strNPackage.Val_str

        nodeName = strNPackage.Com
        nodeID = nicefy2HomieID(strNPackage.Com)

        if nodeID == "" or nodeName == "":
            return

        # Search and conditionally add
        foundDev = False
        for i in range(1, 2):  # no while to avoid error-loops
            for node in self.HOMIE_SWITCH_DEVICES.nodes:
                if node == nodeID:
                    # If found update state -> Buffer
                    if strNPackage.Subcom == "STATUS":
                        try:
                            self.HOMIE_SWITCH_DEVICES.update_switch(strNPackage.Val_str, nodeID)
                        except:
                            logger.debug(traceback.print_exc())
                            logger.error("Error while updating Homie-Buffer!")
                    foundDev = True
                    break

            # Add Device if not existent
            if not foundDev:
                self.HOMIE_SWITCH_DEVICES.createNewNode(
                    node_id=nodeID,
                    node_name=nodeName
                )
                logger.info("Adding " + str(strNPackage.Com) + " to HOMIE_SWITCH_DEVICES")

    ### Main Features
    def BRIDGE(self):
        global GLOBAL_USB_SEND_QUERY

        # Send USB
        self.processUSBSendBuffer()

        # Homie Regular Discovery
        if (time.time() - self.LAST_DISCOVER) > self.DISCOVER_INTERVAL:
            GLOBAL_USB_SEND_QUERY.append("{DISCOVER;TELLALL}")  # to memorize all objects # HARDCODED
            self.LAST_DISCOVER = time.time()

        # Receive USB Input
        self.receiveUSB()

    ####################################################

    ## FWE-Tab
    def DISCOVER_DETAIL(self):
        # Issue StringNet-Packages
        GLOBAL_USB_SEND_QUERY.append("{NAME;TELLDEV}")  # HARDCODED
        GLOBAL_USB_SEND_QUERY.append("{NETMODE;TELLDEV}")  # HARDCODED
        GLOBAL_USB_SEND_QUERY.append("{LIFESIGN;TELLDEV}")  # HARDCODED

        for i in range(1, 30):  # HARDCODED calculated space for Arduino Nano
            GLOBAL_USB_SEND_QUERY.append("{DISCOVER;TELLGPIO;" + str(i) + "}")  # HARDCODED
            GLOBAL_USB_SEND_QUERY.append("{DISCOVER;TELLRF;" + str(i) + "}")  # HARDCODED

        while True:
            line = self.getLine()
            if line is not None:
                logger.info("USB RX: " + line)
            else:
                break
            self.processUSBSendBuffer()
            time.sleep(0.1)

    def formatDEV(self):
        choice = input("\nFormat StringNet-Device?\n"
            "Are you sure you want to wipe the over USB/StringNet connected devices' configuration ?\n[yes / NO [Enter]]")
        if choice.lower() == "yes":
            GLOBAL_USB_SEND_QUERY.append("{FORMAT;;69}")  # HARDCODED MagicNumber

    def loadClistFile(self):
        filename = "flash.clist"
        logger.warning("Looking for in '" + filename + "'...")

        try:
            # Read all Lines of File and close
            file = open(filename, encoding='utf-8')
            lines = file.readlines()
            file.close()

            # Iterate through all lines
            StringNetSendListBuffer = []
            for line in lines:
                # Determine, whether Line is commented and shall not be loaded
                if "#" in line:
                    if line.find("#") <= line.find("{"):  # if comment is before package
                        continue

                # Check for correct Sequences
                strnPackage = checkAndExtractStNPackage(line)
                if strnPackage != None:
                    # Copy Package to Que-List
                    logger.debug(str(line) + str(strnPackage))
                    StringNetSendListBuffer.append(line)  # line instead of strnPackage to make Comments possible

            # Tell success as no error occured
            logger.warning("C-List-File successfully loaded!")
            return StringNetSendListBuffer

        except:
            logger.error("Error | C-List-File not loaded!")
            return None

    def sendClistQue(self, StringNetSendListBuffer):
        if StringNetSendListBuffer is None or StringNetSendListBuffer == []:
            return

        try:
            # Go through all list-elements and buffer them
            for line in StringNetSendListBuffer:
                package = checkAndExtractStNPackage(line)  # Ensure that line is at least a StringNet-Package
                if package is not None:
                    GLOBAL_USB_SEND_QUERY.append(package)  # NOTE: Double-Sending NOT eliminated for pracical reasons
                logger.debug("Got: " + line)
                logger.debug("Will send: " + package)

                logger.info("C-List queried to USB!")
        except:
            logger.error("C-List could not be properly send!")
            logger.debug(traceback.print_exc())

    def PROGRAMMER(self):
        logger.error("\nTHe following options are available:\n"
              "1 - DISCOVER ALL\n"
              "2 - WRITE CLIST TO DEV\n"
              "3 - FORMAT DEV\n"
              "x - EXIT")
        choice = input("\nPlease choose: ")

        if choice == "1":
            self.DISCOVER_DETAIL()
        elif choice == "2":
            self.sendClistQue(self.loadClistFile())
            while len(GLOBAL_USB_SEND_QUERY) > 0:
                self.processUSBSendBuffer()
                logger.info("Got: " + str(GLOBAL_USB_SEND_QUERY))
        elif choice == "3":
            self.formatDEV()
        elif choice == "x":
            exit(0)


##################################################

if __name__ == '__main__':
    # Load File
    app = rf_gateway()
    app.OpenSettingsFile()

    if app.mode == "BRIDGE":
        logger.error(aboutprogramm_bridge)
        if not app.enableHomieBridge and not app.enableMQTTbridge:
            logger.error("No MQTT-endpoint set! Please correct settings!")
            exit(1)

        # Run bridge
        app.EstablishConnections()
        while True:
            try:
                app.BRIDGE()
            except KeyboardInterrupt:
                break

        # Close Bridge
        app.try2closeUSBConnection()
        app.try2closeMQTTConnection()

    elif app.mode == "PROGRAMMER":
        logger.error(aboutprogramm_programmer)
        app.testUSBConn()
        while True:
            try:
                app.PROGRAMMER()
            except KeyboardInterrupt:
                break
