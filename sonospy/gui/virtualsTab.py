###############################################################################
# Virtuals Tab for use with sonospyGUI.py
###############################################################################
# virtualsTab.py copyright (c) 2010-2011 John Chowanec
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
# virtualsTab.py Author: John Chowanec <chowanec@gmail.com>
###############################################################################
# TODO:
# - Load in an SP file
#   How to handle multiple SPs in one File?
# - Hook up default_music_path from ini on file dialog opens, etc.
###############################################################################

import wx
from wxPython.wx import *
import os
import subprocess
from threading import *
import guiFunctions


class VirtualsPanel(wx.Panel):
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

        xIndex = 0
    # --------------------------------------------------------------------------
    # [0] Virtuals Type      ---------------------------------------------------
        label_Type = wx.StaticText(panel, label="Type:")
        sizer.Add(label_Type, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)

        typeOptions = ['work', 'virtual']
        help_typeOptions = "Select the type of virtual you want to create."

        self.combo_typeOptions = wx.ComboBox(panel, 1, "", (25, 25), (290, 25), typeOptions, wx.CB_DROPDOWN)
        self.combo_typeOptions.SetToolTip(wx.ToolTip(help_typeOptions))
        self.combo_typeOptions.Select(guiFunctions.configMe("virtuals", "type", integer=True))
        sizer.Add(self.combo_typeOptions, pos=(xIndex, 1), span=(1,5), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)

        xIndex += 1
    # --------------------------------------------------------------------------
    # [1] Virtuals Title     ---------------------------------------------------
        label_Title = wx.StaticText(panel, label="Title:")
        sizer.Add(label_Title, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)

        help_title = "Title is the base name of the work or virtual (can be overridden in scan.ini)"
        self.tc_Title = wx.TextCtrl(panel)
        self.tc_Title.SetToolTip(wx.ToolTip(help_title))
        self.tc_Title.Value = guiFunctions.configMe("virtuals", "title")
        sizer.Add(self.tc_Title, pos=(xIndex,1), span=(1,5), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        xIndex += 1
    # --------------------------------------------------------------------------
    # [2] Virtuals Artist    ---------------------------------------------------
        label_Artist = wx.StaticText(panel, label="Artist:")
        sizer.Add(label_Artist, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)

        help_artist = "Name of the artist for the Virtual."
        self.tc_Artist = wx.TextCtrl(panel)
        self.tc_Artist.SetToolTip(wx.ToolTip(help_artist))
        self.tc_Artist.Value = guiFunctions.configMe("virtuals", "artist")
        sizer.Add(self.tc_Artist, pos=(xIndex,1), span=(1,5), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        xIndex += 1

    # --------------------------------------------------------------------------
    # [3] Virtuals Album Artist ------------------------------------------------
        label_AlbumArtist = wx.StaticText(panel, label="Album Artist:")
        sizer.Add(label_AlbumArtist, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)

        help_albumartist = "Name of the album artist for the Virtual."
        self.tc_AlbumArtist = wx.TextCtrl(panel)
        self.tc_AlbumArtist.SetToolTip(wx.ToolTip(help_albumartist))
        self.tc_AlbumArtist.Value = guiFunctions.configMe("virtuals", "albumartist")
        sizer.Add(self.tc_AlbumArtist, pos=(xIndex,1), span=(1,5), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        xIndex += 1

    # --------------------------------------------------------------------------
    # [4] Virtuals Composer ------------------------------------------------
        label_Composer = wx.StaticText(panel, label="Composer:")
        sizer.Add(label_Composer, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)

        help_composer = "Name of the composer for the Virtual."
        self.tc_Composer = wx.TextCtrl(panel)
        self.tc_Composer.SetToolTip(wx.ToolTip(help_composer))
        self.tc_Composer.Value = guiFunctions.configMe("virtuals", "composer")
        sizer.Add(self.tc_Composer, pos=(xIndex,1), span=(1,5), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        xIndex += 1

    # --------------------------------------------------------------------------
    # [5] Virtuals Year         ------------------------------------------------
        label_Year = wx.StaticText(panel, label="Year:")
        sizer.Add(label_Year, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)

        help_Year = "The year for the Virtual."
        self.tc_Year = wx.TextCtrl(panel)
        self.tc_Year.SetToolTip(wx.ToolTip(help_Year))
        self.tc_Year.Value = guiFunctions.configMe("virtuals", "year")
        sizer.Add(self.tc_Year, pos=(xIndex,1), span=(1,5), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        xIndex += 1

    # --------------------------------------------------------------------------
    # [6] Virtuals Genre         -----------------------------------------------
        label_Genre = wx.StaticText(panel, label="Genre:")
        sizer.Add(label_Genre, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)

        help_Genre = "The Genre for the Virtual."
        self.tc_Genre = wx.TextCtrl(panel)
        self.tc_Genre.SetToolTip(wx.ToolTip(help_Genre))
        self.tc_Genre.Value = guiFunctions.configMe("virtuals", "genre")
        sizer.Add(self.tc_Genre, pos=(xIndex,1), span=(1,5), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        xIndex += 1

    # --------------------------------------------------------------------------
    # [7] Virtuals Cover         -----------------------------------------------
        label_Cover = wx.StaticText(panel, label="Cover:")
        sizer.Add(label_Cover, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)

        help_Cover = "The Cover for the Virtual."
        self.tc_Cover = wx.TextCtrl(panel)
        self.tc_Cover.SetToolTip(wx.ToolTip(help_Cover))
        self.tc_Cover.Value = guiFunctions.configMe("virtuals", "cover")
        sizer.Add(self.tc_Cover, pos=(xIndex,1), span=(1,5), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        xIndex += 1

    # --------------------------------------------------------------------------
    # [8] Virtuals Disc Number   -----------------------------------------------
        label_DiscNumber = wx.StaticText(panel, label="Disc Number:")
        sizer.Add(label_DiscNumber, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)

        help_DiscNumber = "The Disc Number for the Virtual."
        self.tc_DiscNumber = wx.TextCtrl(panel)
        self.tc_DiscNumber.SetToolTip(wx.ToolTip(help_DiscNumber))
        self.tc_DiscNumber.Value = guiFunctions.configMe("virtuals", "discnumber")
        sizer.Add(self.tc_DiscNumber, pos=(xIndex,1), span=(1,5), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        xIndex += 1

    # 9 inserted=
        xIndex += 1
    # 10 created=
        xIndex += 1
    # 11 lastmodified=
        xIndex += 1

    # --------------------------------------------------------------------------
    # [11] Folders and Tracks    -----------------------------------------------
        self.sb_FilesFolders = wx.StaticBox(panel, label="Files and Folders to Scan:", size=(200, 130))
        help_FilesFolders = "Tracks and folders for your virtual are listed here  Click ADD FOLDER to add a folder and ADD FILE(S) to add individual tracks."
        folderBoxSizer = wx.StaticBoxSizer(self.sb_FilesFolders, wx.VERTICAL)
        self.tc_FilesFolders = wx.TextCtrl(panel, -1,"",size=(300, 130), style=wx.TE_MULTILINE|wx.TE_READONLY)
        self.tc_FilesFolders.SetToolTip(wx.ToolTip(help_FilesFolders))
        self.tc_FilesFolders.Value = guiFunctions.configMe("virtuals", "tracks", parse=True)
        self.tc_FilesFolders.SetInsertionPoint(0)

        folderBoxSizer.Add(self.tc_FilesFolders, flag=wx.EXPAND)
        sizer.Add(folderBoxSizer, pos=(xIndex, 0), span=(1, 6), flag=wx.EXPAND|wx.TOP|wx.LEFT|wx.RIGHT, border=10)

        xIndex += 1

    # --------------------------------------------------------------------------
    # [2] Buttons to Add Folder, Files, Clear, Save Defaults -------------------
        # ADD FOLDER
        self.bt_FoldersToScanAdd = wx.Button(panel, label="Add Folder")
        help_FoldersToScanAdd = "Add a top-level folder to the above field. The scan will search any sub-folders beneath whatever folder you add."
        self.bt_FoldersToScanAdd.SetToolTip(wx.ToolTip(help_FoldersToScanAdd))
        self.bt_FoldersToScanAdd.Bind(wx.EVT_BUTTON, self.bt_FoldersToScanAddClick, self.bt_FoldersToScanAdd)
        sizer.Add(self.bt_FoldersToScanAdd, pos=(xIndex,0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)

        # ADD FILES
        self.bt_FilesToScanAdd = wx.Button(panel, label="Add Track(s)")
        help_FilesToScanAdd = "Add individual tracks to the above field."
        self.bt_FilesToScanAdd.SetToolTip(wx.ToolTip(help_FilesToScanAdd))
        self.bt_FilesToScanAdd.Bind(wx.EVT_BUTTON, self.bt_FilesToScanAddClick, self.bt_FilesToScanAdd)
        sizer.Add(self.bt_FilesToScanAdd, pos=(xIndex, 1), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)

        # CLEAR SCAN AREA
        self.bt_FoldersToScanClear = wx.Button(panel, label="Clear")
        help_FoldersToScanClear = "Clear the Tracks and Folders listed."
        self.bt_FoldersToScanClear.SetToolTip(wx.ToolTip(help_FoldersToScanClear))
        sizer.Add(self.bt_FoldersToScanClear, pos=(xIndex,2), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)
        self.bt_FoldersToScanClear.Bind(wx.EVT_BUTTON, self.bt_FoldersToScanClearClick, self.bt_FoldersToScanClear)

        # SAVE VIRTUAL
        self.bt_SaveVirtual = wx.Button(panel, label="Save as File")
        help_SaveVirtual = "Save current settings .sp file."
        self.bt_SaveVirtual.SetToolTip(wx.ToolTip(help_SaveVirtual))
        self.bt_SaveVirtual.Bind(wx.EVT_BUTTON, self.bt_SavePlaylistClick, self.bt_SaveVirtual)
        sizer.Add(self.bt_SaveVirtual, pos=(xIndex,3), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL, border=10)

        # SAVE AS DEFAULTS
        self.bt_SaveDefaults = wx.Button(panel, label="Save Defaults")
        help_SaveDefaults = "Save current settings as default."
        self.bt_SaveDefaults.SetToolTip(wx.ToolTip(help_SaveDefaults))
        self.bt_SaveDefaults.Bind(wx.EVT_BUTTON, self.bt_SaveDefaultsClick, self.bt_SaveDefaults)
        sizer.Add(self.bt_SaveDefaults, pos=(xIndex,4), flag=wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        sizer.AddGrowableCol(2)
        panel.SetSizer(sizer)

    def bt_FoldersToScanAddClick(self, event):
        dialog = wx.DirDialog(self, "Add a Directory...", style=wx.DD_DEFAULT_STYLE)
        if dialog.ShowModal() == wx.ID_OK:
            if self.tc_FilesFolders.Value == "":
                self.tc_FilesFolders.AppendText("%s" % dialog.GetPath())
            else:
                self.tc_FilesFolders.AppendText("\n%s" % dialog.GetPath())

        dialog.Destroy()
        guiFunctions.statusText(self, "Folder: " + "%s" % dialog.GetPath() + " added.")

    def bt_FoldersToScanClearClick(self, event):
        self.tc_FilesFolders.Value = ""
        guiFunctions.statusText(self, "Cleared folder and track list...")

    def bt_FilesToScanAddClick(self, event):
        dialog = wx.FileDialog(self, "Add Track(s)...", style=wx.DD_DEFAULT_STYLE|wx.FD_MULTIPLE)
        if dialog.ShowModal() == wxID_OK:
            selected = dialog.GetFilenames()
            for selection in selected:
                if self.tc_FilesFolders.Value == "":
                    self.tc_FilesFolders.AppendText(selection)
                else:
                    self.tc_FilesFolders.AppendText("\n" + selection)
        dialog.Destroy()
        guiFunctions.statusText(self, "Tracks added.")

    def bt_SavePlaylistClick(self, event):
        dataToSave = "type=" + self.combo_typeOptions.GetValue()
        dataToSave += "\n" + "title=" + self.tc_Title.Value
        dataToSave += "\n" + "artist=" + self.tc_Artist.Value
        dataToSave += "\n" + "albumartist=" + self.tc_AlbumArtist.Value
        dataToSave += "\n" + "composer=" + self.tc_Composer.Value
        dataToSave += "\n" + "year=" + self.tc_Year.Value
        dataToSave += "\n" + "genre=" + self.tc_Genre.Value
        dataToSave += "\n" + "cover=" + self.tc_Cover.Value
        dataToSave += "\n" + "discnumber=" + self.tc_DiscNumber.Value
        dataToSave += "\n" + "inserted="
        dataToSave += "\n" + "created="
        dataToSave += "\n" + "lastmodified="
        dataToSave += "\n\n"
        dataToSave += self.tc_FilesFolders.Value

        dialog = wx.FileDialog(self, message='Choose a file', wildcard="Playlist Files (*.sp)|*.sp", style=wx.SAVE|wx.OVERWRITE_PROMPT)
        if dialog.ShowModal() == wx.ID_OK:
            savefile = dialog.GetFilename()
            saveMe = open(savefile, 'w')
            saveMe.write(dataToSave)
            saveMe.close()
            guiFunctions.statusText(self, "SP: " + savefile + " saved...")

    def bt_SaveDefaultsClick(self, event):
        section = "virtuals"
        guiFunctions.configWrite(section, "type", self.combo_typeOptions.GetCurrentSelection())
        guiFunctions.configWrite(section, "title", self.tc_Title.Value)

        guiFunctions.configWrite(section, "artist", self.tc_Artist.Value)
        guiFunctions.configWrite(section, "albumartist", self.tc_AlbumArtist.Value)
        guiFunctions.configWrite(section, "composer", self.tc_Composer.Value)
        guiFunctions.configWrite(section, "year", self.tc_Year.Value)
        guiFunctions.configWrite(section, "genre", self.tc_Genre.Value)
        guiFunctions.configWrite(section, "cover", self.tc_Cover.Value)
        guiFunctions.configWrite(section, "discnumber", self.tc_DiscNumber.Value)

        folders = ""
        numLines = 0
        maxLines=(int(self.tc_FilesFolders.GetNumberOfLines()))
        while (numLines < maxLines):
            folders += str(self.tc_FilesFolders.GetLineText(numLines))
            numLines += 1
            if numLines != maxLines:
                folders += "|"
        guiFunctions.configWrite(section, "tracks", folders)


        guiFunctions.statusText(self, "Defaults saved...")