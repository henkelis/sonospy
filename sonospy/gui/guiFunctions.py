###############################################################################
# guiFunctions - shared functions across the Sonospy GUI project.
###############################################################################
# guiFunctions.py copyright (c) 2010-2014 John Chowanec
# mutagen copyright (c) 2005 Joe Wreschnig, Michael Urman (mutagen is Licensed under GPL version 2.0)
# Sonospy Project copyright (c) 2010-2014 Mark Henkelis
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
###############################################################################
import wx
#from wxPython.wx import *
from wx.lib.pubsub import setuparg1
from wx.lib.pubsub import pub

########################################################################################################################
# configMe: Reads GUIpref.ini for settings in the various tab files. 
########################################################################################################################
import ConfigParser

def configMe(heading, term, integer=False, bool=False, parse=False, file=False):
    owd = os.getcwd()
    cmd_folder = os.path.dirname(os.path.abspath(__file__))
    os.chdir(cmd_folder)    
    config = ConfigParser.ConfigParser()
    
    if file == False:
        config.read("GUIpref.ini")
    else:
        config.read(file)

    if config.has_option(heading, term) == True:
        if integer == True:
            fetchMe = config.getint(heading, term)
        elif bool == True:
            fetchMe = config.getboolean(heading, term)
        else:
            fetchMe = config.get(heading, term)

        if parse == True:
            if fetchMe != "":
                if "|" in fetchMe:
                    fetchMe = fetchMe.replace("| ", "|")
                    fetchMe = fetchMe.replace("|", "\n")
                else:
                    fetchMe = fetchMe
    else:
        if integer == True:
            return 1
        elif bool == True:
            return 1
        else:
            return ""
    os.chdir(owd)
    return(fetchMe)

    # DEBUG: Uncomment to dump entire config file ----------------------------------
    # for section in config.sections():
    #    print section
    #    for option in config.options(section):
    #        print " ", option, "=", config.get(section, option)
    # ------------------------------------------------------------------------------
    
########################################################################################################################
# configWrite: Writes GUIpref.ini for settings in the various tab files. 
########################################################################################################################
def configWrite(heading, term, value):
    owd = os.getcwd()
    cmd_folder = os.path.dirname(os.path.abspath(__file__))
    os.chdir(cmd_folder)
    config = ConfigParser.ConfigParser()
    config.read("GUIpref.ini")
    config.set(heading, term, value)
    with open('GUIpref.ini', 'wb') as configfile:
        config.write(configfile)
    os.chdir(owd)

########################################################################################################################
# scrubDB: Scours the provided path for *.db files to return back to the app so that we can dynamically create
#          create widgets for the launch tab.
########################################################################################################################
import os

def scrubDB(path, ext=False):
    asps = []
    filters = ext

    for file in os.listdir(path):
        basename, extension = os.path.splitext(file)
        extension = "*" + extension
        if extension in filters:
            asps.append(file)
    return asps

########################################################################################################################
# scrubINI: Scours the provided path for *.ini files to return back to the app so that we can dynamically create
#           create create dropdowns for the user index on the launch tab.
########################################################################################################################
import os

def scrubINI(path, ext=False):
    inifiles = [""]

    # Step up to GUI folder to find GUIpref.ini
    # Then return to the previous folder to get
    # the iniFile list to compare to.

    ignoreMe = configMe("general", "ignoreini")
    ignoreMe = ignoreMe.replace(".ini", "")
    
    filters = ext

    for file in os.listdir(path):
        basename, extension = os.path.splitext(file)

        if len(extension) > 0:
            extension = "*" + extension
            if extension in filters and basename not in ignoreMe:
                     inifiles.append(file)
    return inifiles

########################################################################################################################
# scrubINI: Simple function to set the status text in any of the other notebook tabs.
########################################################################################################################
def statusText(object, line):
    pub.sendMessage(('change_statusbar'), line)

########################################################################################################################
# errorMsg: Simple error popup.
########################################################################################################################
def errorMsg(type, msg):
    wx.MessageBox(msg, type, wx.OK | wx.ICON_INFORMATION)

