# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Provides a base controller class that logs devices.
    Is extracted code from various Brisa modules that
    builds devices but doesn't generate SOAP services
    for them or subscribe to them.
"""

from brisa.core import log
from brisa.upnp.ssdp import SSDPServer
from brisa.upnp.control_point.msearch import MSearch
from brisa.upnp.base_device import BaseDevice, BaseDeviceIcon

from xml.etree.ElementTree import ElementTree
from xml.etree.ElementTree import tostring

from brisa.core.network import url_fetch, parse_url
from brisa.core.threaded_call import run_async_call
from brisa.upnp.control_point.service import Service
from brisa.upnp.upnp_defaults import UPnPDefaults
from brisa.upnp.control_point import ControlPointAV

import brisa

from control_point_sonos import ControlPointSonos

log = log.getLogger('control-point.basic')

class Controller(ControlPointSonos):
    """ This class implements a cut down UPnP Controller that just logs devices

    The simplest way of using it is by subscribing for the device events,
    starting it with start() and search for devices with start_search().
    It will be listening for search responses only after start_search().

    Available events for subscription:
        - new_device_event     - triggered when a new device is found
        - removed_device_event - triggered when a device announces its departure

    You may stop the controller anytime with stop() and it can be reused by
    calling start() again. If you want to stop it definitely, you may use
    destroy().
    """
    msg_already_started = 'tried to start() Controller when already started'
    msg_already_stopped = 'tried to stop() Controller when already stopped'

    def __init__(self, receive_notify=False):
        """Controller class constructor.

        @param receive_notify: if False, ignores notify messages from devices.
        Default value is False and it can be set during runtime

        @type receive_notify: boolean
        """
        self._ssdp_server = SSDPServer("BRisa Controller", None, receive_notify=receive_notify)
#        self._ssdp_server = SSDPServer("BRisa Controller", 'sonoscp.xml', receive_notify=receive_notify)
        self._ssdp_server.subscribe("new_device_event", self._new_device_event)
        self._ssdp_server.subscribe("removed_device_event", self._removed_device_event)
        self._msearch = MSearch(self._ssdp_server, start=False)
        self._callbacks = {}
        self._known_devices = {}

    def get_devices(self):
        """ Returns a dict of devices found.
        """
        return self._known_devices

    def is_running(self):
        return self._ssdp_server.is_running()

    def start(self):
        """ Starts the controller.
        """
        if not self.is_running():
            self._ssdp_server.start()
        else:
            log.warning(self.msg_already_started)

    def stop(self):
        """ Stops the controller.
        """
        if self.is_running():
            if self.is_msearch_running():
                self.stop_search()
            self._ssdp_server.stop()
        else:
            log.warning(self.msg_already_stopped)

    def destroy(self):
        """ Destroys and quits the controller definitely.
        """
        if self.is_running():
            self.stop_control_point()
        self._msearch.destroy()
        self._ssdp_server.destroy()
        self._cleanup()

    def _cleanup(self):
        """ Cleanup references.
        """
        self._known_devices.clear()
        self._msearch = None
        self._ssdp_server = None

    def subscribe(self, name, callback):
        """ Subscribes the callback for an event.

        @param name: event name
        @param callback: callback which will listen on the event

        @type name: string
        @type callback: callable
        """
        self._callbacks.setdefault(name, []).append(callback)

    def unsubscribe(self, name, callback):
        """ Unsubscribes the callback for an event.

        @param name: event name
        @param callback: callback which listens for the event

        @type name: string
        @type callback: callable
        """
        callbacks = self._callbacks.get(name, [])
        if callback in callbacks:
            callbacks.remove(callback)

    def start_search(self, interval, search_type="ssdp:all", reset=False):
        """ Sends a multicast M-SEARCH message to discover UPnP devices.

        @param interval: interval to wait between sending search messages
        @param search_type: UPnP type search. Default value is "ssdp:all"
        @param reset: clears the device list from any previous search

        @type interval: float
        @type search_type: string
        @type reset: boolean
        """
        if reset:
            self._ssdp_server.clear_device_list()
        self._msearch.start(interval, search_type)

    def stop_search(self):
        """ Stops the device search.
        """
        self._msearch.stop()

    def force_discovery(self, search_type="ssdp:all"):
        """ Forces a multicast MSearch bypassing the time interval. This method
        force msearch to send discovery message, bypassing the initial time
        interval passed to start_search function. Note this method doesn't
        cause any effect if the start_search call was never called.

        @param search_type: UPnP type search
        @type search_type: string
        """
        log.debug('force_discovery, search_type: %s', search_type)
        self._msearch.double_discover(search_type)

    def is_msearch_running(self):
        """ Returns whether MSEARCH is running or not.

        @return: Status of the MSearch
        @rtype: boolean
        """
        return self._msearch.is_running()

    def _get_recv_notify(self):
        """ GET function for the receive_notify property. Use
        self.receive_notify instead.

        @return: The receive_notify status
        @rtype: boolean
        """
        return self._ssdp_server.receive_notify

    def _set_recv_notify(self, n):
        """ SET function for the receive_notify property. Use
        self.receive_notify instead.

        @param n: The value to be set.
        @type n: boolean
        """
        self._ssdp_server.receive_notify = n

    receive_notify = property(_get_recv_notify,
                              _set_recv_notify,
                              doc='If False, the controller ignores NOTIFY\
                              messages from devices.')

    def _new_device_event(self, st, device_info):
        """ Receives a new device event.

        @param st: defines the device type
        @param device_info: informations about the device

        @type st: string
        @type device_info: dict
        """

        log.debug('st: %s, device_info: %s', st, device_info)
        
        # Callback assigned for new device event, processes asynchronously
        if 'LOCATION' not in device_info:
            return

        Device.get_from_location_async(device_info['LOCATION'],
                                       self._new_device_event_impl,
                                       device_info)

    def _new_device_event_impl(self, device_info, device):
        """ Real implementation of the new device event handler.

        @param device_info: informations about the device
        @param device: the device object itself

        @type device_info: dict
        @type device: Device
        """

#        print "control_point _new_device_event_impl udn: " + str(device.udn)

        log.debug('device_info: %s, device: %s', device_info, device)

        if not device and self._ssdp_server:
            # Device creation failed, tell SSDPSearch to forget it
            self._ssdp_server.discovered_device_failed(device_info)
            return

        self._known_devices[device.udn] = device
        self._callback("new_device_event", device)
        log.info('Device found: %s' % device.friendly_name)

    def _removed_device_event(self, device_info):
        """ Receives a removed device event.

        @param device_info: information about the device

        @type device_info: dict
        """
        udn = device_info['USN'].split('::')[0]
        if udn in self._known_devices:
            log.info('Device is gone: %s' %
                     self._known_devices[udn].friendly_name)

        self._known_devices.pop(udn, None)
        self._callback("removed_device_event", udn)

    def _callback(self, name, *args):
        """ Callback for any event. Forwards the event to the subscribed
        callbacks.

        @param name: event name
        @param args: arguments for the callbacks

        @type name: string
        @type args: tuple
        """
        for callback in self._callbacks.get(name, []):
            callback(*args)


class DeviceBuilder(object):

    def __init__(self, device, location, tree):
        self.device = device
        self.tree = tree
        self.location = location
        self.ns = UPnPDefaults.NAME_SPACE_XML_SCHEMA
        self._build()

    def _build(self):
        self._parse_device()
        self._parse_icons()
        self._parse_services()
        self._parse_embedded_devices()

    def _parse_device(self):
        self.device.device_type = self.tree.\
                                     findtext('.//{%s}deviceType' % self.ns)
        self.device.friendly_name = self.tree.\
                                  findtext('.//{%s}friendlyName' % self.ns)
        self.device.manufacturer = self.tree.\
                                     findtext('.//{%s}manufacturer' % self.ns)
        self.device.manufacturer_url = self.tree.\
                                 findtext('.//{%s}manufacturerURL' % self.ns)
        self.device.model_description = self.tree.\
                              findtext('.//{%s}modelDescription' % self.ns)
        self.device.model_name = self.tree.\
                                   findtext('.//{%s}modelName' % self.ns)
        self.device.model_number = self.tree.\
                                     findtext('.//{%s}modelNumber' % self.ns)
        self.device.model_url = self.tree.\
                                  findtext('.//{%s}modelURL' % self.ns)
        self.device.serial_number = self.tree.\
                                  findtext('.//{%s}serialNumber' % self.ns)
        self.device.udn = self.tree.findtext('.//{%s}UDN' % self.ns)
        self.device.upc = self.tree.findtext('.//{%s}UPC' % self.ns)
        self.device.presentation_url = self.tree.\
                                 findtext('.//{%s}presentationURL' % self.ns)

        self.device.location = self.location
        addr = parse_url(self.location)
        self.device.address = '%s://%s:%d' % (addr.scheme, addr.hostname, addr.port)
        self.device.scheme = addr.scheme
        self.device.ip = addr.hostname
        self.device.port = addr.port

    def _parse_services(self):
        for xml_service_element in self.tree.\
                                    findall('.//{%s}service' % self.ns):
            service_type = xml_service_element.\
                                    findtext('{%s}serviceType' % self.ns)
            service_id = xml_service_element.\
                                    findtext('{%s}serviceId' % self.ns)
            control_url = xml_service_element.\
                                    findtext('{%s}controlURL' % self.ns)
            if control_url and not control_url.startswith('/'):
                control_url = '/' + control_url
            event_sub_url = xml_service_element.\
                                    findtext('{%s}eventSubURL' % self.ns)
            if event_sub_url and not event_sub_url.startswith('/'):
                event_sub_url = '/' + event_sub_url
            presentation_url = xml_service_element.\
                                    findtext('{%s}presentationURL' % self.ns)
            if presentation_url and not presentation_url.startswith('/'):
                presentation_url = '/' + presentation_url
            scpd_url = xml_service_element.\
                                    findtext('{%s}SCPDURL' % self.ns)
            if scpd_url and not scpd_url.startswith('/'):
                scpd_url = '/' + scpd_url
            log.debug('control_url: %s, event_sub_url: %s, presentation_url: %s, scpd_url: %s', control_url, event_sub_url, presentation_url, scpd_url)
            service = Service(service_id, service_type, self.location,
                              scpd_url, control_url, event_sub_url,
                              presentation_url)
            self.device.add_service(service)

    def _parse_icons(self):
        if self.tree.findtext('.//{%s}IconList' % self.ns) != None:
            for xml_icon_element in self.tree.findall('.//{%s}icon' % self.ns):
                mimetype = xml_icon_element.findtext('{%s}mimetype' % self.ns)
                width = xml_icon_element.findtext('{%s}width' % self.ns)
                height = xml_icon_element.findtext('{%s}height' % self.ns)
                depth = xml_icon_element.findtext('{%s}depth' % self.ns)
                url = xml_icon_element.findtext('{%s}url' % self.ns)

                icon = DeviceIcon(mimetype, width, height, depth, url)
                self.device.icons.append(icon)

    def _parse_embedded_devices(self):
        device_list = self.tree.find('.//{%s}deviceList' % self.ns)
        if device_list != None:
            embedded_device_tag = device_list.findall('.//{%s}device' %
                                                      self.ns)

            for xml_device_element in embedded_device_tag:
                d = self.device.__class__()
                DeviceBuilder(d, self.location,
                              xml_device_element).cleanup()
                self.device.add_device(d)

    def cleanup(self):
        self.device = None
        self.tree = None
        self.location = None


class DeviceAssembler(object):

    def __init__(self, device, location, filename=None):
        self.device = device
        self.location = location
        self.filename = filename

    def mount_device(self):
        if self.filename is None:
            filecontent = url_fetch(self.location)
            if not filecontent:
                return
            data = filecontent.read()
            data = data[data.find("<"):data.rfind(">")+1]
            tree = ElementTree(data).getroot()
        else:
            from xml.etree.ElementTree import parse
            tree = parse(self.filename)

        DeviceBuilder(self.device, self.location, tree).cleanup()
        return self.device

    def mount_device_async(self, callback, cargo):
        self.callback = callback
        self.cargo = cargo
        log.debug('self.location is %s' % self.location)

#        if '0.0.0.0' in self.location:
#            import traceback        
#            traceback.print_stack()

#        # HACK - get 401's from these
#        if ':49153' in self.location:
#            log.debug("Sky HD device discovered, ignore")
#            self.callback(self.cargo, None)
#            return
        
        if self.filename is None:
            run_async_call(url_fetch,
                           success_callback=self.mount_device_async_gotdata,
                           error_callback=self.mount_device_async_error,
                           delay=0, url=self.location)
        else:
            self.mount_device_async_gotdata(self, open(self.filename))

    def mount_device_async_error(self, cargo, error):
        log.debug("Error fetching %s - Error: %s" % (self.location,
                                                     str(error)))
        self.callback(self.cargo, None)
        return True

    def mount_device_async_gotdata(self, fd, cargo=None):
        try:
            log.debug('to object async got data getting tree')
            tree = ElementTree(file=fd).getroot()
        except Exception, e:
            log.debug("Bad device XML %s" % e)
            self.callback(self.cargo, None)
            return

        log.debug('Device ElementTree: %s' % tostring(tree))

        DeviceBuilder(self.device, self.location, tree).cleanup()
        if brisa.__skip_service_xml__:
            self.callback(self.cargo, self.device)
        else:
            log.debug("Fetching device services")
            self.pending_services = len(self.device.services)
            for service_name, service_object in \
                     self.device.services.items():
                service_object._build_async(self.service_has_been_built)

    def service_has_been_built(self, built_ok):
        log.debug("Service fetched, %d left, result %s", \
                self.pending_services - 1, built_ok)
        if not built_ok and not brisa.__tolerate_service_parse_failure__:
            log.debug("Device killed")
            self.device = None
        self.pending_services -= 1

        if self.pending_services <= 0:
            log.debug("All services fetched, sending device forward")
            self.callback(self.cargo, self.device)
            
class Device(BaseDevice):
    """ Represents an UPnP device.

    Consult http://upnp.org/standardizeddcps/basic.asp as a basic reference.
    """

    def add_device(self, device):
        if not BaseDevice.add_device(self, device):
            # Could not add device
            return False

    @classmethod
    def get_from_location(cls, location):
        return DeviceAssembler(cls(), location).mount_device()

    @classmethod
    def get_from_location_async(cls, location, callback, cargo):
        DeviceAssembler(cls(), location).mount_device_async(callback, cargo)

    @classmethod
    def get_from_file(cls, location, filename):
        return DeviceAssembler(cls(), location, filename).mount_device()

    @classmethod
    def get_from_file_async(cls, location, filename, callback, cargo):
        DeviceAssembler(cls(), location, filename).mount_device_async(callback,
                                                                      cargo)            
