#! /usr/bin/python
###############################################################################
# GUI for Mark Henkelis's awesome Sonospy Project.
###############################################################################
# sonospyGUI.py copyright (c) 2010-2011 John Chowanec
# mutagen copyright (c) 2005 Joe Wreschnig, Michael Urman (mutagen is Licensed under GPL version 2.0)
# Sonospy Project copyright (c) 2010-2011 Mark Henkelis
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
# sonospyGUI.py Author: John Chowanec <chowanec@gmail.com>
###############################################################################
import wx
#from wxPython.wx import *
import os
import sys
import subprocess
from wx.lib.pubsub import setuparg1
from wx.lib.pubsub import pub

################################################################################
# This is to house sonospyGUI.py in the root with the rest of the sonospy
# 'executables'.
cmd_folder = os.path.dirname(os.path.abspath(__file__))
cmd_folder = os.path.join(cmd_folder, "sonospy", "gui")
if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)
import scanTab
import extractTab
import launchTab
import virtualsTab
import guiFunctions
# import scheduleTab
# import nowPlayingTab

def OnTaskBarRight(event):
    app.ExitMainLoop()
             
# set our working directory for the rest of the functions to work right.
os.chdir(cmd_folder)
################################################################################
class SonospyNotebook(wx.Notebook):
    """
    The core layout for the app -- notebook pages are slotted here
    """

    #----------------------------------------------------------------------
    def __init__(self, parent):
        wx.Notebook.__init__(self, parent, id=wx.ID_ANY, style=wx.BK_DEFAULT)
        
        self.AddPage(launchTab.LaunchPanel(self), "Launch")
        self.AddPage(scanTab.ScanPanel(self), "Scan")
        self.AddPage(extractTab.ExtractPanel(self), "Extract")
        self.AddPage(virtualsTab.VirtualsPanel(self), "Virtuals")

#        self.AddPage(scheduleTab.SchedulePanel(self), "Batch")

        # Now Playing is SUPER EXPERIMENTAL, WILL PROBABLY BREAK!
#        self.AddPage(nowPlayingTab.NowPlayingPanel(self), "Now Playing")
   
