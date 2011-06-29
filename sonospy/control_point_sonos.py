#
# pycpoint
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


""" Extends the base control point and adds basic Audio/Video functionality.
"""
#import log
from brisa.core import log

from brisa.upnp.control_point import ControlPoint, ControlPointAV
#from brisa.upnp.didl.didl_lite import Element, ElementItem, find
from brisa.upnp.didl.didl_lite import *
#from brisa.upnp.soap import SOAPProxy
#from brisa.core.network import parse_url
#from brisa.utils import properties
from brisa.upnp.control_point.device import Device
from brisa.upnp.control_point.service import Service
from sonos_service import AvailableServices

from brisa.core.network import url_fetch, parse_url
from xml.etree.ElementTree import ElementTree

from napstersonos import napster

#transportStates = [ 'STOPPED', 'PLAYING', 'TRANSITIONING', 'PAUSED_PLAYBACK', 'PAUSED_RECORDING', 'RECORDING', 'NO_MEDIA_PRESENT' ]

class ControlPointSonos(ControlPointAV):
    """
    """
    # services

    # MR
    AT_namespace = 'urn:schemas-upnp-org:service:AVTransport:1'
    MR_CM_namespace = 'urn:schemas-upnp-org:service:ConnectionManager:1'
    RC_namespace = 'urn:schemas-upnp-org:service:RenderingControl:1'
    # MS
    CD_namespace = 'urn:schemas-upnp-org:service:ContentDirectory:1'
    MS_CM_namespace = 'urn:schemas-upnp-org:service:ConnectionManager:1'
    MRR_namespace = 'urn:microsoft.com:service:X_MS_MediaReceiverRegistrar:1'

    # ZP
    GM_namespace = 'urn:schemas-upnp-org:service:GroupManagement:1'
    MS_namespace = 'urn:schemas-upnp-org:service:MusicServices:1'
    DP_namespace = 'urn:schemas-upnp-org:service:DeviceProperties:1'
    AI_namespace = 'urn:schemas-upnp-org:service:AudioIn:1'
    SP_namespace = 'urn:schemas-upnp-org:service:SystemProperties:1'
    ZT_namespace = 'urn:schemas-upnp-org:service:ZoneGroupTopology:1'
    AC_namespace = 'urn:schemas-upnp-org:service:AlarmClock:1'
    RT_namespace = 'http://www.sonos.com/Services/1.1'

    DZP_type = 'urn:schemas-upnp-org:device:ZonePlayer:'

    msg_invalid_zoneplayer = 'zoneplayer_device parameter must be a Device'
    msg_select_zoneplayer = 'zoneplayer not set. Set it with set_current_zoneplayer().'

    tpms_service = {}

    def __init__(self, port, receive_notify=True):
        """
        """
        ControlPointAV.__init__(self, port, receive_notify)
        self._current_zoneplayer = None

    def get_current_zoneplayer(self):
        """ Returns the current selected zoneplayer.
        """
        return self._current_zoneplayer

    def set_current_zoneplayer(self, zoneplayer_device):
        """ Sets the current zoneplayer.
        """
        assert isinstance(zoneplayer_device, Device), self.msg_invalid_zoneplayer
        self._current_zoneplayer = zoneplayer_device
        
    # zp media renderer services

    def get_at_service(self, device=None):
        """ Returns the AV Transport service from the selected renderer.
        """
        if device:
            pass
        else:
            if not self._current_renderer:
                raise RuntimeError(self.msg_select_renderer)
            else:
                device = self._current_renderer
        return device.get_service_by_type(self.AT_namespace)

    def get_mr_cm_service(self, device=None):
        """ Returns the Connection Manager service from the selected renderer.
        """
        if device:
            pass
        else:
            if not self._current_renderer:
                raise RuntimeError(self.msg_select_renderer)
            else:
                device = self._current_renderer
        return device.get_service_by_type(self.MR_CM_namespace)

    def get_rc_service(self, device=None):
        """ Returns the Rendering Control service from the selected renderer.
        """
        if device:
            pass
        else:
            if not self._current_renderer:
                raise RuntimeError(self.msg_select_renderer)
            else:
                device = self._current_renderer
        return device.get_service_by_type(self.RC_namespace)

    # zp media server services

    def get_cd_service(self, device=None):
        """ Returns the Content Directory service from the selected server.
        """
        if device:
            pass
        else:
            if not self._current_server:
                raise RuntimeError(self.msg_select_server)
            else:
                device = self._current_server
        return device.get_service_by_type(self.CD_namespace)

    def get_ms_cm_service(self, device=None):
        """ Returns the Connection Manager service from the selected server.
        """
        if device:
            pass
        else:
            if not self._current_server:
                raise RuntimeError(self.msg_select_server)
            else:
                device = self._current_server
        return device.get_service_by_type(self.MS_CM_namespace)

    def get_mrr_service(self, device=None):
        """ Returns the Media Receiver Registrar service from the selected server.
        """
        if device:
            pass
        else:
            if not self._current_server:
                raise RuntimeError(self.msg_select_server)
            else:
                device = self._current_server
        return device.get_service_by_type(self.MRR_namespace)

    # zp services

    def get_gm_service(self, device=None):
        """ Returns the Group Management service from the selected zoneplayer.
        """
        if device:
            pass
        else:
            if not self._current_zoneplayer:
                raise RuntimeError(self.msg_select_zoneplayer)
            else:
                device = self._current_zoneplayer
        return device.get_service_by_type(self.GM_namespace)

    def get_ms_service(self, device=None):
        """ Returns the Music Services service from the selected zoneplayer.
        """
        if device:
            pass
        else:
            if not self._current_zoneplayer:
                raise RuntimeError(self.msg_select_zoneplayer)
            else:
                device = self._current_zoneplayer
        return device.get_service_by_type(self.MS_namespace)

    def get_dp_service(self, device=None):
        """ Returns the Device Properties service from the selected zoneplayer.
        """
        if device:
            pass
        else:
            if not self._current_zoneplayer:
                raise RuntimeError(self.msg_select_zoneplayer)
            else:
                device = self._current_zoneplayer
        return device.get_service_by_type(self.DP_namespace)

    def get_ai_service(self, device=None):
        """ Returns the Audio In service from the selected zoneplayer.
        """
        if device:
            pass
        else:
            if not self._current_zoneplayer:
                raise RuntimeError(self.msg_select_zoneplayer)
            else:
                device = self._current_zoneplayer
        return device.get_service_by_type(self.AI_namespace)

    def get_sp_service(self, device=None):
        """ Returns the System Properties service from the selected zoneplayer.
        """
        if device:
            pass
        else:
            if not self._current_zoneplayer:
                raise RuntimeError(self.msg_select_zoneplayer)
            else:
                device = self._current_zoneplayer
        return device.get_service_by_type(self.SP_namespace)

    def get_zt_service(self, device=None):
        """ Returns the Zone Group Topology service from the selected zoneplayer.
        """
        if device:
            pass
        else:
            if not self._current_zoneplayer:
                raise RuntimeError(self.msg_select_zoneplayer)
            else:
                device = self._current_zoneplayer
        return device.get_service_by_type(self.ZT_namespace)

    def get_ac_service(self, device=None):
        """ Returns the Alarm Clock service from the selected zoneplayer.
        """
        if device:
            pass
        else:
            if not self._current_zoneplayer:
                raise RuntimeError(self.msg_select_zoneplayer)
            else:
                device = self._current_zoneplayer
        return device.get_service_by_type(self.AC_namespace)

    def get_rt_service(self, device=None):
        """ Returns the Radiotime service from the selected zoneplayer.
        """
        if device:
            pass
        else:
            if not self._current_zoneplayer:
                raise RuntimeError(self.msg_select_zoneplayer)
            else:
                device = self._current_zoneplayer
