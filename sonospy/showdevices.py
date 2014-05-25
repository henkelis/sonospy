
from brisa.core.reactors import SelectReactor
reactor = SelectReactor()

import sys
fenc = sys.getfilesystemencoding()
#print sys.getdefaultencoding()

import os

import urllib

from brisa.core import log

import brisa

import threading

import pprint
pp = pprint.PrettyPrinter(indent=4)

from brisa.core.network import parse_xml
from brisa.core.network import parse_url, url_fetch
from brisa.core.threaded_call import run_async_function, run_async_call

from brisa.utils.looping_call import LoopingCall

from brisa.upnp.upnp_defaults import UPnPDefaults
from brisa.upnp.control_point.service import is_file, is_relative
from brisa.upnp.base_service import parse_base_url

from xml.etree.ElementTree import ElementTree
from xml.etree.ElementTree import tostring
from controller import Controller

# monkey patch controller module DeviceAssembler so that we can save the device XML
import controller


class sdDeviceAssembler(controller.DeviceAssembler):
    
    ns = UPnPDefaults.NAME_SPACE_XML_SCHEMA
    devicexml = {}
    servicexml = {}
    
    def __init__(self, device, location, filename=None):
        self.device = device
        self.location = location
        self.url_base = parse_base_url(self.location)
        self.filename = filename
        old_deviceassembler.__init__(self, device, location, filename)
    
    def mount_device_async(self, callback, cargo):
        self.callback = callback
        self.cargo = cargo
        log.debug('self.location is %s' % self.location)
        
        if self.filename is None:
            run_async_call(url_fetch,
                           success_callback=self.sd_mount_device_async_gotdata,
                           error_callback=self.mount_device_async_error,
                           delay=0, url=self.location)
        else:
            self.sd_mount_device_async_gotdata(self, open(self.filename))

        # chain to old mount to re-read file
        old_deviceassembler.mount_device_async(self, callback, cargo)

    def sd_mount_device_async_gotdata(self, fd, cargo):
        try:
            tree = ElementTree(file=fd).getroot()
        except Exception, e:
            print "Bad device XML %s" % e
        fd.close()

        friendly_name = tree.findtext('.//{%s}friendlyName' % self.ns)
        udn = tree.findtext('.//{%s}UDN' % self.ns)

#        print 'friendly_name: %s' % friendly_name
#        print 'udn: %s' % udn
#        print 'Device XML: %s' % tostring(tree)
        self.devicexml[udn] = (friendly_name, tostring(tree))

        self.sd_get_services_xml(udn, tree)

    def sd_mount_device_async_error(self, cargo, error):
        log.debug("Error fetching %s - Error: %s" % (self.location,
                                                     str(error)))
        return True

    def sd_get_services_xml(self, udn, tree):
        for xml_service_element in tree.findall('.//{%s}service' % self.ns):
            scpd_url = xml_service_element.findtext('{%s}SCPDURL' % self.ns)
            service_type = xml_service_element.findtext('{%s}serviceType' % self.ns)
            if scpd_url and not scpd_url.startswith('/'):
                scpd_url = '/' + scpd_url
            print '        %s' % service_type
            if is_file(scpd_url):
                fd = open(scpd_url[8:], 'r')
            else:
                if is_relative(scpd_url, self.url_base):
                    url = '%s%s' % (self.url_base, scpd_url)
                else:
                    url = scpd_url
                fd = url_fetch(url)
            if not fd:
                print 'Could not fetch SCPD URL %s' % scpd_url
            else:
                try:
                    tree = ElementTree(file=fd).getroot()
                except Exception, e:
                    print "Bad service XML %s" % e
                fd.close()
                self.servicexml[udn] = self.servicexml.get(udn, '') + '%s\n%s\n\n' % (service_type, tostring(tree))
                
old_deviceassembler = controller.DeviceAssembler
controller.DeviceAssembler = sdDeviceAssembler

