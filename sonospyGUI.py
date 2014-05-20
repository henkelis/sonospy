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
        Publisher().subscribe(self.change_statusbar, 'change_statusbar')

        # Setting the icon, but using small icon files.
        ib = wx.IconBundle()
        ib.AddIconFromFile('icon16.xpm', wx.BITMAP_TYPE_XPM)
        ib.AddIconFromFile('icon32.xpm', wx.BITMAP_TYPE_XPM)
        ib.AddIconFromFile('icon64.xpm', wx.BITMAP_TYPE_XPM)
        
        self.SetIcons(ib)
        self.Layout()
        self.Show()

        # Turning this off now, since we're storing screen position
        # self.Centre()
        self.SetPosition((posx, posy))
        if maximize == True:
            self.Maximize()


    def change_statusbar(self, msg):
        self.SetStatusText(msg.data)

    def OnClose(self, event):
    # tell the window to kill itself and kill the running sonospy process
        owd = os.getcwd()
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

    # Now get back to our launch directior to fire off the stop command.
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

#######################################################################
# TRAY ICONS WORK - BUT WILL REQUIRE A TON OF TWEAKING
#######################################################################

#TRAY_TOOLTIP = 'System Tray Demo'
#TRAY_ICON = 'sonospy.png'


#def create_menu_item(menu, label, func):
    #item = wx.MenuItem(menu, -1, label)
    #menu.Bind(wx.EVT_MENU, func, id=item.GetId())
    #menu.AppendItem(item)
    #return item

#class TaskBarIcon(wx.TaskBarIcon):
    #def __init__(self):
        #super(TaskBarIcon, self).__init__()
        #self.set_icon(TRAY_ICON)
        #self.Bind(wx.EVT_TASKBAR_LEFT_DOWN, self.on_left_down)

    #def CreatePopupMenu(self):
        #menu = wx.Menu()
        #create_menu_item(menu, 'Launch Sonospy', self.on_hello)
        #menu.AppendSeparator()
        #create_menu_item(menu, 'Exit', self.on_exit)
        #return menu

    #def set_icon(self, path):
        #icon = wx.IconFromBitmap(wx.Bitmap(path))
        #self.SetIcon(icon, TRAY_TOOLTIP)

    #def on_left_down(self, event):
        #print 'Tray icon was left-clicked.'

    #def on_hello(self, event):
        #print 'Hello, world!'

    #def on_exit(self, event):
        #wx.CallAfter(self.Destroy)
        
if __name__ == "__main__":
    app = wx.PySimpleApp()
    frame = SonospyFrame()
    #TaskBarIcon()
    app.MainLoop()
