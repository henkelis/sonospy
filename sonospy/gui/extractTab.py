###############################################################################
# Extract Tab for use with sonospyGUI.py
###############################################################################
# extractTab.py copyright (c) 2010-2011 John Chowanec
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
# extractTab.py Author: John Chowanec <chowanec@gmail.com>
# scan.py Author: Mark Henkelis <mark.henkelis@tesco.net>
###############################################################################
# TODO:
# - Tons and tons of error checking (check for int on relevant fields)
# - Use Blue's strategy of scrubbing the SQL database for valid fields?:
#        db = sqlite3.connect(selection)
#        cur = db.cursor()
#        cur.execute('SELECT DISTINCT genre FROM tags')
#        for row in cur:
#            a.append(row)
# - Hook up default_music_path from ini on file dialog opens, etc.
# - Disable Save Defaults and other notebook tabs
###############################################################################

import wx
from wxPython.wx import *
import os
import subprocess
from threading import *
import guiFunctions
import sqlite3

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
        if os.name == "nt":
            proc = subprocess.Popen(scanCMD.replace("\\", "\\\\"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
        else:
            proc = subprocess.Popen([scanCMD], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

        while True:
            line = proc.stdout.readline()
            wx.PostEvent(self._notify_window, ResultEvent(line))
            wx.Yield()
            if not line: break
        proc.wait()
        wx.PostEvent(self._notify_window, ResultEvent(None))
        return


class ExtractPanel(wx.Panel):
    """
    Extract Tab for creating subset databases.
    """
    #----------------------------------------------------------------------
    def __init__(self, parent):
        """"""
        wx.Panel.__init__(self, parent=parent, id=wx.ID_ANY)

        panel = self
        sizer = wx.GridBagSizer(6, 5)
        self.currentDirectory = os.getcwd()

    # [0] Main Database Text, Entry and Browse Button --------------------------
        label_MainDatabase = wx.StaticText(panel, label="Source Database:")
        help_MainDatabase = "Select the source database to extract from.  This is most commonly your main database/index. Enter it into the text field, or click BROWSE to select a .db file."
        label_MainDatabase.SetToolTip(wx.ToolTip(help_MainDatabase))
        sizer.Add(label_MainDatabase, pos=(0, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)

        self.tc_MainDatabase = wx.TextCtrl(panel)
        self.tc_MainDatabase.SetToolTip(wx.ToolTip(help_MainDatabase))
        self.tc_MainDatabase.Value = guiFunctions.configMe("extract", "database_source")
        sizer.Add(self.tc_MainDatabase, pos=(0, 1), span=(1, 3), flag=wx.TOP|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)

        self.bt_MainDatabase = wx.Button(panel, label="Browse...")
        self.bt_MainDatabase.SetToolTip(wx.ToolTip(help_MainDatabase))
        sizer.Add(self.bt_MainDatabase, pos=(0, 4), flag=wx.LEFT|wx.RIGHT|wx.TOP|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)
        self.bt_MainDatabase.Bind(wx.EVT_BUTTON, self.bt_MainDatabaseClick, self.bt_MainDatabase)
    # --------------------------------------------------------------------------
    # [1] Target Database Label, Entry and Browse Button -----------------------

        # Create the label, text control and button
        label_TargetDatabase = wx.StaticText(panel, label="Target Database:")
        help_TargetDatabase = "Select the database you wish to create or update.  Enter it into the text field, or click BROWSE to select a previously created .db file."
        label_TargetDatabase.SetToolTip(wx.ToolTip(help_TargetDatabase))

        self.tc_TargetDatabase = wx.TextCtrl(panel)
        self.tc_TargetDatabase.SetToolTip(wx.ToolTip(help_TargetDatabase))
        self.tc_TargetDatabase.Value = guiFunctions.configMe("extract", "database_target")

        self.bt_TargetDatabase = wx.Button(panel, label="Browse...")
        self.bt_TargetDatabase.SetToolTip(wx.ToolTip(help_TargetDatabase))

        # Add them to the sizer.
        sizer.Add(label_TargetDatabase, pos=(1, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
        sizer.Add(self.tc_TargetDatabase, pos=(1, 1), span=(1, 3), flag=wx.TOP|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_TargetDatabase, pos=(1, 4), flag=wx.LEFT|wx.RIGHT|wx.TOP|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=10)

        # Bind the button to a click event
        self.bt_TargetDatabase.Bind(wx.EVT_BUTTON, self.bt_TargetDatabaseClick,self.bt_TargetDatabase)
    # --------------------------------------------------------------------------
    # [2] Options Static Box ---------------------------------------------------

        # Create static box
        self.sb_ExtractOptions = wx.StaticBox(panel, label="Options for Extract", size=(100,100))
        sbs_ExtractOptions = wx.StaticBoxSizer(self.sb_ExtractOptions, wx.VERTICAL)
        OptionBoxSizer = wx.GridBagSizer(4, 9)

        # Create the options
        logicList = ['<', '<=', '=', '>', '>=']

        sizerIndexX = 0

        # Created
        label_OptionsCreated = wx.StaticText(panel, label="Created:")
        help_Created = "Extract files to the Target Database based on the CREATION DATE of the music files in the Source Database."
        label_OptionsCreated.SetToolTip(wx.ToolTip(help_Created))

        self.combo_LogicalCreated = wx.ComboBox(panel, 1, "", (25, 25), (60, 25), logicList, wx.CB_DROPDOWN)
        self.combo_LogicalCreated.SetToolTip(wx.ToolTip(help_Created))
        self.combo_LogicalCreated.Select(guiFunctions.configMe("extract", "createdidx", integer=True))

        self.tc_DaysAgoCreated = wx.TextCtrl(panel)
        self.tc_DaysAgoCreated.SetToolTip(wx.ToolTip(help_Created))
        self.tc_DaysAgoCreated.Value = guiFunctions.configMe("extract", "createdVal")

        label_DaysAgoCreated = wx.StaticText(panel, label="days ago")
        label_DaysAgoCreated.SetToolTip(wx.ToolTip(help_Created))

        # Add them to the sizer (optionBoxSizer)
        OptionBoxSizer.Add(label_OptionsCreated, pos=(sizerIndexX, 0), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=0)
        OptionBoxSizer.Add(self.combo_LogicalCreated, pos=(sizerIndexX,1), flag=wx.ALIGN_CENTER_VERTICAL|wx.ALL, border=1)
        OptionBoxSizer.Add(self.tc_DaysAgoCreated, pos=(sizerIndexX, 2), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)
        OptionBoxSizer.Add(label_DaysAgoCreated, pos=(sizerIndexX,3), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)

        # Inserted
        sizerIndexX += 1
        label_OptionsInserted = wx.StaticText(panel, label="Inserted:")
        help_Inserted = "Extract files to the Target Database based on the INSERTED DATE (i.e. when the file was first added to the database) of the entries in the Source Database."
        label_OptionsInserted.SetToolTip(wx.ToolTip(help_Inserted))

        self.combo_LogicalInserted = wx.ComboBox(panel, 1, "", (25, 25), (60, 25), logicList, wx.CB_DROPDOWN)
        self.combo_LogicalInserted.SetToolTip(wx.ToolTip(help_Inserted))
        self.combo_LogicalInserted.Select(guiFunctions.configMe("extract", "insertedIdx", integer=True))
        self.tc_DaysAgoInserted = wx.TextCtrl(panel)
        self.tc_DaysAgoInserted.SetToolTip(wx.ToolTip(help_Inserted))
        self.tc_DaysAgoInserted.Value = guiFunctions.configMe("extract", "insertedVal")
        
        label_DaysAgoInserted = wx.StaticText(panel, label="days ago")
        label_DaysAgoInserted.SetToolTip(wx.ToolTip(help_Inserted))

        # Add them to the sizer (optionBoxSizer)
        OptionBoxSizer.Add(label_OptionsInserted, pos=(sizerIndexX, 0), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=0)
        OptionBoxSizer.Add(self.combo_LogicalInserted, pos=(sizerIndexX,1), flag=wx.ALIGN_CENTER_VERTICAL|wx.ALL, border=1)
        OptionBoxSizer.Add(self.tc_DaysAgoInserted, pos=(sizerIndexX, 2), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)
        OptionBoxSizer.Add(label_DaysAgoInserted, pos=(sizerIndexX,3), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)

        # Modified
        sizerIndexX += 1
        label_OptionsModified = wx.StaticText(panel, label="Modified:")
        help_Modified= "Extract files to the Target Database based on the LAST MODIFIED DATE of the music files in the Source Database."
        label_OptionsModified.SetToolTip(wx.ToolTip(help_Modified))

        self.combo_LogicalModified = wx.ComboBox(panel, 1, "", (25, 25), (60, 25), logicList, wx.CB_DROPDOWN)
        self.combo_LogicalModified.SetToolTip(wx.ToolTip(help_Modified))
        self.combo_LogicalModified.Select(guiFunctions.configMe("extract", "modifiedidx", integer=True))

        self.tc_DaysAgoModified = wx.TextCtrl(panel)
        self.tc_DaysAgoModified.SetToolTip(wx.ToolTip(help_Modified))

        label_DaysAgoModified = wx.StaticText(panel, label="days ago")
        label_DaysAgoModified.SetToolTip(wx.ToolTip(help_Modified))
        self.tc_DaysAgoModified.Value = guiFunctions.configMe("extract", "modifiedval")

        # Add them to the sizer (optionBoxSizer)
        OptionBoxSizer.Add(label_OptionsModified, pos=(sizerIndexX, 0), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=0)
        OptionBoxSizer.Add(self.combo_LogicalModified, pos=(sizerIndexX,1), flag=wx.ALIGN_CENTER_VERTICAL|wx.ALL, border=1)
        OptionBoxSizer.Add(self.tc_DaysAgoModified, pos=(sizerIndexX, 2), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)
        OptionBoxSizer.Add(label_DaysAgoModified, pos=(sizerIndexX,3), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)

        # Accessed
        sizerIndexX += 1
        label_OptionsAccessed = wx.StaticText(panel, label="Accessed:")
        help_Accessed= "Extract files to the Target Database based on the LAST ACCESSED DATE of the music files in the Source Database."
        label_OptionsAccessed.SetToolTip(wx.ToolTip(help_Accessed))

        self.combo_LogicalAccessed = wx.ComboBox(panel, 1, "", (25, 25), (60, 25), logicList, wx.CB_DROPDOWN)
        self.combo_LogicalAccessed.Select(guiFunctions.configMe("extract", "accessedIdx", integer=True))
        self.combo_LogicalAccessed.SetToolTip(wx.ToolTip(help_Accessed))

        self.tc_DaysAgoAccessed = wx.TextCtrl(panel)
        self.tc_DaysAgoAccessed.SetToolTip(wx.ToolTip(help_Accessed))
        self.tc_DaysAgoAccessed.Value = guiFunctions.configMe("extract", "accessedVal")

        label_DaysAgoAccessed = wx.StaticText(panel, label="days ago")
        label_DaysAgoAccessed.SetToolTip(wx.ToolTip(help_Accessed))

        # Add them to the sizer (optionBoxSizer)
        OptionBoxSizer.Add(label_OptionsAccessed, pos=(sizerIndexX, 0), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=0)
        OptionBoxSizer.Add(self.combo_LogicalAccessed, pos=(sizerIndexX,1), flag=wx.ALIGN_CENTER_VERTICAL|wx.ALL, border=1)
        OptionBoxSizer.Add(self.tc_DaysAgoAccessed, pos=(sizerIndexX, 2), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)
        OptionBoxSizer.Add(label_DaysAgoAccessed, pos=(sizerIndexX,3), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)

        # Year
        sizerIndexX += 1
        label_OptionsYear = wx.StaticText(panel, label="Year Recorded:")
        help_Year = "Extract files to the Target Database based on the YEAR RECORDED tag of the music files in the Source Database."
        label_OptionsYear.SetToolTip(wx.ToolTip(help_Year))

        self.combo_LogicalYear = wx.ComboBox(panel, 1, "", (25, 25), (60, 25), logicList, wx.CB_DROPDOWN)
        self.combo_LogicalYear.Select(guiFunctions.configMe("extract", "yearIdx", integer=True))
        self.combo_LogicalYear.SetToolTip(wx.ToolTip(help_Year))

        self.tc_Year = wx.TextCtrl(panel)
        self.tc_Year.SetToolTip(wx.ToolTip(help_Year))
        self.tc_Year.Value = guiFunctions.configMe("extract", "yearVal")

        # Add them to the sizer (optionBoxSizer)
        OptionBoxSizer.Add(label_OptionsYear, pos=(sizerIndexX, 0), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=0)
        OptionBoxSizer.Add(self.combo_LogicalYear, pos=(sizerIndexX,1), flag=wx.ALIGN_CENTER_VERTICAL|wx.ALL, border=1)
        OptionBoxSizer.Add(self.tc_Year, pos=(sizerIndexX, 2), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)

        # Genre
        sizerIndexX += 1
        label_OptionsGenre = wx.StaticText(panel, label="Genre:")
        help_Genre = "Extract files to the Target Database based on the GENRE tag of the music files in the Source Database.  This is case sensitive."
        label_OptionsGenre.SetToolTip(wx.ToolTip(help_Genre))

        self.tc_Genre = wx.TextCtrl(panel)
        self.tc_Genre.SetToolTip(wx.ToolTip(help_Genre))
        self.tc_Genre.Value = guiFunctions.configMe("extract", "genre")

        # Add them to the sizer (optionBoxSizer)
        OptionBoxSizer.Add(label_OptionsGenre, pos=(sizerIndexX, 0), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=0)
        OptionBoxSizer.Add(self.tc_Genre, pos=(sizerIndexX, 1), span=(1,2), flag=wx.TOP|wx.LEFT|wx.RIGHT|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=0)

        # Artist
        sizerIndexX += 1
        label_OptionsArtist = wx.StaticText(panel, label="Artist:")
        help_Artist = "Extract files to the Target Database based on the ARTIST tag of the music files in the Source Database.  This is case sensitive."
        label_OptionsArtist.SetToolTip(wx.ToolTip(help_Artist))

        self.tc_Artist = wx.TextCtrl(panel)
        self.tc_Artist.SetToolTip(wx.ToolTip(help_Artist))
        self.tc_Artist.Value = guiFunctions.configMe("extract", "artist")

        # Add them to the sizer (optionBoxSizer)
        OptionBoxSizer.Add(label_OptionsArtist, pos=(sizerIndexX, 0), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=0)
        OptionBoxSizer.Add(self.tc_Artist, pos=(sizerIndexX, 1), span=(1,2), flag=wx.TOP|wx.LEFT|wx.RIGHT|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=0)

        # Composer
        sizerIndexX += 1
        label_OptionsComposer = wx.StaticText(panel, label="Composer:")
        help_Composer = "Extract files to the Target Database based on the COMPOSER tag of the music files in the Source Database.  This is case sensitive."
        label_OptionsComposer.SetToolTip(wx.ToolTip(help_Composer))

        self.tc_Composer = wx.TextCtrl(panel)
        self.tc_Composer.SetToolTip(wx.ToolTip(help_Composer))
        self.tc_Composer.Value = guiFunctions.configMe("extract", "composer")

        # Add them to the sizer (optionBoxSizer)
        OptionBoxSizer.Add(label_OptionsComposer, pos=(sizerIndexX, 0), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=0)
        OptionBoxSizer.Add(self.tc_Composer, pos=(sizerIndexX, 1), span=(1,2), flag=wx.TOP|wx.LEFT|wx.RIGHT|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=0)

        # Bit-rate
        sizerIndexX += 1
        label_OptionsBitrate = wx.StaticText(panel, label="Bitrate:")
        help_Bitrate = "Extract files to the Target Database based on the BIT-RATE of the music files in the Source Database."
        label_OptionsBitrate.SetToolTip(wx.ToolTip(help_Bitrate))

        self.combo_LogicalBitrate = wx.ComboBox(panel, 1, "", (25, 25), (60, 25), logicList, wx.CB_DROPDOWN)
        self.combo_LogicalBitrate.Select(guiFunctions.configMe("extract", "bitrateIdx", integer=True))
        self.combo_LogicalBitrate.SetToolTip(wx.ToolTip(help_Bitrate))

        self.tc_Bitrate = wx.TextCtrl(panel)
        self.tc_Bitrate.SetToolTip(wx.ToolTip(help_Bitrate))
        self.tc_Bitrate.Value = guiFunctions.configMe("extract", "bitrateVal")

        # Add them to the sizer (optionBoxSizer)
        OptionBoxSizer.Add(label_OptionsBitrate, pos=(sizerIndexX, 0), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=0)
        OptionBoxSizer.Add(self.combo_LogicalBitrate, pos=(sizerIndexX, 1), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)
        OptionBoxSizer.Add(self.tc_Bitrate, pos=(sizerIndexX, 2), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)

        # Last X Albums
        sizerIndexX += 1
        label_Last = wx.StaticText(panel, label="Last:")
        help_Last = "[EXPERIMENTAL] Extract files to the Target Database based on the MOST RECENT <#> OF ALBUMS in the Source Database."
        label_Last.SetToolTip(wx.ToolTip(help_Last))

        self.tc_Last = wx.TextCtrl(panel)
        self.tc_Last.SetToolTip(wx.ToolTip(help_Last))
        self.tc_Last.Value = guiFunctions.configMe("extract", "last")

        label_Albums = wx.StaticText(panel, label="Albums")
        label_Albums.SetToolTip(wx.ToolTip(help_Last))

        # Add them to the sizer (optionBoxSizer)
        OptionBoxSizer.Add(label_Last, pos=(sizerIndexX, 0), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_RIGHT, border=0)
        OptionBoxSizer.Add(self.tc_Last, pos=(sizerIndexX, 1), span=(1,2), flag=wx.ALL|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)
        OptionBoxSizer.Add(label_Albums, pos=(sizerIndexX, 3), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL|wx.ALIGN_LEFT, border=0)

        OptionBoxSizer.AddGrowableCol(4)
        sbs_ExtractOptions.Add(OptionBoxSizer, flag=wx.TOP|wx.LEFT|wx.RIGHT|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(sbs_ExtractOptions, pos=(2, 0), span=(1,6),flag=wx.TOP|wx.LEFT|wx.RIGHT|wx.EXPAND|wx.ALIGN_CENTER_VERTICAL, border=10)

    # --------------------------------------------------------------------------
    # [3] Add Scan Options and Scan Button -------------------------------------
        self.bt_Extract = wx.Button(panel, label="Extract")
        help_Extract = "Click to start the extract process based on the options chosen above."
        self.bt_Extract.SetToolTip(wx.ToolTip(help_Extract))
        self.bt_Extract.Bind(wx.EVT_BUTTON, self.bt_ExtractClick, self.bt_Extract)

        self.ck_ExtractVerbose = wx.CheckBox(panel, label="Verbose")
        help_ExtractVerbose = "Select this checkbox if you want to turn on the verbose settings during the extract."
        self.ck_ExtractVerbose.SetToolTip(wx.ToolTip(help_ExtractVerbose))
        self.ck_ExtractVerbose.Value = guiFunctions.configMe("extract", "verbose", bool=True)

        self.bt_SaveLog = wx.Button(panel, label="Save to Log")
        help_SaveLogToFile = "Save the log below to a file."
        self.bt_SaveLog.SetToolTip(wx.ToolTip(help_SaveLogToFile))
        self.bt_SaveLog.Bind(wx.EVT_BUTTON, self.bt_SaveLogClick, self.bt_SaveLog)

        self.ck_OverwriteExisting = wx.CheckBox(panel, label="Overwrite")
        help_Overwrite = "Select this checkbox if you want to overwrite the Target Database."
        self.ck_OverwriteExisting.SetToolTip(wx.ToolTip(help_Overwrite))
        self.ck_OverwriteExisting.Value = guiFunctions.configMe("extract", "overwrite", bool=True)

        # SAVE AS DEFAULTS
        self.bt_SaveDefaults = wx.Button(panel, label="Save Defaults")
        help_SaveDefaults = "Save current settings as default."
        self.bt_SaveDefaults.SetToolTip(wx.ToolTip(help_SaveDefaults))
        self.bt_SaveDefaults.Bind(wx.EVT_BUTTON, self.bt_SaveDefaultsClick, self.bt_SaveDefaults)

        sizer.Add(self.bt_Extract, pos=(3,0), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_SaveLog, pos=(3,1), flag=wx.ALIGN_CENTER_VERTICAL|wx.EXPAND|wx.RIGHT, border=10)
        sizer.Add(self.ck_ExtractVerbose, pos=(3,2), flag=wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.ck_OverwriteExisting, pos=(3,3), flag=wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.bt_SaveDefaults, pos=(3,4), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

    # --------------------------------------------------------------------------
    # [4] Separator line ------------------------------------------------------
        hl_SepLine2 = wx.StaticLine(panel, 0, (250, 50), (300,1))
        sizer.Add(hl_SepLine2, pos=(4, 0), span=(1, 6), flag=wx.EXPAND, border=10)
    # --------------------------------------------------------------------------
    # [5] Output/Log Box -------------------------------------------------------
        self.LogWindow = wx.TextCtrl(panel, -1,"",size=(100, 100), style=wx.TE_MULTILINE|wx.TE_READONLY)
        LogFont = wx.Font(7.5, wx.SWISS, wx.NORMAL, wx.NORMAL, False)
        self.LogWindow.SetFont(LogFont)
        help_LogWindow = "Results of a extract will appear here."
        self.LogWindow.SetToolTip(wx.ToolTip(help_LogWindow))
        self.LogWindow.SetInsertionPoint(0)
        self.LogWindow.Disable()
        sizer.Add(self.LogWindow, pos=(5,0), span=(1,6), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        # Indicate we don't have a worker thread yet
        EVT_RESULT(self,self.onResult)
        self.worker = None

        sizer.AddGrowableCol(2)
        panel.SetSizer(sizer)
        
    def onResult(self, event):
        """Show Result status."""
        if event.data is None:
            # Thread aborted (using our convention of None return)
            self.LogWindow.AppendText("\n[Complete]\n\n")
            guiFunctions.statusText(self, "Job Complete...")
            self.setButtons(True)
        else:
            # Process results here
            self.LogWindow.AppendText(event.data)
        # In either event, the worker is done
        self.worker = None

    def bt_MainDatabaseClick(self, event):
        filters = guiFunctions.configMe("general", "database_extensions")
        wildcards = "Sonospy Database (" + filters + ")|" + filters.replace(" ", ";") + "|All files (*.*)|*.*"

        # back up to the folder below our current one.  save cwd in variable
        owd = os.getcwd()
        os.chdir(os.pardir)

        dialog = wx.FileDialog ( None, message = 'Select Source Database File...', wildcard = wildcards, style = wxOPEN)

        # Open Dialog Box and get Selection
        if dialog.ShowModal() == wxID_OK:
            selected = dialog.GetFilenames()
            for selection in selected:
                self.tc_MainDatabase.Value = selection
        dialog.Destroy()
        guiFunctions.statusText(self, "Main Database: " + selection + " selected...")

        # set back to original working directory
        os.chdir(owd)

    def bt_TargetDatabaseClick(self, event):
        filters = guiFunctions.configMe("general", "database_extensions")
        wildcards = "Sonospy Database (" + filters + ")|" + filters.replace(" ", ";") + "|All files (*.*)|*.*"
        
        # back up to the folder below our current one.  save cwd in variable
        owd = os.getcwd()
        os.chdir(os.pardir)
        
        dialog = wx.FileDialog ( None, message = 'Select Target Database File...', wildcard = wildcards, style = wxOPEN )

        # Open Dialog Box and get Selection
        if dialog.ShowModal() == wxID_OK:
            selected = dialog.GetFilenames()
            for selection in selected:
                self.tc_TargetDatabase.Value = selection
        dialog.Destroy()
        guiFunctions.statusText(self, "Target Database: " + selection + " selected...")

        # set back to original working directory
        os.chdir(owd)

    def setButtons(self, state):
        """
        Toggle for the button states.
        """
        if state == True:
            self.bt_Extract.Enable()
            self.bt_MainDatabase.Enable()
            self.bt_SaveLog.Enable()
            self.bt_TargetDatabase.Enable()
            self.ck_ExtractVerbose.Enable()
            self.ck_OverwriteExisting.Enable()
            wx.SetCursor(wx.StockCursor(wx.CURSOR_ARROW))
        else:
            self.bt_Extract.Disable()
            self.bt_MainDatabase.Disable()
            self.bt_SaveLog.Disable()
            self.bt_TargetDatabase.Disable()
            self.ck_ExtractVerbose.Disable()
            self.ck_OverwriteExisting.Disable()
            wx.SetCursor(wx.StockCursor(wx.CURSOR_WATCH))

    def bt_ExtractClick(self, event):
        global scanCMD
        global getOpts
        # Set Original Working Directory so we can get back to here.
        owd = os.getcwd()
        os.chdir(os.pardir)

        if os.name == 'nt':
            cmdroot = 'python '
        else:
            cmdroot = './'

        self.LogWindow.Enable()

        if self.tc_MainDatabase.Value == "":
            self.LogWindow.AppendText("ERROR:\tNo source database name selected!\n")
        elif self.tc_TargetDatabase.Value == "":
            self.LogWindow.AppendText("ERROR:\tNo target database name selected.\n")
        elif self.tc_MainDatabase.Value == self.tc_TargetDatabase.Value:
            self.LogWindow.AppendText("ERROR:\tSource database and target database cannot be the same database!\n")
        else:
            searchCMD = ""
            # Scrub the fields to see what our extract command should be.
            # Eventually stack these with some sort of AND query.

            if self.tc_DaysAgoCreated.Value != "":
                if searchCMD == "":
                    searchCMD = "where (julianday(datetime(\'now\')) - julianday(datetime(created, \'unixepoch\'))) " + self.combo_LogicalCreated.Value + " " + self.tc_DaysAgoCreated.Value
                else:
                    searchCMD += " AND where (julianday(datetime(\'now\')) - julianday(datetime(created, \'unixepoch\'))) " + self.combo_LogicalCreated.Value + " " + self.tc_DaysAgoCreated.Value

            if self.tc_DaysAgoInserted.Value != "":
                if searchCMD == "":
                    searchCMD = "where (julianday(datetime(\'now\')) - julianday(datetime(inserted, \'unixepoch\'))) " + self.combo_LogicalInserted.Value + " " + self.tc_DaysAgoInserted.Value
                else:
                    searchCMD += " AND where (julianday(datetime(\'now\')) - julianday(datetime(inserted, \'unixepoch\'))) " + self.combo_LogicalInserted.Value + " " + self.tc_DaysAgoInserted.Value

            if self.tc_DaysAgoModified.Value != "":
                if searchCMD == "":
                    searchCMD = "where (julianday(datetime(\'now\')) - julianday(datetime(lastmodified, \'unixepoch\'))) " + self.combo_LogicalModified.Value + " " + self.tc_DaysAgoModified.Value
                else:
                    searchCMD += " AND where (julianday(datetime(\'now\')) - julianday(datetime(lastmodified, \'unixepoch\'))) " + self.combo_LogicalModified.Value + " " + self.tc_DaysAgoModified.Value

            if self.tc_DaysAgoAccessed.Value != "":
                if searchCMD == "":
                    searchCMD = "where (julianday(datetime(\'now\')) - julianday(datetime(lastaccessed, \'unixepoch\'))) " + self.combo_LogicalAccessed.Value + " " + self.tc_DaysAgoAccessed.Value
                else:
                    searchCMD += " AND where (julianday(datetime(\'now\')) - julianday(datetime(lastaccessed, \'unixepoch\'))) " + self.combo_LogicalAccessed.Value + " " + self.tc_DaysAgoAccessed.Value

            if self.tc_Year.Value != "":
                if searchCMD == "":
                    searchCMD = "where year " + self.combo_LogicalYear.Value + " " + self.tc_Year.Value
                else:
                    searchCMD += " AND where year " + self.combo_LogicalYear.Value + " " + self.tc_Year.Value

            if self.tc_Genre.Value != "":
                if searchCMD == "":
                    searchCMD = "where genre=\'" + self.tc_Genre.Value + "\'"
                else:
                    searchCMD += " AND where genre=\'" + self.tc_Genre.Value + "\'"

            if self.tc_Artist.Value != "":
                if searchCMD == "":
                    searchCMD = "where artist=\'" + self.tc_Artist.Value + "\'"
                else:
                    searchCMD += " AND where artist=\'" + self.tc_Artist.Value + "\'"

            if self.tc_Composer.Value != "":
                if searchCMD == "":
                    searchCMD = " AND where composer=\'" + self.tc_Composer.Value + "\'"
                else:
                    searchCMD += " AND where composer=\'" + self.tc_Composer.Value + "\'"

            if self.tc_Bitrate.Value != "":
                if searchCMD == "":
                    searchCMD = "where bitrate " + self.combo_LogicalBitrate.Value + " " + self.tc_Bitrate.Value
                else:
                    searchCMD += "AND where bitrate " + self.combo_LogicalBitrate.Value + " " + self.tc_Bitrate.Value

            if self.tc_Last.Value != "":
                if searchCMD != "":
                    self.LogWindow.AppendText("You cannot combine Last " + self.tc_Last.Value + " albums with other search options...")
                else:
                    searchCMD = "AS t WHERE t.created >= (SELECT a.created FROM albums AS a WHERE a.albumartist != 'Various Artists' ORDER BY a.created DESC LIMIT " + str(int(self.tc_Last.Value) - 1) + ",1)"

            if searchCMD !="":
                searchCMD = "\"" + searchCMD + "\""

                if self.ck_OverwriteExisting.Value == True:
                    if os.path.exists(self.tc_TargetDatabase.Value) == True:
                        illegals = ["/", "~", "!", "@", "#", "$", "%", "^", "&", "*", "(", ")", "+","=",","]
                        for illegal in illegals:
                            if illegal in self.tc_TargetDatabase.Value:
                                self.LogWindow.AppendText("\nERROR:\tInvalid target database! You cannot use " + illegal + " in the database name.")
                                return(1)
                        self.LogWindow.AppendText("\nRemoving file: " + self.tc_TargetDatabase.Value + " because 'Overwrite' is checked.")
                        os.remove(self.tc_TargetDatabase.Value)

                getOpts = ""
                if self.ck_ExtractVerbose.Value == True:
                    getOpts = "-v "

                scanCMD = cmdroot + "scan.py " + getOpts +"-d " + self.tc_MainDatabase.Value + " -x " + self.tc_TargetDatabase.Value + " -w " + searchCMD
                self.LogWindow.AppendText("\nExtracting from " + self.tc_MainDatabase.Value +" into " + self.tc_TargetDatabase.Value + "...\n\n")
                guiFunctions.statusText(self, "Extracting from " + self.tc_MainDatabase.Value +" into " + self.tc_TargetDatabase.Value + "...")


                
# DEBUG ------------------------------------------------------------------------
#                self.LogWindow.AppendText(scanCMD)
# ------------------------------------------------------------------------------

# Multithreading is below this line.
                if not self.worker:
                    self.worker = WorkerThread(self)
                    self.setButtons(False)
                    # set back to original working directory
                    os.chdir(owd)
# ------------------------------------------------------------------------------
            else:
                self.LogWindow.AppendText("\nERROR:\tYou have no extract options selected!")

            # set back to original working directory
            os.chdir(owd)
    def bt_SaveLogClick(self, event):
        dialog = wx.FileDialog(self, message='Choose a file', style=wx.SAVE|wx.OVERWRITE_PROMPT)
        if dialog.ShowModal() == wx.ID_OK:
            savefile = dialog.GetFilename()
            saveMe = open(savefile, 'w')
            saveMe.write(self.LogWindow.Value)
            saveMe.close()
            guiFunctions.statusText(self, "Logfile: " + savefile + " saved...")

    def bt_SaveDefaultsClick(self, event):
        section = "extract"

        guiFunctions.configWrite(section, "database_source", self.tc_MainDatabase.Value)
        guiFunctions.configWrite(section, "database_target", self.tc_TargetDatabase.Value)
        guiFunctions.configWrite(section, "createdidx", self.combo_LogicalCreated.GetCurrentSelection())
        guiFunctions.configWrite(section, "createdval", self.tc_DaysAgoCreated.Value)
        guiFunctions.configWrite(section, "insertedidx", self.combo_LogicalInserted.GetCurrentSelection())
        guiFunctions.configWrite(section, "insertedval", self.tc_DaysAgoInserted.Value)
        guiFunctions.configWrite(section, "modifiedidx", self.combo_LogicalModified.GetCurrentSelection())
        guiFunctions.configWrite(section, "modifiedval", self.tc_DaysAgoModified.Value)
        guiFunctions.configWrite(section, "accessedidx", self.combo_LogicalAccessed.GetCurrentSelection())
        guiFunctions.configWrite(section, "accessedval", self.tc_DaysAgoAccessed.Value)
        guiFunctions.configWrite(section, "yearidx", self.combo_LogicalYear.GetCurrentSelection())
        guiFunctions.configWrite(section, "yearval", self.tc_Year.Value)
        guiFunctions.configWrite(section, "genre", self.tc_Genre.Value)
        guiFunctions.configWrite(section, "artist", self.tc_Artist.Value)
        guiFunctions.configWrite(section, "composer", self.tc_Composer.Value)
        guiFunctions.configWrite(section, "bitrateidx", self.combo_LogicalBitrate.GetCurrentSelection())
        guiFunctions.configWrite(section, "bitrateval", self.tc_Bitrate.Value)
        guiFunctions.configWrite(section, "last", self.tc_Last.Value)
        guiFunctions.configWrite(section, "verbose", self.ck_ExtractVerbose.Value)
        guiFunctions.configWrite(section, "overwrite", self.ck_OverwriteExisting.Value)

        guiFunctions.statusText(self, "Defaults saved...")