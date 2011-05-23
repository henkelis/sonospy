# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Argument parsing for BRisa deployed applications.
"""

import sys
import random
import socket
from optparse import OptionParser

from brisa.core import log, config, network


def parse_args(device_name):
    """ Parses option arguments and configuration values for the given device
    name.

    @param device_name: device name
    @type device_name: string

    @return: 2-tuple (listen_url, daemon) (daemon tells whether -d was passed)
    @rtype: tuple
    """
    usage = "\nBRisa UPnP %s version %s\nusage: python prog [options] arg" \
    % (device_name, config.manager.brisa_version)
    parser = OptionParser(usage)

    parser.add_option("-q", "--quiet",
                      action="store_false", dest="verbose")
    parser.add_option("-i", "--address", dest="address",
                      help="set the UPnP %s IP address" % device_name)
    parser.add_option("-p", "--port", dest="port",
                      help="set the UPnP %s Port" % device_name)
    parser.add_option("-d", "--daemon", action="store_true",
                      dest="daemon", help="Run %s as daemon" % device_name)

    (options, args) = parser.parse_args()

    if len(args) != 0:
        parser.error("incorrect number of arguments")

    listen_addr = options.address

    if not options.port:
        listen_port = random.randint(10000, 65000)
    else:
        listen_port = int(options.port)

    if listen_addr and listen_port:
        listen_url = "http://%s:%d" % (listen_addr, listen_port)
    else:
        listen_url = ''

    daemon = False
    if options.daemon:
        daemon = True

    return (listen_url, daemon)
