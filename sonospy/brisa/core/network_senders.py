# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Facilities for sending UDP datagrams and TCP messages.
"""

import socket
import threading

from brisa.core import log
from brisa.core.threaded_call import run_async_function


class UDPTransport(object):
    """ Provides methods for sending UDP datagrams.
    """

    def __init__(self, TTL=2):
        """ Constructor for the UDPTransport.

        @param TTL: time to live. Default is 2
        @type TTL: integer
        """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                    socket.IPPROTO_UDP)
        self.set_TTL(TTL)

    def set_TTL(self, TTL):
        """ Setter for the time to live parameter.

        @param TTL: time to live
        @type TTL: integer
        """
        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, TTL)

    def send_data(self, data, host, port):
        """ Sends an UDP datagram to the address specified. 

        @param data: raw data
        @param host: target host
        @param port: target port

        @type data: string
        @type host: string
        @type port: integer
        """
        try:
            self.socket.sendto(data, (host, port))
        except socket.error, e:
            log.debug('UDPTransport: couldn\'t send to %s:%d \
                    - %s' % (host, port, e.message))
            return

    def send_delayed(self, delay, data, host, port):
        """ Sends an UDP datagram to the address specified after the delay.

        @param delay: delay to wait before sending
        @param data: raw data
        @param host: target host
        @param port: target port

        @type delay: float
        @type data: string
        @type host: string
        @type port: integer
        """
        t = threading.Timer(delay, self.send_data, args=[data, host, port])
        t.start()


class TCPTransport(object):
    # TODO fixme to use thread manager fd facility
    """ Provides methods for sending data through TCP. Receiving host must be
    listening for connections.
    """

    def __init__(self):
        """ Constructor for the TCPTransport class.
        """
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def send_data(self, data, (host, port)):
        """ Sends data to the specified address. This is a non-blocking method.

        @param data: raw data
        @param host: target host
        @param port: target port

        @type data: string
        @type host: string
        @type port: integer
        """
        run_async_function(self._send_data, (data, (host, port)))

    def _send_data(self, data, (host, port)):
        """ Sends data to the specified address (implementation). If used
        directly will block the thread until it is complete.
        """
        try:
            self.socket.connect((host, port))
            self.socket.send(data)
            self.socket.close()
        except socket.error, e:
            log.debug('TCPTransport: couldn\'t connect to %s:%d to send data \
                    - %s' % (host, port, e.message))
            return

    def connect_and_feed(self, feeder, (host, port)):
        """ Connects to the specified address and feeds it with data from the
        feeder. Note that feeder is supposed to be a generator.

        @param feeder: data generator for feeding
        @param host: target host
        @param port: target port

        @type feeder: generator
        @type host: string
        @type port: integer
        """
        try:
            self.socket.connect((host, port))
            for feed in feeder.next():
                self.socket.send(feed)
            self.socket.close()
        except socket.error, e:
            log.debug('TCPTransport: error while feeding socket - %s'
                      % e.message)
