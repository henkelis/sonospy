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

