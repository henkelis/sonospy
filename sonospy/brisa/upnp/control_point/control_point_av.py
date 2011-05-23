# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Extends the base control point and adds basic Audio/Video functionality.
"""

from brisa.core import log
from brisa.core.network import parse_url
from brisa.upnp.control_point.control_point import ControlPoint
from brisa.upnp.control_point.device import Device
from brisa.upnp.didl.didl_lite import Element


log = log.getLogger('control-point.control-point-av')


class ControlPointAV(ControlPoint):
    """ This class extends ControlPoint and add basic AV functionality.

    Basic usage is to set a server and/or renderer device with
    set_current_server() and/or set_current_renderer() to work on, then use
    the available A/V methods which are listed below.

    Media servers:
        - browse()         - performs browse
        - search()         - performs search
        - get_search_capabilities() - returns the search capabilities
        - get_sort_capabilities()   - returns the sort capabilities

    Media renderer:
        - av_play(id, uri) - plays an item from a media server on a media
                             renderer. Must receive the item id on the media
                             server or the URL where it is available.
        - av_stop()        - stop playing
        - av_pause()       - pause
        - av_next()        - play next track
        - av_previous()    - play previous track
    """

    CDS_namespace = 'urn:schemas-upnp-org:service:ContentDirectory:1'
    AVT_namespace = 'urn:schemas-upnp-org:service:AVTransport:1'
    DMS_type = 'urn:schemas-upnp-org:device:MediaServer:'
    DMR_type = 'urn:schemas-upnp-org:device:MediaRenderer:'
    msg_invalid_server = 'server_device parameter must be a Device'
    msg_invalid_renderer = 'renderer_device parameter must be a Device'
    msg_select_server = 'media server not set. Set it with '\
                        'set_current_server().'
    msg_select_renderer = 'media renderer not set. Set it with '\
                          'set_current_renderer().'

    def __init__(self, port, receive_notify=True):
        """ Constructor for the ControlPointAV class.

        @param receive_notify: if False, disables notify handling. This means
                               it will only listen for MSearch responses.
        @type receive_notify: bool
        """
        ControlPoint.__init__(self, port, receive_notify)
        self._current_server = None
        self._current_renderer = None

    def get_current_server(self):
        """ Returns the current selected server.
        """
        return self._current_server

    def set_current_server(self, server_device):
        """ Sets the current server. Required before performing any action on
        the Content Directory service.

        @param server_device: server
        @type server_device: Device
        """
        assert isinstance(server_device, Device), self.msg_invalid_server
        self._current_server = server_device

    def get_current_renderer(self):
        """ Returns the current selected renderer.
        """
        return self._current_renderer

    def set_current_renderer(self, renderer_device):
        """ Sets the current renderer. Required before performing any action
        on the AV Transport service.

        @param renderer_device: renderer
        @type renderer_device: Device
        """
        assert isinstance(renderer_device, Device), self.msg_invalid_renderer
        self._current_renderer = renderer_device

    def get_cd_service(self):
        """ Returns the Content Directory service from the selected server.
        """
        if not self._current_server:
            raise RuntimeError(self.msg_select_server)
        return self._current_server.get_service_by_type(self.CDS_namespace)

    def get_avt_service(self):
        """ Returns the AV Transport service from the selected renderer.
        """
        if not self._current_renderer:
            raise RuntimeError(self.msg_select_renderer)
        return self._current_renderer.get_service_by_type(self.AVT_namespace)

    def browse(self, object_id, browse_flag, filter, starting_index,
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
        service = self.get_cd_service()
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

    def search(self, container_id, search_criteria, filter, starting_index,
               requested_count, sort_criteria):
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
        service = self.get_cd_service()
        search_response = service.Search(ContainerID=container_id,
                                         SearchCriteria=search_criteria,
                                         Filter=filter,
                                         StartingIndex=starting_index,
                                         RequestedCount=requested_count,
                                         SortCriteria=sort_criteria)
        elt = Element.from_string(search_response['Result'])
        return elt.get_items()

    def get_search_capabilities(self):
        """ Return the fields supported by the server for searching.

        @rtype: dict
        """
        return self.get_cd_service().GetSearchCapabilities()

    def get_sort_capabilities(self):
        """ Returns a list of fields supported by the server for sorting.

        @rtype: dict
        """
        return self.get_cd_service().GetSortCapabilities()

    def av_play(self, id=0, uri=''):
        """ Tells the selected media renderer to play an item given its id or
        media URI.

        @param id: id of the media on the media server
        @param uri: URI where the media is available

        @type id: string
        @type uri: string
        """
        if not uri:
            item = self.browse(id, 'BrowseMetadata', '*', 0, 1, '')
            uri = item['Result'][0].resources[0].value
        avt = self.get_avt_service()
        avt.SetAVTransportURI(InstanceID=0,
                              CurrentURI=uri,
                              CurrentURIMetaData='')
        avt.Play()

    def av_stop(self):
        """ Stops the rendering.
        """
        avt = self.get_avt_service()
        avt.Stop()

    def av_pause(self):
        """ Pauses the rendering.
        """
        avt = self.get_avt_service()
        avt.Pause()

    def av_next(self):
        """ Requests play on the next track.
        """
        avt = self.get_avt_service()
        avt.Next()

    def av_previous(self):
        """ Requests play on the previous track.
        """
        avt = self.get_avt_service()
        avt.Previous()
