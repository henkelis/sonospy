########################################################################################################################
# Volume Tab for use with sonospyGUI.py
########################################################################################################################
# virtualsTab.py copyright (c) 2010-2016 John Chowanec
# mutagen copyright (c) 2005 Joe Wreschnig, Michael Urman (mutagen is Licensed under GPL version 2.0)
# Sonospy Project copyright (c) 2010-2014 Mark Henkelis
#   (specifics for this file: scan.py)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# virtualsTab.py Author: John Chowanec <chowanec@gmail.com>
########################################################################################################################
# TO DO:
# - FIX INSTANCES OF **BROKEN** BELOW
# - Add autopopulate zones
# - Remove zones with fixed volume = true
########################################################################################################################
# IMPORTS FOR PYTHON
########################################################################################################################
import wx
import re
import os
import subprocess
from threading import *
import guiFunctions
from wx.lib.pubsub import setuparg1
from wx.lib.pubsub import pub
import urllib
import socket
import sys
import time
import threading
import datetime

cmd_folder = os.path.dirname(os.path.abspath(__file__))

if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)

socket.setdefaulttimeout(15)

def get_ip_address(ifname):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ip = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, pack('256s', str(ifname[:15])))[20:24])
        return ip
    except:
        return socket.gethostbyname(socket.gethostname())

def get_active_ifaces():
    if os.name == 'nt':
        return [socket.gethostbyname(socket.gethostname())]
    else:
        try:
            rd = open('/proc/net/route').readlines()
        except (IOError, OSError):
            return [socket.gethostbyname(socket.gethostname())]
        net = [line.split('\t')[0:2] for line in rd]
        return [v[0] for v in net if v[1] == '00000000']    

active_ifaces = get_active_ifaces()
if guiFunctions.configMe("volume", "serverIP") == '':
    #ip_address = get_ip_address(active_ifaces[0])
    ip_address = '192.168.1.110'
else:
    ip_address = guiFunctions.configMe("volume", "serverIP")
    
# Global Vars -------------------------------------------------------------------------------------------------------------------
list_checkboxIDNames = []                                                                   # Used later to store check box ids for retrieval
zonesToMonitor = []                                                                         # Global for storing zones to monitor.
maxVolPerZone = []                                                                          # Global to store max vol per zone checked.                                                                 
portNum = guiFunctions.configMe("INI", "controlpoint_port", file="../pycpoint.ini")         # Setting static port num -- can get this from pycpoint.ini
zoneNAME=urllib.urlopen('http://' + ip_address + ':' + portNum +'/data/deviceData').read()  # Getting active zones from Sonospy
debugMe=False                                                                               # Set to TRUE to turn on debug logging.
# -------------------------------------------------------------------------------------------------------------------------------

# Positive look behind, positive look forward 
# http://stackoverflow.com/questions/36827128/stripping-multiple-types-of-strings-from-a-master-string/
zoneNAME = re.findall('(?<=R::).*?(?=_\|_)', zoneNAME)
# Strip it down to ONLY zones with (ZP)
regex = [re.compile('^.*\(ZP\)')]
zoneNAME = [s for s in zoneNAME if any(re.match(s) for re in regex)]

if len(zoneNAME) < 1:
    guiFunctions.errorMsg("Error!", "You don't have any discoverable zones!")

def EVT_RESULT(win, func):
    """Define Result Event."""
    win.Connect(-1, -1, EVT_RESULT_ID, func)
            
class ResultEvent(wx.PyEvent):
    """Simple event to carry arbitrary result data."""
    def __init__(self, data):
        """Init Result Event."""
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_RESULT_ID)
        self.data = data      

class WorkerThread(Thread):
    """Worker Thread Class."""
    def __init__(self, notify_window, func, delay):
        """Init Worker Thread Class."""
        Thread.__init__(self)
        self._notify_window = notify_window
        self.ToKill = False
        self._want_abort = 0
        global function
        global timeout
        function = func
        timeout = delay
        self.start()

    def run(self):
        """Run Worker Thread."""
        while self.ToKill==False:
            function()
            time.sleep(timeout)




