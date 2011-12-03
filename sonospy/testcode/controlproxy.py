#
# proxy
#
# Copyright (c) 2009 Mark Henkelis
# Portions Copyright Brisa Team <brisa-develop@garage.maemo.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author: Mark Henkelis <mark.henkelis@tesco.net>

import os
import re
import ConfigParser


from brisa.core import webserver

from brisa.upnp.device import Device
from brisa.upnp.device.service import Service
from brisa.upnp.device.service import StateVariable
from brisa.upnp.soap import HTTPProxy, HTTPRedirect
from brisa.core.network import parse_url, get_ip_address

class ControlProxy(object):
    
    def __init__(self, proxyname, proxytype, proxytrans, udn, controlpoint, mediaserver, config):
        self.root_device = None
        self.upnp_urn = 'urn:schemas-upnp-org:device:MediaServer:1'
        self.proxyname = proxyname
        self.proxytype = proxytype
        self.proxytrans = proxytrans
        self.udn = udn
        self.controlpoint = controlpoint
        self.mediaserver = mediaserver
        self.destmusicaddress = None
        self.config = config

    def _add_root_device(self):
        """ Creates the root device object which will represent the device
        description.
        """
        project_page = 'http://brisa.garage.maemo.org'
#        ip = get_ip_address('')
        ip, port = self.controlpoint._event_listener.host()
        if self.proxytype == 'WMP':
            listen_url = "http://" + ip + ':10243'
            model_name='Windows Media Player Sharing'
        else:
            listen_url = ''
            model_name='Rhapsody'
        
        self.root_device = Device(self.upnp_urn,
                                  self.proxyname,
                                  udn=self.udn,
                                  manufacturer='Henkelis',
                                  manufacturer_url=project_page,
                                  model_description='Media Server',
                                  model_name=model_name,
                                  model_number='3.0',
                                  model_url=project_page,
                                  udp_listener=self.controlpoint._ssdp_server.udp_listener,
                                  force_listen_url=listen_url)
        self.root_device.webserver.get_render = self.get_render

    def _add_services(self):
        cdservice = ContentDirectory(self.controlpoint, self.mediaserver, self.root_device.location, self)
        self.root_device.add_service(cdservice)
        cmservice = ConnectionManager(self.controlpoint, self.mediaserver)
        self.root_device.add_service(cmservice)
        mrservice = X_MS_MediaReceiverRegistrar()
        self.root_device.add_service(mrservice)

    def _add_resources(self):
        pass

    def _load(self):
        self._add_root_device()
        self._add_services()
        self._add_resources()

    def start(self):
        self.stop()
        self._load()
        self.root_device.start()

    def stop(self):
        if self.root_device:
            self.root_device.stop()
            self.root_device = None

    def get_render(self, uri, params):
        return self

    def render(self, env, start_response):
#        if self.destmusicaddress is not None:
#            address = self.destmusicaddress
#        else:
#            address = self.destaddress
#        respbody = HTTPRedirect().call(address, env, start_response)
        if env['PATH_INFO'] == '/on.mp3':
            print ">>>>>>>>>>>>>>>>>>>>>>"
            print ">>>>>>>>> ON >>>>>>>>>"
            print ">>>>>>>>>>>>>>>>>>>>>>"
        elif env['PATH_INFO'] == '/off.mp3':
            print ">>>>>>>>>>>>>>>>>>>>>>"
            print ">>>>>>>>> OFF >>>>>>>>"
            print ">>>>>>>>>>>>>>>>>>>>>>"

        return []


class ContentDirectory(Service):

    service_name = 'ContentDirectory'
    service_type = 'urn:schemas-upnp-org:service:ContentDirectory:1'
    scpd_xml_path = os.path.join(os.getcwd(), 'content-directory-scpd.xml')

    def __init__(self, controlpoint, mediaserver, proxyaddress, proxy):
        self.controlpoint = controlpoint
        self.mediaserver = mediaserver
#        self.destscheme = mediaserver.scheme
#        self.destip = mediaserver.ip
        self.proxyaddress = proxyaddress
