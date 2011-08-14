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
# - Kill sonsopy process on window close.
# - Look at installers for entire sonospy project (not just GUI)
# - Minimize to tray?
# - Dynamically scale the window to fit the visible tab.
# - Move sonospyGUI.py to the root of the Sonospy app
###############################################################################
import wx
from wxPython.wx import *
################################################################################
import scanTab
import extractTab
import launchTab
import virtualsTab
# import nowPlayingTab

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

########################################################################
class SonospyFrame(wx.Frame):
    """
    Frame that holds all other widgets
    """

    #----------------------------------------------------------------------
    def __init__(self):
        """Constructor"""
        wx.Frame.__init__(self, None, wx.ID_ANY, "Sonospy", size=(580,645))
        panel = wx.Panel(self)

        notebook = SonospyNotebook(panel)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(notebook, 1, wx.ALL|wx.EXPAND, 5)
        panel.SetSizer(sizer)
        ib = wx.IconBundle()
        ib.AddIconFromFile("sonospy.png", wx.BITMAP_TYPE_ANY)
        self.SetIcons(ib)
        self.CreateStatusBar(style=0)
        self.SetStatusText("Welcome to Sonospy...")
        
        self.Layout()

        self.Show()
        self.Centre()

    def OnCloseWindow(self, event):
    # tell the window to kill itself and kill the running sonospy process
        owd = os.getcwd()
        os.chdir(os.pardir)

        if os.name == 'nt':
            cmdroot = 'python '
        else:
            cmdroot = './'
        
        launchCMD = cmdroot + "sonospy_stop"
        
        proc = subprocess.Popen([launchCMD],shell=True)
        os.chdir(owd)

        self.Destroy()

#----------------------------------------------------------------------
if __name__ == "__main__":
    app = wx.PySimpleApp()
    frame = SonospyFrame()
    app.MainLoop()
