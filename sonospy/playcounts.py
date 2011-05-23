#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# pycpoint
#
# pycpoint and sonospy copyright (c) 2009-2010 Mark Henkelis
# BRisa copyright (c) Brisa Team <brisa-develop@garage.maemo.org> (BRisa is licenced under the MIT License)
# circuits.web copyright (c) 2004-2010 James Mills (Circuits is covered by the MIT license)
# cherrypy copyright (c) 2002-2008, CherryPy Team (team@cherrypy.org) (cherrypy is covered by the BSD license)
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

from brisa.core.reactors import SelectReactor
reactor = SelectReactor()

import sys
import os
##import uuid
import time

import urllib

import ConfigParser

from brisa.core import log
from brisa.core.log import modcheck

import brisa

##import threading
##from threading import Timer


##from brisa.core.network import get_active_ifaces, get_ip_address

from brisa.core import webserver

##import re

from xml.sax.saxutils import escape, unescape

import datetime
    
from brisa.upnp.control_point.service import Service, SubscribeRequest

##from proxy import Proxy

import pprint
pp = pprint.PrettyPrinter(indent=4)

import xml.dom
from xml.dom import minidom
from xml.dom.minidom import parseString

from xml.etree.ElementTree import Element, SubElement, dump

from xml.etree.ElementTree import _ElementInterface
from xml.etree import cElementTree as ElementTree

from control_point_sonos import ControlPointSonos
##from brisa.upnp.didl.didl_lite import *     # TODO: fix this
from brisa.core.network import parse_xml
from brisa.core.network import parse_url, url_fetch
from brisa.core.threaded_call import run_async_function ##, run_async_call

##from brisa.utils.looping_call import LoopingCall

##from music_items import music_item, dump_element, prettyPrint, getAlbumArtURL

##from sonos_service import radiotimeMediaCollection, radiotimeMediaMetadata
from sonos_service import AvailableServices

##from brisa.upnp.soap import HTTPTransport, HTTPError, parse_soap_call, parse_soap_fault

from optparse import OptionParser

from brisa import url_fetch_attempts, url_fetch_attempts_interval, __skip_service_xml__, __skip_soap_service__, __tolerate_service_parse_failure__, __enable_logging__, __enable_webserver_logging__, __enable_offline_mode__, __enable_events_logging__

enc = sys.getfilesystemencoding()

###############################################################################
# ControlPointScrob class
###############################################################################

