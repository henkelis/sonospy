# pycpoint
#
# Copyright (c) 2009 Mark Henkelis
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
# Author: Mark Henkelis <mark.henkelis@tesco.net>


import re
import types, string
import os



def chop(str, size = 100):
    if len(str) <= size:
        return str
    else:
        s = ""
        for m in re.finditer('.' * size, str):
            s += m.group() + "\n" + " "*45
            last = m.end()
        s += str[last:]
        return s

def csplit(str, chrs = '{},\[\]'):
    # TODO: need to ignore commas when they are within a string or XML
    s = "\n" + " "*45 + "--->"
    cset = '[' + chrs + ']'
    if re.search(cset, str) == None:
        return ""
    else:
        for m in re.split(cset, str):
            if m.lstrip() != "":
                s +=  "\n" + " "*45 + m.lstrip()
        return s


