# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Provides a simple API and observer model for listening over UDP.
"""

import os
import socket
from struct import pack

from brisa import __enable_offline_mode__
from brisa.core import log, reactor
from brisa.core.network import get_active_ifaces, get_ip_address
from brisa.core.ireactor import EVENT_TYPE_READ
from brisa.core.threaded_call import run_async_function


if not __enable_offline_mode__:
    if not get_active_ifaces():
        raise RuntimeError('Network is down.')


class CannotListenError(Exception):
    """ Exception denoting an error when binding interfaces for listening.
    """

    def __init__(self, interface, port, addr='', reason=''):
        """ Constructor for the CannotListenError class

        @param interface: interface where the error occured
        @param port: port at the error ocurred when binding
        @param addr: address at the error ocurred when binding
        @param reason: reason why the error happened

        @type interface: string
        @type port: integer
        @type addr: string
        @type reason: string
        """
        if addr:
            self.message = "Couldn't listen on %s:%s: %d. " % (interface,
                                                             addr, port)
        else:
            self.message = "Couldn't listen on %s: %d. " % (interface,
                                                               port)
        if reason:
            self.message += reason


class SubscriptionError(Exception):
    """ Exception denoting an observer subscription error. Gets raised when the
    observer does not implement the INetworkObserver interface.
    """
    message = "Couldn't subscribe listener because it does not implement \
    _datagram_received. Implement brisa.core.network_listeners.INetworkObserver."
#    data_received. Implement brisa.core.network_listeners.INetworkObserver."


class INetworkObserver(object):
    """ Interface for network observers. Prototypes the _datagram_received method.
    """

#    def data_received(self, data, addr=None):
    def _datagram_received(self, data, addr=None):
        """ Receives data when subscribed to some network listener.

        @param data: raw data
        @param addr: can receive a 2-tuple (host, port)

        @type data: string
        @type addr: None or tuple
        """
        raise Exception("Classes implementing INetworkObserver must implement \
                        _datagram_received() method")
#                        data_received() method")


class NetworkListener(object):
    """ Network listener abstract class. Forwards data to multiple subscribed
    observers and can have a single callback to get data forwarded to.

    Methods that MUST be implemented by an inheriting class:
        - run()   : main loop that receives data. In order to forward data to
    observers and the data callback run() method MUST call
    self.forward_data(data, addr). Note that addr is optional.
        - close() : closes the connection
    """

    def __init__(self, observers=None, data_callback=None):
        """ Constructor for the NetworkListener class

        @param observers: initial subscribers for data forwarding
        @param data_callback: callback that gets data forwarded to

        @type observers: list
        @type data_callback: callable
        """
        
        self.listening = False
        self.data_callback = data_callback
        if observers == None:
            self.observers = []
        else:
            self.observers = observers

#        print "!!!!!!!!!!!!!!!!!! " + str(observers)
#        print "!!!!!!!!!!!!!!!!!! " + str(self.__dict__)
#        print "!!!!!!!!!!!!!!!!!! " + str(id(observers))
#        print "!!!!!!!!!!!!!!!!!! " + str(id(self.observers))

    def forward_data(self, data, addr=''):
        """ Forwards data to the subscribed observers and to the data callback.

        @param data: raw data to be forwarded
        @param addr: can be a 2-tuple (host, port)

        @type data: string
        @type addr: None or tuple
        """
#        print "@@@@@@@@ FORWARD DATA: " + str(self.data_callback) + " obs: " + str(self.observers)
#@@@@@@@@ FORWARD DATA: <bound method MSearch._datagram_received of <brisa.upnp.control_point.msearch.MSearch object at 0x250bf10>> obs: [<brisa.upnp.ssdp.SSDPServer object at 0x7f57b005d2d0>]
#@@@@@@@@ FORWARD DATA: <bound method SSDPServer._datagram_received of <brisa.upnp.ssdp.SSDPServer object at 0x250bdd0>> obs: [<brisa.upnp.ssdp.SSDPServer object at 0x7f57b005d2d0>]
#        print "######## NetworkListener forward data: " + str(data)
#        print "######## NetworkListener forward addr: " + str(addr)
#        print self.data_callback.__name__
#        c = str(self.data_callback.im_class)
#        if 'SSDP' in c:
#            print "SSDP"

#        print self.observers

        for listener in self.observers:
            if addr:
#                run_async_function(listener.data_received, (data, addr))
                run_async_function(listener._datagram_received, (data, addr))
            else:
#                run_async_function(listener.data_received, (data, ()))
                run_async_function(listener._datagram_received, (data, ()))

        if self.data_callback:
            if addr:
                run_async_function(self.data_callback, (data, addr))
            else:
                run_async_function(self.data_callback, (data, ()))

    def subscribe(self, observer):
        """ Subscribes an observer for data forwarding.

        @param observer: observer instance
        @type observer: INetworkObserver
        """
        if hasattr(observer, '_datagram_received') and observer not in self.observers:
            self.observers.append(observer)
        else:
            raise SubscriptionError()

    def is_listening(self):
        """ Returns whether this network listener is listening (already started
        with start()).
        """
        return self.listening

    def is_running(self):
        """ Same as is_listening().
        """
        return self.is_listening()

    def start(self):
        self.listening = True

    def stop(self):
        self.listening = False

    def _cleanup(self):
        """ Removes references to other classes, in order to make GC easier
        """
        self.data_callback = None
        self.observers = None

    def destroy(self):
        pass


class UDPListener(NetworkListener):
    """ Listens UDP in a given address and port (and in the given interface, if
    provided).
    """
    BUFFER_SIZE = 1500

#    def __init__(self, addr, port, interface='', observers=[],
    def __init__(self, addr, port, interface='', observers=None,
                 data_callback=None, shared_socket=None):
        """ Constructor for the UDPListener class.

        @param addr: address to listen on
        @param port: port to listen on
        @param interface: interface to listen on
        @param observers: list of initial subscribers
        @param data_callback: callback to get data forwarded to
        @param shared_socket: socket to be reused by this network listener

        @type addr: string
        @type port: integer
        @type interface: string
        @type observers: list of INetworkObserver
        @type data_callback: callable
        @type shared_socket: socket.socket
        """
        NetworkListener.__init__(self, observers, data_callback)
        self.addr = addr
        self.port = port
        self.interface = interface

        # win32 does not like interface='' (MSEARCH replies are not propagated) - TODO: check this is correct
        if os.name == 'nt':
            ifaces = get_active_ifaces()
            if ifaces:
                self.interface = get_ip_address(ifaces[0])
        
        self.socket = None
        self.fd_id = None
        self._create_socket(shared_socket)

    def start(self):
        self.fd_id = reactor.add_fd(self.socket, self._receive_datagram,
                                    EVENT_TYPE_READ)
        NetworkListener.start(self)

    def stop(self):
        NetworkListener.stop(self)
        reactor.rem_fd(self.fd_id)

    def destroy(self):
        """ Closes the socket, renders the object unusable.
        """
        self.socket.close()
        self._cleanup()

    def _create_socket(self, shared):
        """ Creates the socket if a shared socket has not been passed to the
        constructor.

        @param shared: socket to be reused
        @type shared: socket.socket
        """
        if shared:
            self.socket = shared
        else:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                         socket.IPPROTO_UDP)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.socket.bind((self.interface, self.port))
            self.mreq = pack('4sl', socket.inet_aton(self.addr),
                             socket.INADDR_ANY)
            self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                                    self.mreq)
        except Exception, e:
            log.critical('Cannot create socket: %s' % str(e))
            raise CannotListenError(self.interface, self.port, self.addr,
                                    "Couldn't bind address")

    def _receive_datagram(self, sock, cond):
        """ Implements the UDPListener listening actions.
        """
#        print "@@@@@@@@ UDP datagram: " + str(sock)
        
        if not self.is_listening():
            return

        try:
            (data, addr) = self.socket.recvfrom(self.BUFFER_SIZE)

#            if 'Coherence' in data:
   #         print "@@@@@@@@ addr: " + str(addr)
   #         print "@@@@@@@@ data before: " + str(data)
            
            # HACK: WMP sometimes returns 0.0.0.0 as the IP in its location field - fix it here            
            if 'http://0.0.0.0:2869' in data:
#                print "@@@@@@@@ addr: " + str(addr)
#                print "@@@@@@@@ data before: " + str(data)
                ip, port = addr
                newaddr = 'http://' + ip + ':2869'
                data = data.replace('http://0.0.0.0:2869', newaddr)
#                print "@@@@@@@@ data after: " + str(data)

            self.forward_data(data, addr)

        except Exception, e:
            log.debug('Error when reading on UDP socket: %s', e)

        return True
