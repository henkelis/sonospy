###############################################################################
# guiFunctions - shared functions across the Sonospy GUI project.
###############################################################################
# guiFunctions.py copyright (c) 2010-2011 John Chowanec
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
# guiFunctions.py Author: John Chowanec <chowanec@gmail.com>
###############################################################################
# TODO:
# - Globalize ONE file selection dialog
# - Globalize ONE folder selection dialog.
###############################################################################
from wxPython.wx import *

#-------------------------------------------------------------------------------
# configMe, configWrite
#
# For reading, parsing and writing the config file.
#-------------------------------------------------------------------------------

import ConfigParser

def configMe(heading, term, integer=False, bool=False, parse=False):
    config = ConfigParser.SafeConfigParser()
    config.read("GUIpref.ini")

    if config.has_option(heading, term) == True:
        if integer == True:
            fetchMe = config.getint(heading, term)
        elif bool == True:
            fetchMe = config.getboolean(heading, term)
        else:
            fetchMe = config.get(heading, term)

        if parse == True:
            if fetchMe != "":
                if "," in fetchMe:
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

    return(fetchMe)

#    Uncomment to dump entire config file
#    for section in config.sections():
#        print section
#        for option in config.options(section):
#            print " ", option, "=", config.get(section, option)

def configWrite(heading, term, value):
    config = ConfigParser.ConfigParser()
    config.read("GUIpref.ini")
    config.set(heading, term, value)
    with open('GUIpref.ini', 'wb') as configfile:
        config.write(configfile)

#-------------------------------------------------------------------------------
# scrubDB
#
# Scours the provided path for *.db files to return back to the app so that we
# can dynamically create widgets for the launch tab
#-------------------------------------------------------------------------------
import os

def scrubDB(path, ext=False):
    asps = []
    filters = ext
    
    for root, dirs, files in os.walk(path):
        for file in files:
            basename, extension = os.path.splitext(file)
            extension = "*" + extension
            if extension in filters:
                asps.append(file)
    return asps

#-------------------------------------------------------------------------------
# statusText
#
# Simple function to set the status text in any of the other notebook tabs.
#-------------------------------------------------------------------------------
def statusText(object, line):
    object.GetParent().GetParent().GetParent().SetStatusText(line)