################################################################################
class SonospyFrame(wx.Frame):
    """
    Frame that holds all other widgets
    """

    #----------------------------------------------------------------------
    def __init__(self):
        """Constructor"""
        # [sonospy] defaults
        # posx = 595
        # posy = 200
        # width = 730
        # height = 770
        # maximize = False    
        
        width = guiFunctions.configMe("sonospy", "width", integer=True)
        height = guiFunctions.configMe("sonospy", "height", integer=True)
        posx = guiFunctions.configMe("sonospy", "posx", integer=True)
        posy = guiFunctions.configMe("sonospy", "posy", integer=True)
        maximize = guiFunctions.configMe("sonospy", "maximize", bool=True)

        wx.Frame.__init__(self, None, wx.ID_ANY, "Sonospy", size=(width,height))

        panel = wx.Panel(self)
        notebook = SonospyNotebook(panel)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(notebook, 1, wx.ALL|wx.EXPAND, 5)
        panel.SetSizer(sizer)
        self.CreateStatusBar(style=0)
        self.SetStatusText("Welcome to Sonospy...")
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        pub.subscribe(self.change_statusbar, 'change_statusbar')

        # Setting the icon, but using small icon files.
        os.chdir(cmd_folder)        
        ib = wx.IconBundle()
        ib.AddIconFromFile('icon16.xpm', wx.BITMAP_TYPE_XPM)
        ib.AddIconFromFile('icon32.xpm', wx.BITMAP_TYPE_XPM)
        ib.AddIconFromFile('icon64.xpm', wx.BITMAP_TYPE_XPM)
        
        self.SetIcons(ib)

        self.tbicon = wx.TaskBarIcon() # This assigns the Icon control that will be used when minimixed to tray
        self.Bind(wx.EVT_ICONIZE, self.OnIconify) # This calls the function that minimizes to tray (Iconize = Minimize)
        self.tbicon.Bind(wx.EVT_TASKBAR_LEFT_DCLICK, self.OnTaskBarActivate) # This is what return the application to the screen. TaskBar Left Double Click
        self.tbicon.Bind(wx.EVT_TASKBAR_RIGHT_UP, self.OnPopup) # Create the menu items
        
        # Setting up the menu.
        filemenu= wx.Menu()

        # wx.ID_ABOUT and wx.ID_EXIT are standard IDs provided by wxWidgets.
        filemenu.Append(wx.ID_ABOUT, "&About"," Information about this program.")
        self.Bind(wx.EVT_MENU, self.OnAbout, id=wx.ID_ABOUT)
        filemenu.Append(wx.ID_PREFERENCES, "&Preferences"," Edit preferences.")
        self.Bind(wx.EVT_MENU, self.OnPref, id=wx.ID_PREFERENCES)
        filemenu.AppendSeparator()
        filemenu.Append(wx.ID_EXIT,"E&xit"," Terminate the program.")
        self.Bind(wx.EVT_MENU, self.OnClose, id=wx.ID_EXIT)

        # Creating the menubar.
        menuBar = wx.MenuBar()
        menuBar.Append(filemenu,"&File") # Adding the "filemenu" to the MenuBar
        self.SetMenuBar(menuBar)  # Adding the MenuBar to the Frame content.
        self.Show(True)
        
        # Receives messages from the Launch Tab for when the Launch button is clicked so that we can
        # make sure we create the right click menu items properly.
        pub.subscribe(self.CreateMenu, 'CreateMenu')
        
        self.Layout()
        self.Show()

        # Turning this off now, since we're storing screen position
        # self.Centre()
        self.SetPosition((posx, posy))
        if maximize == True:
            self.Maximize()
        
    def change_statusbar(self, msg):
        self.SetStatusText(msg.data)

    def OnAbout(self, event):
        print "Eventually, I will celebrate Mark here."

    def OnPref(self, event):
        frame = PreferencesFrame()
        frame.Show()

    def OnClose(self, event):
        # tell the window to kill itself and kill the running sonospy process
        os.chdir(cmd_folder)
        
        # Saving the window width, height, screen position and maximized or not.
        section = "sonospy"

        curWidth, curHeight = self.GetSize()
        curPosX, curPosY = self.GetScreenPosition()
        curMaximize = self.IsMaximized()

        guiFunctions.configWrite(section, "width", curWidth)
        guiFunctions.configWrite(section, "height", curHeight)
        guiFunctions.configWrite(section, "posx", curPosX)
        guiFunctions.configWrite(section, "posY", curPosY)
        guiFunctions.configWrite(section, "maximize", curMaximize)

        # Now get back to our launch directory to fire off the stop command.
        os.chdir(os.pardir)
        os.chdir(os.pardir)

        if os.name == 'nt':
            import codecs
            if os.path.isfile('windowsPID.pid') == True:
                with codecs.open('windowsPID.pid', encoding='utf-16') as f:
                    windowsPid = []
                    f.readline()
                    windowsPid = f.readline()
                    windowsPid = windowsPid.splitlines()
                    if windowsPid == []:
                        # The file is corrupt or empty.
                        f.close()
                        os.remove('windowsPID.pid')
                    else:
                        launchCMD = "TASKKILL /F /PID " + windowsPid[0] + " > nul"            
                        f.close()
                        proc = subprocess.Popen(launchCMD,shell=True)
                        os.remove('windowsPID.pid')
        else:
            cmdroot = './'
            launchCMD = cmdroot + "sonospy_stop"
            # check if service is running...
            if os.path.exists('pycpoint.pid') == True:
                proc = subprocess.Popen([launchCMD],shell=True)
        
        os.chdir(cmd_folder)
        
        event.Skip()
        self.tbicon.RemoveIcon()
        event.Skip()
        self.tbicon.Destroy()
        event.Skip()
        self.Destroy()

    def OnTaskBarActivate(self, evt): # Return from the Taskbar
        if self.IsIconized():
            self.Iconize(False) # Hide the icon from the Taskbar
            self.Show() # Show the Main Window
            self.Raise() #Raise the Main Window to the screen
            self.tbicon.RemoveIcon() # Remove the Icon from the Taskbar
                        
    def OnPopup(self, event):
            self.PopupMenu(self.menu)

    def CreateMenu(self, msg):
        # Typically used to be called from another pubsub in other tabs.
        os.chdir(cmd_folder)
        TB_MENU_STOP = wx.NewId()
        TB_MENU_EXIT = wx.NewId()
        TB_MENU_START = wx.NewId()
        self.menu = wx.Menu()
        self.Bind(wx.EVT_MENU, self.OnClose, id=TB_MENU_EXIT)
        self.Bind(wx.EVT_MENU, self.OnStop, id=TB_MENU_STOP)
        self.Bind(wx.EVT_MENU, self.OnStop, id=TB_MENU_START)
        
        if msg.data != "":
            msg = msg.data

        # Now get back to our launch directior to fire off the stop command.
        os.chdir(os.pardir)
        os.chdir(os.pardir)
        
        if os.path.isfile("windowsPID.pid"):
            self.menu.Append(TB_MENU_STOP, "Stop Sonospy")
            self.menu.AppendSeparator()
            self.menu.Append(TB_MENU_EXIT, 'E&xit')
        else:
            self.menu.Append(TB_MENU_START, "Launch Sonospy")
            self.menu.Append(TB_MENU_EXIT, 'E&xit')

        os.chdir(cmd_folder)

        
    def OnStop(self, event):
        pub.sendMessage(('startStopSonospy'), "startStopSonospy")
        
    def OnIconify(self, evt):  
        if evt.Iconized():
            self.Iconize(True) # Show the Icon on the Taskbar
            self.Hide() # Hide the Main Window from the screen
            ib = wx.Icon('icon16.xpm', wx.BITMAP_TYPE_XPM)
            self.tbicon.SetIcon(ib) # Set the Icon on the Taskbar 
            pub.sendMessage(('CreateMenu'), "Exit Sonospy") # As a backup if we never launch the service, give us a way out via Exit.
        
