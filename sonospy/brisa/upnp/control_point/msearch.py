# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
#
# Copyright (C) 2006 Fluendo, S.A. (www.fluendo.com).
# Copyright 2006, Frank Scholz <coherence@beebits.net>
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Contains the MSearch class which can search for devices.
"""

from brisa.core import log
from brisa.core.network import parse_http_response
from brisa.core.network_senders import UDPTransport
from brisa.core.network_listeners import UDPListener
from brisa.utils.looping_call import LoopingCall
from brisa.upnp.upnp_defaults import UPnPDefaults


DEFAULT_SEARCH_TIME = UPnPDefaults.MSEARCH_DEFAULT_SEARCH_TIME
DEFAULT_SEARCH_TYPE = UPnPDefaults.MSEARCH_DEFAULT_SEARCH_TYPE
#DEFAULT_SEARCH_TYPE = "upnp:rootdevice"


class MSearch(object):
    """ Represents a MSearch. Contains some control functions for starting and
    stopping the search. While running, search will be repeated in regular
    intervals specified at construction or passed to the start() method.
    """

    msg_already_started = 'tried to start() MSearch when already started'
    msg_already_stopped = 'tried to stop() MSearch when already stopped'

    def __init__(self, ssdp, start=True, interval=DEFAULT_SEARCH_TIME,
                 ssdp_addr='239.255.255.250', ssdp_port=1900):
        """ Constructor for the MSearch class.

        @param ssdp: ssdp server instance that will receive new device events
        and subscriptions
        @param start: if True starts the search when constructed
        @param interval: interval between searchs
        @param ssdp_addr: ssdp address for listening (UDP)
        @param ssdp_port: ssdp port for listening (UDP)

        @type ssdp: SSDPServer
        @type start: boolean
        @type interval: float
        @type ssdp_addr: string
        @type ssdp_port integer
        """
        self.ssdp = ssdp
        self.ssdp_addr = ssdp_addr
        self.ssdp_port = ssdp_port
        self.search_type = DEFAULT_SEARCH_TYPE
        self.udp_transport = UDPTransport()
#        self.listen_udp = UDPListener(ssdp_addr, ssdp_port,
        self.listen_udp = UDPListener(ssdp_addr, 2149,      # WMP is not picked up if 1900 is used for source
                                      data_callback=self._datagram_received,
                                      shared_socket=self.udp_transport.socket)
        self.loopcall = LoopingCall(self.double_discover)
        if start:
            self.start(interval)

    def is_running(self):
        """ Returns True if the search is running (it's being repeated in the
        interval given).

        @rtype: boolean
        """
        return self.loopcall.is_running()

    def start(self, interval=DEFAULT_SEARCH_TIME,
              search_type=DEFAULT_SEARCH_TYPE):
        """ Starts the search.

        @param interval: interval between searchs. Default is 600.0 seconds
        @param search_type: type of the search, default is "ssdp:all"

        @type interval: float
        @type search_type: string
        """

#        interval = 30.0
        
        if not self.is_running():
            self.search_type = search_type
            self.listen_udp.start()
            
#            print ">>>>>>>>> interval: " + str(interval)
            
            self.loopcall.start(interval, now=True)
            log.debug('MSearch started')
        else:
            log.warning(self.msg_already_started)

    def stop(self):
        """ Stops the search.
        """
        if self.is_running():
            log.debug('MSearch stopped')
            self.listen_udp.stop()
            self.loopcall.stop()
        else:
            log.warning(self.msg_already_stopped)

    def destroy(self):
        """ Destroys and quits MSearch.
        """
        if self.is_running():
            self.stop()
        self.listen_udp.destroy()
        self.loopcall.destroy()
        self._cleanup()

    def double_discover(self, search_type=DEFAULT_SEARCH_TYPE):
        """ Sends a MSearch imediatelly. Each call to this method will yield a
        MSearch message, that is, it won't repeat automatically.
        """
#        print "<<<<<<<<< start double discover >>>>>>>>>"
        self.discover(search_type)
        self.discover(search_type)
#        print "<<<<<<<<< end double discover >>>>>>>>>"

    def discover(self, type="ssdp:all"):
#    def discover(self, type="upnp:rootdevice"):
        """ Mounts and sends the discover message (MSearch).

        @param type: search type
        @type type: string
        """
        
#        type = "urn:schemas-upnp-org:device:MediaServer:1"
        type = "upnp:rootdevice"
        
#        req = ['M-SEARCH * HTTP/1.1',
#                'HOST: %s:%d' % (self.ssdp_addr, self.ssdp_port),
#                'MAN: "ssdp:discover"',
#                'MX: 5',
#                'ST: ' + type, '', '']
#        req = '\r\n'.join(req)
        req = ['M-SEARCH * HTTP/1.1',
                'HOST:%s:%d' % (self.ssdp_addr, self.ssdp_port),
                'MAN:"ssdp:discover"',
#                'Host:%s:%d' % (self.ssdp_addr, self.ssdp_port),
#                'Man:"ssdp:discover"',
                'MX:5',
                'ST:' + type, '', '', '']
        req = '\r\n'.join(req)
        self.udp_transport.send_data(req, self.ssdp_addr, self.ssdp_port)

    def _datagram_received(self, data, (host, port)):
        """ Callback for the UDPListener when messages arrive.

        @param data: raw data received
        @param host: host where data came from
        @param port: port where data came from

        @type data: string
        @type host: string
        @type port: integer
        """
#        print "datagram_received start"
        cmd, headers = parse_http_response(data)
        if cmd[0] == 'HTTP/1.1' and cmd[1] == '200':
            if self.ssdp != None:
                if not self.ssdp.is_known_device(headers['usn']):
                    log.debug('Received MSearch answer %s,%s from %s:%s',
                              headers['usn'], headers['st'], host, port)
#                    print "_datagram_received _register"
#                    print "_datagram_received headers: " + str(headers)
                    self.ssdp._register(headers['usn'],
                                        headers['st'],
                                        headers['location'],
                                        headers['server'],
                                        headers['cache-control'])
#        print "   datagram_received end"

    def _cleanup(self):
        """ Clean up references.
        """
        self.ssdp = None
        self.listen_udp = None
        self.loopcall = None
