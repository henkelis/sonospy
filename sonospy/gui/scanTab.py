###############################################################################
# Scan Tab for use with sonospyGUI.py
###############################################################################
# scanTab.py copyright (c) 2010-2011 John Chowanec
# mutagen copyright (c) 2005 Joe Wreschnig, Michael Urman (mutagen is Licensed under GPL version 2.0)
# Sonospy Project copyright (c) 2010-2011 Mark Henkelis
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
# scanTab.py Author: John Chowanec <chowanec@gmail.com>
# scan.py Author: Mark Henkelis <mark.henkelis@tesco.net>
###############################################################################
# TODO:
# - Add scheduler functionality (i.e. push command to scheduler tab)
###############################################################################

import wx
from wxPython.wx import *
import os
import subprocess
from threading import *
import guiFunctions
from datetime import datetime
from wx.lib.pubsub import Publisher

# Define notification event for thread completion
EVT_RESULT_ID = wx.NewId()

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

# Worker thread for multi-threading
class WorkerThread(Thread):
    """Worker Thread Class."""
    def __init__(self, notify_window):
        """Init Worker Thread Class."""
        Thread.__init__(self)
        self._notify_window = notify_window
        self._want_abort = 0
        self.start()

    def run(self):
        """Run Worker Thread."""
        wx.PostEvent(self._notify_window, ResultEvent("Command: " + scanCMD + "\n\n"))
        proc = subprocess.Popen(scanCMD, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

        while True:
            line = proc.stdout.readline()
            wx.PostEvent(self._notify_window, ResultEvent(line))
            wx.Yield()
            if not line: break
        proc.wait()
        wx.PostEvent(self._notify_window, ResultEvent(None))
        return

class ScanPanel(wx.Panel):
    """
    Scan Tab for running Sonospy Database Scans, Updates and Repairs
    """
    #----------------------------------------------------------------------
    def __init__(self, parent):
        """"""
        wx.Panel.__init__(self, parent=parent, id=wx.ID_ANY)

        panel = self
        sizer = wx.GridBagSizer(6, 5)

        xIndex = 0
    # [0] Main Database Text, Entry and Browse Button --------------------------
        label_MainDatabase = wx.StaticText(panel, label="Database:")
        help_Database = "The 'Database' is the main collection of music you will create or update. Click BROWSE to select a previously created database, or enter a new name here."
        label_MainDatabase.SetToolTip(wx.ToolTip(help_Database))
        sizer.Add(label_MainDatabase, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)

        self.tc_MainDatabase = wx.TextCtrl(panel)
        self.tc_MainDatabase.SetToolTip(wx.ToolTip(help_Database))
        self.tc_MainDatabase.Value = guiFunctions.configMe("scan", "database")
        sizer.Add(self.tc_MainDatabase, pos=(xIndex, 1), span=(1, 4), flag=wx.TOP|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)

        self.bt_MainDatabase = wx.Button(panel, label="Browse...")
        self.bt_MainDatabase.SetToolTip(wx.ToolTip(help_Database))
        sizer.Add(self.bt_MainDatabase, pos=(xIndex, 5), flag=wx.RIGHT|wx.TOP|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)
        self.bt_MainDatabase.Bind(wx.EVT_BUTTON, self.bt_MainDatabaseClick,self.bt_MainDatabase)
        xIndex += 1
    # [0] INI Overide ----------------------------------------------------------
#        label_INI = wx.StaticText(panel, label="INI File:")
#        help_INI = "Override scan.ini with your own INI file."
#        label_INI.SetToolTip(wx.ToolTip(help_Database))
#        sizer.Add(label_INI, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
#
#        self.tc_INI = wx.TextCtrl(panel)
#        self.tc_INI.SetToolTip(wx.ToolTip(help_INI))
#        self.tc_INI.Value = guiFunctions.configMe("scan", "inioverride")
#        sizer.Add(self.tc_INI, pos=(xIndex, 1), span=(1, 4), flag=wx.TOP|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)
#
#        self.bt_INI = wx.Button(panel, label="Browse...")
#        self.bt_INI.SetToolTip(wx.ToolTip(help_INI))
#        sizer.Add(self.bt_INI, pos=(xIndex, 5), flag=wx.RIGHT|wx.TOP|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)
#        self.bt_INI.Bind(wx.EVT_BUTTON, self.bt_INIClick,self.bt_INI)
#        xIndex += 1
    # --------------------------------------------------------------------------
    # [1] Paths to scan for new Music ------------------------------------------
        self.sb_FoldersToScan = wx.StaticBox(panel, label="Folders to Scan:", size=(200, 100))
        help_FoldersToScan = "Folders you will scan for music files are listed here. Click ADD to browse for a *top-level* folder. Scan will search all sub-folders for valid music."
        folderBoxSizer = wx.StaticBoxSizer(self.sb_FoldersToScan, wx.VERTICAL)
        self.multiText = wx.TextCtrl(panel, -1,"",size=(300, 100), style=wx.TE_MULTILINE|wx.TE_READONLY)
        self.multiText.SetToolTip(wx.ToolTip(help_FoldersToScan))
        self.multiText.SetInsertionPoint(0)
        self.multiText.Value = guiFunctions.configMe("scan", "folder", parse=True)
        folderBoxSizer.Add(self.multiText, flag=wx.EXPAND)
        sizer.Add(folderBoxSizer, pos=(xIndex, 0), span=(1, 6), flag=wx.EXPAND|wx.TOP|wx.LEFT|wx.RIGHT, border=10)
        xIndex += 1
    # --------------------------------------------------------------------------
    # [2] Buttons to Add Folder, Clear Scan Area -------------------------------
        # ADD FOLDER
        self.bt_FoldersToScanAdd = wx.Button(panel, label="Add")
        help_FoldersToScanAdd = "Add a top-level folder to the 'Folders to Scan' field. The scan will search any sub-folders beneath whatever folder you add."
        self.bt_FoldersToScanAdd.SetToolTip(wx.ToolTip(help_FoldersToScanAdd))
        self.bt_FoldersToScanAdd.Bind(wx.EVT_BUTTON, self.bt_FoldersToScanAddClick, self.bt_FoldersToScanAdd)
        sizer.Add(self.bt_FoldersToScanAdd, pos=(xIndex,0), span=(1,2), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        # CLEAR SCAN AREA
        self.bt_FoldersToScanClear = wx.Button(panel, label="Clear")
        help_FoldersToScanClear = "Clear the Folders to Scan field."
        self.bt_FoldersToScanClear.SetToolTip(wx.ToolTip(help_FoldersToScanClear))
        sizer.Add(self.bt_FoldersToScanClear, pos=(xIndex,5), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)
        self.bt_FoldersToScanClear.Bind(wx.EVT_BUTTON, self.bt_FoldersToScanClearClick, self.bt_FoldersToScanClear)
        xIndex += 1
    # --------------------------------------------------------------------------
    # [3] Separator line -------------------------------------------------------
        hl_SepLine1 = wx.StaticLine(panel, 0, (250, 50), (300,1))
        sizer.Add(hl_SepLine1, pos=(xIndex, 0), span=(1, 6), flag=wx.EXPAND, border=10)
        xIndex += 1
    # --------------------------------------------------------------------------
    # [4] Add Scan Options and Scan Button -------------------------------------
        # SCAN/UPDATE
        self.bt_ScanUpdate = wx.Button(panel, label="Scan/Update")
        help_ScanUpdate = "Click here to begin your scan of the folders listed above. This will create a new database if one doesn't exist. Otherwise it will update the database with any new music it finds."
        self.bt_ScanUpdate.SetToolTip(wx.ToolTip(help_ScanUpdate))
        self.bt_ScanUpdate.Bind(wx.EVT_BUTTON, self.bt_ScanUpdateClick, self.bt_ScanUpdate)
        sizer.Add(self.bt_ScanUpdate, pos=(xIndex,0), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        # REPAIR
        self.bt_ScanRepair = wx.Button(panel, label="Repair")
        help_ScanRepair = "Click here to repair the 'Database' listed above."
        self.bt_ScanRepair.SetToolTip(wx.ToolTip(help_ScanRepair))
        self.bt_ScanRepair.Bind(wx.EVT_BUTTON, self.bt_ScanRepairClick, self.bt_ScanRepair)
        sizer.Add(self.bt_ScanRepair, pos=(xIndex,1), span=(1,2), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        # VERBOSE
        self.ck_ScanVerbose = wx.CheckBox(panel, label="Verbose")
        help_ScanVerbose = "Select this checkbox if you want to turn on the verbose settings during the scan."
        self.ck_ScanVerbose.SetToolTip(wx.ToolTip(help_ScanVerbose))
        self.ck_ScanVerbose.Value = guiFunctions.configMe("scan", "verbose", bool=True)
        sizer.Add(self.ck_ScanVerbose, pos=(xIndex,3), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        # SAVE LOG TO FILE
        self.bt_SaveLog = wx.Button(panel, label="Save Log")
        help_SaveLogToFile = "Save the log below to a file."
        self.bt_SaveLog.SetToolTip(wx.ToolTip(help_SaveLogToFile))
        self.bt_SaveLog.Bind(wx.EVT_BUTTON, self.bt_SaveLogClick, self.bt_SaveLog)
        sizer.Add(self.bt_SaveLog, pos=(xIndex,4), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=5)

        # SAVE AS DEFAULTS
        self.bt_SaveDefaults = wx.Button(panel, label="Save Defaults")
        help_SaveDefaults = "Save current settings as default."
        self.bt_SaveDefaults.SetToolTip(wx.ToolTip(help_SaveDefaults))
        self.bt_SaveDefaults.Bind(wx.EVT_BUTTON, self.bt_SaveDefaultsClick, self.bt_SaveDefaults)
        sizer.Add(self.bt_SaveDefaults, pos=(xIndex,5), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        xIndex += 1
    # --------------------------------------------------------------------------
    # [5] Separator line ------------------------------------------------------
        hl_SepLine2 = wx.StaticLine(panel, 0, (250, 50), (330,1))
        sizer.Add(hl_SepLine2, pos=(xIndex, 0), span=(1, 6), flag=wx.EXPAND, border=10)
        xIndex += 1
    # --------------------------------------------------------------------------
    # [6] Output/Log Box -------------------------------------------------------
        self.LogWindow = wx.TextCtrl(panel, -1,"",size=(100, 310), style=wx.TE_MULTILINE|wx.TE_READONLY)
        LogFont = wx.Font(7.5, wx.SWISS, wx.NORMAL, wx.NORMAL, False)
        self.LogWindow.SetFont(LogFont)
        self.LogWindow.Disable()
        help_LogWindow = "Results of a scan or repair will appear here."
        self.LogWindow.SetToolTip(wx.ToolTip(help_LogWindow))
        self.LogWindow.SetInsertionPoint(0)
        sizer.Add(self.LogWindow, pos=(xIndex,0), span=(1,6), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        xIndex += 1

        # Indicate we don't have a worker thread yet
        EVT_RESULT(self,self.onResult)
        self.worker = None

        Publisher().subscribe(self.setScanPanel, 'setScanPanel')

        sizer.AddGrowableCol(2)
        panel.SetSizer(sizer)

    def setScanPanel(self, msg):
        if msg.data == "Disable":
            self.Disable()
        else:
            self.Enable()

    def onResult(self, event):
        """Show Result status."""
        if event.data is None:
            # Thread aborted (using our convention of None return)
            endTime = datetime.now()
            calcdTime = endTime - startTime

            self.LogWindow.AppendText("\n[ Job Complete ] (Duration: " + str(calcdTime)[:-4] +")\n\n")
            guiFunctions.statusText(self, "[ Job Complete ] (Duration: " + str(calcdTime)[:-4] + ")")
            self.setButtons(True)
        else:
            # Process results here
            endTime = datetime.now()
            calcdTime = endTime - startTime

            guiFunctions.statusText(self, "(Duration: " + str(calcdTime)[:-4] +")")

            self.LogWindow.AppendText(event.data)

        # In either event, the worker is done
        self.worker = None
#        guiFunctions.statusText(self, "")

    def bt_ScanRepairClick(self, event):
        global scanCMD
        global startTime
        
        # Set Original Working Directory so we can get back to here.
        owd = os.getcwd()
        os.chdir(os.pardir)

        getOpts = ""
        iniOverride = ""

        if os.name == 'nt':
            cmdroot = 'python '
        else:
            cmdroot = './'

        self.LogWindow.Enable()
        if self.tc_MainDatabase.Value == "":
            self.LogWindow.AppendText("ERROR:\tNo database name selected!\n")
        else:
            if self.ck_ScanVerbose.Value == True:
                getOpts = "-v "
#            if self.tc_INI.Value != "":
##                iniOverride = ""
#                iniOverride = "-i " + self.tc_INI.Value

            scanCMD = cmdroot + "scan.py " + getOpts +"-d " + self.tc_MainDatabase.Value + " -r"
            startTime = datetime.now()
            self.LogWindow.AppendText("[ Starting Repair ] (" + startTime.strftime("%T") + ")\n\n")
            guiFunctions.statusText(self, "[ Repair Started ]")

            if not self.worker:
                self.worker = WorkerThread(self)
                self.setButtons(False)
                wx.SetCursor(wx.StockCursor(wx.CURSOR_WATCH))

        # set back to original working directory
        os.chdir(owd)

    def bt_MainDatabaseClick(self, event):
        filters = guiFunctions.configMe("general", "database_extensions")
        wildcards = "Sonospy Database (" + filters + ")|" + filters.replace(" ", ";") + "|All files (*.*)|*.*"
        
        # back up to the folder below our current one.  save cwd in variable
        owd = os.getcwd()
        os.chdir(os.pardir)
        
        dialog = wx.FileDialog ( None, message = 'Select Database File...', defaultDir=guiFunctions.configMe("general", "default_database_path"), wildcard = wildcards, style = wxOPEN)

        # Open Dialog Box and get Selection
        if dialog.ShowModal() == wxID_OK:
            selected = dialog.GetFilenames()
            for selection in selected:
                self.tc_MainDatabase.Value = selection
                guiFunctions.statusText(self, "Database: " + selection + " selected...")
        dialog.Destroy()

        # set back to original working directory
        os.chdir(owd)

    def bt_INIClick(self, event):
        filters = "*.ini"
        wildcards = "INIFiles (" + filters + ")|" + filters + "|All files (*.*)|*.*"

        # back up to the folder below our current one.  save cwd in variable
        owd = os.getcwd()
        os.chdir(os.pardir)

        dialog = wx.FileDialog ( None, message = 'Select INI File...', defaultDir=guiFunctions.configMe("general", "default_ini_path"), wildcard = wildcards, style = wxOPEN)

        # Open Dialog Box and get Selection
        if dialog.ShowModal() == wxID_OK:
            selected = dialog.GetFilenames()
            for selection in selected:
                self.tc_INI.Value = selection
                guiFunctions.statusText(self, "INI File: " + selection + " selected...")
        dialog.Destroy()

        # set back to original working directory
        os.chdir(owd)

    def bt_FoldersToScanAddClick(self, event):
        dialog = wx.DirDialog(self, "Add a Directory...", defaultPath=guiFunctions.configMe("general", "default_music_path"), style=wx.DD_DEFAULT_STYLE)

        if dialog.ShowModal() == wx.ID_OK:
            if self.multiText.Value == "":
                self.multiText.AppendText("%s" % dialog.GetPath())
            else:
                self.multiText.AppendText("\n%s" % dialog.GetPath())

        dialog.Destroy()
        guiFunctions.statusText(self, "Folder: " + "%s" % dialog.GetPath() + " added.")

    def bt_FoldersToScanClearClick(self, event):
        self.multiText.Value = ""
        guiFunctions.statusText(self, "Cleared folder list...")

    def bt_SaveLogClick(self, event):
        dialog = wx.FileDialog(self, message='Choose a file', style=wx.SAVE|wx.OVERWRITE_PROMPT)
        if dialog.ShowModal() == wx.ID_OK:
            savefile = dialog.GetFilename()

            saveMe = open(savefile, 'w')
            saveMe.write(self.LogWindow.Value)
            saveMe.close()
        guiFunctions.statusText(self, savefile + " saved...")

    def setButtons(self, state):
        """
        Toggle for the button states.
        """
        if state == True:
            self.bt_FoldersToScanAdd.Enable()
            self.bt_FoldersToScanClear.Enable()
            self.bt_MainDatabase.Enable()
            self.bt_SaveLog.Enable()
            self.bt_ScanRepair.Enable()
            self.bt_ScanUpdate.Enable()
            self.ck_ScanVerbose.Enable()
            self.bt_SaveDefaults.Enable()
#            self.bt_INI.Enable()
            wx.SetCursor(wx.StockCursor(wx.CURSOR_ARROW))
            Publisher().sendMessage(('setLaunchPanel'), "Enable")
            Publisher().sendMessage(('setExtractPanel'), "Enable")
            Publisher().sendMessage(('setVirtualPanel'), "Enable")
        else:
            self.bt_FoldersToScanAdd.Disable()
            self.bt_FoldersToScanClear.Disable()
            self.bt_MainDatabase.Disable()
            self.bt_SaveLog.Disable()
            self.bt_ScanRepair.Disable()
            self.bt_ScanUpdate.Disable()
            self.ck_ScanVerbose.Disable()
            self.bt_SaveDefaults.Disable()
#            self.bt_INI.Disable()
            Publisher().sendMessage(('setLaunchPanel'), "Disable")
            Publisher().sendMessage(('setExtractPanel'), "Disable")
            Publisher().sendMessage(('setVirtualPanel'), "Disable")

            wx.SetCursor(wx.StockCursor(wx.CURSOR_WATCH))

    def bt_ScanUpdateClick(self, event):
        if os.name == 'nt':
            cmdroot = 'python '
        else:
            cmdroot = './'

        self.LogWindow.Enable()

        if self.tc_MainDatabase.Value == "":
            self.LogWindow.AppendText("ERROR:\tNo database name selected!\n")
        else:
            # Set Original Working Directory so we can get back to here.
            owd = os.getcwd()
            os.chdir(os.pardir)

            getOpts = ""
            iniOverride = ""
            
            if self.ck_ScanVerbose.Value == True:
                getOpts = "-v "
#            if self.tc_INI.Value != "":
#                iniOverride = " -i " + self.tc_INI.Value

            global scanCMD
            global startTime

            scanCMD = cmdroot + "scan.py " + getOpts +"-d " + self.tc_MainDatabase.Value + iniOverride + " "

            numLines=0
            maxLines=(int(self.multiText.GetNumberOfLines()))

            if self.multiText.GetLineText(numLines) == "":
                self.LogWindow.AppendText("ERROR\tNo folder selected to scan!\n")
            else:
                startTime = datetime.now()
                self.LogWindow.AppendText("[ Starting Scan ] (" + startTime.strftime("%T") + ")\n")


                guiFunctions.statusText(self, "Running Scan...")
                while (numLines < maxLines):
                    if os.name == "nt":
                        line = str(self.multiText.GetLineText(numLines))
                        line = line.replace("\\", "\\\\")
                        line = line.replace(" ", "\ ")
                        scanCMD += "\"" + line + "\" "
                    else:
                        scanCMD += "\"" + str(self.multiText.GetLineText(numLines)).replace(" ", "\ ") + "\" "

                    numLines += 1

                # Multithreading is below this line.
                if not self.worker:
                    self.worker = WorkerThread(self)
                    self.setButtons(False)

                # set back to original working directory
                os.chdir(owd)


    def bt_SaveDefaultsClick(self, event):
        section = "scan"

        # Verbose setting
        guiFunctions.configWrite(section, "verbose", self.ck_ScanVerbose.Value)

        # Database setting
        guiFunctions.configWrite(section, "database", self.tc_MainDatabase.Value)

        # INI Setting
#        guiFunctions.configWrite(section, "inioverride", self.tc_INI.Value)
        
        # Folder setting, comma delineate multiple folder entries
        folders = ""
        numLines = 0
        maxLines=(int(self.multiText.GetNumberOfLines()))
        while (numLines < maxLines):
            folders += str(self.multiText.GetLineText(numLines))
            numLines += 1
            if numLines != maxLines:
                folders += "|"
        guiFunctions.configWrite(section, "folder", folders)

        guiFunctions.statusText(self, "Defaults saved...")
