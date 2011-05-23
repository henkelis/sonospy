# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Bult-in reactors.
"""

#from brisa.core.reactors.gtk2 import *
#from brisa.core.reactors.glib2 import *
#from brisa.core.reactors._ecore import *
from brisa.core.reactors._select import *

def install_default_reactor():
    return SelectReactor()
