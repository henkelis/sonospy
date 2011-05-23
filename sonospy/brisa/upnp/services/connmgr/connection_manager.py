# Licensed # Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>
#
# This module implements the Connection Manager service
# type as documented in the ConnectionManager:1 Service Template
# Version 1.01
# It is implemented the features of MediaServer and only the
# required actions
#

""" Connection Manager service implementation

Common usage is to just add a ConnectionManagerServer (or
ConnectionManagerRenderer) class instance to a device.
"""

__all__ = ('ConnectionManagerServer', 'ConnectionManagerRenderer')

import os.path

from brisa.core import log
from brisa.upnp.services.xmls import xml_path
from brisa.upnp.device import Service


service_name = 'ConnectionManager'
service_type = 'urn:schemas-upnp-org:service:ConnectionManager:1'
server_scpd_xml_path = os.path.join(xml_path, 'connection-manager-scpd.xml')
renderer_scpd_xml_path = os.path.join(xml_path, 'render-connmgr-scpd.xml')


class ConnectionManagerServer(Service):

    def __init__(self):
        Service.__init__(self, service_name, service_type, '',
                         server_scpd_xml_path)

    def soap_GetProtocolInfo(self, *args, **kwargs):
        """Required: Returns the protocol-related info that this \
           ConnectionManager supports in its current state
        """
        log.debug('Action on ConnectionManager: GetProtocolInfo()')
        return {'Source': 'http-get:*:*:*',
                'Sink': ''}

    def soap_GetCurrentConnectionIDs(self, *args, **kwargs):
        """Required: Returns a comma-separated list of ConnectionIDs of
        currently ongoing Connections."""
        log.debug('Action on ConnectionManager: GetCurrentConnectionIDs()')
        #If optional action PrepareForConnection is not implemented
        #this state variable should be set to 0.
        return {'ConnectionIDs': '0'}

    def soap_GetCurrentConnectionInfo(self, *args, **kwargs):
        """Required: Returns associated information of the connection
        referred to by the ConnectionID parameter."""

        log.debug('Action on ConnectionManager: GetCurrentConnectionInfo()')
        #connection information can be retrieved for ConnectionID 0
        return {'RcsID': '-1',
                'AVTransportID': '-1',
                'ProtocolInfo': '',
                'PeerConnectionManager': '',
                'PeerConnectionID': '-1',
                'Direction': 'Output',
                'Status': 'OK'}


class ConnectionManagerRenderer(Service):

    def __init__(self):
        Service.__init__(self, service_name, service_type, '',
                         renderer_scpd_xml_path)

    def soap_GetProtocolInfo(self, *args, **kwargs):
        """Required: Returns the protocol-related info that this
        ConnectionManager supports in its current state - Specific
        for MediaRenderer Devices"""

        log.debug('Action on ConnectionManager: GetProtocolInfo()')
        return {'Source': '', 'Sink':
                'http-get:*:audio/mpeg:*'}

    def soap_GetCurrentConnectionInfo(self, *args, **kwargs):
        """Required: Returns associated information of the connection
        referred to by the ConnectionID parameter."""

        log.debug('Action on ConnectionManager: GetCurrentConnectionInfo()')
        #connection information can be retrieved for ConnectionID 0
        return {'RcsID': '0',
                'AVTransportID': '0',
                'ProtocolInfo': '',
                'PeerConnectionManager': '',
                'PeerConnectionID': '-1',
                'Direction': 'Input',
                'Status': 'OK'}

    def soap_GetCurrentConnectionIDs(self, *args, **kwargs):
        """Required: Returns a comma-separated list of ConnectionIDs of
        currently ongoing Connections."""

        log.debug('Action on ConnectionManager: GetCurrentConnectionIDs()')
        #If optional action PrepareForConnection is not implemented
        #this state variable should be set to 0.
        return {'ConnectionIDs': '0'}