################################################################################
class PreferencesFrame(wx.Frame):
    """"""

    #----------------------------------------------------------------------
    def __init__(self):
        """Constructor"""
        global sizer2
                        
        wx.Frame.__init__(self, None, title="Sonospy Options", size=(520, 550))
        
        panel = wx.Panel(self)
        panel = self

        # SET THE SIZER OBJECT UP
        sizer2 = wx.GridBagSizer(13, 9)

        # SET BASELINE INDEX VARIABLES
        xIndex = 0
        yIndex = 0
        
    # DEFAULT DATABSE EXTENSIONS
        self.tc_DBExt = wx.TextCtrl(panel, -1, "", (0,0), (150,21))
        self.label_DBExt = wx.StaticText(panel, label="Default Database Extensions:")
        help_tc_DBExt= "Enter this as: *.<extension>"
        self.tc_DBExt.SetToolTip(wx.ToolTip(help_tc_DBExt))        
        self.tc_DBExt.Value = guiFunctions.configMe("general", "database_extensions")

        sizer2.Add(self.label_DBExt, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
        sizer2.Add(self.tc_DBExt, pos=(xIndex, 1), span=(1,5), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10).SetMinSize((200,22))
        
        xIndex += 1

    # DEFAULT DATABASE PATH
        self.tc_DBPath = wx.TextCtrl(panel, -1, "", (0,0), (60,21))
        self.label_DBPath = wx.StaticText(panel, label="Default Database Path:")
        help_DBPath= "Enter this as: *.<extension>"
        self.tc_DBPath.SetToolTip(wx.ToolTip(help_DBPath))
        self.bt_DBPath = wx.Button(self, label="Browse")
        self.bt_DBPath.Bind(wx.EVT_BUTTON, self.browseDB, self.bt_DBPath)
        self.tc_DBPath.Value = guiFunctions.configMe("general", "default_database_path")           
        
        sizer2.Add(self.label_DBPath, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
        sizer2.Add(self.tc_DBPath, pos=(xIndex, 1), span=(1,5), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10).SetMinSize((200,22))
        sizer2.Add(self.bt_DBPath, pos=(xIndex, 6), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP|wx.RIGHT, border=10)
        
        xIndex += 1

    # DEFAULT MUSIC PATH
        self.tc_MusicPath = wx.TextCtrl(panel, -1, "", (0,0), (60,21))
        self.label_MusicPath = wx.StaticText(panel, label="Default Music Path:")
        help_MusicPath= "Enter location where music is stored."
        self.tc_MusicPath.SetToolTip(wx.ToolTip(help_MusicPath))
        self.bt_MusicPath = wx.Button(self, label="Browse")
        self.bt_MusicPath.Bind(wx.EVT_BUTTON, self.browseMusicPath, self.bt_MusicPath)
        self.tc_MusicPath.Value = guiFunctions.configMe("general", "default_music_path")
        
        sizer2.Add(self.label_MusicPath, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
        sizer2.Add(self.tc_MusicPath, pos=(xIndex, 1), span=(1,5), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10).SetMinSize((200,22))
        sizer2.Add(self.bt_MusicPath, pos=(xIndex, 6), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP|wx.RIGHT, border=10)
        
        xIndex += 1

    # DEFAULT VIRTUAL PLAYLISTS PATH
        self.tc_VirtPath = wx.TextCtrl(panel, -1, "", (0,0), (60,21))
        self.label_VirtPath = wx.StaticText(panel, label="Default Virtuals Path:")
        help_VirtPath= "Enter location where virtual playlists are stored."
        self.tc_VirtPath.SetToolTip(wx.ToolTip(help_VirtPath))
        self.bt_VirtPath = wx.Button(self, label="Browse")
        self.bt_VirtPath.Bind(wx.EVT_BUTTON, self.browseVirtPath, self.bt_VirtPath)
        self.tc_VirtPath.Value = guiFunctions.configMe("general", "default_sp_path")
        
        sizer2.Add(self.label_VirtPath, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
        sizer2.Add(self.tc_VirtPath, pos=(xIndex, 1), span=(1,5), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10).SetMinSize((200,22))
        sizer2.Add(self.bt_VirtPath, pos=(xIndex, 6), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP|wx.RIGHT, border=10)
        
        xIndex += 1

    # WHICH INI FILES TO IGNORE FOR USERINDEX.INI COMBO ON LAUNCHPANEL
        self.tc_ignoreINI = wx.TextCtrl(panel, -1, "", (0,0), (150,21))
        self.label_ignoreINI = wx.StaticText(panel, label="INI files to ignore:")
        help_tc_ignoreINI= "INI files to ignore for userindex entries."
        self.tc_ignoreINI.SetToolTip(wx.ToolTip(help_tc_DBExt))  
        self.tc_ignoreINI.Value = guiFunctions.configMe("general", "ignoreini")

        sizer2.Add(self.label_ignoreINI, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
        sizer2.Add(self.tc_ignoreINI, pos=(xIndex, 1), span=(1,5), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10).SetMinSize((200,22))
        
        xIndex += 1

    # SUPPRESS WARNINGS CHECKBOX
        self.label_SuppressWarnings = wx.StaticText(panel, label="Suppress Warnings?:")
        self.ck_SuppressWarnings = wx.CheckBox(self, -1, "")
        self.ck_SuppressWarnings.SetToolTip(wx.ToolTip("Set to TRUE if you want to ignore the SMAPI warning."))    
        self.ck_SuppressWarnings.Value = guiFunctions.configMe("general", "supresswarnings", bool=True)

        sizer2.Add(self.label_SuppressWarnings, pos=(xIndex, 0), flag=wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
        sizer2.Add(self.ck_SuppressWarnings, pos=(xIndex,1), flag=wx.EXPAND|wx.LEFT|wx.ALIGN_CENTER_VERTICAL|wx.TOP, border=10)
        self.ck_SuppressWarnings.Bind(wx.EVT_CHECKBOX, self.suppressWarningsClicked, self.ck_SuppressWarnings)
        
        xIndex += 1
        
        self.bt_SaveDefaults = wx.Button(panel, label="Save Defaults")
        help_SaveDefaults = "Save current settings as default."
        self.bt_SaveDefaults.SetToolTip(wx.ToolTip(help_SaveDefaults))
        self.bt_SaveDefaults.Bind(wx.EVT_BUTTON, self.bt_SaveDefaultsClick, self.bt_SaveDefaults)
        
        sizer2.Add(self.bt_SaveDefaults, pos=(xIndex,0), flag=wx.ALL|wx.ALIGN_CENTER_VERTICAL, border=10)
        
        panel.SetSizer(sizer2)
        sizer2.Fit(panel)
        
        panel.Refresh()
        panel.Update()
        panel.Layout()
        
    def browseDB(self, event):
        # Set directory to where launchTab.py lives for reference.
        cmd_folder = os.path.dirname(os.path.abspath(__file__))
        
        dialog = wx.DirDialog(self, "Choose where your Sonospy Database files are stored...", defaultPath=cmd_folder, style=wx.DD_DEFAULT_STYLE)

        if dialog.ShowModal() == wx.ID_OK:
            print dialog.GetPath()
            path = str(dialog.GetPath())
            self.tc_DBPath.Value = path

        dialog.Destroy()
        self.Update()

        # set back to original working directory
        os.chdir(cmd_folder)
    
    def browseMusicPath(self, event):
        # Set directory to where launchTab.py lives for reference.
        cmd_folder = os.path.dirname(os.path.abspath(__file__))
        
        dialog = wx.DirDialog(self, "Choose where your Music files for scanning are stored...", defaultPath=cmd_folder, style=wx.DD_DEFAULT_STYLE)

        if dialog.ShowModal() == wx.ID_OK:
            print dialog.GetPath()
            path = str(dialog.GetPath())
            self.tc_MusicPath.Value = path

        dialog.Destroy()
        self.Update()

        # set back to original working directory
        os.chdir(cmd_folder)
    
    def browseVirtPath(self, event):
        # Set directory to where launchTab.py lives for reference.
        cmd_folder = os.path.dirname(os.path.abspath(__file__))
        
        dialog = wx.DirDialog(self, "Choose where your Virtual Playlists are stored...", defaultPath=cmd_folder, style=wx.DD_DEFAULT_STYLE)

        if dialog.ShowModal() == wx.ID_OK:
            print dialog.GetPath()
            path = str(dialog.GetPath())
            self.tc_VirtPath.Value = path

        dialog.Destroy()
        self.Update()

        # set back to original working directory
        os.chdir(cmd_folder)
    
    def suppressWarningsClicked(self, event):
        pass
        
    def bt_SaveDefaultsClick(self, event):
        section = "general"

        guiFunctions.configWrite(section, "database_extensions", self.tc_DBExt.Value)
        guiFunctions.configWrite(section, "default_music_path", self.tc_MusicPath.Value)
        guiFunctions.configWrite(section, "default_database_path", self.tc_DBPath.Value)
        guiFunctions.configWrite(section, "default_sp_path", self.tc_VirtPath.Value)
        guiFunctions.configWrite(section, "ignoreini", self.tc_ignoreINI.Value)
        guiFunctions.configWrite(section, "supresswarnings", self.ck_SuppressWarnings.Value)
        
if __name__ == "__main__":
    app = wx.App()
    frame = SonospyFrame()
    app.MainLoop()
