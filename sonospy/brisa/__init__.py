# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

"""
BRisa UPnP Framework


B{Author:} BRisa Team <U{brisa-develop@garage.maemo.org}>

B{Version:} 0.10.0

B{License:} MIT License <U{http://opensource.org/lincenses/mit-license.php}>

B{See also:}
    - Home page <U{http://brisa.garage.maemo.org}>
    - Project page <U{http://garage.maemo.org/projects/brisa}>
    - Documentation <U{http://brisa.garage.maemo.org/documentation.htm}>
"""

version = '0.10.0'


# General variables
url_fetch_attempts = 2
url_fetch_attempts_interval = 0.1
__skip_service_xml__ = False
__skip_soap_service__ = False
__tolerate_service_parse_failure__ = True
__enable_logging__ = True
__enable_webserver_logging__ = False
__enable_offline_mode__ = False
__enable_events_logging__ = False