########################################################################################################################
# dirBrowse: Default directory browser function.
########################################################################################################################
def dirBrowse(control, dialogMsg, defaultPathToLook):
    # Set directory to where launchTab.py lives for reference.
    cmd_folder = os.path.dirname(os.path.abspath(__file__))

    if control.Value != "":
        defaultPathToLook = control.Value
    elif defaultPathToLook == "":
        defaultPathToLook = cmd_folder

    dialog = wx.DirDialog(None,dialogMsg, defaultPath=defaultPathToLook, style=wx.DD_DEFAULT_STYLE)

    if dialog.ShowModal() == wx.ID_OK:
        path = str(dialog.GetPath())
        control.Value = path

    dialog.Destroy()

    # set back to original working directory
    os.chdir(cmd_folder)

########################################################################################################################
# dirBrowseMulti: Use this when we need to repeatedly append to a text control (like on scan tab's music folders)
########################################################################################################################
def dirBrowseMulti(control, dialogMsg, defaultPathToLook):
    cmd_folder = os.path.dirname(os.path.abspath(__file__))    

    dialog = wx.DirDialog(None, "Add a Directory...", defaultPath=defaultPathToLook, style=wx.DD_DEFAULT_STYLE)

    if dialog.ShowModal() == wx.ID_OK:
        if control.Value == "":
            control.AppendText("%s" % dialog.GetPath())
        else:
            control.AppendText("\n%s" % dialog.GetPath())
    
        dialog.Destroy()
        os.chdir(cmd_folder)        
        return dialog.GetPath()

    dialog.Destroy()
    os.chdir(cmd_folder)

########################################################################################################################
# fileBrowse: Default file browser function.
########################################################################################################################
def fileBrowse(dialogMsg, defaultPathToLook, defaultWildcards=False, multiple=False):
    # Set directory to where launchTab.py lives for reference.
    cmd_folder = os.path.dirname(os.path.abspath(__file__))

    if defaultPathToLook == "":
        os.chdir(cmd_folder)
        os.chdir(os.pardir)
        defaultPathToLook = os.getcwd()
    
    if multiple == True:
        flagsForStyle = wx.FD_OPEN|wx.FD_MULTIPLE
    else:
        flagsForStyle = wx.FD_OPEN
        
    dialog = wx.FileDialog (None, message = dialogMsg, defaultDir=defaultPathToLook, wildcard = defaultWildcards, style = flagsForStyle)
    
    # Open Dialog Box and get Selection
    if dialog.ShowModal() == wx.ID_OK:
        selected = dialog.GetFilenames()
        os.chdir(cmd_folder)
        dialog.Destroy()
        return selected
            
    dialog.Destroy()

    # set back to original working directory

########################################################################################################################
# saveLog: Use this when we need to repeatedly append to a text control (like on scan tab's music folders)
########################################################################################################################
def saveLog(control, defaultFileName):
    cmd_folder = os.path.dirname(os.path.abspath(__file__))
    
    dialog = wx.FileDialog(None, message='Enter a file name or choose a file to save...', \
                           defaultDir = configMe("general", "default_log_path"), \
                           defaultFile = defaultFileName, wildcard = "Sonospy Logs (*.log)|*.log|All files (*.*)|*.*",\
                           style=wx.SAVE|wx.OVERWRITE_PROMPT)
    
    if dialog.ShowModal() == wx.ID_OK:
        savefile=dialog.GetFilename()
        dirname=dialog.GetDirectory()
        filehandle=open(os.path.join(dirname, savefile),'w')
        filehandle.write(control.Value)
        filehandle.close()
        dialog.Destroy()
               
        return savefile
    
    dialog.Destroy()
    os.chdir(cmd_folder)

########################################################################################################################
# savePlaylist: Use this when we are going to write out .SP files
########################################################################################################################
def savePlaylist(dataToSave):
    cmd_folder = os.path.dirname(os.path.abspath(__file__))
    dialog = wx.FileDialog(None, message='Choose a file', defaultDir=configMe("general", "default_sp_path"), \
                           wildcard="Playlist Files (*.sp)|*.sp", style=wx.SAVE|wx.OVERWRITE_PROMPT)

    if dialog.ShowModal() == wx.ID_OK:
        savefile = dialog.GetFilename()
        basename, extension = os.path.splitext(savefile)
        if extension == "":
            extension = ".sp"
        savefile = basename + extension
        savedir = dialog.GetDirectory()
        saveMe=open(os.path.join(savedir, savefile),'w')
        saveMe.write(dataToSave)
        saveMe.close()
        os.chdir(cmd_folder) 
        dialog.Destroy()
        return savefile
