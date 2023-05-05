aboutprogramm = "\
Softwarepurpose: StringNet-IoT-Gateway - Serial Programming, Setup and Control\n\
Version: 2.1.2 05.05.2023\n\
Author: Emil Sedlacek (U2Firestar, Firestar)\n\
Originally supported by: UAS Technikum Vienna and 3S-Sedlak\n\
Note: See paper, Note.txt, commandtable in Excle and Firmware-Source-Files for more info!\n\
Patch-Notes (Firmware and GUI) since 1.0.x:\n\
    - Revised Firmware and StringNet-Protocol\n\
    -- Dynamic digital Objects and Remotes\n\
    - Temporary UDP-support removed because of pure security-risk\n\
    - Added GUI (Busviewer moved to Commandline)\n\
    - Homie (V4) - Support (backwards-compatible to OpenHABs HomieV3-Implementation)\n\
    -- In the modified Python HomieV4-Library the \"Switch\"-Element is extended!\n\
    - FW Settings: Addressing disabled, Lifesign every 60sec\
"

## Special thanks and Credits to:
# - Pygubu-Designer from alejandroautalan @ Github: https://github.com/alejandroautalan/pygubu-designer
# - Eclipse Paho™ MQTT Python Client from eclipse @ Github: https://github.com/eclipse/paho.mqtt.python
# - homie4 from mjcumming @ Github: https://github.com/mjcumming/Homie4

## Imports
# Standard-Python
import pathlib
import sys
import platform
import time
from datetime import datetime
from typing import List, Any
import serial
import json

import traceback
import logging

import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox
from tkinter.filedialog import askopenfilename, asksaveasfile

# Extern
import pygubu

import paho.mqtt.client as mqtt

from homie.device_switch import Device_Switch
from homie.node.node_switch import Node_Switch

## Setup
PROJECT_PATH = pathlib.Path(__file__).parent
PROJECT_UI = PROJECT_PATH / "main.ui"  # Contains all visuals! HARDCODED 

GLOBAL_USB_SEND_QUERY = []  # Needed between MainApp & Homie-Implementation - Buffers all StringNet-packages that shall be sent

logging.basicConfig(level=logging.WARN)  # DEBUG for Homie-API

## StringNet Functions and Definitions
# Commands which get filtered both ways as they are systemcommands, so "STATUS" is not included
COMMANDS = ["FORMAT", "LIFESIGN", "NETMODE", "DISCOVER", "CREATE", "DELETE", "NAME", "PIN", "TYPE",
            "ONSEQUENCE", "OFFSEQUENCE", "PROTOCOLL", "PULSLENGTH", "RF_TX_REP"]
SUBCOMMANDS = ["TELLALL", "TELLDEV", "TELLGPIO", "TELLRF", "SETDEV", "SETGPIO", "SETRF"]
STN_STATES = ["ON", "SilentON", "OFF", "SilentOFF", "TOGGLE", "SilentTOGGLE", "STATUS"] #Standard Name States

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
            print("USB2MQTT_BRIDGE() | Too many objects in StringNetPackage!")
            break
        i = i + 1

    # print(StringNetPackage(command, subcommand, Val_num, Val_str))
    # print(len(stringNetPackage))  # DEBUG

    return StringNetPackage(command, subcommand, Val_num, Val_str)

# Little globally needed StringNet-Package Wrapper
def convert2sendablePackage(COM, SUBCOM, VAL_NUM, VAL_STR):
    return "{" + str(COM) + ";" + str(SUBCOM) + ";" + str(VAL_NUM) + ";" + str(VAL_STR) + "}"

# Little Helper for String-Conversion of Booleans
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

    try:
        # print("on_message() | Incomming Generic-MQTT-Topic: " + message.topic + " with message: ", str(message.payload.decode("utf-8")))  # debug

        # Filter for Echos between MQTT-Server <- Bridge -> Arduino
        if "/STATUS" not in message.topic:
            # convert MQTT-Strcuture to Stringnet:  root/xyz payload  --> {xyz;payload}
            workBuffer = message.topic.split('/')
            i = 1
            command = ""
            for object in workBuffer:
                if i == 1:
                    pass                    # not further interesting - contains root
                elif i == 2:
                    command = object  # contains xyz
                # Check if the positions are correct: If there are postions after - they are ignored!
                elif i >= 3:
                    print("on_message() | Warning : Too many objects in workBuffer as StringNetPackage!")
                    break
                i = i + 1

            # Wrapp the Package
            workBuffer = convert2sendablePackage(command, message.payload.decode("utf-8"), "", "")

            # Eliminate double-sending
            if workBuffer not in GLOBAL_USB_SEND_QUERY:
                GLOBAL_USB_SEND_QUERY.append(workBuffer)
                print("on_message() | Querying: " + workBuffer)

        else:
            print("on_message() | Ignored: " + message.topic + " and message: " + str(message.payload.decode("utf-8")))
    except:
        traceback.print_exc()


# Customized Device_Switch-Object from Homie-Convention; It is modified to store multiple Switches in one Node
# Note: The Library is also modified! device_base.py needed a State and Topic-Buffer
class My_Switch(Device_Switch):
    def __init__(
            self, device_id=None, device_name="Switch Device", homie_settings=None, mqtt_settings=None
    ):
        super().__init__(device_id, device_name, homie_settings, mqtt_settings)
        self.start()

    def addANode(self, node_id, node_name):
        self.add_node(Node_Switch(self, id=node_id, name=node_name, set_switch=self.set_switch))
        self.subscribe_topics()  # always resubribe if a new node is added

    def update_switch(self, onoff, node_id):  # sends updates to clients
        self.get_node(node_id).update_switch(onoff)  # pick out node needed to be updated --> set_switch()
        super().update_switch(onoff)  # for logger = debug

    def set_switch(self, onoff):
        global GLOBAL_USB_SEND_QUERY

        # First: Check coherence of Buffers from device_base.py
        if len(self.TOPIC_BUFFER) > 0 and len(self.STATE_BUFFER) > 0:
            if len(self.TOPIC_BUFFER) != len(self.STATE_BUFFER):
                print("set_switch() | Warning: There is an inconsistence between buffers!")

            iteration = 0

            # loops through whole selfmade homie-topic-state-buffer
            for topic, state in zip(self.TOPIC_BUFFER, self.STATE_BUFFER):
                topic = topic.replace("switch", "", 1)  # Always in it and confuses following node-check

                # Check if a stored node is namend within the topic
                for node in self.nodes:
                    # print(topic, node, state, onoff) # DEBUG
                    if node in topic:
                        workBuffer = convert2sendablePackage(self.nodes[node].name, onoff, "", "")

                        # Eliminate double-sending
                        if workBuffer not in GLOBAL_USB_SEND_QUERY:
                            GLOBAL_USB_SEND_QUERY.append(workBuffer)
                            print("set_switch() | Querying 2 USB: " + workBuffer)

                        # Free topic-state-pair
                        self.TOPIC_BUFFER.pop(iteration)
                        self.STATE_BUFFER.pop(iteration)
                        iteration = iteration - 1

                iteration = iteration + 1

        else:
            print("set_switch() | Error in causal query for Homie")

        super().set_switch(onoff)  # for logger = debug

# Little Wrapper to match Homie-Librarys Needs
def nicefy2HomieID(string):
    # Follow Homie-Conventions
    forbidden = "!:;',@#/_$ "

    string = string.lower()
    for char in forbidden:
        string = string.replace(char, "")

    return string