class ControlPointScrob(object):

    ###########################################################################
    # class vars
    ###########################################################################

    current_renderer_events_avt = {}

    now_playing = ''
    now_extras = ''
    now_playing_dict = {}
    now_extras_dict = {}

    known_zone_players = {}
    known_zone_names = {}
    known_media_servers = {}
    known_media_renderers = {}

    zoneattributes = {}
    musicservices = {}
    mediaservers = {}
    databases = {}
    
    subscriptions = []
    subscription_ids = {}
    at_lookup = {}
    at_subscription_ids = {}
    at_service =  {}
    cd_subscription_ids = {}
    cd_service =  {}
    zt_lookup = {}
    zt_subscription_ids = {}
    zt_service =  {}

    event_queue = []

    zone_groups = {}
    zone_group_coordinators_lookup = {}

    current_track_scrobbled = {}
    current_play_state = {}
    current_position_info = {}
    current_track_duration = {}
    current_track_relative_time_position = {}
    current_track_absolute_time_position = {}
    current_track_URI = {}
    current_track_start = {}
    current_track_metadata = {}
    current_transport_metadata = {}
    
    avt_track_URI = {}

    previous_play_state = {}
    previous_track_URI = {}
    
    zone_grouped = {}

    transport_error = {}

    ###########################################################################
    # command line parser
    ###########################################################################

    usage = "usage: %prog [options] arg"
    parser = OptionParser(usage)
    
    parser.add_option("-m", "--module", action="append", type="string", dest="modcheckmods")
    parser.add_option("-d", "--debug", action="store_true", dest="debug")
    parser.add_option("-v", "--verbose",
                      action="store_true", dest="verbose", default=False,
                      help="print verbose status messages to stdout")
    parser.add_option("-l", "--log",
                      action="store_true", dest="logging", default=False,
                      help="print log messages to stdout")

    (options, args) = parser.parse_args()

    if options.debug:
        modcheck['all'] = True
    if options.modcheckmods:
        for m in options.modcheckmods:
            modcheck[m] = True

    __enable_webserver_logging__ = True
    __enable_events_logging__ = True

    ###########################################################################
    # ini parser
    ###########################################################################

    config = ConfigParser.ConfigParser()
    config.optionxform = str
    config.read('pycpoint.ini')

    # get ports to use
    ws_port = 50103
    try:        
        ws_port = int(config.get('INI', 'playcounts_port'))
    except ConfigParser.NoOptionError:
        pass

    # get playcounts file
    pc_file = 'playcounts.log'
    try:        
        pc_file = int(config.get('INI', 'playcounts_file'))
    except ConfigParser.NoOptionError:
        pass

    # get log file
    log_file = 'playcountslog.log'
    try:        
        log_file = int(config.get('INI', 'playcounts_log_file'))
    except ConfigParser.NoOptionError:
        pass

    # get log file 2
    log_file2 = 'playcountslog2.log'
    try:        
        log_file2 = int(config.get('INI', 'playcounts_log2_file'))
    except ConfigParser.NoOptionError:
        pass

    ###########################################################################
    # __init__
    ###########################################################################

    def __init__(self):

        self.control_point = ControlPointSonos(self.ws_port)
        self.control_point.subscribe("new_device_event", self.on_new_device)
        self.control_point.subscribe("removed_device_event", self.on_del_device)
        self.control_point.subscribe('device_event_seq', self.on_device_event_seq)
        self.control_point.start()

        # start MSEARCH
        run_async_function(self.control_point.start_search, (600.0, "ssdp:all"), 0.001)

    def subscribe_to_device(self, service, udn, servicetype, name):
        try:
            service.event_subscribe(self.control_point.event_host, self._event_subscribe_callback, (udn, servicetype, service, name), True, self._event_renewal_callback)
            self.subscriptions.append((service, udn, servicetype, name))
        except:
            raise Exception("Error occured during subscribe to device")

    def subscribe_for_variable(self, device, service, variable):
        try:
            print variable
            print service.get_state_variable(variable)
            service.subscribe_for_variable(variable, self._event_variable_callback)
        except:
            raise Exception("Error occured during subscribe for variable")

    def _event_variable_callback(self, name, value):
        print "Event message!"
        print 'State variable:', name
        print 'Variable value:', value

#    def renew_device_subscription(self, device, service):
#        try:
#            device.services[service].event_renew(self.control_point.event_host, self._event_renewal_callback, None)
#        except:
#            raise Exception("Error occured during device subscription renewal")

    def _event_subscribe_callback(self, cargo, subscription_id, timeout):
        log.debug('Event subscribe done cargo=%s sid=%s timeout=%s', cargo, subscription_id, timeout)
        udn, servicetype, service, name = cargo
        uuid = udn[5:]
        if servicetype == 'AVTransport':
            self.at_lookup[uuid] = subscription_id
            self.at_subscription_ids[subscription_id] = udn
            self.at_service[subscription_id] = service
            self.current_track_scrobbled[subscription_id] = False
            self.current_play_state[subscription_id] = None
            self.current_position_info[subscription_id] = None
            self.current_track_duration[subscription_id] = None
            self.current_track_relative_time_position[subscription_id] = None
            self.current_track_absolute_time_position[subscription_id] = None
            self.current_track_URI[subscription_id] = None
            self.current_track_start[subscription_id] = None
            self.previous_track_URI[subscription_id] = None
            self.previous_play_state[subscription_id] = None
            self.zone_grouped[subscription_id] = False
            self.current_track_metadata[subscription_id] = None
            self.current_transport_metadata[subscription_id] = None
            self.avt_track_URI[subscription_id] = None
            self.transport_error[subscription_id] = False
            self.zone_groups[subscription_id] = None
            self.zone_group_coordinators_lookup[subscription_id] = None
        if servicetype == 'ContentDirectory':
            self.cd_subscription_ids[subscription_id] = udn
            self.cd_service[subscription_id] = service
        if servicetype == 'ZoneGroupTopology':
            self.zt_lookup[uuid] = subscription_id
            self.zt_subscription_ids[subscription_id] = udn
            self.zt_service[subscription_id] = service
        self.subscription_ids[subscription_id] = '%s, %s' % (servicetype, name)
        self.process_event_queue(subscription_id)

    def _event_renewal_callback(self, cargo, subscription_id, timeout):