#        return device.get_service_by_type(self.RT_namespace)
        # TODO: we only hold a single Radiotime service atm, need to expand that to (potentially) one per server
        return self.rt_service

    def get_np_service(self, device=None):
        """ Returns the Napster service from the selected zoneplayer.
        """
        if device:
            pass
        else:
            if not self._current_zoneplayer:
                raise RuntimeError(self.msg_select_zoneplayer)
            else:
                device = self._current_zoneplayer
        # TODO: we only hold a single Napster service atm
        return self.np_service

    def get_tpms_service(self, name, device=None):
        """ Returns the Third Party Media Server service from the selected zoneplayer.
        """
        if device:
            pass
        else:
            if not self._current_zoneplayer:
                raise RuntimeError(self.msg_select_zoneplayer)
            else:
                device = self._current_zoneplayer
#        return device.get_service_by_type(self.RT_namespace)
        # TODO: we only hold a single Third Party Media Server service atm, need to expand that to (potentially) one per server
        return self.tpms_service[name]


    def get_zone_attributes(self, device):
        """
        """
        return self.get_dp_service(device).GetZoneAttributes()

    def register_with_registrar(self, device):
        """
        """
        # incompete
        service = self.get_mrr_service(device)
        authorised = service.IsAuthorized(DeviceID="")
        register = service.RegisterDevice('')
        return

    def make_third_party_mediaserver_service(self, mediaserver):
        """
        Mmanually create Sonos Third Party Media Server service
        """
        '''
        mediaserver['CURL'] = "http://192.168.0.10:56043/ContentDirectory/50565062-8a5b-7f33-c3de-168e9401eaee/control.xml" 
        mediaserver['EURL'] = "http://192.168.0.10:56043/ContentDirectory/50565062-8a5b-7f33-c3de-168e9401eaee/event.xml" 
        mediaserver['T'] = "1" 
        mediaserver['EXT'] = ""
        mediaserver['Name'] = "Sonos: Asset UPnP: HENKELIS" 
        mediaserver['UDN'] = "50565062-8a5b-7f33-c3de-168e9401eaee" 
        mediaserver['Location'] = "http://192.168.0.10:56043/DeviceDescription.xml"
        '''
        
        # For Third Party Media Servers in Sonos, the event and control urls are absolute and may be at different ip's
        # Sonos doesn't provide the Media Server SCPD address - so we get it from the location
        # As the urls can be at different ip's, when we build the service we send absolute ip's and a null base url

        log.debug("make_third_party_mediaserver_service: %s", mediaserver)
        scpd_url = self.getscpdurl(mediaserver['Location'])
        if scpd_url != None:    # Sonos may hold out of date info, especially for proxies
            log.debug("create tpms_service: %s", mediaserver['Name'])
            self.tpms_service[unicode(mediaserver['Name'])] = Service('Browse', 'urn:schemas-upnp-org:service:ContentDirectory:1',  #'http://www.sonos.com/Services/1.1', 
                                                               url_base = '',
                                                               control_url = mediaserver['CURL'],
                                                               event_url = mediaserver['EURL'],
                                                               scpd_url = scpd_url,
                                                               build = True)


    def getscpdurl(self, location):
        '''
        Gets the scpd url from a url specifying the device xml location. If not fetched, return None
        '''
