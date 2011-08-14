###############################################################################
# Launch Tab for use with sonospyGUI.py
###############################################################################
# launchTab.py copyright (c) 2010-2011 John Chowanec
# mutagen copyright (c) 2005 Joe Wreschnig, Michael Urman (mutagen is Licensed under GPL version 2.0)
# Sonospy Project copyright (c) 2010-2011 Mark Henkelis
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
# - Connect Show Duplicates (i.e. read in from Mark's INI and then override
#   without overwriting.
# - Windowsify the commands to run properly -- namely pOpen and how
#   to capture stdout?
# - Add scratchpad?
#
# Windows Command:
# Launch: python pycpoint.py -p -wSonospy=Henk,virtualsdatabase
###############################################################################

import wx
from wxPython.wx import *
import os
import subprocess
import guiFunctions

list_checkboxID = []
list_checkboxLabel = []
list_txtctrlID = []
list_txtctrlLabel = []
list_buttonID = []

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

        global sizer
        
        panel = self
        sizer = wx.GridBagSizer(11, 3)
        
        xIndex = 0
        yIndex = 0

    # [0] Make Header Columns --------------------------
        label_ProxyName = wx.StaticText(panel, label="Display Name")
        self.ck_EnableAll = wxCheckBox(panel, label="Enable All ")
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
        sizer.Add(label_ProxyName, pos=(xIndex, 1), flag=wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
        sizer.Add(self.ck_EnableAll, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
        sizer.Add(self.bt_AutoPopulate, pos=(xIndex, 3), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
        sizer.Add(self.bt_Clear, pos=(xIndex, 2), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.TOP|wx.ALIGN_RIGHT, border=10)


        xIndex +=1
    # --------------------------------------------------------------------------
    # [1] Separator line ------------------------------------------------------

        hl_SepLine1 = wx.StaticLine(panel, 0, (250, 50), (300,1))
        sizer.Add(hl_SepLine1, pos=(xIndex, 0), span=(1, 3), flag=wx.EXPAND)
        xIndex +=1

    # --------------------------------------------------------------------------
    # [2-9] Checkbox, database name and proxy name field, plus browse button
    #   [2]
        self.ck_DB1 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB1.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))
        
        self.tc_DB1 = wx.TextCtrl(panel)
        self.tc_DB1.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))

        self.bt_DB1 = wx.Button(self, label="Browse")
        self.bt_DB1.tc = self.tc_DB1
        self.bt_DB1.ck = self.ck_DB1

        sizer.Add(self.ck_DB1, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB1, pos=(xIndex,1), span=(1,2),flag=wx.EXPAND|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB1, pos=(xIndex, 3), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)

        self.ck_DB1.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB1)
        self.bt_DB1.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB1)

        # Read in config
        self.ck_DB1.Value = guiFunctions.configMe("launch", "db1_check", bool=True)
        self.ck_DB1.Label =  guiFunctions.configMe("launch", "db1_dbname")
        self.tc_DB1.Value = guiFunctions.configMe("launch", "db1_proxyname")

        if self.ck_DB1.Label == "":
            self.ck_DB1.Label = "<add database>"

        if self.ck_DB1.Label == "<add database>":
            self.ck_DB1.Disable()

        # Add items to lists
        list_checkboxID.append(self.ck_DB1.GetId())
        list_checkboxLabel.append(self.ck_DB1.GetLabel())
        list_txtctrlID.append(self.tc_DB1.GetId())
        list_txtctrlLabel.append(self.tc_DB1.Value)

        xIndex +=1

    #   [3]
        self.ck_DB2 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB2.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))

        self.tc_DB2 = wx.TextCtrl(panel)
        self.tc_DB2.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))
        self.bt_DB2 = wx.Button(self, label="Browse")
        self.bt_DB2.tc = self.tc_DB2
        self.bt_DB2.ck = self.ck_DB2

        sizer.Add(self.ck_DB2, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB2, pos=(xIndex,1), span=(1,2),flag=wx.EXPAND|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB2, pos=(xIndex, 3), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)

        self.ck_DB2.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB2)
        self.bt_DB2.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB2)

        # Read in config
        self.ck_DB2.Value = guiFunctions.configMe("launch", "db2_check", bool=True)
        self.ck_DB2.Label =  guiFunctions.configMe("launch", "db2_dbname")
        self.tc_DB2.Value = guiFunctions.configMe("launch", "db2_proxyname")

        if self.ck_DB2.Label == "":
            self.ck_DB2.Label = "<add database>"

        if self.ck_DB2.Label == "<add database>":
            self.ck_DB2.Disable()

        # Add items to lists
        list_checkboxID.append(self.ck_DB2.GetId())
        list_checkboxLabel.append(self.ck_DB2.GetLabel())
        list_txtctrlID.append(self.tc_DB2.GetId())
        list_txtctrlLabel.append(self.tc_DB2.Value)

        xIndex +=1

    #   [4]
        self.ck_DB3 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB3.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))

        self.tc_DB3 = wx.TextCtrl(panel)
        self.tc_DB3.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))
        self.bt_DB3 = wx.Button(self, label="Browse")
        self.bt_DB3.tc = self.tc_DB3
        self.bt_DB3.ck = self.ck_DB3

        sizer.Add(self.ck_DB3, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB3, pos=(xIndex,1), span=(1,2),flag=wx.EXPAND|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB3, pos=(xIndex, 3), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)

        self.ck_DB3.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB3)
        self.bt_DB3.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB3)

        # Read in config
        self.ck_DB3.Value = guiFunctions.configMe("launch", "db3_check", bool=True)
        self.ck_DB3.Label =  guiFunctions.configMe("launch", "db3_dbname")
        self.tc_DB3.Value = guiFunctions.configMe("launch", "db3_proxyname")

        if self.ck_DB3.Label == "":
            self.ck_DB3.Label = "<add database>"

        if self.ck_DB3.Label == "<add database>":
            self.ck_DB3.Disable()

        # Add items to lists
        list_checkboxID.append(self.ck_DB3.GetId())
        list_checkboxLabel.append(self.ck_DB3.GetLabel())
        list_txtctrlID.append(self.tc_DB3.GetId())
        list_txtctrlLabel.append(self.tc_DB3.Value)

        xIndex +=1

    #   [5]
        self.ck_DB4 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB4.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))

        self.tc_DB4 = wx.TextCtrl(panel)
        self.tc_DB4.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))
        self.bt_DB4 = wx.Button(self, label="Browse")
        self.bt_DB4.tc = self.tc_DB4
        self.bt_DB4.ck = self.ck_DB4

        sizer.Add(self.ck_DB4, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB4, pos=(xIndex,1), span=(1,2),flag=wx.EXPAND|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB4, pos=(xIndex, 3), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)

        self.ck_DB4.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB4)
        self.bt_DB4.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB4)

        # Read in config
        self.ck_DB4.Value = guiFunctions.configMe("launch", "db4_check", bool=True)
        self.ck_DB4.Label =  guiFunctions.configMe("launch", "db4_dbname")
        self.tc_DB4.Value = guiFunctions.configMe("launch", "db4_proxyname")

        if self.ck_DB4.Label == "":
            self.ck_DB4.Label = "<add database>"

        if self.ck_DB4.Label == "<add database>":
            self.ck_DB4.Disable()

        # Add items to lists
        list_checkboxID.append(self.ck_DB4.GetId())
        list_checkboxLabel.append(self.ck_DB4.GetLabel())
        list_txtctrlID.append(self.tc_DB4.GetId())
        list_txtctrlLabel.append(self.tc_DB4.Value)

        xIndex +=1

    #   [6]
        self.ck_DB5 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB5.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))

        self.tc_DB5 = wx.TextCtrl(panel)
        self.tc_DB5.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))
        self.bt_DB5 = wx.Button(self, label="Browse")
        self.bt_DB5.tc = self.tc_DB5
        self.bt_DB5.ck = self.ck_DB5

        sizer.Add(self.ck_DB5, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB5, pos=(xIndex,1), span=(1,2),flag=wx.EXPAND|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB5, pos=(xIndex, 3), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)

        self.ck_DB5.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB5)
        self.bt_DB5.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB5)

        # Read in config
        self.ck_DB5.Value = guiFunctions.configMe("launch", "db5_check", bool=True)
        self.ck_DB5.Label =  guiFunctions.configMe("launch", "db5_dbname")
        self.tc_DB5.Value = guiFunctions.configMe("launch", "db5_proxyname")

        if self.ck_DB5.Label == "":
            self.ck_DB5.Label = "<add database>"

        if self.ck_DB5.Label == "<add database>":
            self.ck_DB5.Disable()

        # Add items to lists
        list_checkboxID.append(self.ck_DB5.GetId())
        list_checkboxLabel.append(self.ck_DB5.GetLabel())
        list_txtctrlID.append(self.tc_DB5.GetId())
        list_txtctrlLabel.append(self.tc_DB5.Value)

        xIndex +=1

    #   [7]
        self.ck_DB6 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB6.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))

        self.tc_DB6 = wx.TextCtrl(panel)
        self.tc_DB6.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))
        self.bt_DB6 = wx.Button(self, label="Browse")
        self.bt_DB6.tc = self.tc_DB6
        self.bt_DB6.ck = self.ck_DB6

        sizer.Add(self.ck_DB6, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB6, pos=(xIndex,1), span=(1,2),flag=wx.EXPAND|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB6, pos=(xIndex, 3), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)

        self.ck_DB6.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB6)
        self.bt_DB6.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB6)

        # Read in config
        self.ck_DB6.Value = guiFunctions.configMe("launch", "db6_check", bool=True)
        self.ck_DB6.Label =  guiFunctions.configMe("launch", "db6_dbname")
        self.tc_DB6.Value = guiFunctions.configMe("launch", "db6_proxyname")

        if self.ck_DB6.Label == "":
            self.ck_DB6.Label = "<add database>"

        if self.ck_DB6.Label == "<add database>":
            self.ck_DB6.Disable()

        # Add items to lists
        list_checkboxID.append(self.ck_DB6.GetId())
        list_checkboxLabel.append(self.ck_DB6.GetLabel())
        list_txtctrlID.append(self.tc_DB6.GetId())
        list_txtctrlLabel.append(self.tc_DB6.Value)

        xIndex +=1

    #   [8]
        self.ck_DB7 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB7.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))

        self.tc_DB7 = wx.TextCtrl(panel)
        self.tc_DB7.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))
        self.bt_DB7 = wx.Button(self, label="Browse")
        self.bt_DB7.tc = self.tc_DB7
        self.bt_DB7.ck = self.ck_DB7

        sizer.Add(self.ck_DB7, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB7, pos=(xIndex,1), span=(1,2),flag=wx.EXPAND|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB7, pos=(xIndex, 3), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)

        self.ck_DB7.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB7)
        self.bt_DB7.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB7)

        # Read in config
        self.ck_DB7.Value = guiFunctions.configMe("launch", "db7_check", bool=True)
        self.ck_DB7.Label =  guiFunctions.configMe("launch", "db7_dbname")
        self.tc_DB7.Value = guiFunctions.configMe("launch", "db7_proxyname")

        if self.ck_DB7.Label == "":
            self.ck_DB7.Label = "<add database>"

        if self.ck_DB7.Label == "<add database>":
            self.ck_DB7.Disable()

        # Add items to lists
        list_checkboxID.append(self.ck_DB7.GetId())
        list_checkboxLabel.append(self.ck_DB7.GetLabel())
        list_txtctrlID.append(self.tc_DB7.GetId())
        list_txtctrlLabel.append(self.tc_DB7.Value)

        xIndex +=1

    #   [9]
        self.ck_DB8 = wx.CheckBox(self, -1, "<add database>")
        self.ck_DB8.SetToolTip(wx.ToolTip("Click here to enable/disable this database for launch."))

        self.tc_DB8 = wx.TextCtrl(panel)
        self.tc_DB8.SetToolTip(wx.ToolTip("Enter a name for display on your Sonos Controller."))
        self.bt_DB8 = wx.Button(self, label="Browse")
        self.bt_DB8.tc = self.tc_DB8
        self.bt_DB8.ck = self.ck_DB8

        sizer.Add(self.ck_DB8, pos=(xIndex,0), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_DB8, pos=(xIndex,1), span=(1,2),flag=wx.EXPAND|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_DB8, pos=(xIndex, 3), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)

        self.ck_DB8.Bind(wx.EVT_CHECKBOX, self.OnCheck, self.ck_DB8)
        self.bt_DB8.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DB8)

        # Read in config
        self.ck_DB8.Value = guiFunctions.configMe("launch", "db8_check", bool=True)
        self.ck_DB8.Label =  guiFunctions.configMe("launch", "db8_dbname")
        self.tc_DB8.Value = guiFunctions.configMe("launch", "db8_proxyname")

        if self.ck_DB8.Label == "":
            self.ck_DB8.Label = "<add database>"

        if self.ck_DB8.Label == "<add database>":
            self.ck_DB8.Disable()

        # Add items to lists
        list_checkboxID.append(self.ck_DB8.GetId())
        list_checkboxLabel.append(self.ck_DB8.GetLabel())
        list_txtctrlID.append(self.tc_DB8.GetId())
        list_txtctrlLabel.append(self.tc_DB8.Value)

        xIndex +=1

    # --------------------------------------------------------------------------
    # [12] Separator line ------------------------------------------------------

        hl_SepLine1 = wx.StaticLine(panel, 0, (250, 50), (300,1))
        sizer.Add(hl_SepLine1, pos=(10, 0), span=(1, 3), flag=wx.EXPAND)

    # --------------------------------------------------------------------------
    # [13] Create and add a launch button and radios for Proxy vs. Web
    # Eventually add "Use Sorts" and "Remove Dupes"
        self.bt_Launch = wx.Button(panel, label="Launch")
        help_bt_Launch = "Click here to launch the Sonospy service."
        self.bt_Launch.SetToolTip(wx.ToolTip(help_bt_Launch))
        self.bt_Launch.Bind(wx.EVT_BUTTON, self.bt_LaunchClick, self.bt_Launch)
        self.rd_Proxy = wx.RadioButton(panel, label="Proxy")
        help_rd_Proxy = "Run only as a proxy service in the background."
        self.rd_Proxy.SetToolTip(wx.ToolTip(help_rd_Proxy))
        self.rd_Web = wx.RadioButton(panel, label="Web")
        help_rd_Web = "Run as the web interface to Sonospy."
        self.rd_Web.SetToolTip(wx.ToolTip(help_rd_Web))

        if guiFunctions.configMe("launch", "proxy", bool=True) == True:
            self.rd_Proxy.SetValue(True)
        else:
            self.rd_Web.SetValue(True)

        # SAVE AS DEFAULTS
        self.bt_SaveDefaults = wx.Button(panel, label="Save Defaults")
        help_SaveDefaults = "Save current settings as default."
        self.bt_SaveDefaults.SetToolTip(wx.ToolTip(help_SaveDefaults))
        self.bt_SaveDefaults.Bind(wx.EVT_BUTTON, self.bt_SaveDefaultsClick, self.bt_SaveDefaults)

        sizer.Add(self.bt_Launch, pos=(11,0), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.rd_Proxy, pos=(11,1), flag=wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.rd_Web, pos=(11,2), flag=wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_SaveDefaults, pos=(11,3), flag=wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        panel.Refresh()
        panel.Update()
        
        sizer.AddGrowableCol(2)
        panel.SetSizer(sizer)

    def browseDB(self, event):
        filters = guiFunctions.configMe("general", "database_extensions")
        wildcards = "Sonospy Database (" + filters + ")|" + filters.replace(" ", ";") + "|All files (*.*)|*.*"
        
        # back up to the folder below our current one.  save cwd in variable
        owd = os.getcwd()
        os.chdir(os.pardir)

        dialog = wx.FileDialog ( None, message = 'Select database...', wildcard = wildcards, style = wxOPEN)

        # Open Dialog Box and get Selection
        if dialog.ShowModal() == wxID_OK:
            selected = dialog.GetFilenames()
            for selection in selected:
                basename, extension = os.path.splitext(selection)
                event.GetEventObject().tc.Value = basename
                event.GetEventObject().ck.Label = selection
                event.GetEventObject().ck.Enable()
                event.GetEventObject().ck.Value = True
                guiFunctions.statusText(self, "Database: " + selection + " selected...")
        dialog.Destroy()
        self.Update()

        # set back to original working directory
        os.chdir(owd)

    def OnCheck(self, event):

# DEBUG ------------------------------------------------------------------------
#        for item in range(len(list_checkboxID)):
#            print "Checkbox " + str(item) + ":\t\t\tID:" + str(list_checkboxID[item]) + "\tLABEL:" + list_checkboxLabel[item]
#            print "Text Control " + str(item) + ":\t\tID:" + str(list_txtctrlID[item]) + "\tLABEL:" + list_txtctrlLabel[item]
# ------------------------------------------------------------------------------

        pass

    def enableAllChecks(self, event):
        if self.ck_EnableAll.Value == True:
            self.ck_EnableAll.Label = "Disable All"
        else:
            self.ck_EnableAll.Label = "Enable All"

        for item in range(len(list_checkboxID)):
            if wx.FindWindowById(list_checkboxID[item]).Label != "<add database>":
                wx.FindWindowById(list_checkboxID[item]).Value = self.ck_EnableAll.Value

    def bt_LaunchClick(self, event):
        # back up to the folder below our current one.  save cwd in variable
        owd = os.getcwd()
        os.chdir(os.pardir)
        os.chdir(os.pardir)

        # Check for OS
        if os.name == 'nt':
            cmdroot = 'sonospy_ '
            launchCMD = cmdroot
            # which version are we running?
            if self.rd_Proxy.Value == True:
                launchCMD += "p "
            else:
                launchCMD += "w "

        else:
            cmdroot = './'
            launchCMD = cmdroot + "sonospy_"
            # which version are we running?
            if self.rd_Proxy.Value == True:
                launchCMD += "proxy "
            else:
                launchCMD += "web "

        # rebuild text labels now, user may have changed them
        for item in range(len(list_checkboxID)):
            list_txtctrlLabel[item] = wxFindWindowById(list_txtctrlID[item]).Value
            list_checkboxLabel[item] = wxFindWindowById(list_checkboxID[item]).Label
            
        # build out the command
        if self.bt_Launch.Label == "Stop":
            if os.name != 'nt':
                launchCMD = cmdroot + "sonospy_stop"
        else:
            for item in range(len(list_checkboxID)):
                if wx.FindWindowById(list_checkboxID[item]).Value == True:
                    launchCMD += "-wSonospy=" + list_txtctrlLabel[item] + "," + list_checkboxLabel[item] + " "

# DEBUG ------------------------------------------------------------------------
#            print launchCMD
# ------------------------------------------------------------------------------
        if os.name != 'nt':
            proc = subprocess.Popen([launchCMD],shell=True)
            if self.bt_Launch.Label == "Stop":
                self.bt_Launch.Label = "Launch"
                self.bt_Launch.SetToolTip(wx.ToolTip("Click here to launch the Sonospy service."))
                guiFunctions.statusText(self, "Sonospy Service Stopped...")
            else:
                self.bt_Launch.Label = "Stop"
                self.bt_Launch.SetToolTip(wx.ToolTip("Click here to stop the Sonospy service."))
                guiFunctions.statusText(self, "Sonospy Service Started...")
        else:
            proc = subprocess.Popen(launchCMD, shell=True)

        # set back to original working directory
        os.chdir(owd)

    def bt_SaveDefaultsClick(self, event):
        section = "launch"

        guiFunctions.configWrite(section, "proxy", self.rd_Proxy.Value)
        guiFunctions.configWrite(section, "db1_check", self.ck_DB1.Value)
        guiFunctions.configWrite(section, "db1_dbname", self.ck_DB1.Label)
        guiFunctions.configWrite(section, "db1_proxyname", self.tc_DB1.Value)
        guiFunctions.configWrite(section, "db2_check", self.ck_DB2.Value)
        guiFunctions.configWrite(section, "db2_dbname", self.ck_DB2.Label)
        guiFunctions.configWrite(section, "db2_proxyname", self.tc_DB2.Value)
        guiFunctions.configWrite(section, "db3_check", self.ck_DB3.Value)
        guiFunctions.configWrite(section, "db3_dbname", self.ck_DB3.Label)
        guiFunctions.configWrite(section, "db3_proxyname", self.tc_DB3.Value)
        guiFunctions.configWrite(section, "db4_check", self.ck_DB4.Value)
        guiFunctions.configWrite(section, "db4_dbname", self.ck_DB4.Label)
        guiFunctions.configWrite(section, "db4_proxyname", self.tc_DB4.Value)
        guiFunctions.configWrite(section, "db5_check", self.ck_DB5.Value)
        guiFunctions.configWrite(section, "db5_dbname", self.ck_DB5.Label)
        guiFunctions.configWrite(section, "db5_proxyname", self.tc_DB5.Value)
        guiFunctions.configWrite(section, "db6_check", self.ck_DB6.Value)
        guiFunctions.configWrite(section, "db6_dbname", self.ck_DB6.Label)
        guiFunctions.configWrite(section, "db6_proxyname", self.tc_DB6.Value)
        guiFunctions.configWrite(section, "db7_check", self.ck_DB7.Value)
        guiFunctions.configWrite(section, "db7_dbname", self.ck_DB7.Label)
        guiFunctions.configWrite(section, "db7_proxyname", self.tc_DB7.Value)
        guiFunctions.configWrite(section, "db8_check", self.ck_DB8.Value)
        guiFunctions.configWrite(section, "db8_dbname", self.ck_DB8.Label)
        guiFunctions.configWrite(section, "db8_proxyname", self.tc_DB8.Value)

        guiFunctions.statusText(self, "Defaults saved...")

    def bt_AutoPopulateClick(self, event):
        filters = guiFunctions.configMe("general", "database_extensions").split()

        # Set Original Working Directory so we can get back to here.
        owd = os.getcwd()
        os.chdir(os.pardir)

        #   Get a count of *database from the filesystem
        numDB = guiFunctions.scrubDB(os.getcwd(), filters)
        curCount = 1
        # Checkbox (enable, disable for launch)
        # textCtrl (for Proxy name in controller)
        # database name (based on *database)
        for db in numDB:

            if curCount >= 8:
                pass
            if curCount == 1:
                ck = self.ck_DB1
                tc = self.tc_DB1
            if curCount == 2:
                ck = self.ck_DB2
                tc = self.tc_DB2
            if curCount == 3:
                ck = self.ck_DB3
                tc = self.tc_DB3
            if curCount == 4:
                ck = self.ck_DB4
                tc = self.tc_DB4
            if curCount == 5:
                ck = self.ck_DB5
                tc = self.tc_DB5
            if curCount == 6:
                ck = self.ck_DB6
                tc = self.tc_DB6
            if curCount == 7:
                ck = self.ck_DB7
                tc = self.tc_DB7
            if curCount == 8:
                ck = self.ck_DB8
                tc = self.tc_DB8
            else:
                basename, extension = os.path.splitext(db)
                tc.Value = basename
                ck.Label = db
                ck.Enable()
                ck.Value = True
            curCount +=1
            
#            #-------------------------------------------------------
#            # Save references to the widgets created dynamically
#                list_checkboxID.append(check.GetId())
#                list_checkboxLabel.append(check.GetLabel())
#                list_txtctrlID.append(name.GetId())
#                list_txtctrlLabel.append(name.Value)
#
#            # Bind to event for later (DEBUG)
#                check.Bind(wx.EVT_CHECKBOX, self.OnCheck, check)

        # set back to original working directory
        os.chdir(owd)
    
    def bt_ClearClick(self, event):
        for item in range(len(list_checkboxID)):
            wxFindWindowById(list_txtctrlID[item]).Value = ""
            wxFindWindowById(list_checkboxID[item]).Label = "<add database>"
            wxFindWindowById(list_checkboxID[item]).Value = False
            wxFindWindowById(list_checkboxID[item]).Disable()
