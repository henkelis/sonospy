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
# TODO:
# - Look at installers for entire sonospy project (not just GUI)
# - Minimize to tray?
# - Add Scheduler Tab (check for time and run scans/extracts)
###############################################################################
import wx
from wxPython.wx import *
import os
import sys
import subprocess
from wx.lib.pubsub import Publisher
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
# import nowPlayingTab

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


        # Now Playing is SUPER EXPERIMENTAL, WILL PROBABLY BREAK!
#        self.AddPage(nowPlayingTab.NowPlayingPanel(self), "Now Playing")

## Task bar
#class BibTaskBarIcon(wx.TaskBarIcon):
#    def __init__(self, frame):
#        wx.TaskBarIcon.__init__(self)
#        self.frame = frame
#        icon = wx.Icon('sonospy.png', wx.BITMAP_TYPE_PNG)
#        self.SetIcon(icon, "title")
#
#    def CreatePopupMenu(self):
#        self.menu = wx.Menu()
#        self.menu.Append(wx.NewId(), "Launch Sonospy")
#        self.menu.Append(wx.NewId(), "dummy menu 2")
#        return self.menu
## Task bar ends

########################################################################
class SonospyFrame(wx.Frame):
    """
    Frame that holds all other widgets
    """

    #----------------------------------------------------------------------
    def __init__(self):
        """Constructor"""
        wx.Frame.__init__(self, None, wx.ID_ANY, "Sonospy", size=(630,645))
        panel = wx.Panel(self)


        notebook = SonospyNotebook(panel)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(notebook, 1, wx.ALL|wx.EXPAND, 5)
        panel.SetSizer(sizer)
        ib = wx.IconBundle()
        ib.AddIconFromFile("sonospy.png", wx.BITMAP_TYPE_PNG)
        self.SetIcons(ib)
        self.CreateStatusBar(style=0)
        self.SetStatusText("Welcome to Sonospy...")
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        Publisher().subscribe(self.change_statusbar, 'change_statusbar')

#        # Task bar stuff here...
#        self.tbicon = BibTaskBarIcon(self)
#        wx.EVT_TASKBAR_LEFT_UP(self.tbicon, self.OnTaskBarLeftClick)
#        wx.EVT_TASKBAR_RIGHT_UP(self.tbicon, self.OnClose)
        self.Layout()
        self.Show()
        self.Centre()

#    def OnTaskBarLeftClick(self, evt):
#        self.tbicon.PopupMenu(self.tbicon.CreatePopupMenu())

    # Task bar stuff ends here...

    def change_statusbar(self, msg):
        self.SetStatusText(msg.data)

    def OnClose(self, event):
    # tell the window to kill itself and kill the running sonospy process
        owd = os.getcwd()
        os.chdir(os.pardir)
        os.chdir(os.pardir)
        
        if os.name == 'nt':
            cmdroot = 'python '
        else:
            cmdroot = './'
        
        launchCMD = cmdroot + "sonospy_stop"

        # check if service is running...
        if os.path.exists('pycpoint.pid') == True:
            proc = subprocess.Popen([launchCMD],shell=True)
        os.chdir(owd)
        event.Skip()
        self.Destroy()

#----------------------------------------------------------------------
if __name__ == "__main__":
    app = wx.PySimpleApp()
    frame = SonospyFrame()
    app.MainLoop()