#        print "---> location: " + str(location)
        addr = parse_url(location)
        base_url = '%s://%s' % (addr.scheme, addr.netloc)
#        print "---> base_url: " + str(base_url)
        filecontent = url_fetch(location, silent=True)
        if not filecontent:
            return None
        log.debug("getscpdurl filecontent: %s", filecontent)
        tree = ElementTree(file=filecontent).getroot()
        for device in tree.findall('{urn:schemas-upnp-org:device-1-0}device'):
            for xml_service_element in device.findall('.//{urn:schemas-upnp-org:device-1-0}service'):
                service_type = xml_service_element.findtext('{urn:schemas-upnp-org:device-1-0}serviceType')
                if service_type == 'urn:schemas-upnp-org:service:ContentDirectory:1':
                    scpd_url = xml_service_element.findtext('{urn:schemas-upnp-org:device-1-0}SCPDURL')
                    if not scpd_url.startswith('/'):
                        scpd_url = '/' + scpd_url
                    scpd_url = base_url + scpd_url
                    return scpd_url
        return None        


    def get_music_services(self):
        """
        """
        service = self.get_ms_service()
        service_response = service.ListAvailableServices()

        if 'AvailableServiceDescriptorList' in service_response:
        
            '''
				<Services>
					<Service Capabilities="31" Id="0" MaxMessagingChars="0" Name="Napster" SecureUri="https://api.napster.com/device/soap/v1" Uri="http://api.napster.com/device/soap/v1" Version="1.0">
						<Policy Auth="UserId" PollInterval="30"/>
						<Presentation>
							<Strings Uri="http://update-services.sonos.com/services/napster/string.xml" Version="1"/>
							<Logos Large="http://www.napster.com/services/Sonos/LargeLogo.png" Small="http://www.napster.com/services/Sonos/SmallLogo.png"/>
						</Presentation>
					</Service>
					<Service Capabilities="0" Id="254" MaxMessagingChars="0" Name="RadioTime" SecureUri="http://legato.radiotime.com/Radio.asmx" Uri="http://legato.radiotime.com/Radio.asmx" Version="1.1">
						<Policy Auth="Anonymous" PollInterval="0"/>
						<Presentation/>
					</Service>
					<Service Capabilities="19" Id="2" MaxMessagingChars="0" Name="Deezer" SecureUri="https://moapi.sonos.com/Deezer/SonosAPI.php" Uri="http://moapi.sonos.com/Deezer/SonosAPI.php" Version="1.1">
						<Policy Auth="UserId" PollInterval="60"/>
						<Presentation/>
					</Service>
				</Services>

            '''

            elt = AvailableServices().from_string(service_response['AvailableServiceDescriptorList'])
            service_response['AvailableServiceDescriptorList'] = elt.get_items()

            for item in service_response['AvailableServiceDescriptorList']:
                # manually create Sonos specific add-on services
                
                serviceversion = 'http://www.sonos.com/Services/' + item.Version

                # TODO: fix params so they are fully dynamic
                
                if item.Name == 'RadioTime':
                    addr = parse_url(item.Uri)
                    port = 80 if addr.port == None else addr.port
                    url_base = '%s://%s:%s' % (addr.scheme, addr.hostname, port)
                    self.rt_service = Service('getMetadata', serviceversion, 
                                               url_base=url_base,
                                               control_url=addr.path,
                                               scpd_url='file:///radiotime-scpd.xml',
                                               build=True)
                elif item.Name == 'Napster':
                    self.np_service = napster(item.SecureUri, item.Uri, serviceversion)
            
        return service_response        

    #TODO: remove AVT method


    def browsetpms(self, name, device, object_id, browse_flag, filter, starting_index,
                   requested_count, sort_criteria="dc:title"):
        """ Browses media servers.

        @param object_id: object id
        @param browse_flag: BrowseDirectChildren or BrowseMetadata
        @param filter: a filter to indicate which metadata properties
                       are to be returned. Usually "*".
        @param starting_index: starting index to consider the requested count
        @param requested_count: requested number of entries
        @param sort_criteria: sorting criteria

        @type object_id: string
        @type browse_flag: string
        @type filter: string
        @type starting_index: int
        @type requested_count: int
        @type sort_criteria: string

        @return: a list of containers and items, or a fault
        @rtype: list
        """
        if name:
            service = self.get_tpms_service(name)
        else:
            service = self.get_cd_service(device)
        browse_response = service.Browse(ObjectID=str(object_id),
                                         BrowseFlag=browse_flag,
                                         Filter=filter,
                                         StartingIndex=starting_index,
                                         RequestedCount=requested_count,
                                         SortCriteria=sort_criteria)

        if 'Result' in browse_response:
            elt = Element.from_string(browse_response['Result'])
            browse_response['Result'] = elt.get_items()
        return browse_response


    def searchtpms(self, name, device, container_id, search_criteria, filter, starting_index,
                   requested_count, sort_criteria="dc:title"):
        """ Searches media servers.
        """
        if name:
            service = self.get_tpms_service(name)
        else:
            service = self.get_cd_service(device)
        browse_response = service.Search(ContainerID=container_id,
                                         SearchCriteria=search_criteria,
                                         Filter=filter,
                                         StartingIndex=starting_index,
                                         RequestedCount=requested_count,
                                         SortCriteria=sort_criteria)

        if 'Result' in browse_response:
            elt = Element.from_string(browse_response['Result'])
            browse_response['Result'] = elt.get_items()
        return browse_response






    def browse(self, object_id, browse_flag, filter, starting_index,
               requested_count, sort_criteria="dc:title", device=None):
        """ Browses media servers.
            Replace control_point_av.browse to cater for extra elements
        """
        
        service = self.get_cd_service(device)
        browse_response = service.Browse(ObjectID=str(object_id),
                                         BrowseFlag=browse_flag,
                                         Filter=filter,
                                         StartingIndex=starting_index,
                                         RequestedCount=requested_count,
                                         SortCriteria=sort_criteria)

        if 'Result' in browse_response:

            items = ElementItem().from_string(browse_response['Result'])
            browse_response['Result'] = []
            
            for item in items:
                # get the class of the item
                class_name = find(item, 'upnp', 'class').text

                # for certain classes parse the attributes into a Sonos object to capture the extended elements
                # TODO: decide whether to patch the BRisa classes
                # TODO: this assumes Sonos even when we may be browsing something else - check as we've refined the browse since
                elt = None
                if class_name == 'object.item.audioItem.audioBroadcast':
                    elt = SonosAudioBroadcast()
                elif class_name == 'object.item.audioItem.musicTrack':
                    elt = SonosMusicTrack()
                elif class_name == 'object.item.audioItem.musicTrack.recentShow':
                    elt = SonosMusicTrackShow()
                elif class_name == 'object.item':
                    elt = SonosItem()
                else:
                    try:
                        name = class_name.split('.')[-1]
                        c_name = "%s%s" % (name[0].upper(), name[1:])
                        upnp_class = eval(c_name)
                        elt = upnp_class()
                    except Exception:
                        print 'Unknown upnp class in media server browse: ' + str(class_name)
                        log.debug('Unknown upnp class in media server browse')
                if elt != None:
                    elt.from_element(item)
                    browse_response['Result'].append(elt)
                
        return browse_response


    def simplebrowse(self, object_id, browse_flag, filter, starting_index,
               requested_count, sort_criteria="dc:title", device=None):
        service = self.get_cd_service(device)
        browse_response = service.Browse(ObjectID=str(object_id),
                                         BrowseFlag=browse_flag,
                                         Filter=filter,
                                         StartingIndex=starting_index,
                                         RequestedCount=requested_count,
                                         SortCriteria=sort_criteria)

        return browse_response


    def proxyBrowse(self, object_id, browse_flag, filter, starting_index,
                    requested_count, sort_criteria="dc:title", device=None):
        """ Browses media servers.
            For proxy, just pass XML result back
        """
        service = self.get_cd_service(device)
        browse_response = service.Browse(ObjectID=str(object_id),
                                         BrowseFlag=browse_flag,
                                         Filter=filter,
                                         StartingIndex=starting_index,
                                         RequestedCount=requested_count,
                                         SortCriteria=sort_criteria)
                
        return browse_response


    def search(self, container_id, search_criteria, filter, starting_index,
               requested_count, sort_criteria, device=None):
        """ Search items in Media Server.

        This method search items with search_criteria key in the container_id
        of current media server.

        @param container_id: unique identifier of the container in which
                             to begin searching.
        @param search_criteria: search criteria
        @param filter: a filter to indicate which metadata properties
                       are to be returned.
        @param starting_index: starting index to consider the requested
                               count
        @param requested_count: requested number of entries under the
                                object specified by container_id
        @param sort_criteria: sorting criteria

        @type container_id: string
        @type search_criteria: string
        @type filter: string
        @type starting_index: int
        @type requested_count: int
        @type sort_criteria: string

        @return: search result
        @rtype: dict
        """
        service = self.get_cd_service(device)
        search_response = service.Search(ContainerID=container_id,
                                         SearchCriteria=search_criteria,
                                         Filter=filter,
                                         StartingIndex=starting_index,
                                         RequestedCount=requested_count,
                                         SortCriteria=sort_criteria)