# TODO: add error processing for if renewal fails - basically resubscribe. NEW - check if this is catered for in 0.10.0
        log.debug('Event renew done cargo=%s sid=%s timeout=%s', cargo, subscription_id, timeout)

    def _event_unsubscribe_callback(self, cargo, subscription_id):
        if self.options.verbose:
            out = "cancelled subscription for service: %s\n" % str(cargo)
            self.write_log(out)
        log.debug('Event unsubscribe done cargo=%s sid=%s', cargo, subscription_id)
        
    def unsubscribe_from_device(self, serviceset):
        service, udn, servicetype, name = serviceset
        try:
            service.event_unsubscribe(self.control_point.event_host, self._event_unsubscribe_callback, serviceset)
        except:
            raise Exception("Error occured during unsubscribe from device")

    def cancel_subscriptions(self):
        log.debug("Cancelling subscriptions")
        for serviceset in self.subscriptions:
            log.debug("Service: %s", serviceset)
            self.unsubscribe_from_device(serviceset)

    def get_zone_details(self, device):
        return self.control_point.get_zone_attributes(device)

#    def _renew_subscriptions(self):
#        """ Renew subscriptions
#        """
#        self.renew_device_subscription(self.control_point.current_renderer, self.control_point.avt_s)
#        self.renew_device_subscription(self.control_point.current_renderer, self.control_point.rc_s)

    def on_new_device(self, device_object):
        log.debug('got new device: %s' % str(device_object))
        log.debug('fn: %s' % str(device_object.friendly_name))
        log.debug('loc: %s' % str(device_object.location))
        log.debug('add: %s' % str(device_object.address))
#        print ">>>> new device: " + str(device_object.friendly_name) + " at " + str(device_object.address) + "  udn: " + str(device_object.udn)

        device_list = []
        if device_object.devices:
            root_device = device_object
            root_device.devices = []
            device_list.append(root_device)
            device_list.extend(device_object.devices)
        else:
            device_list.append(device_object)

        for device_item in device_list:
            log.debug('new device: %s' % str(device_item))
            log.debug('new device type: %s' % str(device_item.device_type))
            log.debug('new device udn: %s' % str(device_item.udn))                                    
            log.debug('new device services: %s' % str(device_item.services))
            # assumes root device is processed first so that zone name is known
            newmediaserver = False
            newmediarenderer = False
            t = device_item.device_type
            if 'ZonePlayer' in t:
                self.on_new_zone_player(device_item)
                # now register zoneplayer as server and renderer
#                newmediaserver = self.on_new_media_server(device_item)
                newmediarenderer = self.on_new_media_renderer(device_item)
            log.debug('new device fn: %s' % str(device_item.friendly_name))                                    

    def on_new_zone_player(self, device_object):
        self.known_zone_players[device_object.udn] = device_object
        self.zoneattributes[device_object.udn] = self.get_zone_details(device_object)
        self.musicservices[device_object.udn] = self.get_music_services(device_object)
        log.debug('new zone player - %s' % self.zoneattributes[device_object.udn]['CurrentZoneName'])
        self.known_zone_names[device_object.udn] = self.zoneattributes[device_object.udn]['CurrentZoneName']
        self.subscribe_to_device(self.control_point.get_zt_service(device_object), device_object.udn, "ZoneGroupTopology", self.known_zone_names[device_object.udn])
        self.subscribe_to_device(self.control_point.get_ms_service(device_object), device_object.udn, "MusicServices", self.known_zone_names[device_object.udn])
        self.subscribe_to_device(self.control_point.get_dp_service(device_object), device_object.udn, "DeviceProperties", self.known_zone_names[device_object.udn])
        self.subscribe_to_device(self.control_point.get_sp_service(device_object), device_object.udn, "SystemProperties", self.known_zone_names[device_object.udn])
        self.subscribe_to_device(self.control_point.get_gm_service(device_object), device_object.udn, "GroupManagement", self.known_zone_names[device_object.udn])

    def on_new_media_server(self, device_object):
        if device_object.udn in self.known_media_servers:
#            print '>>>> new server device: duplicate'
            return False
        self.known_media_servers[device_object.udn] = device_object
        # subscribe to events from this device
        self.subscribe_to_device(self.control_point.get_cd_service(device_object), device_object.udn, "ContentDirectory", self.known_zone_names[device_object.udn])
        self.subscribe_to_device(self.control_point.get_ms_cm_service(device_object), device_object.udn, "ServerConnectionManager", self.known_zone_names[device_object.udn])
        return True

    def on_new_media_renderer(self, device_object):
        if device_object.udn in self.known_media_renderers:
#            print '>>>> new renderer device: duplicate'
            return False
        self.known_media_renderers[device_object.udn] = device_object
        # subscribe to events from this device
        self.subscribe_to_device(self.control_point.get_at_service(device_object), device_object.udn, "AVTransport", self.known_zone_names[device_object.udn])
        self.subscribe_to_device(self.control_point.get_rc_service(device_object), device_object.udn, "RendereringControl", self.known_zone_names[device_object.udn])
        self.subscribe_to_device(self.control_point.get_mr_cm_service(device_object), device_object.udn, "RendererConnectionManager", self.known_zone_names[device_object.udn])
        return True

    def on_del_device(self, udn):
        # TODO: unsubscribe from events from deleted device
        if udn in self.known_media_servers:
            del self.known_media_servers[udn]
        if udn in self.known_media_renderers:
            del self.known_media_renderers[udn]
        # do this last so name above can be generated correctly
        # TODO: save name from initial generation
        if udn in self.known_zone_players:
            del self.known_zone_players[udn]
    



    def check_playing(self, sid):
    
        if self.options.verbose:
            out  = "check_playing\n"
            out += "    sid: %s\n" % sid
            out += "    subscription_ids              : %s\n" % self.subscription_ids
            out += "    at_lookup                     : %s\n" % self.at_lookup
            out += "    at_subscription_ids           : %s\n" % self.at_subscription_ids
            out += "    cd_subscription_ids           : %s\n" % self.cd_subscription_ids
            out += "    zt_lookup                     : %s\n" % self.zt_lookup
            out += "    zt_subscription_ids           : %s\n" % self.zt_subscription_ids
            out += "    zone_groups                   : %s\n" % self.zone_groups
            out += "    zone_group_coordinators_lookup: %s\n" % self.zone_group_coordinators_lookup
            out += "    zone_grouped                  : %s\n\n" % self.zone_grouped
            self.write_log(out)
          
        # check whether track was moved to another zone
        if self.current_play_state[sid] == 'STOPPED' and self.avt_track_URI[sid] == '':
            # TODO: check whether we need to check other fields for streaming tracks
            # check for a transport stream error
            if self.transport_error[sid]:
                # transport error - check existing track stats
                ZP = self.zoneattributes[self.at_subscription_ids[sid]]['CurrentZoneName']
                delta = self.getmintime(time.time(), self.current_track_absolute_time_position[sid], self.current_track_start[sid])
                if self.options.logging:
                    out = "%s Transport Error. Old duration: %s, position: %s, delta: %s\n" % (ZP, self.current_track_duration[sid], self.current_track_relative_time_position[sid], delta)
                    self.write_log(out)
                self.check_scrobble(sid, self.current_track_duration[sid], self.current_track_relative_time_position[sid], delta)
            # ignore this notification
            return
            
        # check whether track was passed/grouped from another zone
        passed_track = False
        # TODO: check whether z_g conditional supports both cases
        if self.avt_track_URI[sid].startswith('x-rincon:'):
            # this track was passed from another zone
            # get other zone sid
            uuid = self.avt_track_URI[sid][9:]
            other_sid = self.at_lookup[uuid]
            # set scrobbled flag
            self.current_track_scrobbled[sid] = self.current_track_scrobbled[other_sid]
            passed_track = True

        self.zone_grouped[sid] = self.check_zone_grouped(sid)
        if self.zone_grouped[sid] == True:
            # this zone is grouped with another zone
            # get other zone sid
            coord_sid = self.get_zone_coordinator(sid)
            other_sid = self.at_lookup[coord_sid]
            # set scrobbled flag
            self.current_track_scrobbled[sid] = self.current_track_scrobbled[other_sid]
            passed_track = True

        if self.options.logging:
            ZP = self.zoneattributes[self.at_subscription_ids[sid]]['CurrentZoneName']
            out = "%s play_state: %s\n" % (ZP, self.current_play_state[sid])
            self.write_log(out)
        # get latest position info
        self.current_position_info[sid] = self.get_position_info(sid)
        if self.options.logging:
            out = "%s current_position_info: %s\n" % (ZP, self.current_position_info[sid])
            self.write_log(out)
        # check if track has changed
        if self.current_track_URI[sid] == self.current_position_info[sid]['TrackURI'] or passed_track:
            # same track
            # whatever the play state, set/update position and check scrobble
            self.current_track_duration[sid] = self.current_position_info[sid]['TrackDuration']
            self.current_track_relative_time_position[sid] = self.current_position_info[sid]['RelTime']
            if self.options.logging:
                out = "%s Same track. Duration: %s, position: %s\n" % (ZP, self.current_track_duration[sid], self.current_track_relative_time_position[sid])
                self.write_log(out)
            self.current_track_absolute_time_position[sid] = time.time()
            self.current_track_metadata[sid] = self.current_position_info[sid]['TrackMetaData']
            self.check_scrobble(sid, self.current_track_duration[sid], self.current_track_relative_time_position[sid])
            if passed_track:
                # set track details to details from other zone
                self.current_track_URI[sid] = self.current_track_URI[other_sid]
                self.current_track_start[sid] = self.current_track_start[other_sid]
                self.current_track_metadata[sid] = self.current_track_metadata[other_sid]
                self.previous_track_URI[sid] = self.previous_track_URI[other_sid]
        else:
            # new track - check how long previous track played for (only if it was playing, otherwise it has already been processed)
            if self.previous_play_state[sid] == 'PLAYING':
                delta = self.getmintime(time.time(), self.current_track_absolute_time_position[sid], self.current_track_start[sid])
                if self.options.logging:
                    out = "%s New track. Old duration: %s, position: %s, delta: %s\n" % (ZP, self.current_track_duration[sid], self.current_track_relative_time_position[sid], delta)
                    self.write_log(out)
                self.check_scrobble(sid, self.current_track_duration[sid], self.current_track_relative_time_position[sid], delta)
            # set up for new track
            self.current_track_start[sid] = time.time()
            self.current_track_URI[sid] = self.current_position_info[sid]['TrackURI']
            self.current_track_duration[sid] = self.current_position_info[sid]['TrackDuration']
            self.current_track_relative_time_position[sid] = self.current_position_info[sid]['RelTime']
            if self.options.logging:
                out = "%s New track. Duration: %s, position: %s\n" % (ZP, self.current_track_duration[sid], self.current_track_relative_time_position[sid])
                self.write_log(out)
            self.current_track_absolute_time_position[sid] = time.time()
            self.current_track_metadata[sid] = self.current_position_info[sid]['TrackMetaData']
            self.current_track_scrobbled[sid] = False
            self.check_scrobble(sid, self.current_track_duration[sid], self.current_track_relative_time_position[sid])
        self.previous_play_state[sid] = self.current_play_state[sid]

    def get_position_info(self, sid):
        atservice = self.at_service[sid]
        return atservice.GetPositionInfo(InstanceID=0)

    def getmintime(self, now, t1, t2):
        m = 0
        if t1 != None:
            d1 = now - t1
            m = d1
        if t2 != None:
            d2 = now - t2
            m = d2
        if t1 != None and t2 != None:
            m = min(d1, d2)
        return m

    def check_scrobble(self, sid, duration, position, delta=0):
        if not self.current_track_scrobbled[sid]:
            # check whether we have valid data
            if duration == 'NOT_IMPLEMENTED' or position == 'NOT_IMPLEMENTED':
                return
            # delta = playing time since position was logged
            totalsecs = self.makeseconds(duration)
            if totalsecs == 0:
                # assume this is a radio station
                self.current_track_scrobbled[sid] = True
                self.previous_track_URI[sid] = self.current_track_URI[sid]
                return
            currsecs = self.makeseconds(position) + delta
            percentage = (100 * currsecs)/totalsecs
            if percentage >= 50.0:
                self.scrobble(sid)

    def scrobble(self, sid):
        ZP = self.zoneattributes[self.at_subscription_ids[sid]]['CurrentZoneName']
        trackURI = self.current_track_URI[sid]
        database = ''
        extras = ''
        if '?sid=' in trackURI and '&flags=' in trackURI:
            musicservices = self.musicservices[self.at_subscription_ids[sid]]
            id = trackURI.split('?sid=')[1].split('&flags=')[0]
            service = musicservices[id]
        elif trackURI.startswith('x-file-cifs:'):
            service = 'Sonos Library'
        elif trackURI.startswith('http://') and '.x-udn/' in trackURI:
            mediaservers = self.mediaservers[self.at_subscription_ids[sid]]
            databases = self.databases[self.at_subscription_ids[sid]]
            uuid = trackURI[7:].split('.x-udn/')[0]
            service = mediaservers[uuid]
            database = databases[uuid]
            filename = trackURI.split(os.sep)[-1]
            if filename.startswith(database):
                extras = ',"%s","%s"' % (filename, database)
        elif trackURI.startswith('lfmtrack:http'):
            service = 'last.fm'
            if self.current_transport_metadata[sid] != "":
                extras = ',%s' % self.unwrap_transport_metadata(self.current_transport_metadata[sid])
        else:
            service = "UNKNOWN"

        trackdata = self.unwrap_metadata(self.current_track_metadata[sid])
