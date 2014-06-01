###############################################################################
# Launch Tab for use with sonospyGUI.py
###############################################################################
# launchTab.py copyright (c) 2010-2014 John Chowanec
# mutagen copyright (c) 2005 Joe Wreschnig, Michael Urman (mutagen is Licensed
# under GPL version 2.0)
# Sonospy Project copyright (c) 2010-2014 Mark Henkelis
#   (specifics for this file: sonospy_proxy, sonospy_web, sonospy_stop)
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
# guiFunctions.py Author: John Chowanec <chowanec@gmail.com>
# sonospy_proxy Author: Mark Henkelis <mark.henkelis@tesco.net>
# sonospy_stop Author: Mark Henkelis <mark.henkelis@tesco.net>
# sonospy_web Author: Mark Henkelis <mark.henkelis@tesco.net>
###############################################################################
# TODO:
# - Look at the README file.
###############################################################################

import wx
#from wxPython.wx import *
import os
import subprocess
import guiFunctions
from wx.lib.pubsub import setuparg1
from wx.lib.pubsub import pub

list_checkboxID = []
list_checkboxLabel = []
list_txtctrlID = []
list_txtctrlLabel = []
list_buttonID = []
list_userindexLabel = []
list_userindexID = []
sonospyRunning = False

class LaunchPanel(wx.Panel):
    """
    Launch Tab for finding and launching databases
    """
    #----------------------------------------------------------------------


    def __init__(self, parent):
        """"""
        wx.Panel.__init__(self, parent=parent, id=wx.ID_ANY)

        super(LaunchPanel, self)
        self.initialize()

    def initialize(self):
       
        panel = self
        
        # SET THE SIZER OBJECT UP
        sizer = wx.GridBagSizer(13, 4)

        # SET BASELINE INDEX VARIABLES
        xIndex = 0
        yIndex = 0

        # GET INI LIST FOR USER INDEXES
        cmd_folder = os.path.dirname(os.path.abspath(__file__))
        os.chdir(os.pardir)
        iniList = guiFunctions.scrubINI(os.getcwd(), "*.ini")
        os.chdir(cmd_folder)        
    # -------------------------------------------------------------------------
    # [0] Make Header Columns 
        self.label_ProxyName = wx.StaticText(panel, label="Display Name")
        self.label_UserIndexName = wx.StaticText(panel, label="User Index")
        self.ck_EnableAll = wx.CheckBox(panel, label="Enable All")
        help_EnableAll = "Click here to enable or disable all the databases below."
        self.ck_EnableAll.SetToolTip(wx.ToolTip(help_EnableAll))
        self.bt_AutoPopulate = wx.Button(panel, label="Auto Populate")
        help_AutoPopulate = "Autopopulate with up to 8 found databases."
        self.bt_AutoPopulate.SetToolTip(wx.ToolTip(help_AutoPopulate))
        self.bt_AutoPopulate.Bind(wx.EVT_BUTTON, self.bt_AutoPopulateClick, self.bt_AutoPopulate)

        self.bt_Clear = wx.Button(panel, label="Clear")
        help_Clear = "Clear database fields."
        self.bt_Clear.SetToolTip(wx.ToolTip(help_Clear))
        self.bt_Clear.Bind(wx.EVT_BUTTON, self.bt_ClearClick, self.bt_Clear)

        self.ck_EnableAll.Bind(wx.EVT_CHECKBOX, self.enableAllChecks, self.ck_EnableAll)
        sizer.Add(self.ck_EnableAll, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
        sizer.Add(self.label_ProxyName, pos=(xIndex, 1), flag=wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
        sizer.Add(self.label_UserIndexName, pos=(xIndex, 2), flag=wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
        sizer.Add(self.bt_Clear, pos=(xIndex, 3), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.TOP|wx.ALIGN_RIGHT, border=10)
        sizer.Add(self.bt_AutoPopulate, pos=(xIndex, 4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
      
        xIndex +=1
    # -------------------------------------------------------------------------
    # [1] Separator line 

        hl_SepLine1 = wx.StaticLine(panel, 0, (250, 50), (300,1))
        sizer.Add(hl_SepLine1, pos=(xIndex, 0), span=(1, 5), flag=wx.EXPAND)
        xIndex +=1

    # -------------------------------------------------------------------------
    # [2-9] Checkbox, database name and proxy name field, plus browse button
    # -------------------------------------------------------------------------
    # [2] - DB1
        self.ck_DB1 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB1.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))

        self.tc_DB1 = wx.TextCtrl(panel, -1, "", (0,0), (60,21))
        self.tc_DB1.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))

        self.comboDB1 = wx.ComboBox(panel, -1, "", (25,25), (60,20), iniList, wx.CB_DROPDOWN)
        self.comboDB1.Bind(wx.EVT_COMBOBOX, self.updateCombo, self.comboDB1)
        self.comboDB1.SetToolTip(wx.ToolTip("Set user index file if using SMAPI."))
        
        self.bt_DB1 = wx.Button(self, label="Browse")
        
        self.bt_DB1.tc = self.tc_DB1
        self.bt_DB1.ck = self.ck_DB1

        sizer.Add(self.ck_DB1, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB1, pos=(xIndex,1), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((200,22))
        sizer.Add(self.comboDB1, pos=(xIndex,2), span=(1,2), flag=wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB1, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)
        
        self.ck_DB1.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB1)
        self.bt_DB1.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB1)

        # Read in config
        self.ck_DB1.Value = guiFunctions.configMe("launch", "db1_check", bool=True)
        self.ck_DB1.Label =  guiFunctions.configMe("launch", "db1_dbname")
        self.tc_DB1.Value = guiFunctions.configMe("launch", "db1_proxyname")
        self.comboDB1.Select(guiFunctions.configMe("launch", "db1_userindex", integer=True))

        if self.ck_DB1.Label == "":
            self.ck_DB1.Label = "<add database>"

        if self.ck_DB1.Label == "<add database>":
            self.ck_DB1.Disable()

        # Add items to lists
        list_checkboxID.append(self.ck_DB1.GetId())
        list_checkboxLabel.append(self.ck_DB1.GetLabel())
        list_txtctrlID.append(self.tc_DB1.GetId())
        list_txtctrlLabel.append(self.tc_DB1.Value)
        list_userindexID.append(self.comboDB1.GetId())
        list_userindexLabel.append(self.comboDB1.Value)

        xIndex +=1
    # -------------------------------------------------------------------------
    # [3] - DB2
        self.ck_DB2 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB2.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))
        
        self.tc_DB2 = wx.TextCtrl(panel, -1, "", (0,0), (60,21))
        self.tc_DB2.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))
        
        self.comboDB2 = wx.ComboBox(panel, -1, "", (25,25), (60,20), iniList, wx.CB_DROPDOWN)
        self.comboDB2.Bind(wx.EVT_COMBOBOX, self.updateCombo, self.comboDB2)
        self.comboDB2.SetToolTip(wx.ToolTip("Set user index file if using SMAPI."))
        
        self.bt_DB2 = wx.Button(self, label="Browse")
        
        self.bt_DB2.tc = self.tc_DB2
        self.bt_DB2.ck = self.ck_DB2
        
        sizer.Add(self.ck_DB2, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB2, pos=(xIndex,1), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((200,22))
        sizer.Add(self.comboDB2, pos=(xIndex,2), span=(1,2), flag=wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB2, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)
        
        self.ck_DB2.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB2)
        self.bt_DB2.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB2)
        
        # Read in config
        self.ck_DB2.Value = guiFunctions.configMe("launch", "db2_check", bool=True)
        self.ck_DB2.Label =  guiFunctions.configMe("launch", "db2_dbname")
        self.tc_DB2.Value = guiFunctions.configMe("launch", "db2_proxyname")
        self.comboDB2.Select(guiFunctions.configMe("launch", "db2_userindex", integer=True))
        
        if self.ck_DB2.Label == "":
            self.ck_DB2.Label = "<add database>"
        
        if self.ck_DB2.Label == "<add database>":
            self.ck_DB2.Disable()
        
        # Add items to lists
        list_checkboxID.append(self.ck_DB2.GetId())
        list_checkboxLabel.append(self.ck_DB2.GetLabel())
        list_txtctrlID.append(self.tc_DB2.GetId())
        list_txtctrlLabel.append(self.tc_DB2.Value)
        list_userindexID.append(self.comboDB2.GetId())
        list_userindexLabel.append(self.comboDB2.Value)
        
        xIndex +=1
    # -------------------------------------------------------------------------
    # [4] - DB3
        self.ck_DB3 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB3.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))
    
        self.tc_DB3 = wx.TextCtrl(panel, -1, "", (0,0), (60,21))
        self.tc_DB3.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))
    
        self.comboDB3 = wx.ComboBox(panel, -1, "", (25,25), (60,20), iniList, wx.CB_DROPDOWN)
        self.comboDB3.Bind(wx.EVT_COMBOBOX, self.updateCombo, self.comboDB3)
        self.comboDB3.SetToolTip(wx.ToolTip("Set user index file if using SMAPI."))
        
        self.bt_DB3 = wx.Button(self, label="Browse")
        
        self.bt_DB3.tc = self.tc_DB3
        self.bt_DB3.ck = self.ck_DB3
        
        sizer.Add(self.ck_DB3, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB3, pos=(xIndex,1), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((200,22))
        sizer.Add(self.comboDB3, pos=(xIndex,2), span=(1,2), flag=wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB3, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)
        
        self.ck_DB3.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB3)
        self.bt_DB3.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB3)
        
        # Read in config
        self.ck_DB3.Value = guiFunctions.configMe("launch", "DB3_check", bool=True)
        self.ck_DB3.Label =  guiFunctions.configMe("launch", "DB3_dbname")
        self.tc_DB3.Value = guiFunctions.configMe("launch", "DB3_proxyname")
        self.comboDB3.Select(guiFunctions.configMe("launch", "DB3_userindex", integer=True))
        
        if self.ck_DB3.Label == "":
            self.ck_DB3.Label = "<add database>"
        
        if self.ck_DB3.Label == "<add database>":
            self.ck_DB3.Disable()
        
        # Add items to lists
        list_checkboxID.append(self.ck_DB3.GetId())
        list_checkboxLabel.append(self.ck_DB3.GetLabel())
        list_txtctrlID.append(self.tc_DB3.GetId())
        list_txtctrlLabel.append(self.tc_DB3.Value)
        list_userindexID.append(self.comboDB3.GetId())
        list_userindexLabel.append(self.comboDB3.Value)
        
        xIndex +=1
    # -------------------------------------------------------------------------
    # [5] - DB4
        self.ck_DB4 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB4.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))
    
        self.tc_DB4 = wx.TextCtrl(panel, -1, "", (0,0), (60,21))
        self.tc_DB4.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))
    
        self.comboDB4 = wx.ComboBox(panel, -1, "", (25,25), (60,20), iniList, wx.CB_DROPDOWN)
        self.comboDB4.Bind(wx.EVT_COMBOBOX, self.updateCombo, self.comboDB4)
        self.comboDB4.SetToolTip(wx.ToolTip("Set user index file if using SMAPI."))
        
        self.bt_DB4 = wx.Button(self, label="Browse")
        
        self.bt_DB4.tc = self.tc_DB4
        self.bt_DB4.ck = self.ck_DB4
        
        sizer.Add(self.ck_DB4, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB4, pos=(xIndex,1), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((200,22))
        sizer.Add(self.comboDB4, pos=(xIndex,2), span=(1,2), flag=wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB4, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)
        
        self.ck_DB4.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB4)
        self.bt_DB4.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB4)
        
        # Read in config
        self.ck_DB4.Value = guiFunctions.configMe("launch", "DB4_check", bool=True)
        self.ck_DB4.Label =  guiFunctions.configMe("launch", "DB4_dbname")
        self.tc_DB4.Value = guiFunctions.configMe("launch", "DB4_proxyname")
        self.comboDB4.Select(guiFunctions.configMe("launch", "DB4_userindex", integer=True))
        
        if self.ck_DB4.Label == "":
            self.ck_DB4.Label = "<add database>"
        
        if self.ck_DB4.Label == "<add database>":
            self.ck_DB4.Disable()
        
        # Add items to lists
        list_checkboxID.append(self.ck_DB4.GetId())
        list_checkboxLabel.append(self.ck_DB4.GetLabel())
        list_txtctrlID.append(self.tc_DB4.GetId())
        list_txtctrlLabel.append(self.tc_DB4.Value)
        list_userindexID.append(self.comboDB4.GetId())
        list_userindexLabel.append(self.comboDB4.Value)
        
        xIndex +=1

    # -------------------------------------------------------------------------
    # [6] - DB5
        self.ck_DB5 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB5.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))
    
        self.tc_DB5 = wx.TextCtrl(panel, -1, "", (0,0), (60,21))
        self.tc_DB5.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))
    
        self.comboDB5 = wx.ComboBox(panel, -1, "", (25,25), (60,20), iniList, wx.CB_DROPDOWN)
        self.comboDB5.Bind(wx.EVT_COMBOBOX, self.updateCombo, self.comboDB5)
        self.comboDB5.SetToolTip(wx.ToolTip("Set user index file if using SMAPI."))
        
        self.bt_DB5 = wx.Button(self, label="Browse")
        
        self.bt_DB5.tc = self.tc_DB5
        self.bt_DB5.ck = self.ck_DB5
        
        sizer.Add(self.ck_DB5, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB5, pos=(xIndex,1), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((200,22))
        sizer.Add(self.comboDB5, pos=(xIndex,2), span=(1,2), flag=wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB5, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)
        
        self.ck_DB5.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB5)
        self.bt_DB5.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB5)
        
        # Read in config
        self.ck_DB5.Value = guiFunctions.configMe("launch", "DB5_check", bool=True)
        self.ck_DB5.Label =  guiFunctions.configMe("launch", "DB5_dbname")
        self.tc_DB5.Value = guiFunctions.configMe("launch", "DB5_proxyname")
        self.comboDB5.Select(guiFunctions.configMe("launch", "DB5_userindex", integer=True))
        
        if self.ck_DB5.Label == "":
            self.ck_DB5.Label = "<add database>"
        
        if self.ck_DB5.Label == "<add database>":
            self.ck_DB5.Disable()
        
        # Add items to lists
        list_checkboxID.append(self.ck_DB5.GetId())
        list_checkboxLabel.append(self.ck_DB5.GetLabel())
        list_txtctrlID.append(self.tc_DB5.GetId())
        list_txtctrlLabel.append(self.tc_DB5.Value)
        list_userindexID.append(self.comboDB5.GetId())
        list_userindexLabel.append(self.comboDB5.Value)
        
        xIndex +=1

    # -------------------------------------------------------------------------
    # [7] - DB6
        self.ck_DB6 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB6.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))
        
        self.tc_DB6 = wx.TextCtrl(panel, -1, "", (0,0), (60,21))
        self.tc_DB6.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))
        
        self.comboDB6 = wx.ComboBox(panel, -1, "", (25,25), (60,20), iniList, wx.CB_DROPDOWN)
        self.comboDB6.Bind(wx.EVT_COMBOBOX, self.updateCombo, self.comboDB6)
        self.comboDB6.SetToolTip(wx.ToolTip("Set user index file if using SMAPI."))
        
        self.bt_DB6 = wx.Button(self, label="Browse")
        
        self.bt_DB6.tc = self.tc_DB6
        self.bt_DB6.ck = self.ck_DB6
        
        sizer.Add(self.ck_DB6, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB6, pos=(xIndex,1), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((200,22))
        sizer.Add(self.comboDB6, pos=(xIndex,2), span=(1,2), flag=wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB6, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)
        
        self.ck_DB6.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB6)
        self.bt_DB6.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB6)
        
        # Read in config
        self.ck_DB6.Value = guiFunctions.configMe("launch", "DB6_check", bool=True)
        self.ck_DB6.Label =  guiFunctions.configMe("launch", "DB6_dbname")
        self.tc_DB6.Value = guiFunctions.configMe("launch", "DB6_proxyname")
        self.comboDB6.Select(guiFunctions.configMe("launch", "DB6_userindex", integer=True))
        
        if self.ck_DB6.Label == "":
            self.ck_DB6.Label = "<add database>"
        
        if self.ck_DB6.Label == "<add database>":
            self.ck_DB6.Disable()
        
        # Add items to lists
        list_checkboxID.append(self.ck_DB6.GetId())
        list_checkboxLabel.append(self.ck_DB6.GetLabel())
        list_txtctrlID.append(self.tc_DB6.GetId())
        list_txtctrlLabel.append(self.tc_DB6.Value)
        list_userindexID.append(self.comboDB6.GetId())
        list_userindexLabel.append(self.comboDB6.Value)
        
        xIndex +=1

    # -------------------------------------------------------------------------
    # [8] - DB7
        self.ck_DB7 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB7.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))
        
        self.tc_DB7 = wx.TextCtrl(panel, -1, "", (0,0), (60,21))
        self.tc_DB7.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))
        
        self.comboDB7 = wx.ComboBox(panel, -1, "", (25,25), (60,20), iniList, wx.CB_DROPDOWN)
        self.comboDB7.Bind(wx.EVT_COMBOBOX, self.updateCombo, self.comboDB7)
        self.comboDB7.SetToolTip(wx.ToolTip("Set user index file if using SMAPI."))
        
        self.bt_DB7 = wx.Button(self, label="Browse")
        
        self.bt_DB7.tc = self.tc_DB7
        self.bt_DB7.ck = self.ck_DB7
        
        sizer.Add(self.ck_DB7, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB7, pos=(xIndex,1), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((200,22))
        sizer.Add(self.comboDB7, pos=(xIndex,2), span=(1,2), flag=wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB7, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)
        
        self.ck_DB7.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB7)
        self.bt_DB7.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB7)
        
        # Read in config
        self.ck_DB7.Value = guiFunctions.configMe("launch", "DB7_check", bool=True)
        self.ck_DB7.Label =  guiFunctions.configMe("launch", "DB7_dbname")
        self.tc_DB7.Value = guiFunctions.configMe("launch", "DB7_proxyname")
        self.comboDB7.Select(guiFunctions.configMe("launch", "DB7_userindex", integer=True))
        
        if self.ck_DB7.Label == "":
            self.ck_DB7.Label = "<add database>"
        
        if self.ck_DB7.Label == "<add database>":
            self.ck_DB7.Disable()
        
        # Add items to lists
        list_checkboxID.append(self.ck_DB7.GetId())
        list_checkboxLabel.append(self.ck_DB7.GetLabel())
        list_txtctrlID.append(self.tc_DB7.GetId())
        list_txtctrlLabel.append(self.tc_DB7.Value)
        list_userindexID.append(self.comboDB7.GetId())
        list_userindexLabel.append(self.comboDB7.Value)
        
        xIndex +=1

    # -------------------------------------------------------------------------
    # [9] - DB8
        self.ck_DB8 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB8.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))
        
        self.tc_DB8 = wx.TextCtrl(panel, -1, "", (0,0), (60,21))
        self.tc_DB8.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))
        
        self.comboDB8 = wx.ComboBox(panel, -1, "", (25,25), (60,20), iniList, wx.CB_DROPDOWN)
        self.comboDB8.Bind(wx.EVT_COMBOBOX, self.updateCombo, self.comboDB8)
        self.comboDB8.SetToolTip(wx.ToolTip("Set user index file if using SMAPI."))
        
        self.bt_DB8 = wx.Button(self, label="Browse")
        
        self.bt_DB8.tc = self.tc_DB8
        self.bt_DB8.ck = self.ck_DB8
        
        sizer.Add(self.ck_DB8, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB8, pos=(xIndex,1), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10).SetMinSize((200,22))
        sizer.Add(self.comboDB8, pos=(xIndex,2), span=(1,2), flag=wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB8, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)
        
        self.ck_DB8.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB8)
        self.bt_DB8.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB8)
        
        # Read in config
        self.ck_DB8.Value = guiFunctions.configMe("launch", "DB8_check", bool=True)
        self.ck_DB8.Label =  guiFunctions.configMe("launch", "DB8_dbname")
        self.tc_DB8.Value = guiFunctions.configMe("launch", "DB8_proxyname")
        self.comboDB8.Select(guiFunctions.configMe("launch", "DB8_userindex", integer=True))
        
        if self.ck_DB8.Label == "":
            self.ck_DB8.Label = "<add database>"
        
        if self.ck_DB8.Label == "<add database>":
            self.ck_DB8.Disable()
        
        # Add items to lists
        list_checkboxID.append(self.ck_DB8.GetId())
        list_checkboxLabel.append(self.ck_DB8.GetLabel())
        list_txtctrlID.append(self.tc_DB8.GetId())
        list_txtctrlLabel.append(self.tc_DB8.Value)
        list_userindexID.append(self.comboDB8.GetId())
        list_userindexLabel.append(self.comboDB8.Value)
        
        xIndex +=1
    
    # --------------------------------------------------------------------------
    # [12] Separator line 

        hl_SepLine1 = wx.StaticLine(panel, 0, (250, 50), (300,1))
        sizer.Add(hl_SepLine1, pos=(xIndex, 0), span=(1, 5), flag=wx.EXPAND)

        xIndex +=1
    # --------------------------------------------------------------------------
    # [13] Create and add a launch button and radios for Proxy vs. Web

    # - SMAPI CHECK BUTTON
        self.ck_SMAPI = wx.CheckBox(panel, label="Run as SMAPI service.")
        help_ck_SMAPI = "Run as the SMAPI interface to Sonospy."
        self.ck_SMAPI.SetToolTip(wx.ToolTip(help_ck_SMAPI))
        self.ck_SMAPI.Bind(wx.EVT_CHECKBOX, self.enableSMAPI, self.ck_SMAPI)
        self.ck_SMAPI.Value = guiFunctions.configMe("launch", "smapi", bool=True)

    # - PROXY ONLY CHECK BUTTON
        self.ck_ProxyOnly = wx.CheckBox(panel, label="Proxy Only Mode.")
        help_ck_ProxyOnly = "Disable the built in web GUI in Sonospy."
        self.ck_ProxyOnly.SetToolTip(wx.ToolTip(help_ck_ProxyOnly))
        self.ck_ProxyOnly.Bind(wx.EVT_CHECKBOX, self.proxyOnly, self.ck_ProxyOnly)
        self.ck_ProxyOnly.Value = guiFunctions.configMe("launch", "proxyonly", bool=True)

    # - LAUNCH MODE LABEL
        self.label_launchMode = wx.StaticText(panel, label="Select Launch Mode:")

    # - PROXY RADIO BUTTON
        self.rd_Proxy = wx.RadioButton(panel, label="Proxy")
        help_rd_Proxy = "Run only as a proxy service in the background."
        self.rd_Proxy.SetToolTip(wx.ToolTip(help_rd_Proxy))
        
    # - WEB RADIO BUTTON
        self.rd_Web = wx.RadioButton(panel, label="Web")
        help_rd_Web = "Run as the web interface to Sonospy."
        self.rd_Web.SetToolTip(wx.ToolTip(help_rd_Web))

        if guiFunctions.configMe("launch", "proxy", bool=True) == True:
            self.rd_Proxy.SetValue(True)
        else:
            self.rd_Web.SetValue(True)
    
        self.rd_Proxy.Bind(wx.EVT_RADIOBUTTON, self.updateScratchPad, self.rd_Proxy)
        self.rd_Web.Bind(wx.EVT_RADIOBUTTON, self.updateScratchPad, self.rd_Web)

        sizer.Add(self.ck_SMAPI, pos=(xIndex,0), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)        
        sizer.Add(self.ck_ProxyOnly, pos=(xIndex,1), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)    
        sizer.Add(self.label_launchMode, pos=(xIndex, 2), flag=wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT|wx.RIGHT, border=1)
        sizer.Add(self.rd_Proxy, pos=(xIndex,3), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.rd_Web, pos=(xIndex,4), flag=wx.ALIGN_CENTER_VERTICAL, border=10)

        xIndex +=1

    # --------------------------------------------------------------------------
    # [13] Create Scratch Pad

        self.sb_Scratchpad = wx.StaticBox(panel, label="Scratchpad:", size=(200, 185))
        help_Scratchpad = "You can cut and paste this into a command/shell window..."
        scratchpadSizer = wx.StaticBoxSizer(self.sb_Scratchpad, wx.VERTICAL)
        self.tc_Scratchpad = wx.TextCtrl(panel, -1,"",size=(300, 185), style=wx.TE_MULTILINE|wx.TE_READONLY)
        self.tc_Scratchpad.SetToolTip(wx.ToolTip(help_Scratchpad))
        self.tc_Scratchpad.SetInsertionPoint(0)
        LogFont = wx.Font(7.5, wx.SWISS, wx.NORMAL, wx.NORMAL, False)
        self.tc_Scratchpad.SetFont(LogFont)

        scratchpadSizer.Add(self.tc_Scratchpad, flag=wx.EXPAND)
        sizer.Add(scratchpadSizer, pos=(xIndex, 0), span=(1,5), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.BOTTOM|wx.ALIGN_BOTTOM, border=10)

        xIndex += 1

    # --------------------------------------------------------------------------
    # [14] Launch Button and Save Default Button

        # - LAUNCH BUTTON
        self.bt_Launch = wx.Button(panel, label="Launch")
        help_bt_Launch = "Click here to launch the Sonospy service."
        self.bt_Launch.SetToolTip(wx.ToolTip(help_bt_Launch))
        self.bt_Launch.Bind(wx.EVT_BUTTON, self.startStopSonospy, self.bt_Launch)    

        # SAVE AS DEFAULTS
        self.bt_SaveDefaults = wx.Button(panel, label="Save Defaults")
        help_SaveDefaults = "Save current settings as default."
        self.bt_SaveDefaults.SetToolTip(wx.ToolTip(help_SaveDefaults))
        self.bt_SaveDefaults.Bind(wx.EVT_BUTTON, self.bt_SaveDefaultsClick, self.bt_SaveDefaults)
        
        sizer.Add(self.bt_Launch, pos=(xIndex,0), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_SaveDefaults, pos=(xIndex,4), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        
        # Bind a text event to autoupdate the scratchpad if the user decides
        # to edit the proxy name manually.
        self.tc_DB1.Bind(wx.EVT_TEXT, self.updateScratchPad, self.tc_DB1)
        self.tc_DB2.Bind(wx.EVT_TEXT, self.updateScratchPad, self.tc_DB2)
        self.tc_DB3.Bind(wx.EVT_TEXT, self.updateScratchPad, self.tc_DB3)
        self.tc_DB4.Bind(wx.EVT_TEXT, self.updateScratchPad, self.tc_DB4)
        self.tc_DB5.Bind(wx.EVT_TEXT, self.updateScratchPad, self.tc_DB5)
        self.tc_DB6.Bind(wx.EVT_TEXT, self.updateScratchPad, self.tc_DB6)
        self.tc_DB7.Bind(wx.EVT_TEXT, self.updateScratchPad, self.tc_DB7)
        self.tc_DB8.Bind(wx.EVT_TEXT, self.updateScratchPad, self.tc_DB8)

        pub.subscribe(self.setLaunchPanel, 'setLaunchPanel')
        pub.subscribe(self.startStopSonospy, 'startStopSonospy')
        pub.subscribe(self.alreadyRunning, 'alreadyRunning')

        sizer.AddGrowableCol(2)
        panel.SetSizer(sizer)

        self.buildLaunch()

    ########################################################################################################################
    # setLaunchPanel: Used to enable and disable the panel, and is called from
    #                 other tabs.
    ########################################################################################################################
    def setLaunchPanel(self, msg):
        if msg.data == "Disable":
            self.Disable()
        else:
            self.Enable()

    ########################################################################################################################
    # browseDB: Used to open a sonospy database file (.sdb, .db)
    ########################################################################################################################
    def browseDB(self, event):
        dbPath = guiFunctions.configMe("general", "default_database_path")
        extensions = guiFunctions.configMe("general", "database_extensions") 
        
        selected = guiFunctions.fileBrowse("Select database...", dbPath, "Sonospy Database (" + extensions + ")|" + \
                                extensions.replace(" ", ";") + "|All files (*.*)|*.*")

        for selection in selected:
            basename, extension = os.path.splitext(selection)
            event.GetEventObject().tc.Value = basename
            event.GetEventObject().ck.Label = selection
            event.GetEventObject().ck.Enable()
            event.GetEventObject().ck.Value = True
            guiFunctions.statusText(self, "Database: " + selection + " selected...")

        self.buildLaunch()        
    
    ########################################################################################################################
    # OnCheck: Used anytime a checkbox is clicked, to make sure we are updating
    #          the scratchpad to reflect changes.
    ########################################################################################################################
    def OnCheck(self, event):
    # DEBUG ------------------------------------------------------------------------
    #    for item in range(len(list_checkboxID)):
    #        print "Checkbox " + str(item) + ":\t\tID:" + str(list_checkboxID[item]) + "\tLABEL:" + list_checkboxLabel[item]
    #        print "Text Control " + str(item) + ":\t\tID:" + str(list_txtctrlID[item]) + "\tLABEL:" + list_txtctrlLabel[item]
    #        print "User Index " + str(item) + ":\t\tID:" + str(list_userindexID[item]) + "\tLABEL:" + list_userindexLabel[item]
    #------------------------------------------------------------------------------
        self.buildLaunch()

    ########################################################################################################################
    # updateCombo: Used anytime a wxComboBox is changed/updated.
    ########################################################################################################################
    def updateCombo(self, event):
        self.buildLaunch()
        
    ########################################################################################################################
    # enableAllChecks: If selected, it will enable every available database.
    ########################################################################################################################
    def enableAllChecks(self, event):
        if self.ck_EnableAll.Value == True:
            self.ck_EnableAll.Label = "Disable All"
        else:
            self.ck_EnableAll.Label = "Enable All"

        for item in range(len(list_checkboxID)):
            if wx.FindWindowById(list_checkboxID[item]).Label != "<add database>":
                wx.FindWindowById(list_checkboxID[item]).Value = self.ck_EnableAll.Value
        self.buildLaunch()

    ########################################################################################################################
    # enableSMAPI: Updates scracthpad if SMAPI is selected
    ########################################################################################################################
    def enableSMAPI(self, event):
        self.buildLaunch()

    ########################################################################################################################
    # alreadyRunning: Pubsub function to determine from other tabs (based on PID), if we're already running.
    ########################################################################################################################
    def alreadyRunning(self, msg):
        if msg.data == "alreadyRunning":
            self.bt_Launch.Label = "Stop"
            self.buildLaunch()
        
    ########################################################################################################################
    # proxyOnly: Updates scracthpad if Proxy Only is selected
    ######################################################################################################################## 
    def proxyOnly(self, event):
        self.buildLaunch()
        
    ########################################################################################################################
    # startStopSonospy: Used in sonospyGUI.py to call a stop to the Sonospy service so that we can use this from the
    #                   systray.  Used in the above function to be a bit more efficient as well.
    ########################################################################################################################
    def startStopSonospy(self, event):
        # Reset folder to where this file lives, and then drop down two levels to the "root" of Sonospy.
        cmd_folder = os.path.dirname(os.path.abspath(__file__))
        os.chdir(cmd_folder)
        os.chdir(os.pardir)
        os.chdir(os.pardir)

        launchCMD = self.buildLaunch()
                
        # This would mean we have no databases selected and should, thus, throw up an error for the user.
        if launchCMD == 0:
            guiFunctions.errorMsg('Error!', 'You have no databases selected for launch.')
        else:            
            # Check our GUIpref.ini to see if we want to be bothered with warnings.  If we do
            # then throw up a popup to the user reminding them to open their ports to make
            # multiple SMAPI databases work.
            if guiFunctions.configMe("general", "supresswarnings", bool=True) == False:
                if launchCMD.count("-sSonospy=") > 1:
                    wx.MessageBox('Please make sure that you have enough ports open to run multiple SMAPI services in pycpoint.ini', 'Warning!', wx.OK | wx.ICON_INFORMATION)
    
            # DEBUG ------------------------------------------------------------------------
            # print launchCMD
            # ------------------------------------------------------------------------------
    
            if os.name != 'nt':
                proc = subprocess.Popen([launchCMD],shell=True)
                if self.bt_Launch.Label == "Stop":
                    self.bt_Launch.Label = "Launch"
                    self.bt_Launch.SetToolTip(wx.ToolTip("Click here to launch the Sonospy service."))
                    guiFunctions.statusText(self, "Sonospy Service Stopped...")
                    self.setButtons(True)
                    sonospyRunning = True
                    self.buildLaunch()
                    pub.sendMessage(('CreateMenu'), "Exit Sonospy")
                else:
                    self.bt_Launch.Label = "Stop"
                    self.bt_Launch.SetToolTip(wx.ToolTip("Click here to stop the Sonospy service."))
                    guiFunctions.statusText(self, "Sonospy Service Started...")
                    self.setButtons(False)
                    sonospyRunning = False
                    self.buildLaunch()
                    pub.sendMessage(('CreateMenu'), "Stop Sonospy")
            else:
                proc = subprocess.Popen(launchCMD, shell=True)
                # Trap the windows processID into a windowsPID.txt file so we can read it later to kill the process on stop.
                temp = os.system('wmic process where ^(CommandLine like "pythonw%pycpoint%")get ProcessID > windowsPID.pid 2> nul')
                if self.bt_Launch.Label == "Stop":
                    self.bt_Launch.Label = "Launch"
                    self.bt_Launch.SetToolTip(wx.ToolTip("Click here to launch the Sonospy service."))
                    guiFunctions.statusText(self, "Sonospy Service Stopped...")
                    if launchCMD.count("TASKKILL") > 0:
                        if os.path.isfile('windowsPID.pid') == True:
                            os.remove('windowsPID.pid')                
                    self.setButtons(True)
                    sonospyRunning = True
                    self.buildLaunch()
                    pub.sendMessage(('CreateMenu'), "Exit Sonospy")
                else:
                    self.bt_Launch.Label = "Stop"
                    self.bt_Launch.SetToolTip(wx.ToolTip("Click here to stop the Sonospy service."))
                    guiFunctions.statusText(self, "Sonospy Service Started...")
                    self.setButtons(False)
                    sonospyRunning = False
                    self.buildLaunch()
                    pub.sendMessage(('CreateMenu'), "Stop Sonospy")

        # set back to original working directory
        os.chdir(cmd_folder)
        
    ########################################################################################################################
    # bt_SaveDefaultsClick: Will write out the current values in this panel as the defaults in GUIpref.ini    
    ########################################################################################################################
    def bt_SaveDefaultsClick(self, event):
        section = "launch"
        comment = "# Commments for the launch tab. 1 = true for the radio and checkboxes."
        comment2 = "# String values will be entered into the default text boxes on launch."
        
        guiFunctions.configWrite(section, "proxy", self.rd_Proxy.Value)
        guiFunctions.configWrite(section, "db1_check", self.ck_DB1.Value)
        guiFunctions.configWrite(section, "db1_dbname", self.ck_DB1.Label)
        guiFunctions.configWrite(section, "db1_proxyname", self.tc_DB1.Value)
        guiFunctions.configWrite(section, "db1_userindex", self.comboDB1.GetCurrentSelection())
        guiFunctions.configWrite(section, "db2_check", self.ck_DB2.Value)
        guiFunctions.configWrite(section, "db2_dbname", self.ck_DB2.Label)
        guiFunctions.configWrite(section, "db2_proxyname", self.tc_DB2.Value)
        guiFunctions.configWrite(section, "db2_userindex", self.comboDB2.GetCurrentSelection())
        guiFunctions.configWrite(section, "db3_check", self.ck_DB3.Value)
        guiFunctions.configWrite(section, "db3_dbname", self.ck_DB3.Label)
        guiFunctions.configWrite(section, "db3_proxyname", self.tc_DB3.Value)
        guiFunctions.configWrite(section, "db3_userindex", self.comboDB3.GetCurrentSelection())
        guiFunctions.configWrite(section, "db4_check", self.ck_DB4.Value)
        guiFunctions.configWrite(section, "db4_dbname", self.ck_DB4.Label)
        guiFunctions.configWrite(section, "db4_proxyname", self.tc_DB4.Value)
        guiFunctions.configWrite(section, "db4_userindex", self.comboDB4.GetCurrentSelection())
        guiFunctions.configWrite(section, "db5_check", self.ck_DB5.Value)
        guiFunctions.configWrite(section, "db5_dbname", self.ck_DB5.Label)
        guiFunctions.configWrite(section, "db5_proxyname", self.tc_DB5.Value)
        guiFunctions.configWrite(section, "db5_userindex", self.comboDB5.GetCurrentSelection())
        guiFunctions.configWrite(section, "db6_check", self.ck_DB6.Value)
        guiFunctions.configWrite(section, "db6_dbname", self.ck_DB6.Label)
        guiFunctions.configWrite(section, "db6_proxyname", self.tc_DB6.Value)
        guiFunctions.configWrite(section, "db6_userindex", self.comboDB6.GetCurrentSelection())
        guiFunctions.configWrite(section, "db7_check", self.ck_DB7.Value)
        guiFunctions.configWrite(section, "db7_dbname", self.ck_DB7.Label)
        guiFunctions.configWrite(section, "db7_proxyname", self.tc_DB7.Value)
        guiFunctions.configWrite(section, "db7_userindex", self.comboDB7.GetCurrentSelection())
        guiFunctions.configWrite(section, "db8_check", self.ck_DB8.Value)
        guiFunctions.configWrite(section, "db8_dbname", self.ck_DB8.Label)
        guiFunctions.configWrite(section, "db8_proxyname", self.tc_DB8.Value)
        guiFunctions.configWrite(section, "db8_userindex", self.comboDB8.GetCurrentSelection())
        guiFunctions.configWrite(section, "SMAPI", self.ck_SMAPI.Value)
        guiFunctions.configWrite(section, "proxyonly", self.ck_ProxyOnly.Value)

        guiFunctions.statusText(self, "Defaults saved...")

    ########################################################################################################################
    # bt_AutoPopulateClick: Scours the sonospy/ director for valid database files (as specified in the GUIpref.ini).  
    #                       Then populates the various fields with databases.
    ########################################################################################################################
    def bt_AutoPopulateClick(self, event):
        filters = guiFunctions.configMe("general", "database_extensions").split()

        # Set working directory to where launchTab.py lives
        cmd_folder = os.path.dirname(os.path.abspath(__file__))
        os.chdir(cmd_folder)
        os.chdir(os.pardir)

        #   Get a count of *database from the filesystem
        numDB = guiFunctions.scrubDB(os.getcwd(), filters)
        curCount = 0
        # Checkbox (enable, disable for launch)
        # textCtrl (for Proxy name in controller)
        # database name (based on *database)
        for db in numDB:

            if curCount > 7:
                pass
            else:
                if curCount == 0:
                    ck = self.ck_DB1
                    tc = self.tc_DB1
                if curCount == 1:
                    ck = self.ck_DB2
                    tc = self.tc_DB2
                if curCount == 2:
                    ck = self.ck_DB3
                    tc = self.tc_DB3
                if curCount == 3:
                    ck = self.ck_DB4
                    tc = self.tc_DB4
                if curCount == 4:
                    ck = self.ck_DB5
                    tc = self.tc_DB5
                if curCount == 5:
                    ck = self.ck_DB6
                    tc = self.tc_DB6
                if curCount == 6:
                    ck = self.ck_DB7
                    tc = self.tc_DB7
                if curCount == 7:
                    ck = self.ck_DB8
                    tc = self.tc_DB8

                basename, extension = os.path.splitext(db)
                tc.Value = basename
                ck.Label = db
                ck.Enable()
                ck.Value = True

            curCount +=1

             # DEBUG ------------------------------------------------------------------------
             # Save references to the widgets created dynamically
             #   list_checkboxID.append(check.GetId())
             #   list_checkboxLabel.append(check.GetLabel())
             #   list_txtctrlID.append(name.GetId())
             #   list_txtctrlLabel.append(name.Value)

             # Bind to event for later (DEBUG)
             #   check.Bind(wx.EVT_CHECKBOX, self.OnCheck, check)
             # ------------------------------------------------------------------------------
             
        self.buildLaunch()
        # set back to original working directory
        os.chdir(cmd_folder)

    ########################################################################################################################
    # bt_ClearClick: Clear the various fields to wipe the panel clean.
    ########################################################################################################################
    def bt_ClearClick(self, event):
        for item in range(len(list_checkboxID)):
            wx.FindWindowById(list_txtctrlID[item]).Value = ""
            wx.FindWindowById(list_checkboxID[item]).Label = "<add database>"
            wx.FindWindowById(list_checkboxID[item]).Value = False
            wx.FindWindowById(list_checkboxID[item]).Disable()
            wx.FindWindowById(list_userindexID[item]).Selection = 0
        self.buildLaunch()

    ########################################################################################################################
    # updateScratchPad: This is for a set of buttons, I don't know how to have a function called as an event yet.
    ########################################################################################################################
    def updateScratchPad(self, event):
        event.Skip()
        self.buildLaunch()

    ########################################################################################################################
    # buildLaunch: The bulk of this panel relies on this function.  It builds out the command that will ultimately be run
    #              and then updates the scratchpad to reflect the changes.
    ########################################################################################################################
    def buildLaunch(self):
        # Check for OS
        dbCount = 0
        
        if os.name == 'nt':
            cmdroot = 'sonospy_'
            launchME = cmdroot
            launchMode = '-wSonospy='
            
            # which version are we running?
            if self.rd_Proxy.Value == True:
                launchME += "p "
            if self.rd_Web.Value == True:
                launchME += "w "

        else:
            cmdroot = './'
            launchME = cmdroot + "sonospy_"
            launchMode = "-wSonospy="
            
            # which version are we running?
            if self.rd_Proxy.Value == True:
                launchME += "proxy "
            if self.rd_Web.Value == True:
                launchME += "web "

        if self.ck_SMAPI.Value == True:
            launchMode = '-sSonospy='
        else:
            lauchMode = '-wSonospy='

        # rebuild text labels now, user may have changed them
        for item in range(len(list_checkboxID)):
            list_txtctrlLabel[item] = wx.FindWindowById(list_txtctrlID[item]).Value
            list_checkboxLabel[item] = wx.FindWindowById(list_checkboxID[item]).Label
            list_userindexLabel[item]= wx.FindWindowById(list_userindexID[item]).Value

        # build out the command
        sonospyKill = False
        if self.bt_Launch.Label == "Stop":
            if os.name != 'nt':
                launchME = cmdroot + "sonospy_stop"
                sonospyKill = True
            else:
                import codecs

                if os.path.isfile('windowsPID.pid') == True: 
                    with codecs.open('windowsPID.pid', encoding='utf-16') as f:
                        f.readline()
                        windowsPid = f.readline()
                        windowsPid = windowsPid.splitlines()
                        launchME = "TASKKILL /F /PID " + windowsPid[0] + " > nul"
                        sonospyKill = True
                        self.tc_Scratchpad.Value = "Sonospy currently running with Windows Process ID: " + windowsPid[0] + "\n\nPress STOP below when finished."
        else:
            for item in range(len(list_checkboxID)):
                if wx.FindWindowById(list_checkboxID[item]).Value == True:
                    dbCount += 1
                    if self.ck_SMAPI.Value == True:
                        if list_userindexLabel[item] == '':
                            userindexLabel = 'defaultindex.ini'
                        else:
                            userindexLabel = list_userindexLabel[item]
                            
                        launchME += launchMode + list_txtctrlLabel[item].replace(" ", "") + "," + list_checkboxLabel[item] + "," + userindexLabel + " "
                    else:
                        launchME += launchMode + list_txtctrlLabel[item].replace(" ", "") + "," + list_checkboxLabel[item] + " "

        if self.ck_ProxyOnly.Value == True:
            if sonospyKill == False:
                launchME = launchME + " -p"
            
        if self.ck_SMAPI.Value == True:
            if sonospyKill == False:
                launchME = launchME + " -r"

            
        if sonospyKill == False:
            self.tc_Scratchpad.Value = launchME

        # Disable any database entries that are emtpy
        # Weirdness with some of the labels.
        if sonospyKill == False:
            for item in range(len(list_checkboxID)):
                DBname = wx.FindWindowById(list_checkboxID[item]).Label
                if DBname == "<add database>":
                    wx.FindWindowById(list_checkboxID[item]).Disable()
                    wx.FindWindowById(list_userindexID[item]).Disable()
                    wx.FindWindowById(list_txtctrlID[item]).Disable()
                else:
                    wx.FindWindowById(list_checkboxID[item]).Enable()
                    wx.FindWindowById(list_userindexID[item]).Enable()   
                    wx.FindWindowById(list_txtctrlID[item]).Enable()
                if self.ck_SMAPI.Value == False:
                    wx.FindWindowById(list_userindexID[item]).Disable()

        # If we don't have any databases, return 0 so that we can throw
        # up a messagebox in startStopSonospy.  Otherwise, return what
        # would be a valid launch command.
        if self.bt_Launch.Label != "Stop":
            if dbCount == 0:
                return 0
        return launchME

    ########################################################################################################################
    # setButtons: Turns the various panel buttons on and off -- this is so we don't go making changes to the fields
    #             while Sonospy is running.
    ########################################################################################################################
    def setButtons(self, state):
        """
        Toggle for the button states.
        """
        if state == True:
            self.ck_DB1.Enable()
            self.tc_DB1.Enable()
            self.bt_DB1.Enable()
            self.ck_DB2.Enable()
            self.tc_DB2.Enable()
            self.bt_DB2.Enable()
            self.ck_DB3.Enable()
            self.tc_DB3.Enable()
            self.bt_DB3.Enable()
            self.ck_DB4.Enable()
            self.tc_DB4.Enable()
            self.bt_DB4.Enable()
            self.ck_DB5.Enable()
            self.tc_DB5.Enable()
            self.bt_DB5.Enable()
            self.ck_DB6.Enable()
            self.tc_DB6.Enable()
            self.bt_DB6.Enable()
            self.ck_DB7.Enable()
            self.tc_DB7.Enable()
            self.bt_DB7.Enable()
            self.ck_DB8.Enable()
            self.tc_DB8.Enable()
            self.bt_DB8.Enable()
            self.bt_AutoPopulate.Enable()
            self.bt_Clear.Enable()
            self.bt_SaveDefaults.Enable()
            self.ck_EnableAll.Enable()
            self.rd_Proxy.Enable()
            self.rd_Web.Enable()
            self.label_ProxyName.Enable()
            self.ck_SMAPI.Enable()
            self.comboDB1.Enable()
            self.comboDB2.Enable()
            self.comboDB3.Enable()
            self.comboDB4.Enable()
            self.comboDB5.Enable()
            self.comboDB6.Enable()
            self.comboDB7.Enable()
            self.comboDB8.Enable()
            self.label_UserIndexName.Enable()
            self.label_launchMode.Enable()
            self.ck_ProxyOnly.Enable()
            self.label_UserIndexName.Enable()
        else:
            self.ck_DB1.Disable()
            self.tc_DB1.Disable()
            self.bt_DB1.Disable()
            self.ck_DB2.Disable()
            self.tc_DB2.Disable()
            self.bt_DB2.Disable()
            self.ck_DB3.Disable()
            self.tc_DB3.Disable()
            self.bt_DB3.Disable()
            self.ck_DB4.Disable()
            self.tc_DB4.Disable()
            self.bt_DB4.Disable()
            self.ck_DB5.Disable()
            self.tc_DB5.Disable()
            self.bt_DB5.Disable()
            self.ck_DB6.Disable()
            self.tc_DB6.Disable()
            self.bt_DB6.Disable()
            self.ck_DB7.Disable()
            self.tc_DB7.Disable()
            self.bt_DB7.Disable()
            self.ck_DB8.Disable()
            self.tc_DB8.Disable()
            self.bt_DB8.Disable()
            self.bt_AutoPopulate.Disable()
            self.bt_Clear.Disable()
            self.bt_SaveDefaults.Disable()
            self.ck_EnableAll.Disable()
            self.rd_Proxy.Disable()
            self.rd_Web.Disable()
            self.label_ProxyName.Disable()
            self.ck_SMAPI.Disable()
            self.comboDB1.Disable()
            self.comboDB2.Disable()
            self.comboDB3.Disable()
            self.comboDB4.Disable()
            self.comboDB5.Disable()
            self.comboDB6.Disable()
            self.comboDB7.Disable()
            self.comboDB8.Disable()
            self.label_UserIndexName.Disable()
            self.label_launchMode.Disable()
            self.ck_ProxyOnly.Disable()
            
            