#        self.destmusicaddress = None
        self.proxy = proxy
        self.translate = 0
        self.containers = {}
        self.container_mappings = {}
        self.attribute_mappings = {}        
        
        Service.__init__(self, self.service_name, self.service_type, url_base='', scpd_xml_filepath=self.scpd_xml_path)

    def soap_Browse(self, *args, **kwargs):

        res =       '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
        res = res + '<item id="1" restricted="1" parentID="0"><dc:title>On</dc:title><res duration="0:00:01.000" protocolInfo="http-get:*:audio/mpegurl">' + self.proxyaddress + '/on.mp3</res><upnp:class>object.item.audioItem.musicTrack</upnp:class></item>'
        res = res + '<item id="2" restricted="1" parentID="0"><dc:title>Off</dc:title><res duration="0:00:01.000" protocolInfo="http-get:*:audio/mpegurl">' + self.proxyaddress + '/off.mp3</res><upnp:class>object.item.audioItem.musicTrack</upnp:class></item>'
        res = res + '</DIDL-Lite>'

        result = {'NumberReturned': '2', 'UpdateID': '1', 'Result': res, 'TotalMatches': '2'}
        
        return result

    def soap_Search(self, *args, **kwargs):

        res =       '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
        res = res + '<item id="1" restricted="1" parentID="0"><dc:title>On</dc:title><res duration="0:00:01.000" protocolInfo="http-get:*:audio/mpeg:*">' + self.proxyaddress + '/on.mp3</res><upnp:class>object.item.audioItem.musicTrack</upnp:class><upnp:album>OnOff</upnp:album></item>'
        res = res + '<item id="2" restricted="1" parentID="0"><dc:title>Off</dc:title><res duration="0:00:01.000" protocolInfo="http-get:*:audio/mpeg:*">' + self.proxyaddress + '/off.mp3</res><upnp:class>object.item.audioItem.musicTrack</upnp:class><upnp:album>OnOff</upnp:album></item>'
        res = res + '</DIDL-Lite>'

        print "res: " + res

        result = {'NumberReturned': '2', 'UpdateID': '1', 'Result': res, 'TotalMatches': '2'}
        
        return result

    def soap_GetSearchCapabilities(self, *args, **kwargs):
        result = {'SearchCaps': ''}
#        result = self.controlpoint.proxyGetSearchCapabilities(self.mediaserver)
#        print "gsearch result: " + str(result)
        return result
    def soap_GetSortCapabilities(self, *args, **kwargs):
        result = {'SortCaps': ''}
#        result = self.controlpoint.proxyGetSortCapabilities(self.mediaserver)
#        print "gsort result: " + str(result)
        return result
    def soap_GetSystemUpdateID(self, *args, **kwargs):
        result = {'SystemUpdateID': '1'}
#        result = self.controlpoint.proxyGetSystemUpdateID(self.mediaserver)
#        print "gsys result: " + str(result)
        return result


class ConnectionManager(Service):

    service_name = 'ConnectionManager'
    service_type = 'urn:schemas-upnp-org:service:ConnectionManager:1'
    scpd_xml_path = os.path.join(os.getcwd(), 'connection-manager-scpd.xml')

    def __init__(self, controlpoint, mediaserver):
        self.controlpoint = controlpoint
        self.mediaserver = mediaserver
        Service.__init__(self, self.service_name, self.service_type, url_base='', scpd_xml_filepath=self.scpd_xml_path)
    def soap_GetCurrentConnectionInfo(self, *args, **kwargs):
        result = self.controlpoint.proxyGetCurrentConnectionInfo(kwargs['ConnectionID'], self.mediaserver)
        return result
    def soap_GetProtocolInfo(self, *args, **kwargs):
        result = self.controlpoint.proxyGetProtocolInfo(self.mediaserver)
        return result
    def soap_GetCurrentConnectionIDs(self, *args, **kwargs):
        result = self.controlpoint.proxyGetCurrentConnectionIDs(self.mediaserver)
        return result


class X_MS_MediaReceiverRegistrar(Service):

    service_name = 'X_MS_MediaReceiverRegistrar'
    service_type = 'urn:microsoft.com:service:X_MS_MediaReceiverRegistrar:1'
    scpd_xml_path = os.path.join(os.getcwd(), 'media-receiver-registrar-scpd.xml')

    def __init__(self):
        Service.__init__(self, self.service_name, self.service_type, url_base='', scpd_xml_filepath=self.scpd_xml_path)
    def soap_IsAuthorized(self, *args, **kwargs):
#        print "IsAuthorised"
#        for arg in args:
#            print "another arg: " + str(arg)
#        for key in kwargs:
#            print "another keyword arg: " + str(key) + " : " + str(kwargs[key])
        ret = {'Result': '1'}
        return ret
    def soap_IsValidated(self, *args, **kwargs):
#        print "IsValidated"
#        for arg in args:
#            print "another arg: " + str(arg)
#        for key in kwargs:
#            print "another keyword arg: " + str(key) + " : " + str(kwargs[key])
        ret = {'Result': '1'}
        return ret
    def soap_RegisterDevice(self, *args, **kwargs):
#        print "RegisterDevice"
#        for arg in args:
#            print "another arg: " + str(arg)
#        for key in kwargs:
#            print "another keyword arg: " + str(key) + " : " + str(kwargs[key])
        ret = {'RegistrationRespMsg': '1'}
        return ret

def fixcolon(clist):
    cdict = {}
    for n,v in clist:
        if v.find('=') != -1:
            cat = n + ':' + v
            scat = cat.split('=')
            nn = scat[0]
            vv = scat[1] 
            cdict[nn] = vv
        else:
            cdict[n] = v
    return cdict
    