## Main Class of the complete UI
class MainApp:
    # Bulding and Init of UI
    def __init__(self, master=None):
        ## Build Base-UI
        self.builder = builder = pygubu.Builder()
        builder.add_resource_path(PROJECT_PATH)
        builder.add_from_file(PROJECT_UI)
        self.mainwindow = builder.get_object('mainWindow', master)

        self.mainwindow.protocol("WM_DELETE_WINDOW", self.on_closing_mainWindow)  # Add close-event

        # Buffer synced with UI
        self.enableMQTTbridge = None
        self.enableHomieBridge = None
        self.autostartBridge = None
        self.USB_PORT = None
        self.USB_BAUDRATE = None
        self.USB_TIMEOUT = None
        self.USB_HOST_NAME = None
        self.MQTT_BROKER_IP = None
        self.MQTT_BROKER_PORT = None
        self.MQTT_HOMEPATH = None
        self.MQTT_TIMEOUT = None
        self.MQTT_QOS = None

        # Volatile UI-I/O
        self.autostartBridgeCheckVal = None
        self.networkModeCheckVal = None
        self.toggleUSBConnBtnTxt = None
        self.USBPortEntryVal = None
        self.USBBaudrateEntryVal = None
        self.USBHostEntryVal = None
        self.USBReadTimeoutEntryVal = None
        self.USBPortCheckVal = None
        self.USBBaudrateCheckVal = None
        self.USBHostCheckVal = None
        self.USBReadTimeoutCheckVal = None
        self.toggleMQTTConnBtnTxt = None
        self.enableGenMQTTBridgeBtnVal = None
        self.enableHomieBridgeBtnVal = None
        self.MQTTBrokerIPEntryVal = None
        self.MQTTBrokerPortEntryVal = None
        self.MQTTHomepathEntryVal = None
        self.MQTTQOSEntryVal = None
        self.MQTTBrokerIPCheckVal = None
        self.MQTTBrokerPortCheckVal = None
        self.MQTTHomepathCheckVal = None
        self.MQTTQOSCheckVal = None
        self.manualPackageEntryText = None
        self.aboutsoftwareVar = None
        self.statusText = None
        builder.import_variables(self, ['autostartBridgeCheckVal', 'networkModeCheckVal', 'toggleUSBConnBtnTxt',
                                        'USBPortEntryVal', 'USBBaudrateEntryVal', 'USBHostEntryVal',
                                        'USBReadTimeoutEntryVal', 'USBPortCheckVal', 'USBBaudrateCheckVal',
                                        'USBHostCheckVal', 'USBReadTimeoutCheckVal', 'toggleMQTTConnBtnTxt',
                                        'enableGenMQTTBridgeBtnVal', 'enableHomieBridgeBtnVal', 'MQTTBrokerIPEntryVal',
                                        'MQTTBrokerPortEntryVal', 'MQTTHomepathEntryVal', 'MQTTQOSEntryVal',
                                        'MQTTBrokerIPCheckVal', 'MQTTBrokerPortCheckVal', 'MQTTHomepathCheckVal',
                                        'MQTTQOSCheckVal', 'manualPackageEntryText', 'aboutsoftwareVar', 'statusText'])

        builder.connect_callbacks(self)

        # Load References and make Objects accessable
        self.appNotebook = self.builder.get_object("appNotebook", self.mainwindow)  # Tabs

        self.toggleBridgeBtn = self.builder.get_object("toggleBridgeBtn", self.mainwindow)
        self.toggleFWEditorBtn = self.builder.get_object("toggleFWEditorBtn", self.mainwindow)

        self.toggleUSBConnBtn = self.builder.get_object("toggleUSBConnBtn", self.mainwindow)
        self.USBPortEntry = self.builder.get_object("USBPortEntry", self.mainwindow)
        self.USBBaudrateEntry = self.builder.get_object("USBBaudrateEntry", self.mainwindow)
        self.USBHostEntry = self.builder.get_object("USBHostEntry", self.mainwindow)
        self.USBReadTimeoutEntry = self.builder.get_object("USBReadTimeoutEntry", self.mainwindow)

        self.toggleMQTTConnBtn = self.builder.get_object("toggleMQTTConnBtn", self.mainwindow)
        self.MQTTBrokerIPEntry = self.builder.get_object("MQTTBrokerIPEntry", self.mainwindow)
        self.MQTTBrokerPortEntry = self.builder.get_object("MQTTBrokerPortEntry", self.mainwindow)
        self.MQTTHomepathEntry = self.builder.get_object("MQTTHomepathEntry", self.mainwindow)
        self.MQTTQOSEntry = self.builder.get_object("MQTTQOSEntry", self.mainwindow)

        self.startBridgeBtn = self.builder.get_object("startBridgeBtn", self.mainwindow)
        self.stopBridgeBtn = self.builder.get_object("stopBridgeBtn", self.mainwindow)

        self.StringNetObjectList = self.builder.get_object("StringNetObjectList", self.mainwindow)
        self.StringNetObjectList.bind("<<TreeviewSelect>>", self.onFWERowClick)
        self.ComQueList = self.builder.get_object("ComQueList", self.mainwindow)
        self.ComQueList.bind("<<TreeviewSelect>>", self.onQueRowClick)

        self.loadClistFileBtn = self.builder.get_object("loadClistFileBtn", self.mainwindow)
        self.saveAsClistFileBtn = self.builder.get_object("saveAsClistFileBtn", self.mainwindow)
        self.clearQueBtn = self.builder.get_object("clearQueBtn", self.mainwindow)
        self.sendClistQueBtn = self.builder.get_object("sendClistQueBtn", self.mainwindow)

        ## Setup UI-independent variables
        self.UI_State = "I"  # I ... Init, S ... Setup, B ... Bridge-Mode, F ... FWE-Mode
        self.SettingsLoadable = False
        self.BRIDGE_KILLSIGNAL = False
        self.pauseProcessing = False

        # USB - Interaction
        self.StringNetPackageBuffer = []  # Holds received Packages from USB to Filter-Interpret Objects
        self.StringNetSendListBuffer = []  # Holds Que of Packages to be sent
        self.StringNetInteractionObjectBuffer = []  # Holds interactable Objects besides System-Commands
        self.StringNetInteractionNumValsBuffer = [0, 60000]  # Holds numbers of interactable Objects besides System-Commands
        self.USB_CON_PARTNER = "" # Buffers newest Device-Name
        self.USB_CON = None
        self.USB_OK = False
        self.USB_SINGLEBUFFER_SIZE = 200

        # MQTT-Generic - Interaction
        self.MQTT_CON = None
        self.MQTT_OK = False

        # MQTT-Homie - Interaction
        self.HOMIE_MQTT_SETTINGS = {
            "MQTT_BROKER": self.MQTT_BROKER_IP,
            "MQTT_PORT": self.MQTT_BROKER_PORT,
            "MQTT_SHARE_CLIENT": True  # limited ressources and many "devices" == objects!
            # The root is /homie
        }
        self.HOMIE_SWITCH_DEVICES = None  # stores central MySwitch-Objects with many nodes in it
        self.HOMIE_DISCOVER_INTERVAL = 24 * 60 * 60 #in seconds
        self.HOMIE_DISCOVER_LAST_TIME = time.time() - self.HOMIE_DISCOVER_INTERVAL + 30 # HARDCODED WAITING

        ## Limit and Setting UI-Options
        self.appNotebook.tab(2, state='disabled')  # Bridge
        self.appNotebook.tab(3, state='disabled')  # FW Editor
        self.appNotebook.tab(4, state='disabled')  # Que

        self.stopBridgeBtn["state"] = 'disabled'

        ## Reload Settings
        self.statusText.set("Status | Loading Setttings!")

        self.aboutsoftwareVar.set(aboutprogramm)

        self.UI_State = "S"
        self.OpenSettingsFile()
        self.loadSettingsToEntry()

        self.statusText.set("Status | Application initialized!")
        print("run() | Stringnet-Center Init complete!")

    # Actually jumpstarting UI
    def run(self):
        ## Run conditional autotstart first and loop routine
        print("run() | Stringnet-Center started. Running conditional autostart now...")
        secondsCntDown = 10  # HARDCODED 

        # Count Down and Update Windows meanwhile
        while self.autostartBridgeCheckVal.get() == 1 and secondsCntDown > 0:
            self.statusText.set("Status | Autostart Bridge in " + str(
                secondsCntDown) + " seconds! Abort by unchecking Autostart of Bridge.")
            for s in range(1, 20):
                time.sleep(0.05)
                self.mainwindow.update() #Needed for simultanious UI-Inputs
                if self.autostartBridgeCheckVal.get() == 0:
                    self.statusText.set("Status | Autostart of Bridge canceled!")
            secondsCntDown = secondsCntDown - 1

        # Run Autostart as autostart-option is still checked
        if self.autostartBridgeCheckVal.get() == 1:
            self.statusText.set("Status | Autostart - Prepartion in progress!")
            self.mainwindow.update()
            time.sleep(0.1)

            # Lead to correct UI-State
            if self.UI_State == "F":
                self.toggleFWEditorUpdate()
                self.mainwindow.update()
                time.sleep(0.1)
            if self.UI_State == "S":
                self.statusText.set("Status | Autostart - Checking connections!")
                self.mainwindow.update()
                time.sleep(0.1)

                # Prepair Connections to change to Bridge-Mode
                self.testUSBConn()
                self.testMQTTConn()

                # change if Successfull
                self.toggleBridgeUpdate()

            # Check wether Entering Bridge-Mode was successfull
            if self.UI_State == "B":
                self.statusText.set("Status | Autostart - Activating Bridge!")
                self.mainwindow.update()
                time.sleep(0.1)
                self.startBridge()
            else:
                self.statusText.set("Error | Autostart of Bridge failed!")

        ## Run blocking main-loop
        print("run() | Stringnet-Center idling...")
        self.statusText.set("Status | Program idling...")
        self.mainwindow.mainloop()

    ## Window-Creater and Opener, if existant
    # Open Object - Editor - Is an Object which makes it easier to create StringNet-Packages
    def openObjectEditor(self):
        try:
            # Initialize Window
            self.stringNetObjectEditor = self.builder.get_object('stringNetObjectEditor', self.mainwindow)

            self.stringNetObjectEditor.protocol("WM_DELETE_WINDOW", self.on_closing_editor)

            # Make Variables accessable
            self.comChooserComboboxTxt = None
            self.subcomChooserComboboxTxt = None
            self.valnumChooserComboboxTxt = None
            self.valstrChooserComboboxTxt = None
            self.builder.import_variables(self,
                                          ['comChooserComboboxTxt', 'subcomChooserComboboxTxt',
                                           'valnumChooserComboboxTxt',
                                           'valstrChooserComboboxTxt'])

            # Make Objects accessable
            self.comChooserCombobox = self.builder.get_object("comChooserCombobox", self.mainwindow)
            self.subcomChooserCombobox = self.builder.get_object("subcomChooserCombobox", self.mainwindow)
            self.valnumChooserCombobox = self.builder.get_object("valnumChooserCombobox", self.mainwindow)
            self.valstrChooserCombobox = self.builder.get_object("valstrChooserCombobox", self.mainwindow)

            # Finish building
            self.builder.connect_callbacks(self)
        except:
            self.statusText.set("Error | Could not create Object-Editor properly!")
            traceback.print_exc()

        try:
            # Update Content and Show Window
            self.rebuildObjectEditorLists()
            self.stringNetObjectEditor.deiconify()
        except:
            self.statusText.set("Error | Could not update and show Object Editor!")

    ### Window HANDLER
    # Row-Click on Que
    def onQueRowClick(self, extra):
        try:
            index = self.ComQueList.selection()[0]
            try:
                package = self.ComQueList.item(index)["values"][0]
                if package != "":
                    self.manualPackageEntryText.set(package)
            except:
                traceback.print_exc()
        except:
            pass

    # Row-Click on Que
    def onFWERowClick(self, extra):
        try:
            index = self.StringNetObjectList.selection()[0]
            try:
                package = ""
                for value in self.StringNetObjectList.item(index)["values"]:
                    package = package + " " + str(value)
                if package != "":
                    self.manualPackageEntryText.set(package)
            except:
                traceback.print_exc()
        except:
            pass

    # Row-Click in Object List
    def onObjectListRowClick(self, extra):
        try:
            index = self.StringNetObjectList.selection()[0]
            try:
                package = self.StringNetObjectList.item(index)["values"][0]
                if package != "":
                    self.manualPackageEntryText.set(package)
            except:
                traceback.print_exc()
        except:
            pass

    # Event on Closing MainWindow
    def on_closing_mainWindow(self):
        self.pauseProcessing = True
        if messagebox.askokcancel("Quit program?", "Are you sure you want to close all connections and the program?"):
            self.try2closeUSBConnection()
            self.try2closeMQTTConnection()
            self.mainwindow.destroy()  # Leads back to run()
        self.pauseProcessing = False

    # Event on Closing Editor
    def on_closing_editor(self):
        self.pauseProcessing = True
        if messagebox.askokcancel("Close Editor?", "Are you sure you want hide the editor?"):
            self.stringNetObjectEditor.withdraw()
        self.pauseProcessing = False

    ### UI-issued functions
    ## Instruction Tab
    def autostartBridgeCheckUpdate(self):
        if self.autostartBridgeCheckVal.get() == 0:
            self.autostartBridge = False
        else:
            self.autostartBridge = True
        self.statusText.set("Warning | Autostart-option changed! Don't forget to save!")

    def networkModeUpdate(self):
        # TODO: Address-Mode
        pass

    def toggleBridgeUpdate(self):
        if self.UI_State != "B":
            if not self.SettingsLoadable:
                self.statusText.set("Error | Settings not loaded yet!")
            elif not self.USB_OK or not self.MQTT_OK:
                self.statusText.set("Error | At least one connection invalid! Please try again!")
                if not self.USB_OK:
                    self.toggleUSBConn()
                if not self.MQTT_OK:
                    self.toggleMQTTConn()
            else:
                self.appNotebook.tab(2, state='normal')  # Bridge
                self.toggleFWEditorBtn["state"] = 'disabled'
                self.UI_State = "B"
                self.statusText.set("Status | Autostart - Changing to Bridge-Tab!")
                self.appNotebook.select(2)  # Change to Bridge

        elif self.UI_State == "B":
            self.appNotebook.tab(2, state='disabled')  # Bridge
            self.toggleFWEditorBtn["state"] = 'normal'
            self.UI_State = "S"
            self.stopBridge()
            self.appNotebook.select(0)  # Change to Instructions

    def toggleFWEditorUpdate(self):
        if self.UI_State != "F":
            if not self.SettingsLoadable:
                self.statusText.set("Error | Settings not loaded yet!")
            elif not self.USB_OK:
                self.statusText.set("Error | USB-connection-state not valid! Trying to open... Please retry then!")
                self.toggleUSBConn()
            else:
                self.appNotebook.tab(3, state='normal')  # FW Editor
                self.appNotebook.tab(4, state='normal')  # Que
                self.toggleBridgeBtn["state"] = 'disabled'
                self.UI_State = "F"
                self.statusText.set("Status | Autostart - Changing to FWE-Tab!")
                self.appNotebook.select(3)  # Change to FWE
                self.openObjectEditor()

                # Tell and Loop
                self.statusText.set("Status | Firmware Editor active!")
                self.mainwindow.after(100, self.FirmwareEditorMode)

        elif self.UI_State == "F":
            self.appNotebook.tab(3, state='disabled')  # FW Editor
            self.appNotebook.tab(4, state='disabled')  # Que
            self.toggleBridgeBtn["state"] = 'normal'
            self.UI_State = "S"
            self.appNotebook.select(0)  # Change to Instructions
            self.statusText.set("Status | Exiting FWE and changing to Instructions-Tab!")

    ## Settings-Tab
    # USB-Specific Check-Updates and Buttonpresses
    def USBPortCheck(self):
        if self.USBPortCheckVal.get() == 1:
            self.USBPortEntry["state"] = "normal"
        else:
            self.USBPortEntry["state"] = "disabled"

    def USBBaudrateCheck(self):
        if self.USBBaudrateCheckVal.get() == 1:
            self.USBBaudrateEntry["state"] = "normal"
        else:
            self.USBBaudrateEntry["state"] = "disabled"

    def USBHostCheck(self):
        if self.USBHostCheckVal.get() == 1:
            self.USBHostEntry["state"] = "normal"
        else:
            self.USBHostEntry["state"] = "disabled"

    def USBReadTimeoutCheck(self):
        if self.USBReadTimeoutCheckVal.get() == 1:
            self.USBReadTimeoutEntry["state"] = "normal"
        else:
            self.USBReadTimeoutEntry["state"] = "disabled"

    def toggleUSBConn(self):
        if self.USB_OK:
            self.try2closeUSBConnection()
        else:
            self.testUSBConn()

    # MQTT-specific Check-Updates and Buttonpresses
    def enableGenMQTTBridgeBtn(self):
        if self.enableGenMQTTBridgeBtnVal.get() == 1:
            self.enableMQTTbridge = True
            if self.enableHomieBridge == True:
                self.statusText.set("Warning | Avoid to run bridge with both chosen MQTT-Option!")
        else:
            self.enableMQTTbridge = False
            if self.enableHomieBridge == False:
                self.statusText.set("Warning | Avoid to run bridge without chosen MQTT-Option!")

    def enableHomieBridgeBtn(self):
        if self.enableHomieBridgeBtnVal.get() == 1:
            self.enableHomieBridge = True
            if self.enableMQTTbridge == True:
                self.statusText.set("Warning | Avoid to run bridge with both chosen MQTT-Option!")
        else:
            self.enableHomieBridge = False
            if self.enableMQTTbridge == False:
                self.statusText.set("Warning | Avoid to run bridge without any chosen MQTT-Option!")

    def MQTTBrokerIPCheck(self):
        if self.MQTTBrokerIPCheckVal.get() == 1:
            self.MQTTBrokerIPEntry["state"] = "normal"
        else:
            self.MQTTBrokerIPEntry["state"] = "disabled"

    def MQTTBrokerPortCheck(self):
        if self.MQTTBrokerPortCheckVal.get() == 1:
            self.MQTTBrokerPortEntry["state"] = "normal"
        else:
            self.MQTTBrokerPortEntry["state"] = "disabled"

    def MQTTHomepathCheck(self):
        if self.MQTTHomepathCheckVal.get() == 1:
            self.MQTTHomepathEntry["state"] = "normal"
        else:
            self.MQTTHomepathEntry["state"] = "disabled"

    def MQTTQOSCheck(self):
        if self.MQTTQOSCheckVal.get() == 1:
            self.MQTTQOSEntry["state"] = "normal"
        else:
            self.MQTTQOSEntry["state"] = "disabled"

    def toggleMQTTConn(self):
        if self.MQTT_OK:
            self.try2closeMQTTConnection()
        else:
            self.testMQTTConn()

    # Persistance
    def OpenSettingsFileChoose(self):
        # Triggers the standard procedur of open a settings file differently - by opening a File-Window
        self.OpenSettingsFile(ask="")

    def OpenSettingsFile(self, ask=None):
        # Choosing the wanted settings-file - dependend on Variable
        if ask is not None:
            # show an "Open" dialog box and return the path to the selected file
            newPath = askopenfilename(initialfile="settings.json",
                                      title="Open Settingsfile for StringNet-Center",
                                      filetypes=(("JSON", "*.json"),
                                                 ("All files",
                                                  "*.*")))
        else:
            newPath = "settings.json"

        # Check if it is not empty
        if len(newPath) > 0:
            # print(newPath) #DEBUG
            pass

        try:
            # Open File
            file = open(newPath, encoding='utf-8')

            # parse JSON to data-Object
            data = json.load(file)

            # Close File
            file.close()

            # Load all gathered information into UI
            self.autostartBridge = data["autostartBridge"]
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

            # If all Settings where present: Say so
            self.SettingsLoadable = True
            self.statusText.set("Status | Settingsfile successfully loaded!")
        except:
            # If not: Tell as well!
            self.ResetSettings()
            self.statusText.set("Error | Settingsfile not loaded! Leading to reset!")
        finally:
            self.loadSettingsToEntry()

    def ResetSettings(self):
        ## Load all stock-settings to UI
        # Setup Vars
        self.USB_OK = False
        self.MQTT_OK = False
        self.SettingsLoadable = False

        self.enableMQTTbridge = False
        self.enableHomieBridge = True
        self.autostartBridge = False

        self.USB_PORT = "COMx or /dev/ttyUSB0"
        self.USB_BAUDRATE = 115200
        self.USB_TIMEOUT = .1  # for Buffer-Receiv and Busy-Waiting
        self.USB_HOST_NAME = "stringNet"
        self.MQTT_BROKER_IP = "127.0.0.1 or other"
        self.MQTT_BROKER_PORT = 1883
        self.MQTT_HOMEPATH = self.USB_HOST_NAME + "/"  # HARDCODED 
        self.MQTT_TIMEOUT = 60  # Keeps Connection open for x Sec. # HARDCODED 
        self.MQTT_QOS = 0  # 0: fire and forget, 1: at least once, 2: make sure once

        # Reset Checks
        self.USBPortCheckVal.set(0)
        self.USBBaudrateCheckVal.set(0)
        self.USBHostCheckVal.set(0)
        self.USBReadTimeoutCheckVal.set(0)
        self.MQTTBrokerIPCheckVal.set(0)
        self.MQTTBrokerPortCheckVal.set(0)
        self.MQTTHomepathCheckVal.set(0)
        self.MQTTQOSCheckVal.set(0)

        # Backload and feedback
        self.loadSettingsToEntry()
        self.statusText.set("Status | Settings reset! Don't forget to save.")

    def StoreSettings(self):
        try:
            # Open Settingsfile - if present
            file = open("settings.json", "w")

            # Make sure UI is synched with background-vars
            self.loadSettingsFromEntry()

            # Pack all data to JSON-compatible format
            data = {
                "enableMQTTbridge": self.enableMQTTbridge,
                "enableHomieBridge": self.enableHomieBridge,
                "autostartBridge": self.autostartBridge,
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
            self.statusText.set("Status | Settingsfile successfully saved!")
        except:
            self.statusText.set("Error | Saving Settingsfile failed!")

    ## Bridge-Tab
    def startBridge(self):
        # Retest Connections
        self.testUSBConn()
        self.testMQTTConn()

        #If all OK, init of Bridge
        if self.USB_OK and self.MQTT_OK:
            self.statusText.set("Status | Start Bridge - Activating Bridge!")
            self.mainwindow.update()
            time.sleep(0.1)

            # Toggle available Btns in UI
            self.startBridgeBtn["state"] = "disabled"
            self.stopBridgeBtn["state"] = "normal"

            # Start actual bridge
            global GLOBAL_USB_SEND_QUERY
            self.BRIDGE_KILLSIGNAL = False

            # Tell and Enter Loop
            self.statusText.set("Status | Bridge active!")
            self.mainwindow.after(100, self.USB2MQTT_BRIDGE)
        else:
            self.statusText.set("Error | Could not start Bridge as not all connections setup!")

    def stopBridge(self):
        # Toggle available Btns in UI
        self.startBridgeBtn["state"] = "normal"
        self.stopBridgeBtn["state"] = "disabled"
        self.BRIDGE_KILLSIGNAL = True

        # Tell it's done
        self.statusText.set("Status | Bridge deactivated!")

    ## FWE-Tab
    def DISCOVER(self):
        # If FWE-Mode the DISCOVER-Function ask for all initial objects instead of simple Name-State-Pair
        if self.UI_State == "F":
            # Reset FWE-UI
            self.clearObjectList()

            # Issue StringNet-Packages
            GLOBAL_USB_SEND_QUERY.append("{NAME;TELLDEV}") # HARDCODED 
            GLOBAL_USB_SEND_QUERY.append("{NETMODE;TELLDEV}") # HARDCODED 
            GLOBAL_USB_SEND_QUERY.append("{LIFESIGN;TELLDEV}") # HARDCODED 

            for i in range(1, 30):  # HARDCODED calculated space for Arduino Nano
                GLOBAL_USB_SEND_QUERY.append("{DISCOVER;TELLGPIO;" + str(i) + "}") # HARDCODED 
                GLOBAL_USB_SEND_QUERY.append("{DISCOVER;TELLRF;" + str(i) + "}") # HARDCODED 
        else:
            GLOBAL_USB_SEND_QUERY.append("{DISCOVER;TELLALL}")  # to memorize all objects # HARDCODED 

    def formatDEV(self):
        # Prevent Missclicks
        self.pauseProcessing = True
        if messagebox.askokcancel("Format StringNet-Device?",
                                  "Are you sure you want to wipe the over USB/StringNet connected devices' configuration ?"):

            # Issue Package
            GLOBAL_USB_SEND_QUERY.append("{FORMAT;;69}")  # HARDCODED  MagicNumber
        self.pauseProcessing = False

    def clearObjectList(self):
        # Reset Buffer and Update UI
        self.StringNetPackageBuffer = []
        self.loadObjectBuffer2UI()

    ## Que-Editor-Tab
    # Command Que-Actions
    def loadClistFile(self):
        # show an "Open" dialog box and return the path to the selected file
        filename = askopenfilename(initialfile="demo.clist",
                                   title="Open Command-List-Script-File",
                                   filetypes=(("C-List files", "*.clist"),
                                              ("All files", "*.*"))
                                   )

        # If not a empty string...
        if len(filename) > 0:
            # print(filename)

            try:
                self.clearClistQue()  # Clean up before loading

                # Read all Lines of File and close
                file = open(filename, encoding='utf-8')
                lines = file.readlines()
                file.close()

                # Iterate through all lines
                for line in lines:
                    # Determine, whether Line is commented and shall not be loaded
                    if "#" in line:
                        if line.find("#") <= line.find("{"): #if comment is before package
                            continue

                    # Check for correct Sequences
                    strnPackage = checkAndExtractStNPackage(line)
                    if strnPackage != None:
                        # Copy Package to Que-List
                        # print(line, strnPackage) #DEBUG
                        self.StringNetSendListBuffer.append(line) # line instead of strnPackage to make Comments possible

                # Tell success as no error occured
                self.statusText.set("Status | C-List-File successfully loaded!")

            except:
                self.statusText.set("Error | C-List-File not loaded!")
            finally:
                # UI has to be updated - even tho there was an error
                self.loadClistBuffer2UI()

    def saveAsClistFile(self):
        # show an "Open" dialog box and return the path to the selected file
        filename = asksaveasfile(
            initialfile="new.clist",
            title="Save Command-List-Script-File",
            defaultextension='.clist',
            filetypes=(("C-List files", "*.clist"),
                       ("All files", "*.*"))
        )

        # Check for valid path
        if filename is not None and filename.name != "":
            # print(filename.name) #DEBUG
            filename = filename.name

            try:
                # Open file to write
                file = open(filename, encoding='utf-8', mode="w")

                # Write a header
                file.writelines("# Autogenerated c-list-file!\n")

                # Go through all list-elements and write them down
                for item in self.ComQueList.get_children():
                    for value in self.ComQueList.item(item)['values']:
                        # print(value)
                        # Ensure that line is at least a StringNet-Package
                        try:
                            package = checkAndExtractStNPackage(value)
                            if package != None:
                                file.writelines(value) # value instead of package to make Comments possible
                        except:
                            self.statusText.set("Warning | C-List-File writing-Error!")

                # Operation done - close file and tell success
                file.close()
                self.statusText.set("Status | C-List-File successfully saved!")
            except:
                self.statusText.set("Error | C-List-File not properly saved!")
                traceback.print_exc()  # DEBUG
            finally:
                self.loadClistBuffer2UI()

    def clearClistQue(self):
        # Reset Buffer and Update UI
        self.StringNetSendListBuffer = []
        self.loadClistBuffer2UI()

    def sendClistQue(self):
        try:
            # Go through all list-elements and buffer them
            for line in self.ComQueList.get_children():
                for value in self.ComQueList.item(line)['values']:
                    print(value)
                    # Ensure that line is at least a StringNet-Package
                    package = checkAndExtractStNPackage(value)
                    if package != None:
                        GLOBAL_USB_SEND_QUERY.append(package) # TODO: Double-Sending NOT eliminated for pracical reasons

                self.statusText.set("Status | C-List queried to USB!")
        except:
            self.statusText.set("Error | C-List could not be properly send!")
            traceback.print_exc()  # DEBUG

    # Manual Package-Entry
    def manualPackageEntry(self):
        # Check, buffer and Update UI
        input = self.manualPackageEntryText.get()
        if input != "":
            package = checkAndExtractStNPackage(input)
            if package != None:
                self.StringNetSendListBuffer.append(input) # # input instead of package to make Comments possible
                self.loadClistBuffer2UI()
            else:
                self.statusText.set("Warning | Invalid input!")

    def manualPackageEntryDel(self):
        # Check for valid selection, delete out of buffer and Update UI
        try:
            index2Del = int(self.ComQueList.selection()[0])
            self.StringNetSendListBuffer.pop(index2Del - 1)
            self.loadClistBuffer2UI()
        except:
            traceback.print_exc()
            self.statusText.set("Warning | Selection was invalid!")

    def manualPackageEntryEdit(self):
        # Check for valid selection, copy from buffer to Entry and Update UI
        try:
            package = self.manualPackageEntryText.get()
            if package != "":
                index2Del = int(self.ComQueList.selection()[0])
                self.StringNetSendListBuffer[index2Del - 1] = package
                self.loadClistBuffer2UI()
        except:
            traceback.print_exc()

    ## StringNet Object Editor
    def sendSTENow(self):
        # Copy all Entrys from Object Editor and Convert 2 StringNetPackage
        pack = convert2sendablePackage(
            self.comChooserComboboxTxt.get(),
            self.subcomChooserComboboxTxt.get(),
            self.valnumChooserComboboxTxt.get(),
            self.valstrChooserComboboxTxt.get()
        )

        # Buffer Package to USB
        if pack not in GLOBAL_USB_SEND_QUERY: # eliminate Double-Sending
            GLOBAL_USB_SEND_QUERY.append(pack)

    def sendSTEQue(self):
        # Copy all Entrys from Object Editor and Convert 2 StringNetPackage
        # Update Buffer and UI
        self.StringNetSendListBuffer.append(convert2sendablePackage(
            self.comChooserComboboxTxt.get(),
            self.subcomChooserComboboxTxt.get(),
            self.valnumChooserComboboxTxt.get(),
            self.valstrChooserComboboxTxt.get()
        ))
        self.loadClistBuffer2UI()

    #### Helper
    # Settings
    def loadSettingsFromEntry(self):
        # Depending on selected Checkmarks the function stores the value of the Entry or uses the old value.
        self.autostartBridge = self.autostartBridgeCheckVal.get()
        self.enableMQTTbridge = self.enableGenMQTTBridgeBtnVal.get()
        self.enableHomieBridge = self.enableHomieBridgeBtnVal.get()

        if self.USBPortCheckVal.get() == 1:
            self.USB_PORT = self.USBPortEntryVal.get()
        if self.USBBaudrateCheckVal.get() == 1:
            self.USB_BAUDRATE = self.USBBaudrateEntryVal.get()
        if self.USBReadTimeoutCheckVal.get() == 1:
            self.USB_TIMEOUT = self.USBReadTimeoutEntryVal.get()
        if self.USBHostCheckVal.get() == 1:
            self.USB_HOST_NAME = self.USBHostEntryVal.get()
        if self.MQTTBrokerIPCheckVal.get() == 1:
            self.MQTT_BROKER_IP = self.MQTTBrokerIPEntryVal.get()
        if self.MQTTBrokerPortCheckVal.get() == 1:
            self.MQTT_BROKER_PORT = self.MQTTBrokerPortEntryVal.get()
        if self.MQTTHomepathCheckVal.get() == 1:
            self.MQTT_HOMEPATH = self.MQTTHomepathEntryVal.get()
        if self.USBPortCheckVal.get() == 1:
            self.MQTT_QOS = self.MQTTQOSEntryVal.get()

    def loadSettingsToEntry(self):
        # Update all Checks and Entrys from background-buffer
        self.autostartBridgeCheckVal.set(self.autostartBridge)
        self.enableGenMQTTBridgeBtnVal.set(self.enableMQTTbridge)
        self.enableHomieBridgeBtnVal.set(self.enableHomieBridge)

        self.USBPortEntryVal.set(self.USB_PORT)
        self.USBBaudrateEntryVal.set(self.USB_BAUDRATE)
        self.USBReadTimeoutEntryVal.set(self.USB_TIMEOUT)
        self.USBHostEntryVal.set(self.USB_HOST_NAME)
        self.MQTTBrokerIPEntryVal.set(self.MQTT_BROKER_IP)
        self.MQTTBrokerPortEntryVal.set(self.MQTT_BROKER_PORT)
        self.MQTTHomepathEntryVal.set(self.MQTT_HOMEPATH)
        self.MQTTQOSEntryVal.set(self.MQTT_QOS)

        self.USBPortCheck()
        self.USBBaudrateCheck()
        self.USBHostCheck()
        self.USBReadTimeoutCheck()
        self.MQTTBrokerIPCheck()
        self.MQTTBrokerPortCheck()
        self.MQTTHomepathCheck()
        self.MQTTQOSCheck()

    # FWE
    def loadObjectBuffer2UI(self):
        # Clear list manually
        try:
            for item in self.StringNetObjectList.get_children():
                self.StringNetObjectList.delete(item)
        except:
            traceback.print_exc()  # DEBUG
            print("loadObjectBuffer2UI() | Clearing failed!")

        # Sort Object-Tree by <dev>/<devtype>/<indexNum>/<InfoObject>/<INFO>
        try:
            self.StringNetPackageBuffer.sort()
            index = 0
            for line in self.StringNetPackageBuffer:
                if self.USB_CON_PARTNER not in line:
                    self.StringNetPackageBuffer.pop(index)
                else:
                    index = index + 1
        except:
            traceback.print_exc()  # DEBUG
            print("loadObjectBuffer2UI() | Sorting failed!")

        # Load Info 2 List
        try:
            for line in self.StringNetPackageBuffer:
                # Extract Information
                x = line.split("/")
                lastDev = x[0]
                lastTyp = x[1]
                try:
                    lastNum = int(x[2])
                except:
                    lastNum = 0
                lastObject = x[3]
                lastStr = x[4]

                # Extract for the Object Editor
                if lastObject not in self.StringNetInteractionObjectBuffer and lastObject not in COMMANDS:  # TODO: Not working
                    self.StringNetInteractionObjectBuffer.append(lastObject)
                if lastNum not in self.StringNetInteractionNumValsBuffer:
                    self.StringNetInteractionNumValsBuffer.append(lastNum)
                self.rebuildObjectEditorLists()

                # Insert into UI
                self.StringNetObjectList.insert(parent="", index=index, iid=index,
                                                values=(lastDev + "/" + lastTyp, lastObject, str(lastNum), lastStr))
                index = index + 1 #YES, it does us the previous index-var! It must throw an error if not initialized as well!
                
            self.statusText.set("Status | Object-List-Updated!")
        except:
            traceback.print_exc()  # DEBUG
            print("loadObjectBuffer2UI() | Loading failed!")

    def loadClistBuffer2UI(self):
        # Clear list
        for item in self.ComQueList.get_children():
            self.ComQueList.delete(item)

        # Load Info 2 List
        index = 1
        for stnPack in self.StringNetSendListBuffer:
            self.ComQueList.insert(parent="", index=index, iid=index, values=(stnPack, index))
            index = index + 1

        self.statusText.set("Status | Que-List-Updated!")

    # USB
    def testUSBConn(self):
        if self.USB_CON is None or not self.USB_CON.isOpen():
            self.USB_OK = False
            for i in range(1, 30):
                try:
                    self.USB_CON = serial.Serial(
                        port=self.USB_PORT,
                        baudrate=self.USB_BAUDRATE,
                        timeout=self.USB_TIMEOUT
                    )
                    self.USB_OK = True
                   
                    testMsg = "{LIFESIGN;TELLDEV}"
                    try:
                        print("testUSBConn() | Sending testwise:", testMsg)
                        self.USB_CON.write(testMsg.encode("UTF-8"))
                        time.sleep(0.1)  # wait for
                        print("testUSBConn() | Answer was:", self.USB_CON.readline().decode("UTF-8"))
                    except:
                        traceback.print_exc()  # DEBUG
                        print("testUSBConn() | Garbage received! ... Its fine.")
                    break

                except:
                    #traceback.print_exc() # DEBUG
                    self.statusText.set("Status | Establishing USB-Connection: Try: #" + str(i) + "/30")
                    for j in range(1, 20):
                        self.mainwindow.update()
                        time.sleep(0.05)

            if not self.USB_OK:
                self.statusText.set("Error | Not able to setup USB-Connection!")
                self.toggleUSBConnBtnTxt.set("Connect")
            else:
                self.statusText.set("Status | Establishing USB-Connection successful!")
                self.toggleUSBConnBtnTxt.set("Disconnect")

    def processUSBSendBuffer(self):  # Returns whether Package was successfully sent
        if len(GLOBAL_USB_SEND_QUERY) > 0:
            try:
                self.USB_CON.write(GLOBAL_USB_SEND_QUERY[0].encode("UTF-8"))
                print("processUSBSendBuffer() |", datetime.now().strftime("%d/%m/%Y, %H:%M:%S") + " | USB-TX: " + str(GLOBAL_USB_SEND_QUERY[0])) # DEBUG
                GLOBAL_USB_SEND_QUERY.pop(0)

                return True

            except:
                traceback.print_exc()  # DEBUG
                print("processUSBSendBuffer() | USB-Send-Error!")
                self.USB_OK = False

        return False

    def try2closeUSBConnection(self):
        try:
            self.USB_CON.close()
            self.statusText.set("Status | USB-Connection closed!")
        except:
            self.statusText.set("Warning | No USB-Connection closable!")

        self.USB_OK = False
        self.toggleUSBConnBtnTxt.set("Connect")

    # MQTT-based
    def testMQTTConn(self):
        try:
            if self.enableMQTTbridge:
                self.MQTT_CON = mqtt.Client()
                self.MQTT_CON.on_message = genericMQTT_on_message
                self.MQTT_CON.connect(host=self.MQTT_BROKER_IP, port=self.MQTT_BROKER_PORT, keepalive=self.MQTT_TIMEOUT)
                self.MQTT_CON.loop_start()
                self.MQTT_CON.subscribe(topic=(self.MQTT_HOMEPATH + "#"),
                                        qos=self.MQTT_QOS)  # Subscribe to set root-topic
                self.MQTT_OK = True
                self.statusText.set("Status | Init of Generic MQTT-Bridge successfull! (path: " + self.MQTT_HOMEPATH + "#)")


            if self.enableHomieBridge:
                self.HOMIE_MQTT_SETTINGS = {
                    "MQTT_BROKER": self.MQTT_BROKER_IP,
                    "MQTT_PORT": self.MQTT_BROKER_PORT,
                    "MQTT_SHARE_CLIENT": True  # limited ressources and many "devices" == objects!
                    # The root is /homie
                }

                # Follow Homie-Conventions
                devName = self.MQTT_HOMEPATH.replace("/", "")
                devID = nicefy2HomieID(devName)
                self.HOMIE_SWITCH_DEVICES = My_Switch(
                    mqtt_settings=self.HOMIE_MQTT_SETTINGS,
                    device_id=devID,
                    device_name=devName
                )
                self.MQTT_OK = True
                self.statusText.set("Status | Init of Homie MQTT-Bridge successfull!")

            if self.MQTT_OK:
                self.toggleMQTTConnBtnTxt.set("Disconnect")
            else:
                self.statusText.set("Warning | No MQTT-Option to init!")

        except:
            traceback.print_exc()
            self.statusText.set("Error | Failed to init Generic MQTT-Bridge!")
            self.MQTT_OK = False

    def try2closeMQTTConnection(self):
        if self.enableMQTTbridge:
            try:
                self.MQTT_CON.loop_stop()  # stops network loop
                self.MQTT_CON.disconnect()  # disconnect gracefully
                self.statusText.set("Status | MQTT-Connection closed!")
            except:
                self.statusText.set("Warning | No MQTT-Connection closable!")

        if self.enableHomieBridge:
            try:
                self.HOMIE_SWITCH_DEVICES.close()
            except:
                self.statusText.set("Warning | No Homie-Devices closable!")

        self.MQTT_OK = False
        self.toggleMQTTConnBtnTxt.set("Connect")

    #Object Editor
    def rebuildObjectEditorLists(self):
        # Accesses known viable options for a StringNet-Package
        try:
            self.comChooserCombobox["values"] = ("## SYSTEM ##",) + tuple(COMMANDS) + ("## OBJECTS ##",) + tuple(
                self.StringNetInteractionObjectBuffer)
            self.subcomChooserCombobox["values"] = ("## SUBCOMMANDS ##",) + tuple(SUBCOMMANDS) + (
                "## STATES for Interaction ##",) + tuple(STN_STATES)
            self.valnumChooserCombobox["values"] = tuple(self.StringNetInteractionNumValsBuffer)
            self.valstrChooserCombobox["values"] = ("## STATES for Setup ##",) + tuple(STN_STATES)

            self.statusText.set("Status | Lists in Object Editor have been updated!")
        except:
            traceback.print_exc()

    ### Main Features
    def USB2MQTT_BRIDGE(self):
        try:
            # Check connections
            try:
                if not self.USB_CON.isOpen():
                    self.USB_OK = False
                    raise ValueError('USB2MQTT_BRIDGE() | USB-Connection broke!')
                if self.enableMQTTbridge:
                    if not self.MQTT_CON.is_connected():
                        self.MQTT_CON = False
                        raise ValueError('USB2MQTT_BRIDGE() | MQTT-Connection broke!')
            except:
                traceback.print_exc()

            if (not self.BRIDGE_KILLSIGNAL) and (self.MQTT_OK or self.USB_OK) and (not self.pauseProcessing):
                # Homie Regular Discovery
                if self.enableHomieBridge and (time.time() - self.HOMIE_DISCOVER_LAST_TIME) > self.HOMIE_DISCOVER_INTERVAL:
                    self.DISCOVER()
                    self.HOMIE_DISCOVER_LAST_TIME = time.time()

                # Send USB
                self.processUSBSendBuffer()

                # Receive USB Input
                try:
                    line = self.USB_CON.readline().decode("UTF-8")
                except:
                    #traceback.print_exc()  # DEBUG
                    #print("USB2MQTT_BRIDGE() | USB-Receive-Error!")
                    line = ""

                try:
                    # Check and Process
                    line = checkAndExtractStNPackage(line)
                    if line != None:
                        print("USB2MQTT_BRIDGE() |", datetime.now().strftime("%d/%m/%Y, %H:%M:%S") + " | USB-RX: " + str(line)) #DEBUG

                        # Convert and Check for it not being a sys-command
                        strNPackage = convert2StNPackage(line)
                        isValid = True
                        for COMMAND in COMMANDS:  # Only Object - no sys - commands shall pass
                            if COMMAND == strNPackage.Com:
                                isValid = False
                                break

                        # Trigger Publish-Events
                        if isValid and self.enableMQTTbridge:  # Filters
                            # Packing and Sending Package
                            try:
                                topic = self.MQTT_HOMEPATH + strNPackage.Com + "/" + strNPackage.Subcom
                                message = strNPackage.Val_str
                                self.MQTT_CON.publish(topic, message, self.MQTT_QOS)

                                print("USB2MQTT_BRIDGE() | GenericMQTT-TX: ", line, "\t", topic, " ", message)
                            except:
                                traceback.print_exc()  # DEBUG
                                print("USB2MQTT_BRIDGE() | Error while sending Generic MQTT-Paket!")

                        if isValid and self.enableHomieBridge:
                            # Make Name-Command storeable for Homie and find device in RAM
                            try:
                                if strNPackage.Com == "NAME":  #
                                    strNPackage.Com = strNPackage.Val_str

                                nodeName = strNPackage.Com
                                nodeID = nicefy2HomieID(strNPackage.Com)

                                if nodeID != "" and nodeName != "":
                                    # Search and conditionally add
                                    foundDev = False
                                    for i in range(1, 2):  # no while to avoid error-loops
                                        for node in self.HOMIE_SWITCH_DEVICES.nodes:
                                            if node == nodeID:
                                                # If found update state -> Buffer
                                                if strNPackage.Subcom == "STATUS":
                                                    self.HOMIE_SWITCH_DEVICES.update_switch(strNPackage.Val_str, nodeID)
                                                foundDev = True
                                                break

                                        # Add Device if not existent
                                        if not foundDev:
                                            self.HOMIE_SWITCH_DEVICES.addANode(
                                                node_id=nodeID,
                                                node_name=nodeName
                                            )
                                            print(
                                                "USB2MQTT_BRIDGE() | Adding " + strNPackage.Com + " to HOMIE_SWITCH_DEVICES")
                            except:
                                traceback.print_exc()  # DEBUG
                                print("USB2MQTT_BRIDGE() | Error while processing Homie-Buffer!")
                except:
                    #traceback.print_exc()  # DEBUG
                    print("USB2MQTT_BRIDGE() | Error while parsing! Probably nothing to read.")

                # Finishing run and schedule loop
                self.mainwindow.after(100, self.USB2MQTT_BRIDGE)
            
            elif self.pauseProcessing:
                #print("USB2MQTT_BRIDGE() | Waiting for next round as bridge is paused!") #DEBUG
                self.mainwindow.after(100, self.USB2MQTT_BRIDGE)
            elif self.BRIDGE_KILLSIGNAL:
                self.statusText.set("Status | Bridge closed! Mind that connections are still active!")
                print("USB2MQTT_BRIDGE() | Bridge closed with BRIDGE_KILLSIGNAL: ", str(self.BRIDGE_KILLSIGNAL))
                self.stopBridge()
            else:
                self.statusText.set("Error | Bridge collapsed! Mind that connections are still active!")
                print("USB2MQTT_BRIDGE() | Bridge collapsed with unknwown cause!")
        except:
            traceback.print_exc()  # DEBUG            
            self.statusText.set("Error | Bridge closed by force!")
            self.mainwindow.update()
            time.sleep(0.1)

    def FirmwareEditorMode(self):
        try:
            # TODO: Imperformant but neccessary for Raspberry
            if "arm" in platform.machine():
                self.mainwindow.update() # Force to update UI because it freezes

            # Check connections
            try:
                if not self.USB_OK:
                    if self.UI_State == "F" or self.UI_State != "S":
                        self.toggleFWEditorUpdate()
                if not self.USB_CON.isOpen():
                    self.USB_OK = False
                    raise ValueError('FirmwareEditorMode() | USB-Connection broke!')
            except:
                traceback.print_exc() #DEBUG
            
            # Run Routine
            if self.UI_State == "F" and self.USB_OK and not self.pauseProcessing:
                # Send USB
                self.processUSBSendBuffer()

                # Receive USB Input
                try:
                    line = self.USB_CON.readline().decode("UTF-8")
                except:
                    # traceback.print_exc()  # DEBUG
                    # print("USB2MQTT_BRIDGE() | USB-Receive-Error!")
                    line = ""

                try:
                    line = checkAndExtractStNPackage(line)
                    if line != None:
                        print("FirmwareEditorMode() |", datetime.now().strftime("%d/%m/%Y, %H:%M:%S") + " | USB-RX: " + str(line)) # DEBUG

                        # Convert and Extract
                        strNPackage = convert2StNPackage(line)
                        valnumstr = f"{strNPackage.Val_num:02d}" # Important formating to make sorting better!

                        # Konvert to Object-Tree <dev>/<DEV/GP/RF>/<Num>/<InfoObject>/<INFO>
                        appendable = False
                        if strNPackage.Com in COMMANDS: # HARDCODED
                            # The 3 cases differ in Object-Tree differences
                            if strNPackage.Subcom == "TELLDEV":
                                if strNPackage.Com == "NAME":
                                    self.USB_CON_PARTNER = strNPackage.Val_str
                                line = self.USB_CON_PARTNER + "/DEV/" + valnumstr + "/" + strNPackage.Com + "/" + strNPackage.Val_str
                                appendable = True
                            elif strNPackage.Subcom == "TELLGPIO":
                                if strNPackage.Val_num >= 1:
                                    line = self.USB_CON_PARTNER + "/GPIO/" + valnumstr + "/" + strNPackage.Com + "/" + strNPackage.Val_str
                                    appendable = True
                            elif strNPackage.Subcom == "TELLRF":
                                if strNPackage.Val_num >= 1:
                                    line = self.USB_CON_PARTNER + "/RF/" + valnumstr + "/" + strNPackage.Com + "/" + strNPackage.Val_str
                                    appendable = True
                        elif strNPackage.Subcom == "STATUS":
                            line = self.USB_CON_PARTNER + "/ObjState/" + valnumstr + "/" + strNPackage.Com + "/" + strNPackage.Val_str
                            appendable = True
                        else:
                            line = self.USB_CON_PARTNER + "/undef/" + strNPackage.Com + "/" + strNPackage.Subcom + "+" + valnumstr + "/" + strNPackage.Val_str
                            appendable = True

                        # If Objecttree is valid and not allready known -> Append
                        if appendable and line not in self.StringNetPackageBuffer:
                            # print("FirmwareEditorMode() | Adding to StringNetObjectbuffer: " + line) #DEBUG
                            self.StringNetPackageBuffer.append(line)
                            self.loadObjectBuffer2UI()
                except:
                    traceback.print_exc()  # DEBUG
                    print("FirmwareEditorMode() | Error while parsing! Probably nothing to read.")

                # Finishing run and schedule loop
                self.mainwindow.after(100, self.FirmwareEditorMode)
                
            elif self.pauseProcessing:
                # print("MQTT-FirmwareEditorMode() | Waiting for next round as FWE is paused!") #DEBUG
                self.mainwindow.after(100, self.FirmwareEditorMode)
                
            else:
                self.statusText.set("Status | FWE closed! Mind that connections are still active!")
                print("FirmwareEditorMode() | FWE collapsed with UI_State: ", str(self.UI_State))
        except:
            traceback.print_exc()  # DEBUG
            self.statusText.set("Error | FWE closed by force!")
            self.mainwindow.update()
            time.sleep(0.1)        


if __name__ == '__main__':
    try:
        app = MainApp()
        app.run()
    except:
        traceback.print_exc()
