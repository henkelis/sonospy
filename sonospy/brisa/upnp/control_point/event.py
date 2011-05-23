# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Control point side UPnP event support.
"""

from xml.etree import ElementTree

from brisa.core import log, webserver
from brisa.core.threaded_call import run_async_function
from brisa.core.network_senders import UDPTransport
from brisa.core.network_listeners import UDPListener
from brisa.core.network import parse_http_response, get_active_ifaces, get_ip_address
from brisa.upnp.upnp_defaults import UPnPDefaults


def read_notify_message_body(body_data):
    changed_vars = {}

    try:
        tree = ElementTree.XML(body_data)
    except:
        log.debug('Event XML invalid: %s', body_data)
        tree = None

    if tree:
        for prop1 in tree.findall('{%s}property' %
                                  'urn:schemas-upnp-org:event-1-0'):
            # prop1 = <e:property> <Ble> cont </Ble> </e:property>
            for prop2 in prop1:
                # <Ble>cont</Ble>
                changed_vars[prop2.tag] = prop2.text

    return changed_vars


class EventListener(webserver.CustomResource):
    """ EventListener resource available at the control point web server,
    listening for events.
    """

    def __init__(self, observer):
        """ Constructor for the EventListener class

        @param observer: observer class with a _on_event() method.
        """
        webserver.CustomResource.__init__(self, 'eventSub')
        self.observer = observer
        
    def cleanup(self):
        """ Removes reference to observer to make GC easier """
        self.observer = None

    def render(self, uri, request, response):
        """ Event renderer method. As events come only on NOTIFY messages, this
        method ignores any other type of message (GET, POST, ...).

        @param uri: URI of the request
        @param request: request object (Cherrypy)
        @param response: response object (Cherrypy)

        @type uri: string

        @note: see Cherrypy documentation for further info about request and
        response attributes and methods.
        """
        log.debug('Received render (%s)' % str((uri, request, response)))

        if request.method == 'NOTIFY':
            log.debug('Ok, got notify!')
            self.render_NOTIFY(request, response)
        else:
            log.debug('Did not get notify, got %s' % request.method)

        log.debug('Returning from render')
        
#        return ['']
        response.status = 200
        response.body = ['\n']
        response.headers["Connection"] = 'close'
 
        return response.body


    def render_NOTIFY(self, request, response):
        """ Renders the notify message for an event.

        @param request: request object (Cherrypy)
        @param response: response object (Cherrypy)

        @note: see Cherrypy documentation for further info about request and
        response attributes and methods.
        """
        data = request.read()
        # extraneous characters after the end of XML will choke ElementTree
        data = data[data.find("<"):data.rfind(">")+1]

        run_async_function(self.forward_notification, (request.headers, data),
                           0.0001)
        return ""

    def forward_notification(self, received_headers, data):
        """ Forwards notifications to the observer registered.

        @param received_headers: headers received on the event notify
        @param data: XML data for the event

        @type received_headers: dictionary
        @type data: string
        """
        log.debug('forward notification')
        headers = {}
        for k, v in received_headers.items():
            headers[k.lower()] = v

        changed_vars = read_notify_message_body(data)

        log.debug('Event changed vars: %s', changed_vars)

        if self.observer and 'sid' in headers:
        
            seq_method = getattr(self.observer, '_on_event_seq', None)
            if callable(seq_method) and 'seq' in headers:
                self.observer._on_event_seq(headers['sid'], headers['seq'], changed_vars)
            else:            
                self.observer._on_event(headers['sid'], changed_vars)

            for id, dev in self.observer._known_devices.items():

                log.debug('id: %s - dev: %s', id, dev)
            
                service = self._find_service(dev, headers['sid'])
                if service != None:
                    service._on_event(changed_vars)
                    return

    def _find_service(self, device, subscription_id):
        """ Method to find a service with a specific subscription
        id on the given device or on it children devices.

        @param device: instance of a device
        @param subscription_id: the id to compare with the service

        @type device: RootDevice or Device
        @type subscription_id: str

        @return: if found, the service
        @rtype: Service or None
        """
        for k, service in device.services.items():
            if service.event_sid == subscription_id:
                return service
#        print str(device) + " - " + str(device.devices)
        for k, child_dev in device.devices:
            service = self._find_service(child_dev, subscription_id)
            if service:
                return service
        return None






#class EventListener2(EventListener):
#    def __init__(self, observer):
#        print "EventListener2 init"
#        print "EventListener2 init observer: " + str(observer)
#        webserver.CustomResource.__init__(self, 'notify')
#        self.observer = observer
#        print "EventListener2 init end"






class EventListenerServer(object):
    """ EventListener server. Wraps BRisa's web server and listens for events.
    """

    def __init__(self, observer, port):
        """ Constructor for the EventListenerServer class.

        @param observer: observer that implements the _on_event() method
        """
        self.srv = None
        self.port = port
        self.event_listener = EventListener(observer)
#        self.event_listener2 = EventListener2(observer)

    def host(self):
        """ Returns a tuple in the form (host, port) where the server is being
        hosted at.

        @return: the host and port of the server host
        @rtype: tuple
        """
        if not self.srv:
            self.srv = webserver.WebServer(port=self.port)
            self.srv.start()
        return (self.srv.get_host(), self.srv.get_port())

    def start(self, event_host=None):
        if not self.srv:
            self.srv = webserver.WebServer(port=self.port)
            self.srv.start()
        if event_host:
            self.srv.listen_url = 'http://%s:%d' % event_host
        self.srv.add_resource(self.event_listener)
#        self.srv.add_resource(self.event_listener2)

    def stop(self):
        """ Stops the EventListenerServer. For restarting after stopping with
        this method use EventListenerServer.srv.start().
        """
        if self.srv:
            self.srv.stop()

    def is_running(self):
        if self.srv:
            return self.srv.is_running()
        else:
            return False

    def destroy(self):
        if self.is_running():
            self.stop()
        self._cleanup()

    def _cleanup(self):
        self.srv = None
        self.event_listener.cleanup()
        self.event_listener = None


class MulticastEventListener:
    """ Represents a multicast event listener. Contains some control 
    functions for starting and stopping the listener.
    """

    msg_already_started = 'tried to start() MulticastEventListener when already started'
    msg_already_stopped = 'tried to stop() MulticastEventListener when already stopped'

    def __init__(self, control_point, start=True):
        """ Constructor for the MulticastEventListener class.

        @param ssdp: ssdp server instance that will receive new device events
        and subscriptions
        @param start: if True starts the search when constructed
        @param ssdp_addr: ssdp address for listening (UDP)
        @param ssdp_port: ssdp port for listening (UDP)

        @type ssdp: SSDPServer
        @type start: boolean
        @type ssdp_addr: string
        @type ssdp_port integer
        """
        self.udp_transport = UDPTransport()
        self.listen_udp = UDPListener(UPnPDefaults.MULTICAST_EVENT_ADDR,
                                      UPnPDefaults.MULTICAST_EVENT_PORT,
                                      data_callback=self._datagram_received,
                                      shared_socket=self.udp_transport.socket)
        self.control_point = control_point
        if start:
            self.start()

    def _datagram_received(self, data, (host, port)):
        """ Callback for the UDPListener when messages arrive.

        @param data: raw data received
        @param host: host where data came from
        @param port: port where data came from

        @type data: string
        @type host: string
        @type port: integer
        """
        log.debug("cp.event._datagram_received host: %s, port: %s\ndata: %s", host, port, data)
        try:
            cmd, headers = parse_http_response(data)
            body = data[data.find("<"):data.rfind(">")+1]
        except Exception, err:
            log.error('Error while receiving datagram packet: %s', str(err))
            return

        # Render notify message
        if not (cmd[0] == 'NOTIFY' and cmd[1] == '*' and cmd[2] == 'HTTP/1.0' and \
           headers.has_key('content-type') and \
           headers['content-type'] == 'text/xml; charset="utf-8"' and \
           headers.has_key('nt') and headers['nt'] == 'upnp:event' and \
           headers.has_key('nts') and headers['nts'] == 'upnp:propchange' and \
           headers.has_key('host') and headers.has_key('usn') and \
           headers.has_key('svcid') and headers.has_key('seq') and \
           headers.has_key('lvl') and headers.has_key('bootid.upnp.org') and \
           headers.has_key('content-length')):

            log.warning('Invalid message')
            return

        addr = headers['host'].split(':')[0]
        port = int(headers['host'].split(':')[1])
        udn = headers['usn'].split('::')[0]
        service_type = headers['usn'].split('::')[1]
        svcid = headers['svcid']
        seq = int(headers['seq'])
        lvl = headers['lvl']
        content_length = int(headers['content-length'])
        bootid = int(headers['bootid.upnp.org'])

        if addr != UPnPDefaults.MULTICAST_EVENT_ADDR or \
           port != UPnPDefaults.MULTICAST_EVENT_PORT:
            log.warning('Invalid address %s:%d' % (addr, port))
            return

        changed_vars = read_notify_message_body(body)

        self.control_point._on_event('', changed_vars)

        for id, dev in self.control_point._known_devices.items():
            service = self._find_service(dev, udn, service_type, svcid)
            if service != None:
                service._on_event(changed_vars)
                log.debug('Multicast event. Event changed vars: %s', changed_vars)

    def is_running(self):
        """ Returns True if the listener is running.

        @rtype: boolean
        """
        return self.listen_udp.is_running()

    def start(self):
        """ Starts the listener.
        """
        if not self.is_running():
            self.listen_udp.start()
            log.debug('Multicast event listener started')
        else:
            log.warning(self.msg_already_started)

    def stop(self):
        """ Stops the search.
        """
        if self.is_running():
            log.debug('Multicast event listener stopped')
            self.listen_udp.stop()
        else:
            log.warning(self.msg_already_stopped)

    def destroy(self):
        """ Destroys and quits MSearch.
        """
        if self.is_running():
            self.stop()
        self.listen_udp.destroy()
        self._cleanup()

    def _find_service(self, device, udn, service_type, svcid):
        """ Method to find a service.

        @param device: instance of a device
        @param udn: device id
        @param service_type: service type
        @param svcid: service id

        @type device: RootDevice or Device
        @type udn: string
        @type service_type: string
        @type svcid: string

        @return: if found, the service
        @rtype: Service or None
        """
        if device.udn != udn:
            for k, child_dev in device.devices:
                service = self._find_service(child_dev, udn, service_type, svcid)
                if service:
                    return service
        else:
            for k, service in device.services.items():
                if service.service_type == service_type and \
                   str(service.id) == svcid:
                    return service
            return None

    def _cleanup(self):
        """ Clean up references.
        """
        self.ssdp = None
        self.listen_udp = None
        self.control_point = None