#        elt = Element.from_string(search_response['Result'])
#        return elt.get_items()
        if 'Result' in search_response:

            items = ElementItem().from_string(search_response['Result'])
            search_response['Result'] = []
            
            for item in items:
                # get the class of the item
                class_name = find(item, 'upnp', 'class').text

                # for certain classes parse the attributes into a Sonos object to capture the extended elements
                # TODO: decide whether to patch the BRisa classes
                elt = None
                if class_name == 'object.item.audioItem.audioBroadcast':
                    elt = SonosAudioBroadcast()
                elif class_name == 'object.item.audioItem.musicTrack':
                    elt = SonosMusicTrack()
                elif class_name == 'object.item.audioItem.musicTrack.recentShow':
                    elt = SonosMusicTrackShow()
                elif class_name == 'object.item':
                    elt = SonosItem()
                else:
                    try:
                        name = class_name.split('.')[-1]
                        class_name = "%s%s" % (name[0].upper(), name[1:])
                        upnp_class = eval(class_name)
                        elt = upnp_class()
                    except Exception:
                        log.debug('Unknown upnp class in media server search')
                if elt != None:
                    elt.from_element(item)
                    search_response['Result'].append(elt)
                
        return search_response


    def proxySearch(self, container_id, search_criteria, filter, starting_index,
               requested_count, sort_criteria, device=None):
        """ Search items in Media Server.

            For proxy, just pass XML result back
        """
        service = self.get_cd_service(device)
        search_response = service.Search(ContainerID=str(container_id),
                                         SearchCriteria=search_criteria,
                                         Filter=filter,
                                         StartingIndex=starting_index,
                                         RequestedCount=requested_count,
                                         SortCriteria=sort_criteria)
        return search_response









    def proxyGetCurrentConnectionInfo(self, connection_id, device=None):
        service = self.get_ms_cm_service(device)
        response = service.GetCurrentConnectionInfo(ConnectionID=connection_id)
        return response
    def proxyGetProtocolInfo(self, device=None):
        service = self.get_ms_cm_service(device)
        response = service.GetProtocolInfo()
        return response
    def proxyGetCurrentConnectionIDs(self, device=None):
        service = self.get_ms_cm_service(device)
        response = service.GetCurrentConnectionIDs()
        return response

    def proxyGetSearchCapabilities(self, device=None):
        service = self.get_cd_service(device)
        response = service.GetSearchCapabilities()
        return response
    def proxyGetSortCapabilities(self, device=None):
        service = self.get_cd_service(device)
        response = service.GetSortCapabilities()
        return response
    def proxyGetSystemUpdateID(self, device=None):
        service = self.get_cd_service(device)
        response = service.GetSystemUpdateID()
        return response










    def get_position_info(self):
        """Returns the current position info for the current transport.

        This method returns the current position info."""
