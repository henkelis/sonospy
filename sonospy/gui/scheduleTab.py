###############################################################################
# Schedule Tab for use with sonospyGUI.py
###############################################################################
# scheduleTab.py copyright (c) 2010-2013 John Chowanec
# mutagen copyright (c) 2005 Joe Wreschnig, Michael Urman (mutagen is Licensed under GPL version 2.0)
# Sonospy Project copyright (c) 2010-2013 Mark Henkelis
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
# scheduleTab.py Author: John Chowanec <chowanec@gmail.com>
###############################################################################
# TODO:
# - All of it!
###############################################################################

import wx
from wxPython.wx import *
import os
import subprocess
from threading import *
import guiFunctions
from wx.lib.pubsub import Publisher

class SchedulePanel(wx.Panel):
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

    # [0] Make Header Columns --------------------------
        label_CmdToRun = wx.StaticText(panel, label="Command to Run")
        label_HrToRun = wx.StaticText(panel, label="Hour")
        label_MinToRun = wx.StaticText(panel, label="Minute")

        sizer.Add(label_CmdToRun, pos=(xIndex, 0), flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT|wx.RIGHT|wx.TOP, border=10)
        sizer.Add(label_HrToRun, pos=(xIndex, 4), flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT|wx.RIGHT|wx.TOP, border=10)
        sizer.Add(label_MinToRun, pos=(xIndex, 5), flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT|wx.RIGHT|wx.TOP, border=10)

        xIndex += 1
    # --------------------------------------------------------------------------
    # [1] Schedule 1-12          -----------------------------------------------
        self.tc_S1 = wx.TextCtrl(panel)
        self.tc_S1hr = wx.TextCtrl(panel)
        self.tc_S1hr.Value = guiFunctions.configMe("schedule", "cmd1hr")
        self.tc_S1.Value = guiFunctions.configMe("schedule", "cmd1")
        self.tc_S1min = wx.TextCtrl(panel)
        self.tc_S1min.Value = guiFunctions.configMe("schedule", "cmd1min")

        sizer.Add(self.tc_S1, pos=(xIndex,0), span=(1,3), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_S1hr, pos=(xIndex,4), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_S1min, pos=(xIndex, 5), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        xIndex += 1

        self.tc_S2 = wx.TextCtrl(panel)
        self.tc_S2hr = wx.TextCtrl(panel)
        self.tc_S2hr.Value = guiFunctions.configMe("schedule", "cmd2hr")
        self.tc_S2.Value = guiFunctions.configMe("schedule", "cmd2")
        self.tc_S2min = wx.TextCtrl(panel)
        self.tc_S2min.Value = guiFunctions.configMe("schedule", "cmd2min")

        sizer.Add(self.tc_S2, pos=(xIndex,0), span=(1,3), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_S2hr, pos=(xIndex,4), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_S2min, pos=(xIndex, 5), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        xIndex += 1

        self.tc_S3 = wx.TextCtrl(panel)
        self.tc_S3hr = wx.TextCtrl(panel)
        self.tc_S3hr.Value = guiFunctions.configMe("schedule", "cmd3hr")
        self.tc_S3.Value = guiFunctions.configMe("schedule", "cmd3")
        self.tc_S3min = wx.TextCtrl(panel)
        self.tc_S3min.Value = guiFunctions.configMe("schedule", "cmd3min")

        sizer.Add(self.tc_S3, pos=(xIndex,0), span=(1,3), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_S3hr, pos=(xIndex,4), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_S3min, pos=(xIndex, 5), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        xIndex += 1

        self.tc_S4 = wx.TextCtrl(panel)
        self.tc_S4hr = wx.TextCtrl(panel)
        self.tc_S4hr.Value = guiFunctions.configMe("schedule", "cmd4hr")
        self.tc_S4.Value = guiFunctions.configMe("schedule", "cmd4")
        self.tc_S4min = wx.TextCtrl(panel)
        self.tc_S4min.Value = guiFunctions.configMe("schedule", "cmd4min")

        sizer.Add(self.tc_S4, pos=(xIndex,0), span=(1,3), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_S4hr, pos=(xIndex,4), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)
        sizer.Add(self.tc_S4min, pos=(xIndex, 5), flag=wx.EXPAND|wx.LEFT|wx.RIGHT|wx.ALIGN_CENTER_VERTICAL, border=10)

        xIndex += 1

        Publisher().subscribe(self.setSchedulePanel, 'setSchedulePanel')

        sizer.AddGrowableCol(2)
        panel.SetSizer(sizer)



    def setSchedulePanel(self, msg):
        if msg.data == "Disable":
            self.Disable()
        else:
            self.Enable()

    def bt_FoldersToScanAddClick(self, event):
        dialog = wx.DirDialog(self, "Add a Directory...", defaultPath=guiFunctions.configMe("general", "default_music_path"), style=wx.DD_DEFAULT_STYLE)
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
        dialog = wx.FileDialog(self, "Add Track(s)...", defaultDir=guiFunctions.configMe("general", "default_music_path"), style=wx.DD_DEFAULT_STYLE|wx.FD_MULTIPLE)
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

        dialog = wx.FileDialog(self, message='Choose a file', defaultDir=guiFunctions.configMe("general", "default_sp_path"), wildcard="Playlist Files (*.sp)|*.sp", style=wx.SAVE|wx.OVERWRITE_PROMPT)
        if dialog.ShowModal() == wx.ID_OK:
            savefile = dialog.GetFilename()
            basename, extension = os.path.splitext(savefile)
            if extension == "":
                extension = ".sp"
            savefile = basename + extension
            savedir = dialog.GetDirectory()
            saveMe=open(os.path.join(savedir, savefile),'w')
            print os.path.join(savedir, savefile)
            saveMe.write(dataToSave)
            saveMe.close()
            guiFunctions.statusText(self, "SP: " + savefile + " saved...")

    def bt_LoadVirtualClick(self, event):
        filters = guiFunctions.configMe("general", "playlist_extensions")
        defDir = guiFunctions.configMe("general", "default_sp_path")
        wildcards = "Virtual/Work Playlists (" + filters + ")|" + filters.replace(" ", ";") + "|All files (*.*)|*.*"

        # back up to the folder below our current one.  save cwd in variable
        owd = os.getcwd()
        os.chdir(os.pardir)

        dialog = wx.FileDialog ( None, message = 'Select Virtual/Works Playlist File...', defaultDir=defDir, wildcard = wildcards, style = wxOPEN)

        
        # Open Dialog Box and get Selection
        if dialog.ShowModal() == wxID_OK:
            selected = dialog.GetFilenames()
            for selection in selected:
                # All the hard work goes here...
                file = open(selection)
                print file.read()
                guiFunctions.statusText(self, "Playlist: " + selection + " selected...")
        dialog.Destroy()

        # set back to original working directory
        os.chdir(owd)

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