'''

def _parse_embedded_devices(tree):
    device_list = self.tree.find('.//{%s}deviceList' % self.ns)
    if device_list != None:
        embedded_device_tag = device_list.findall('.//{%s}device' %
                                                  self.ns)

        for xml_device_element in embedded_device_tag:
            d = self.device.__class__()
            DeviceBuilder(d, self.location,
                          xml_device_element).cleanup()
            self.device.add_device(d)
'''



from brisa import url_fetch_attempts, url_fetch_attempts_interval, __skip_service_xml__, __skip_soap_service__, __tolerate_service_parse_failure__, __enable_logging__, __enable_webserver_logging__, __enable_offline_mode__, __enable_events_logging__

class ShowDevices(object):
    
    known_devices = {}
    known_zone_players = {}
    zoneattributes = {}
    known_zone_names = {}
    known_media_servers = {}
    known_media_renderers = {}
    DP_namespace = 'urn:schemas-upnp-org:service:DeviceProperties:1'
    
    def __init__(self):
        self.controller = Controller()
        self.controller.subscribe("new_device_event", self.on_new_device_controller)
        self.controller.subscribe("removed_device_event", self.on_del_device_controller)
        self.controller.start()
        run_async_function(self.controller.start_search, (600.0, "ssdp:all"), 0.001)

    def on_new_device_controller(self, device_object):
        if device_object.udn in self.known_devices.keys():
            return False
        self.known_devices[device_object.udn] = device_object
        print ">>>> found device: " + str(device_object.friendly_name) + " at " + str(device_object.address) + "  udn: " + str(device_object.udn)
        device_list = []
        if device_object.devices:
            root_device = device_object
            device_list.append(root_device)
            device_list.extend(device_object.devices.values())
        else:
            device_list.append(device_object)
        for device_item in device_list:
            t = device_item.device_type
            if 'ZonePlayer' in t:
                # only process for Zoneplayers, not Dock etc
                # - assume player if it has embedded devices
                self.known_zone_players[device_object.udn] = device_object
                self.zoneattributes[device_object.udn] = self.controller.get_zone_attributes(device_object)
                self.known_zone_names[device_object.udn] = self.zoneattributes[device_object.udn]['CurrentZoneName']
                if device_object.devices:
                    print "    >>>> found zoneplayer - %s" % self.zoneattributes[device_object.udn]['CurrentZoneName']
                else:
                    print "    >>>> found sonos component - %s" % self.zoneattributes[device_object.udn]['CurrentZoneName']
            elif 'MediaServer' in t:
#                if device_object.udn in self.known_media_servers.keys():
#                    return False
                self.known_media_servers[device_object.udn] = device_object
                print "        >>>> found mediaserver - %s" % str(device_object.friendly_name)
            elif 'MediaRenderer' in t:
#                if device_object.udn in self.known_media_renderers.keys():
#                    return False
                self.known_media_renderers[device_object.udn] = device_object
                print "        >>>> found mediarenderer - %s" % str(device_object.friendly_name)

    def on_del_device_controller(self, udn):
        if udn in self.known_media_servers:
            del self.known_media_servers[udn]
        if udn in self.known_media_renderers:
            del self.known_media_renderers[udn]
        if udn in self.known_zone_players:
            del self.known_zone_players[udn]
            del self.known_zone_names[udn]

def main():
    web = ShowDevices()
    reactor.main()
    reactor.main_quit()
    filename = 'devices.txt'
    with open(filename, 'w+') as f:
        for udn,v in sdDeviceAssembler.devicexml.iteritems():
            if udn in web.known_zone_players.keys():
                friendly, xml = v
                f.write('#### Device ####\n%s\n%s\n%s\n\n' % (udn, friendly, xml))
                if udn in sdDeviceAssembler.servicexml.keys():
                    f.write('#### Services ####\n%s\n\n' % (sdDeviceAssembler.servicexml[udn]))
    
if __name__ == "__main__":
    main()