#        avt = self.get_avt_service()
        avt = self.get_at_service()
        return avt.GetPositionInfo(InstanceID=0)
        
    def get_transport_state(self):
        """Returns the current transport state.

        This method returns the current transport state (only)."""
#        avt = self.get_avt_service()
        avt = self.get_at_service()
        return avt.GetTransportInfo(InstanceID=0)

    def add_uri_to_queue(self, uri, xml, desiredfirsttrack, enqueuenext):

        metadata = self.make_didl(xml)

        avt = self.get_at_service()
        ssresult = avt.AddURIToQueue(InstanceID=0, EnqueuedURI=uri, EnqueuedURIMetaData=metadata, DesiredFirstTrackNumberEnqueued=desiredfirsttrack, EnqueueAsNext=enqueuenext)

        '''
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
        <s:Body>
        <u:AddURIToQueueResponse xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
        <FirstTrackNumberEnqueued>57</FirstTrackNumberEnqueued>
        <NumTracksAdded>1</NumTracksAdded>
        <NewQueueLength>57</NewQueueLength>
        </u:AddURIToQueueResponse>
        </s:Body>
        </s:Envelope>        
        '''
        return ssresult


    def update_object(self, id, currenttagvalue, newtagvalue):

        '''
        <ObjectID>SQ:1</ObjectID>
        <CurrentTagValue>
        <dc:title>Sonos Playlist  Mark</dc:title>
        </CurrentTagValue>
        <NewTagValue>
        <dc:title>Mark</dc:title>
        </NewTagValue>
        '''

        cds = self.get_cd_service()
        ssresult = cds.UpdateObject(ObjectID=id, CurrentTagValue=currenttagvalue, NewTagValue=newtagvalue)

        return ssresult


    def create_object(self, containerid, elements):

        cds = self.get_cd_service()
        ssresult = cds.CreateObject(ContainerID=containerid, Elements=elements)

        return ssresult


    def make_didl(self, xml):
        # HACK: make item in DIDL-Lite if necessary
        if xml.startswith('<DIDL-Lite'):
            metadata = xml
        else:
            metadata = '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">' + xml + '</DIDL-Lite>'
        return metadata

    def set_avtransport_uri(self, uri, xml):

        log.debug('set_avtransport_uri uri: %s', uri)
        log.debug('set_avtransport_uri xml: %s', xml)

        metadata = self.make_didl(xml)
        log.debug('set_avtransport_uri metadata: %s', metadata)

        avt = self.get_at_service()
        avt.SetAVTransportURI(InstanceID=0, CurrentURI=uri, CurrentURIMetaData=metadata)   # does not return result - need to check for HTTP success

    def play(self):
        ssresult = self.get_at_service().Play(InstanceID=0, Speed=1)
        log.debug('play result: %s', ssresult)

    def seek(self, unit, target):
        '''
        <InstanceID>0</InstanceID>
        <Unit>TRACK_NR</Unit>
        <Target>57</Target>
        '''
        ssresult = self.get_at_service().Seek(InstanceID=0, Unit=unit, Target=target)
        log.debug('seek result: %s', ssresult)

    def pause(self):
        ssresult = self.get_at_service().Pause(InstanceID=0)
        log.debug('pause result: %s', ssresult)

    def unpause(self):
        ssresult = self.get_at_service().Play(InstanceID=0, Speed=1)
        log.debug('unpause result: %s', ssresult)

    def stop(self):
        if self._current_renderer:
            ssresult = self.get_at_service().Stop(InstanceID=0)
            log.debug('stop result: %s', ssresult)

    def next(self):
        avt = self.get_at_service()
        avt.Next(InstanceID=0)

    def previous(self):
        avt = self.get_at_service()
        avt.Previous(InstanceID=0)
        
    def get_volume(self):
        rc = self.get_rc_service()
        ssresult = rc.GetVolume(InstanceID=0, Channel='Master')
        current_volume = ssresult['CurrentVolume']
        return current_volume

    def set_volume(self, volume):
        rc = self.get_rc_service()
        rc.SetVolume(InstanceID=0, Channel='Master', DesiredVolume=volume)

    def mute(self, value):
        rc = self.get_rc_service()
        rc.SetMute(InstanceID=0, Channel='Master', DesiredMute=value)

    # End of Media Renderer Methods
