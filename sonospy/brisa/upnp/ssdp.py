# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
#
# Copyright 2005, Tim Potter <tpot@samba.org>
# Copyright 2006 John-Mark Gurney <gurney_j@resnet.uroegon.edu>
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" SSDP Server implementation which listens for devices messages and searches.

When used implementing a device, it's used for announcing the device, its
embedded devices and all services.

When used on a control point, it's used for keeping record of known devices
(obtained through search or announcements).
"""

import random

from brisa.core import log
from brisa.core.network_senders import UDPTransport
from brisa.core.network_listeners import UDPListener

from brisa.utils.looping_call import LoopingCall

from brisa.upnp.upnp_defaults import UPnPDefaults

SSDP_ADDR = UPnPDefaults.SSDP_ADDR
SSDP_PORT = UPnPDefaults.SSDP_PORT

log = log.getLogger('upnp.ssdp')


class SSDPServer(object):
    """ Implementation of a SSDP server.

    The notify_received and search_received methods are called when the
    appropriate type of datagram is received by the server.
    """

    msg_already_started = 'tried to start() SSDPServer when already started'
    msg_already_stopped = 'tried to stop() SSDPServer when already stopped'

    def __init__(self, server_name, xml_description_filename, max_age=1800,
                receive_notify=True, udp_listener=''):
        """ Constructor for the SSDPServer class.

        @param server_name: server name
        @param xml_description_filename: XML description filename
        @param max_age: max age parameter, default 1800.
        @param receive_notify: if False, ignores notify messages

        @type server_name: string
        @type xml_description_filename:
        @type max_age: integer
        @type receive_notify: boolean
        """
        self.server_name = server_name
        self.xml_description_filename = xml_description_filename
        self.max_age = max_age
        log.debug("max_age: %s", max_age)
        self.receive_notify = receive_notify
        self.running = False
        self.known_device = {}
        self.advertised = {}
        self._callbacks = {}
        self.udp_transport = UDPTransport()
        if udp_listener == '':
            self.udp_listener = UDPListener(SSDP_ADDR, SSDP_PORT,
                                            data_callback=self._datagram_received)
        else:
            self.udp_listener = None
            udp_listener.subscribe(self)
        self.renew_loop = LoopingCall(self._renew_notifications)
        self.renew_loop.start(0.8 * self.max_age, now=True)

    def is_running(self):
        """ Returns True if the SSDPServer is running, False otherwise.
        """
        return self.running

    def start(self):
        """ Starts the SSDPServer.
        """
        if not self.is_running():
            if self.udp_listener != None:
                self.udp_listener.start()
            self.running = True
        else:
            log.warning(self.msg_already_started)

    def stop(self):
        """ Sends bye bye notifications and stops the SSDPServer.
        """
        if self.is_running():
            # Avoid racing conditions
            own_temp = self.advertised.copy()
            for usn in own_temp:
                self._do_byebye(usn)

            self.renew_loop.stop()
            if self.udp_listener != None:
                self.udp_listener.stop()
            self.running = False
        else:
            log.warning(self.msg_already_stopped)

    def destroy(self):
        """ Destroys the SSDPServer.
        """
        if self.is_running():
            self.stop()
        self.renew_loop.destroy()
        if self.udp_listener != None:
            self.udp_listener.destroy()
        self._cleanup()

    def clear_device_list(self):
        """ Clears the device list.
        """
        self.known_device.clear()

    def discovered_device_failed(self, dev):
        """ Device could not be fully built, so forget it.
        """
        usn = dev['USN']
        if usn in self.known_device:
            self.known_device.pop(usn)

    def is_known_device(self, usn):
        """ Returns if the device with the passed usn is already known.

        @param usn: device's usn
        @type usn: string

        @return: True if it is known
        @rtype: boolean
        """
        return usn in self.known_device

    def subscribe(self, name, callback):
        """ Subscribes a callback for an event.

        @param name: name of the event. May be "new_device_event" or
                     "removed_device_event"
        @param callback: callback

        @type name: string
        @type callback: callable
        """
        self._callbacks.setdefault(name, []).append(callback)

    def unsubscribe(self, name, callback):
        """ Unsubscribes a callback for an event.

        @param name: name of the event
        @param callback: callback

        @type name: string
        @type callback: callable
        """
        callbacks = self._callbacks.get(name, [])
        [callbacks.remove(c) for c in callbacks]
        self._callbacks[name] = callbacks

    def announce_device(self):
        """ Announces the device.
        """
        log.debug("announce_device")
        [self._do_notify(usn) for usn in self.advertised]

    def register_device(self, device):
        """ Registers a device on the SSDP server.

        @param device: device to be registered
        @type device: Device
        """
        self._register_device(device)
        if device.is_root_device():
            [self._register_device(d) for d in device.devices.values()]

    # Messaging

    def _datagram_received(self, data, (host, port)):
        """ Handles a received multicast datagram.

        @param data: raw data
        @param host: datagram source host
        @param port: datagram source port

        @type data: string
        @type host: string
        @type port: integer
        """
        log.debug("SSDP._datagram_received host: %s, port: %s\ndata: %s", host, port, data)
        try:
            header, payload = data.split('\r\n\r\n')
        except ValueError, err:
            log.error('Error while receiving datagram packet: %s', str(err))
            return

        lines = header.split('\r\n')
        cmd = lines[0].split(' ')
        lines = map(lambda x: x.replace(': ', ':', 1), lines[1:])
        lines = filter(lambda x: len(x) > 0, lines)

        headers = [x.split(':', 1) for x in lines]
        headers = dict(map(lambda x: (x[0].lower(), x[1]), headers))

        if cmd[0] == 'M-SEARCH' and cmd[1] == '*':
#        if cmd[0] == 'M-SEARCH' and cmd[1] == '*' \
#	        and headers['man'] == '"ssdp:discover"':
            # SSDP discovery
            log.debug('Received M-Search command from %s:%s', host, port)
            self._discovery_request(headers, (host, port))
        elif cmd[0] == 'NOTIFY' and cmd[1] == '*':
            log.debug("NOTIFY receive_notify: %s", self.receive_notify)
            if not self.receive_notify:
                # Ignore notify
                log.debug('Received NOTIFY command from %s:%s (ignored '\
                          'because of SSDPServer.receive_notify is False)',
                          host, port)
                return
            # SSDP presence
            self._notify_received(headers, (host, port))
        else:
            log.warning('Received unknown SSDP command %s with headers %s '\
                        'from %s:%s', cmd, str(headers), host, port)

    def _discovery_request(self, headers, (host, port)):
        """ Processes discovery requests and responds accordingly.

        @param headers: discovery headers
        @param host: discovery source host
        @param port: discovery source port

        @type headers: dictionary
        @type host: string
        @type port integer
        """
        right_key = 0

        # Do we know about this service?
        if headers['st'] == 'ssdp:all':
            for i in self.known_device.keys():
                hcopy = dict(headers.iteritems())
                hcopy['st'] = self.known_device[i]['ST']
                self._discovery_request(hcopy, (host, port))
            return

        for key in self.known_device.keys():
            if self.known_device[key]['ST'].split()[0] == (headers['st']).split()[0]:
                right_key = key
                break
        else:
            log.debug('Discovery request ST %s not found', headers['st'])
            return

        if right_key == 0:
            log.error('Unknown error in DiscoveryRequest for %s',
                      headers['st'])
            return

        # Generate a response
        response = []
        response.append('HTTP/1.1 200 OK')
        append = response.append

        [append('%s: %s' % (k, v)) for k, v in self.known_device[right_key].items()]
        response.extend(('', ''))
        delay = random.randint(0, int(headers['mx']))
        # Avoid using a timer with delay 0 :)
        if delay:
            self.udp_transport.send_delayed(delay, '\r\n'.join(response),
                                            host, port)
        else:
            self.udp_transport.send_data('\r\n'.join(response), host, port)
        log.debug('Discovery request response sent to (%s, %d)', host, port)

    def _notify_received(self, headers, (host, port)):
        """ Processes a presence announcement.

        @param headers: notify headers
        @param host: notify source host
        @param port: notify source port

        @type headers: dictionary
        @type host: string
        @type port: integer
        """
        log.debug("_notify_received known_device: %s", self.known_device)
        if headers['nts'] == 'ssdp:alive':
        
#            print "headers: " + str(headers)
        
            if 'cache-control' not in headers:
                headers['cache-control'] = 'max-age=1800'
            try:
                self.known_device[headers['usn']]
            except KeyError:
                self._register(headers['usn'], headers['nt'],
                               headers['location'], headers['server'],
                               headers['cache-control'])
        elif headers['nts'] == 'ssdp:byebye':
            if self.is_known_device(headers['usn']):
                self._unregister(headers['usn'])
        else:
            log.warning('Unknown subtype %s for notification type %s',
                        headers['nts'], headers['nt'])

    # Registering

    def _register(self, usn, st, location, server, cache_control,
                  where='remote'):
        """ Registers a service or device.

        @param usn: usn
        @param st: st
        @param location: location
        @param server: server
        @param cache_control: cache control

        @type usn: string
        @type location: string
        @type st: string
        @type server: string
        @type cache_control: string

        @note: these parameters are part of the UPnP Specification. Even though
        they're abstracted by the framework (devices and services messages
        already contain these parameters), if you want to understand it please
        refer to the UPnP specification. Links can be found at our developer
        documentation homepage.
        """
        log.debug('_register')

        if where == 'remote':
            d = self.known_device
        elif where == 'local':
            d = self.advertised

        d[usn] = {'USN': usn,
                  'LOCATION': location,
                  'ST': st,
                  'EXT': '',
                  'SERVER': server,
                  'CACHE-CONTROL': cache_control}

        if st == 'upnp:rootdevice' and where == 'remote':
        
#            print "NEW DEVICE EVENT: " + str(self.known_device[usn])
        
            self._callback("new_device_event", st, self.known_device[usn])

    def _local_register(self, usn, st, location, server, cache_control):
        """ Registers locally a new service or device.
        """
        log.debug('Registering locally %s (%s)', st, location)
        self._register(usn, st, location, server, cache_control, 'local')
        self._do_notify(usn)

    def _register_device(self, device):
        device_id = device.udn
        device_type = device.device_type
        device_server = "BRisa Webserver UPnP/1.0 %s" % self.server_name
        device_location = "%s/%s" % (device.location,
                                     self.xml_description_filename)
        age = 'max-age=%d' % self.max_age

        # uuid:device-UUID::upnp:rootdevice
        self._local_register('%s::upnp:rootdevice' % device_id,
                             'upnp:rootdevice',
                             device_location,
                             device_server, age)

        # uuid:device-UUID
        self._local_register(device_id,
                             device_id,
                             device_location,
                             device_server, age)


        # urn:schemas-upnp-org:device:deviceType:v
        self._local_register('%s::%s' % (device_id, device_type),
                             device_type, device_location,
                             device_server, age)

        for serv_type, service in device.services.items():
            # urn:schemas-upnp-org:service:serviceType:v
            self._local_register('%s::%s' % (device_id, service.service_type),
                                 service.service_type,
                                 device_location, device_server, age)

    def _renew_notifications(self):
        """ Renew notifications (sends a notify
        """
        log.debug("_renew_notifications")
        own_temp = self.advertised.copy()
        for usn in own_temp:
            log.debug('Renew notification for %s ', usn)
            log.debug('Renew notification for %s ', own_temp[usn]['USN'])
            self._do_notify(own_temp[usn]['USN'])

    def _unregister(self, usn):
        log.debug("Unregistering %s", usn)

        try:
            self._callback("removed_device_event", self.known_device[usn])
            if usn in self.known_device:
                del self.known_device[usn]
        except:
            pass

    # Notify and byebye

    def _do_notify(self, usn):
        """ Do a notification for the usn specified.

        @param usn: st
        @type usn: string
        """
        log.debug('Sending alive notification for %s', usn)
        resp = ['NOTIFY * HTTP/1.1', 'HOST: %s:%d' % (SSDP_ADDR, SSDP_PORT),
                'NTS: ssdp:alive', ]
        stcpy = dict(self.advertised[usn].iteritems())
        stcpy['NT'] = stcpy['ST']
        del stcpy['EXT']
        del stcpy['ST']
        resp.extend(map(lambda x: ': '.join(x), stcpy.iteritems()))
        resp.extend(('', ''))
        self.udp_transport.send_data('\r\n'.join(resp), SSDP_ADDR, SSDP_PORT)
        self.udp_transport.send_data('\r\n'.join(resp), SSDP_ADDR, SSDP_PORT)

    def _do_byebye(self, usn):
        """ Do byebye notification for the usn specified.

        @param usn: usn
        @type usn: string
        """
        log.debug('Sending byebye notification for %s', usn)
        resp = ['NOTIFY * HTTP/1.1', 'HOST: %s:%d' % (SSDP_ADDR, SSDP_PORT),
                'NTS: ssdp:byebye', ]
        stcpy = dict(self.advertised[usn].iteritems())
        stcpy['NT'] = stcpy['ST']
        del stcpy['ST']
        del stcpy['EXT']
        resp.extend(map(lambda x: ': '.join(x), stcpy.iteritems()))
        resp.extend(('', ''))
        self.udp_transport.send_data('\r\n'.join(resp), SSDP_ADDR, SSDP_PORT)
        self.udp_transport.send_data('\r\n'.join(resp), SSDP_ADDR, SSDP_PORT)

    # Eventing

    def _callback(self, name, *args):
        """ Performs callbacks for events.
        """
        for callback in self._callbacks.get(name, []):
            callback(*args)

    # Cleanup

    def _cleanup(self):
        """ Cleans the SSDPServer by removing known devices and internal cache.
        """
        self.clear_device_list()