########################################################################################################################
# VolumePanel: The layout and binding section for the frame.
########################################################################################################################
class VolumePanel(wx.Panel):
    """
    Volume Tab for creating subset databases.
    """
    #----------------------------------------------------------------------
    def __init__(self, parent):
        """"""
        wx.Panel.__init__(self, parent=parent, id=wx.ID_ANY)

        panel = self
        sizer = wx.GridBagSizer(13, 4)
        self.currentDirectory = os.getcwd()

        xIndex = 0
        curZoneNum = 0

    # -------------------------------------------------------------------------
    # [1] - Server IP address and Port

        label_serverIP = wx.StaticText(panel, label="Server IP/Port:")
        help_serverIP = "The IP address of the running server"
        label_serverIP.SetToolTip(wx.ToolTip(help_serverIP))
        sizer.Add(label_serverIP, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
    
        self.tc_serverIP = wx.TextCtrl(panel)
        self.tc_serverIP.SetToolTip(wx.ToolTip(help_serverIP))
        self.tc_serverIP.Value = ip_address
        sizer.Add(self.tc_serverIP, pos=(xIndex, 1), flag=wx.LEFT|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)

        self.tc_serverPort = wx.TextCtrl(panel)
        self.tc_serverPort.SetToolTip(wx.ToolTip(help_serverIP))
        self.tc_serverPort.Value = portNum
        sizer.Add(self.tc_serverPort, pos=(xIndex, 2), flag=wx.LEFT|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10).SetMinSize((30,22))

        xIndex +=0
    # -------------------------------------------------------------------------
    # [2] - Sleep Interval
    
        label_CheckInterval = wx.StaticText(panel, label="Vol Check Frequency (sec):")
        help_CheckInterval = "How frequently do you want to check for volume levels?"
        label_CheckInterval.SetToolTip(wx.ToolTip(help_CheckInterval))
        sizer.Add(label_CheckInterval, pos=(xIndex, 3), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
        
        self.tc_CheckInterval = wx.TextCtrl(panel)
        self.tc_CheckInterval.SetToolTip(wx.ToolTip(help_CheckInterval))
        self.tc_CheckInterval.Value = guiFunctions.configMe("volume", "timeout")
        sizer.Add(self.tc_CheckInterval, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10).SetMinSize((30,22))  

        xIndex +=1

    # -------------------------------------------------------------------------
    # [3] - Quiet Hours
        
        self.ck_QuietHours = wx.CheckBox(self, -1, 'Quiet Hours')
        self.ck_QuietHours.SetToolTip(wx.ToolTip("Click here to turn on Quiet Hours"))
        help_QuietHours = "Set time HH:MM in 24 hour notation to drop volume. 23:00 for example."
        self.ck_QuietHours.Bind(wx.EVT_CHECKBOX, self.quietCkClick)
        self.ck_QuietHours.Value = guiFunctions.configMe("volume", "quietCk", bool=True)
        sizer.Add(self.ck_QuietHours, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
            
        self.tc_quietHr = wx.TextCtrl(panel)
        self.tc_quietHr.SetToolTip(wx.ToolTip(help_QuietHours))
        self.tc_quietHr.Value = guiFunctions.configMe("volume", "quietHr")
        sizer.Add(self.tc_quietHr, pos=(xIndex, 1), flag=wx.LEFT|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)

        self.tc_quietHrStop = wx.TextCtrl(panel)
        self.tc_quietHrStop.SetToolTip(wx.ToolTip("Set the time HHMM in 24 hour notation to stop quiet hours. 23:59 for example."))
        self.tc_quietHrStop.Value = guiFunctions.configMe("volume", "quietHrStop")
        sizer.Add(self.tc_quietHrStop, pos=(xIndex, 2), flag=wx.LEFT|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)
        
        xIndex +=1
        
        self.label_QuietVol = wx.StaticText(panel, label="Quiet Volume:")
        help_QuietVol = "Set desired Quiet Hour max volume."
        self.label_QuietVol.SetToolTip(wx.ToolTip(help_QuietVol))
        sizer.Add(self.label_QuietVol, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        self.quietSlider = wx.Slider(self, -1, guiFunctions.configMe("volume", "quietSlider", integer=True), 0, 100, size=(400,10), style=wx.SL_HORIZONTAL)
        
        self.tc_QuietVol = wx.TextCtrl(panel, -1, guiFunctions.configMe("volume", "quietSlider"), (0,0), (30,21))
        self.tc_QuietVol.SetToolTip(wx.ToolTip(help_QuietVol))
        
        self.quietSlider.Bind(wx.EVT_SLIDER, lambda event: self.sliderUpdate(event, self.quietSlider, self.tc_QuietVol,), self.quietSlider)
        self.tc_QuietVol.Bind(wx.EVT_CHAR, lambda event: self.tcVolUpdate(event, self.quietSlider, self.tc_QuietVol,), self.tc_QuietVol)
        
        sizer.Add(self.quietSlider, pos=(xIndex,1), span=(1, 3), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_QuietVol, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((30,22))        
        
        if self.ck_QuietHours.Value == False:
            self.tc_quietHr.Disable()
            self.tc_quietHrStop.Disable()
            self.label_QuietVol.Disable()
            self.quietSlider.Disable()
            self.tc_QuietVol.Disable()

        xIndex +=1

    # -------------------------------------------------------------------------
    # [4] - Mute Hours
            
        self.ck_MuteHours = wx.CheckBox(self, -1, 'Mute Hours')
        self.ck_MuteHours.SetToolTip(wx.ToolTip("Click here to turn on Mute Hours"))
        self.ck_MuteHours.Bind(wx.EVT_CHECKBOX, self.muteHoursClick)
        self.ck_MuteHours.Value = guiFunctions.configMe("volume", "muteCk", bool=True)
        sizer.Add(self.ck_MuteHours, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
                
        self.tc_MuteHr = wx.TextCtrl(panel)
        self.tc_MuteHr.SetToolTip(wx.ToolTip("Time to start muting zones. 00:00 = midnight, for instance"))
        self.tc_MuteHr.Value = guiFunctions.configMe("volume", "muteHr")
        sizer.Add(self.tc_MuteHr, pos=(xIndex, 1), flag=wx.LEFT|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)
    
        self.tc_MuteHrStop = wx.TextCtrl(panel)
        self.tc_MuteHrStop.SetToolTip(wx.ToolTip("Time to end muting zones. 07:00 = 7am, for instance."))
        self.tc_MuteHrStop.Value = guiFunctions.configMe("volume", "mutehrStop")
        sizer.Add(self.tc_MuteHrStop, pos=(xIndex, 2), flag=wx.LEFT|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)

        if self.ck_MuteHours.Value == False:
            self.tc_MuteHr.Disable()
            self.tc_MuteHrStop.Disable()
        
        xIndex +=1

    # -------------------------------------------------------------------------
    # [5] Make Header Columns 

        self.label_ProxyName = wx.StaticText(panel, label="Zone")
        self.label_UserIndexName = wx.StaticText(panel, label="Max. Volume %")
        sizer.Add(self.label_ProxyName, pos=(xIndex, 0), flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT|wx.TOP, border=10)
        sizer.Add(self.label_UserIndexName, pos=(xIndex, 2), flag=wx.ALIGN_CENTER_VERTICAL|wx.CENTER|wx.TOP, border=10)        
        xIndex +=1
        
    # -------------------------------------------------------------------------
    # [6] Separator line 

        hl_SepLine1 = wx.StaticLine(panel, 0, (250, 50), (300,1))
        sizer.Add(hl_SepLine1, pos=(xIndex, 0), span=(1, 5), flag=wx.EXPAND)
        xIndex +=1

    # -------------------------------------------------------------------------
    # Zones, sliders and max volume
    # -------------------------------------------------------------------------
    # [7,8] - Zone 1
    # **BROKEN** - Fix zoneNAME[] if it does not exist in savetodefaults - then populate to the rest.
        self.ck_ZONE1 = wx.CheckBox(self, -1, zoneNAME[curZoneNum], name="1")
        self.ck_ZONE1.SetToolTip(wx.ToolTip("Click here to monitor volume for this zone."))
        list_checkboxIDNames.append(self.ck_ZONE1.GetId())
        sizer.Add(self.ck_ZONE1, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
    
        self.tc_ZONEVOL1 = wx.TextCtrl(panel, -1, guiFunctions.configMe("volume", "slider1"), (0,0), (30,21))
        self.tc_ZONEVOL1.SetToolTip(wx.ToolTip("Set max volume for the zone (0-100)"))
        sizer.Add(self.tc_ZONEVOL1, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((30,22))

        self.sliderZone1 = wx.Slider(self, -1, guiFunctions.configMe("volume", "slider1", integer=True), 0, 100, size=(400,10), name="sliderZone1", style=wx.SL_HORIZONTAL)

        self.sliderZone1.Bind(wx.EVT_SLIDER, lambda event: self.sliderUpdate(event, self.sliderZone1, self.tc_ZONEVOL1,), self.sliderZone1)
        self.tc_ZONEVOL1.Bind(wx.EVT_CHAR, lambda event: self.tcVolUpdate(event, self.sliderZone1, self.tc_ZONEVOL1,), self.tc_ZONEVOL1)
        self.ck_ZONE1.Bind(wx.EVT_CHECKBOX, lambda event: self.zoneCkClick(event, self.ck_ZONE1, self.sliderZone1, self.tc_ZONEVOL1,), self.ck_ZONE1)
        
        sizer.Add(self.sliderZone1, pos=(xIndex,1), span=(1, 3), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)        

        if self.ck_ZONE1.Value == False:
            self.tc_ZONEVOL1.Disable()
            self.sliderZone1.Disable()
        
        curZoneNum += 1
        xIndex += 1
    # -------------------------------------------------------------------------
    # [9,10] - Zone2

        if curZoneNum < len(zoneNAME):
            self.ck_ZONE2 = wx.CheckBox(self, -1, zoneNAME[curZoneNum], name='2')
            self.ck_ZONE2.SetToolTip(wx.ToolTip("Click here to monitor volume for this zone."))
            list_checkboxIDNames.append(self.ck_ZONE2.GetId())
            sizer.Add(self.ck_ZONE2, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        
            self.tc_ZONEVOL2 = wx.TextCtrl(panel, -1, guiFunctions.configMe("volume", "slider2"), (0,0), (30,21))
            self.tc_ZONEVOL2.SetToolTip(wx.ToolTip("Set max volume for the zone (0-100)"))
            sizer.Add(self.tc_ZONEVOL2, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((30,22))
        
            self.sliderZone2 = wx.Slider(self, -1, guiFunctions.configMe("volume", "slider2", integer=True), 0, 100, size=(400,10), name="sliderZone2", style=wx.SL_HORIZONTAL)

            self.sliderZone2.Bind(wx.EVT_SLIDER, lambda event: self.sliderUpdate(event, self.sliderZone2, self.tc_ZONEVOL2,), self.sliderZone2)
            self.tc_ZONEVOL2.Bind(wx.EVT_CHAR, lambda event: self.tcVolUpdate(event, self.sliderZone2, self.tc_ZONEVOL2,), self.tc_ZONEVOL2)
            self.ck_ZONE2.Bind(wx.EVT_CHECKBOX, lambda event: self.zoneCkClick(event, self.ck_ZONE2, self.sliderZone2, self.tc_ZONEVOL2,), self.ck_ZONE2)
            
            sizer.Add(self.sliderZone2, pos=(xIndex,1), span=(1, 3), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)        

            if self.ck_ZONE2.Value == False:
                self.tc_ZONEVOL2.Disable()
                self.sliderZone2.Disable()

        curZoneNum += 1  
        xIndex +=1

    # -------------------------------------------------------------------------
    # [10,11] - Zone3
    # **BROKEN** - Fix zoneNAME[] if it does not exist in savetodefaults
        if curZoneNum < len(zoneNAME):
            self.ck_ZONE3 = wx.CheckBox(self, -1, zoneNAME[curZoneNum], name='3')
            self.ck_ZONE3.SetToolTip(wx.ToolTip("Click here to monitor volume for this zone."))
            list_checkboxIDNames.append(self.ck_ZONE3.GetId())
            sizer.Add(self.ck_ZONE3, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
            
            
            self.tc_ZONEVOL3 = wx.TextCtrl(panel, -1, guiFunctions.configMe("volume", "slider3"), (0,0), (30,21))
            self.tc_ZONEVOL3.SetToolTip(wx.ToolTip("Set max volume for the zone (0-100)"))
            sizer.Add(self.tc_ZONEVOL3, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((30,22))
            
            self.sliderZone3 = wx.Slider(self, -1, guiFunctions.configMe("volume", "slider3", integer=True), 0, 100, size=(400,10), name="sliderZone3", style=wx.SL_HORIZONTAL)

            self.sliderZone3.Bind(wx.EVT_SLIDER, lambda event: self.sliderUpdate(event, self.sliderZone3, self.tc_ZONEVOL3,), self.sliderZone3)
            self.tc_ZONEVOL3.Bind(wx.EVT_CHAR, lambda event: self.tcVolUpdate(event, self.sliderZone3, self.tc_ZONEVOL3,), self.tc_ZONEVOL3)
            self.ck_ZONE3.Bind(wx.EVT_CHECKBOX, lambda event: self.zoneCkClick(event, self.ck_ZONE3, self.sliderZone3, self.tc_ZONEVOL3,), self.ck_ZONE3)
            
            sizer.Add(self.sliderZone3, pos=(xIndex,1), span=(1, 3), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)

            if self.ck_ZONE3.Value == False:
                self.tc_ZONEVOL3.Disable()
                self.sliderZone3.Disable()            

        curZoneNum +=1
        xIndex +=1
    
    # -------------------------------------------------------------------------
    # [12,13] - Zone4
        if curZoneNum < len(zoneNAME):
            self.ck_ZONE4 = wx.CheckBox(self, -1, zoneNAME[curZoneNum], name='4')
            self.ck_ZONE4.SetToolTip(wx.ToolTip("Click here to monitor volume for this zone."))
            list_checkboxIDNames.append(self.ck_ZONE4.GetId())
            sizer.Add(self.ck_ZONE4, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
            
            self.tc_ZONEVOL4 = wx.TextCtrl(panel, -1, guiFunctions.configMe("volume", "slider4"), (0,0), (30,21))
            self.tc_ZONEVOL4.SetToolTip(wx.ToolTip("Set max volume for the zone (0-100)"))
            sizer.Add(self.tc_ZONEVOL4, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((30,22))
                
            self.sliderZone4 = wx.Slider(self, -1, guiFunctions.configMe("volume", "slider4", integer=True), 0, 100, size=(400,10), name="sliderZone4", style=wx.SL_HORIZONTAL)

            self.sliderZone4.Bind(wx.EVT_SLIDER, lambda event: self.sliderUpdate(event, self.sliderZone4, self.tc_ZONEVOL4,), self.sliderZone4)
            self.tc_ZONEVOL4.Bind(wx.EVT_CHAR, lambda event: self.tcVolUpdate(event, self.sliderZone4, self.tc_ZONEVOL4,), self.tc_ZONEVOL4)
            self.ck_ZONE4.Bind(wx.EVT_CHECKBOX, lambda event: self.zoneCkClick(event, self.ck_ZONE4, self.sliderZone4, self.tc_ZONEVOL4,), self.ck_ZONE4)
            
            sizer.Add(self.sliderZone4, pos=(xIndex,1), span=(1, 3), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)

            if self.ck_ZONE4.Value == False:
                self.tc_ZONEVOL4.Disable()
                self.sliderZone4.Disable()

        curZoneNum += 1     
        xIndex +=1

    # -------------------------------------------------------------------------
    # [14,15] - Zone5
        if curZoneNum < len(zoneNAME):        
            self.ck_ZONE5 = wx.CheckBox(self, -1, zoneNAME[curZoneNum], name='5')
            self.ck_ZONE5.SetToolTip(wx.ToolTip("Click here to monitor volume for this zone."))
            list_checkboxIDNames.append(self.ck_ZONE5.GetId())
            sizer.Add(self.ck_ZONE5, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
                    
            self.tc_ZONEVOL5 = wx.TextCtrl(panel, -1, guiFunctions.configMe("volume", "slider5"), (0,0), (30,21))
            self.tc_ZONEVOL5.SetToolTip(wx.ToolTip("Set max volume for the zone (0-100)"))
            sizer.Add(self.tc_ZONEVOL5, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((30,22))
                    
            self.sliderZone5 = wx.Slider(self, -1, guiFunctions.configMe("volume", "slider5", integer=True), 0, 100, size=(400,10), name="sliderZone5", style=wx.SL_HORIZONTAL)

            self.sliderZone5.Bind(wx.EVT_SLIDER, lambda event: self.sliderUpdate(event, self.sliderZone5, self.tc_ZONEVOL5,), self.sliderZone5)
            self.tc_ZONEVOL5.Bind(wx.EVT_CHAR, lambda event: self.tcVolUpdate(event, self.sliderZone5, self.tc_ZONEVOL5,), self.tc_ZONEVOL5)
            self.ck_ZONE5.Bind(wx.EVT_CHECKBOX, lambda event: self.zoneCkClick(event, self.ck_ZONE5, self.sliderZone5, self.tc_ZONEVOL5,), self.ck_ZONE5)
            
            sizer.Add(self.sliderZone5, pos=(xIndex,1), span=(1, 3), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)        

            if self.ck_ZONE5.Value == False:
                self.tc_ZONEVOL5.Disable()
                self.sliderZone5.Disable()

        curZoneNum += 1                    
        xIndex +=1

    # -------------------------------------------------------------------------
    # [16,17] - Zone6
        if curZoneNum < len(zoneNAME):        
            self.ck_ZONE6 = wx.CheckBox(self, -1, zoneNAME[curZoneNum], name='6')
            self.ck_ZONE6.SetToolTip(wx.ToolTip("Click here to monitor volume for this zone."))
            list_checkboxIDNames.append(self.ck_ZONE6.GetId())
            sizer.Add(self.ck_ZONE6, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
                    
            self.tc_ZONEVOL6 = wx.TextCtrl(panel, -1, guiFunctions.configMe("volume", "slider6"), (0,0), (30,21))
            self.tc_ZONEVOL6.SetToolTip(wx.ToolTip("Set max volume for the zone (0-100)"))
            sizer.Add(self.tc_ZONEVOL6, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((30,22))
                    
            self.sliderZone6 = wx.Slider(self, -1, guiFunctions.configMe("volume", "slider6", integer=True), 0, 100, size=(400,10), name="sliderZone6", style=wx.SL_HORIZONTAL)

            self.sliderZone6.Bind(wx.EVT_SLIDER, lambda event: self.sliderUpdate(event, self.sliderZone6, self.tc_ZONEVOL6,), self.sliderZone6)
            self.tc_ZONEVOL6.Bind(wx.EVT_CHAR, lambda event: self.tcVolUpdate(event, self.sliderZone6, self.tc_ZONEVOL6,), self.tc_ZONEVOL6)
            self.ck_ZONE6.Bind(wx.EVT_CHECKBOX, lambda event: self.zoneCkClick(event, self.ck_ZONE6, self.sliderZone6, self.tc_ZONEVOL6,), self.ck_ZONE6)

            sizer.Add(self.sliderZone6, pos=(xIndex,1), span=(1, 3), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)        

            if self.ck_ZONE6.Value == False:
                self.tc_ZONEVOL6.Disable()
                self.sliderZone6.Disable()        

        curZoneNum += 1                    
        xIndex +=1
    # -------------------------------------------------------------------------
    # [18,19] - Zone7
        if curZoneNum < len(zoneNAME):        
            self.ck_ZONE7 = wx.CheckBox(self, -1, zoneNAME[curZoneNum], name='7')
            self.ck_ZONE7.SetToolTip(wx.ToolTip("Click here to monitor volume for this zone."))
            list_checkboxIDNames.append(self.ck_ZONE7.GetId())
            sizer.Add(self.ck_ZONE7, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
                    
            self.tc_ZONEVOL7 = wx.TextCtrl(panel, -1, guiFunctions.configMe("volume", "slider7"), (0,0), (30,21))
            self.tc_ZONEVOL7.SetToolTip(wx.ToolTip("Set max volume for the zone (0-100)"))
            sizer.Add(self.tc_ZONEVOL7, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((30,22))
                    
            self.sliderZone7 = wx.Slider(self, -1, guiFunctions.configMe("volume", "slider7", integer=True), 0, 100, size=(400,10), name="sliderZone7", style=wx.SL_HORIZONTAL)

            self.sliderZone7.Bind(wx.EVT_SLIDER, lambda event: self.sliderUpdate(event, self.sliderZone7, self.tc_ZONEVOL7,), self.sliderZone7)
            self.tc_ZONEVOL7.Bind(wx.EVT_CHAR, lambda event: self.tcVolUpdate(event, self.sliderZone7, self.tc_ZONEVOL7,), self.tc_ZONEVOL7)
            self.ck_ZONE7.Bind(wx.EVT_CHECKBOX, lambda event: self.zoneCkClick(event, self.ck_ZONE7, self.sliderZone7, self.tc_ZONEVOL7,), self.ck_ZONE7)
            
            sizer.Add(self.sliderZone7, pos=(xIndex,1), span=(1, 3), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)        

            if self.ck_ZONE7.Value == False:
                self.tc_ZONEVOL7.Disable()
                self.sliderZone7.Disable()            

        curZoneNum += 1                    
        xIndex +=1

    # -------------------------------------------------------------------------
    # [20,21] - Zone8
        if curZoneNum < len(zoneNAME):        
            self.ck_ZONE8 = wx.CheckBox(self, -1, zoneNAME[curZoneNum], name='8')
            self.ck_ZONE8.SetToolTip(wx.ToolTip("Click here to monitor volume for this zone."))
            list_checkboxIDNames.append(self.ck_ZONE8.GetId())
            sizer.Add(self.ck_ZONE8, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
                    
            self.tc_ZONEVOL8 = wx.TextCtrl(panel, -1, guiFunctions.configMe("volume", "slider8"), (0,0), (30,21))
            self.tc_ZONEVOL8.SetToolTip(wx.ToolTip("Set max volume for the zone (0-100)"))
            sizer.Add(self.tc_ZONEVOL8, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((30,22))
                    
            self.sliderZone8 = wx.Slider(self, -1, guiFunctions.configMe("volume", "slider8", integer=True), 0, 100, size=(400,10), name="sliderZone8", style=wx.SL_HORIZONTAL)

            self.sliderZone8.Bind(wx.EVT_SLIDER, lambda event: self.sliderUpdate(event, self.sliderZone8, self.tc_ZONEVOL8,), self.sliderZone8)
            self.tc_ZONEVOL8.Bind(wx.EVT_CHAR, lambda event: self.tcVolUpdate(event, self.sliderZone8, self.tc_ZONEVOL8,), self.tc_ZONEVOL8)
            self.ck_ZONE8.Bind(wx.EVT_CHECKBOX, lambda event: self.zoneCkClick(event, self.ck_ZONE8, self.sliderZone8, self.tc_ZONEVOL8,), self.ck_ZONE8)
                        
            sizer.Add(self.sliderZone8, pos=(xIndex,1), span=(1, 3), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)        

            if self.ck_ZONE8.Value == False:
                self.tc_ZONEVOL8.Disable()
                self.sliderZone8.Disable()                

        curZoneNum += 1                    
        xIndex +=1

    # -------------------------------------------------------------------------
    # [22,23] - Zone9
        if curZoneNum < len(zoneNAME):        
            self.ck_ZONE9 = wx.CheckBox(self, -1, zoneNAME[curZoneNum], name='9')
            self.ck_ZONE9.SetToolTip(wx.ToolTip("Click here to monitor volume for this zone."))
            list_checkboxIDNames.append(self.ck_ZONE9.GetId())

            sizer.Add(self.ck_ZONE9, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
                    
            self.tc_ZONEVOL9 = wx.TextCtrl(panel, -1, guiFunctions.configMe("volume", "slider9"), (0,0), (30,21))
            self.tc_ZONEVOL9.SetToolTip(wx.ToolTip("Set max volume for the zone (0-100)"))
            sizer.Add(self.tc_ZONEVOL9, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((30,22))
                    
            self.sliderZone9 = wx.Slider(self, -1, guiFunctions.configMe("volume", "slider9", integer=True), 0, 100, size=(400,10), name="sliderZone9", style=wx.SL_HORIZONTAL)

            self.sliderZone9.Bind(wx.EVT_SLIDER, lambda event: self.sliderUpdate(event, self.sliderZone9, self.tc_ZONEVOL9,), self.sliderZone9)
            self.tc_ZONEVOL9.Bind(wx.EVT_CHAR, lambda event: self.tcVolUpdate(event, self.sliderZone9, self.tc_ZONEVOL9,), self.tc_ZONEVOL9)
            self.ck_ZONE9.Bind(wx.EVT_CHECKBOX, lambda event: self.zoneCkClick(event, self.ck_ZONE9, self.sliderZone9, self.tc_ZONEVOL9,), self.ck_ZONE9)
                
            sizer.Add(self.sliderZone9, pos=(xIndex,1), span=(1, 3), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)        

            if self.ck_ZONE9.Value == False:
                self.tc_ZONEVOL9.Disable()
                self.sliderZone9.Disable()                    

            xIndex +=4

    # -------------------------------------------------------------------------
    # [22,23] - LAUNCH / DEFAULTS / AUTOPOP BUTTONS

        # - LAUNCH BUTTON
        self.bt_Launch = wx.Button(panel, label="Enable Volume Monitor")
        help_bt_Launch = "Click here to enable the volume monitor."
        self.bt_Launch.SetToolTip(wx.ToolTip(help_bt_Launch))
        self.bt_Launch.Bind(wx.EVT_BUTTON, self.launchVolClick, self.bt_Launch)    
    
        # **BROKEN** Add autopopulate button here
        
        # SAVE AS DEFAULTS
        self.bt_SaveDefaults = wx.Button(panel, label="Save Defaults")
        help_SaveDefaults = "Save current settings as default."
        self.bt_SaveDefaults.SetToolTip(wx.ToolTip(help_SaveDefaults))
        self.bt_SaveDefaults.Bind(wx.EVT_BUTTON, self.bt_SaveDefaultsClick, self.bt_SaveDefaults)
    
        sizer.Add(self.bt_Launch, pos=(xIndex,0), span=(1,2), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_SaveDefaults, pos=(xIndex,2), span=(1,3), flag=wx.EXPAND|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

    # -------------------------------------------------------------------------
    # Finalize the sizer
        self.worker = None
        pub.subscribe(self.setVolumePanel, 'setVolumePanel')
        sizer.AddGrowableCol(1)
        panel.SetSizer(sizer)

########################################################################################################################
# BIND Events per the panel above
########################################################################################################################

    def sliderUpdate(self, event, slider, textctrl):
        textctrl.SetValue(str(slider.GetValue()))

    def tcVolUpdate(self, event, slider, textctrl):
        slider.SetValue(int(textctrl.GetValue()))
        
    def zoneCkClick(self, event, ck, slider, textctrl):
        if ck.Value == False:
            slider.Disable()
            textctrl.Disable()
        else:
            slider.Enable()
            textctrl.Enable()

    def quietCkClick(self, event):
        if self.ck_QuietHours.Value == False:
            self.quietSlider.Disable()
            self.tc_QuietVol.Disable()
            self.tc_quietHr.Disable()
            self.tc_quietHrStop.Disable()
            self.label_QuietVol.Disable()
        else:
            self.quietSlider.Enable()
            self.tc_QuietVol.Enable()
            self.tc_quietHr.Enable()
            self.tc_quietHrStop.Enable()
            self.label_QuietVol.Enable()

    def muteHoursClick(self, event):
        if self.ck_MuteHours.Value == False:
            self.tc_MuteHr.Disable()
            self.tc_MuteHrStop.Disable()
        else:
            self.tc_MuteHr.Enable()
            self.tc_MuteHrStop.Enable()     

    def launchVolClick(self, event):
        if self.bt_Launch.Label == "Enable Volume Monitor":
            global zonesToMonitor
            zonesToMonitor = []
            # Build array of checkboxes set to True
            for item in range(len(list_checkboxIDNames)):
                if wx.FindWindowById(list_checkboxIDNames[item]).Value == True:        
                    zonesToMonitor.append(wx.FindWindowById(list_checkboxIDNames[item]).Label)
        
            self.worker = WorkerThread(self, self.startStop, int(self.tc_CheckInterval.Value))
            self.bt_Launch.Label = "Disable Volume Monitor"
        else:
            self.worker.ToKill = True
            self.bt_Launch.Label = "Enable Volume Monitor"
            
########################################################################################################################
# setVolumePanel: This is for the pubsub to receive a call to disable or enable the panel buttons.
########################################################################################################################
    def setVolumePanel(self, msg):
        if msg.data == "Disable":
            self.Disable()
        else:
            self.Enable()

########################################################################################################################
# bt_SaveDefaultsClick: A simple function to write out the defaults for the panel to GUIpref.ini
########################################################################################################################
    def bt_SaveDefaultsClick(self, event):
        section = "volume"
        guiFunctions.configWrite(section, "serverip", self.tc_serverIP.Value)
        guiFunctions.configWrite(section, "timeout", self.tc_CheckInterval.Value)
        guiFunctions.configWrite(section, "quietck", self.ck_QuietHours.Value)
        guiFunctions.configWrite(section, "quiethr", self.tc_quietHr.Value)
        guiFunctions.configWrite(section, "quiethrstop", self.tc_quietHrStop.Value)
        guiFunctions.configWrite(section, "quietslider", self.quietSlider.GetValue())
        guiFunctions.configWrite(section, "mutehr", self.tc_MuteHr.Value)
        guiFunctions.configWrite(section, "mutehrstop", self.tc_MuteHrStop.Value)
        guiFunctions.configWrite(section, "muteck", self.ck_MuteHours.Value)
        curZoneNum = 0
        while curZoneNum < len(zoneNAME):
            guiFunctions.configWrite(section, 'slider' + str((curZoneNum + 1)), wx.FindWindowByName('sliderZone' + str((curZoneNum + 1))).GetValue())
            curZoneNum += 1

        guiFunctions.statusText(self, "Defaults saved...")

########################################################################################################################
# startStop: Enable or disable the volume monitor loop
########################################################################################################################

    def startStop(self):
        global zonesToMonitor
        
        quietStart = self.tc_quietHr.Value
        quietStop = self.tc_quietHrStop.Value
        muteStart = self.tc_MuteHr.Value
        muteStop = self.tc_MuteHrStop.Value
    
        if os.name == 'nt':
            os.chdir(cmd_folder)
            os.chdir(os.pardir)
            os.chdir(os.pardir)
    
            # **BROKEN** - Check to ensure Sonospy is running. THIS IS BROKEN
            temp = os.system('wmic process where ^(CommandLine like "pythonw%pycpoint%")get ProcessID > windowsPID.pid 2> nul')
            import codecs
            with codecs.open('windowsPID.pid', encoding='utf-16') as f:
                windowsPid = []
                f.readline()
                windowsPid = f.readline()
                windowsPid = windowsPid.splitlines()
                if windowsPid == []:
                    # The file is empty, so Sonospy is not running already.
                    f.close()
                    os.remove('windowsPID.pid')              
                else:
                    pub.sendMessage(('alreadyRunning'), "alreadyRunning")
            os.chdir(cmd_folder)
    
        # Guts of the loop... trying to figoure out how to thread this.     
        if zonesToMonitor != []: 
            j = 0
            for i in zonesToMonitor:
                # Reset all variables in the loop for safety.
                maxVOL = 0
                INFO = ''
                curVOL = []
                url = ''
                
                # 6 Set the input zone: curl -s http://"$ipADDR":"$portNUM"/data/rendererData?data=R::"$zoneNAME"%20%28ZP%29 &>/dev/null
                url = 'http://' + ip_address + ':' + self.tc_serverPort.Value + '/data/rendererData?data=R::' + wx.FindWindowByLabel(i).Label
                urllib.urlopen(url).read()
                time.sleep(timeout)
                urllib.urlopen(url).read()

                if debugMe == True:
                    guiFunctions.debug('ZONE: ' + i)
                    guiFunctions.debug('INPUT URL: ' + url)
                    
                # Get the volume level for the zonesToMonitor[i]
                zoneNum = wx.FindWindowByLabel(i).GetName()
                maxVOL = wx.FindWindowByName('sliderZone' + zoneNum).GetValue()
                
                # 7 Grab relevant info about the active zone: INFO=$(curl -s $(echo "http://$ipADDR:$portNUM/data/rendererAction?data=class" | sed 's/ //g'))
                url = "http://" + ip_address + ":" + self.tc_serverPort.Value +"/data/rendererAction?data=class"
                INFO = urllib.urlopen(url).read()
                if debugMe == True:
                    guiFunctions.debug('INFO URL: ' + url)
                    guiFunctions.debug('INFO: ' + INFO)
                # 8 Check for current time to get curTIME
                curTime = datetime.datetime.now()
                curTime = curTime.strftime("%H:%M")
    
                # 9 Setup loop for curTIME vs. Quiet Hours vs. Mute Hours
                # get quiet hours start and stop.  get quiet hour volume
                if self.ck_QuietHours.Value == True:
                    quietStartHr = self.tc_quietHr.Value
                    quietEndHr = self.tc_quietHrStop.Value
                    quietVol = self.tc_QuietVol.Value
                    if (curTime > quietStartHr) and (curTime < quietEndHr):
                        guiFunctions.debug('In quiet hour conditional...')
                        maxVOL = quietVol            
    
                # get mute hours start and stop.
                if self.ck_MuteHours.Value == True:
                    muteStartHr = self.tc_MuteHr.Value
                    muteEndHr = self.tc_MuteHrStop.Value                   
                    if (curTime > muteStartHr) and (curTime < muteEndHr):
                        guiFunctions.debug('In mute hour conditional...')
                        maxVOL = 0
    
                # 10 Strip INFO to just the Volume number to test against, assign to curVOL
                curVOL = re.findall('(?<=_\|_VOLUME::).*?(?=_\|_)', INFO)
 
                if curVOL == '':
                    curVOL = 0
    
                # Convert from a list to an int for comparisons below.
                curVOL = map(int, curVOL)             

                # 13 Check curVOL > maxVOLUME, if true: curl -s http://"$ipADDR":"$portNUM"/data/rendererAction?data=VOLUME::"$maxVOLUME" &>/dev/null                
                if curVOL[0] > int(maxVOL):
                    url = "http://" + ip_address + ":" + self.tc_serverPort.Value + "/data/rendererAction?data=VOLUME::" + str(maxVOL)
                    if debugMe == True:
                        guiFunctions.debug("INFO: " + INFO)
                        guiFunctions.debug('SET URL: ' + url)
                        guiFunctions.debug("Adjusting ZONE: " + i + " from current volume: " + str(curVOL) + " to max volume: " + str(maxVOL))
                    
                    urllib.urlopen(url).read()
                j += 1
    
    




        
        
        
        
        
        
        

        
    