#        currenttime = time.time()

        scrob_log ='"%s","%s","%s",%s,"%s","%s"%s\n' % (self.current_track_start[sid], ZP, service, trackdata, self.current_track_duration[sid], trackURI, extras)
        scrob_log = scrob_log.encode(enc, 'replace')
        print scrob_log
        self.write_log(scrob_log)
        
        f = open(self.pc_file, 'a')
        f.write(scrob_log)
        f.close()
        self.current_track_scrobbled[sid] = True
        self.previous_track_URI[sid] = self.current_track_URI[sid]

    def write_log(self, out):
        f = open(self.log_file, 'a')
        f.write(out)
        f.close()

    def write_log2(self, out):
        f = open(self.log_file2, 'a')
        f.write(out)
        f.close()

    def unwrap_metadata(self, metadata):
        title = artist = album = ''
        elt = self.from_string(metadata)
        ns = "{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}"
        self.remove_namespace(elt, ns)
        item = elt.find('item')
        if item != None:
            ititle = item.find('{http://purl.org/dc/elements/1.1/}title')
            if ititle != None:
                title = ititle.text
            iartist = item.find('{http://purl.org/dc/elements/1.1/}creator')
            if iartist != None:
                artist = iartist.text
            ialbum = item.find('{urn:schemas-upnp-org:metadata-1-0/upnp/}album')
            if ialbum != None:
                album = ialbum.text
        details = '"%s","%s","%s"' % (title, artist, album)
        return details

    def unwrap_transport_metadata(self, metadata):
        title = ''
        elt = self.from_string(metadata)
        ns = "{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}"
        self.remove_namespace(elt, ns)
        item = elt.find('item')
        if item != None:
            ititle = item.find('{http://purl.org/dc/elements/1.1/}title')
            if ititle != None:
                title = ititle.text
        details = '"%s"' % title
        return details

    def get_music_services(self, device):
        service = self.control_point.get_ms_service(device)
        service_response = service.ListAvailableServices()
        musicservices = {}
        if 'AvailableServiceDescriptorList' in service_response:
            elt = AvailableServices().from_string(service_response['AvailableServiceDescriptorList'])
            service_response['AvailableServiceDescriptorList'] = elt.get_items()
            for item in service_response['AvailableServiceDescriptorList']:
                musicservices[item.Id] = item.Name
        return musicservices    

    def makeseconds(self, time):
        if not ':' in time:
            return 0
        h, m, s = time.split(':')
        return (int(h)*60*60 + int(m)*60 +int(float(s)))

    def process_event(self, event, sid):
        esid, seq, changed_vars = event
        if sid == esid:
            # subscription callback has been called - check for events and process and dequeue
            if self.options.verbose:
                out = "notification dequeued: seq=%s, sid=%s\nchanged_vars=%s\n\n" % (seq, sid, changed_vars)
                self.write_log(out)
            self.on_device_event_seq(sid, seq, changed_vars)
            return None
        return event

    def process_event_queue(self, sid):
        # process any outstanding events for this sid
        self.event_queue = [event for event in self.event_queue if self.process_event(event, sid)]
        time.sleep(0.1)     # just in case - replace with locks on queue
        self.event_queue = [event for event in self.event_queue if self.process_event(event, sid)]
            
    def on_device_event_seq(self, sid, seq, changed_vars):

        if not sid in self.subscription_ids:
            # notification arrived before subscription callback - queue event
            if self.options.verbose:
                out = "notification queued: seq=%s, sid=%s\nchanged_vars=%s\n\n" % (seq, sid, changed_vars)
                self.write_log(out)
            self.event_queue.append((sid, seq, changed_vars))
            return

        if self.options.verbose:
            out = "service, Zone=%s, seq=%s, sid=%s\nchanged_vars=%s\n\n" % (self.subscription_ids[sid], seq, sid, changed_vars)
            self.write_log(out)
        if self.subscription_ids[sid].startswith('ZoneGroupTopology'):
            self.process_zgt(sid, self.subscription_ids[sid][19:], changed_vars)
    
        # check it is a LastChange event
        if 'LastChange' in changed_vars and changed_vars['LastChange'] != None and changed_vars['LastChange'] != 'NOT_IMPLEMENTED'  and changed_vars['LastChange'] != '0':

            if sid in self.at_subscription_ids:

                ZP = self.zoneattributes[self.at_subscription_ids[sid]]['CurrentZoneName']
                
                # event from AVTransport
                # TODO: check if we need to remove the ns, and if it is actually removed anyway
                ns = "{urn:schemas-upnp-org:metadata-1-0/AVT/}"
                elt = self.from_string(changed_vars['LastChange'])
                self.remove_namespace(elt, ns)
                # check if it is initial event message
                if self.current_renderer_events_avt == {}:
                    # save all tags
                    self.process_event_tags_avt(elt, self.current_renderer_events_avt)
                else:
                    # not initial message, update vars
                    tag_list = {}
                    self.process_event_tags_avt(elt, tag_list)
                    # save changed tags                    
                    for key, value in tag_list.iteritems():
                        self.current_renderer_events_avt[key] = value

                self.current_play_state[sid] = self.current_renderer_events_avt['TransportState']
                self.avt_track_URI[sid] = self.current_renderer_events_avt['CurrentTrackURI']
                if self.current_play_state[sid] != 'STOPPED':
                    self.current_transport_metadata[sid] = self.current_renderer_events_avt['{urn:schemas-rinconnetworks-com:metadata-1-0/}EnqueuedTransportURIMetaData']
                if 'TransportErrorDescription' in self.current_renderer_events_avt:
                    self.transport_error[sid] = True
                else:
                    self.transport_error[sid] = False
                self.check_playing(sid)

        elif 'ThirdPartyMediaServers' in changed_vars:

            if sid in self.zt_subscription_ids:

                uuid = sid.split('_sub')[0]
                self.mediaservers[uuid], self.databases[uuid] = self.process_thirdpartymediaservers(changed_vars['ThirdPartyMediaServers'])
 
    def process_event_tags_avt(self, elt, event_list):
        # save values
        InstanceID = elt.find('InstanceID')
        if InstanceID != None:
            event_list['InstanceID'] = InstanceID.get('val')    # not checking this at present, assuming zero
            for child in elt.findall('InstanceID/*'):
                nodename = child.tag
                val = child.get('val')
                event_list[nodename] = val

    def process_thirdpartymediaservers(self, thirdpartymediaservers):
        elt = self.from_string(thirdpartymediaservers)
        mediaservers = {}
        databases = {}
        ms = elt.findall('MediaServer')
        for entry in ms:
            udn = entry.attrib['UDN']
            mediaservers[udn] = entry.attrib['Name']
            location = entry.attrib['Location']
            dbname = ''
            xml = urllib.urlopen(location).read()
            elt = parse_xml(xml)
            if elt != None:
                root = elt.getroot()
                ns = "{urn:schemas-upnp-org:device-1-0}"
                self.remove_namespace(root, ns)
                if root != None:
                    dev = root.find('device')
                    if dev != None:
                        serialNumber = dev.find('serialNumber')
                        if serialNumber != None:
                            dbname = serialNumber.text
            databases[udn] = dbname
        return (mediaservers, databases)

    def from_string(self, aString):
        elt = parse_xml(aString)
        elt = elt.getroot()
        return elt

    def remove_namespace(self, doc, ns):
        """Remove namespace in the passed document in place."""
        nsl = len(ns)
        for elem in doc.getiterator():
            if elem.tag.startswith(ns):
                elem.tag = elem.tag[nsl:]

    def process_zgt(self, sid, node, nodedict):
        if 'ZoneGroupState' in nodedict:
            xml = nodedict['ZoneGroupState']
            elt = parse_xml(xml)
            elt = elt.getroot()
            out = node + ' ZoneGroupTopology\n'
            self.zone_groups[sid] = {}
            self.zone_group_coordinators_lookup[sid] = {}
            for e in elt.findall('ZoneGroup'):
                zg_tag = e.tag
                zg_coord = e.get('Coordinator')
                zone_group_members = []            
                for child in e.findall('ZoneGroupMember'):
                    zgm_tag = child.tag
                    zgm_uuid = child.get('UUID')
                    zgm_zonename = child.get('ZoneName')
                    zone_group_members.append((zgm_uuid, zgm_zonename))
                    if zgm_uuid == zg_coord:
                        zg_coord_name = zgm_zonename
                out += '    ' + 'Coordinator ' + zg_coord_name + '\n'
                zgm = []
                for m in zone_group_members:
                    uuid, name = m
                    out += '        ' + 'Member ' + name + '\n'
                    zgm.append(uuid)
                    self.zone_group_coordinators_lookup[sid][uuid] = zg_coord
                self.zone_groups[sid][zg_coord] = zgm
            out += '\n'
            if self.options.verbose:
                self.write_log2(out)

    def check_zone_grouped(self, sid):
        # get udn of zone
        zudn = self.at_subscription_ids[sid][5:]
        # get sid of zone ZGT
        zsid = self.zt_lookup[zudn]
        zgsid = sid[5:].split('_sub')[0]
        if not zgsid in self.zone_groups[zsid]:
            # sid does not exist as coordinator
            return True
        else:
            return False

    def get_zone_coordinator(self, sid):
        # get udn of zone
        zudn = self.at_subscription_ids[sid][5:]
        # get sid of zone ZGT
        zsid = self.zt_lookup[zudn]
        zgsid = sid[5:].split('_sub')[0]
        return self.zone_group_coordinators_lookup[zsid][zgsid]

    def _main_quit(self):
        print "cancelling subscriptions, please wait..."
        self.cancel_subscriptions()
        print "subscriptions cancelled."
        reactor.main_quit()

def ustr(string):
    # TODO: sort out unicode and UTF-8
    if type(string) is unicode:
        return string
    else:
        return str(string)

class Error(Exception):
    """Base class for exceptions in this module."""
    pass

class UnknownClassError(Error):
    """Exception raised for errors in classes.
    Attributes:
        message -- explanation of the error
    """
    def __init__(self, message):
        self.message = message
    def __str__(self):
        return repr(self.message)

def main(argv=None):
    try:
        web = ControlPointScrob()
        reactor.main()
    except KeyboardInterrupt, e:
        pass
    finally:
        web._main_quit()
        web.control_point.destroy()

if __name__ == "__main__":
    main()
    
