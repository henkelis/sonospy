#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# event
#
# pycpoint and sonospy copyright (c) 2009-2014 Mark Henkelis
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

import brisa
from brisa.core.reactors import SelectReactor
reactor = SelectReactor()
from brisa.core import log
from brisa.core.log import modcheck
from brisa.core import webserver
from brisa.upnp.control_point.service import Service, SubscribeRequest
##from brisa.upnp.didl.didl_lite import *     # TODO: fix this
from brisa.core.network import parse_xml
from brisa.core.network import parse_url, url_fetch
from brisa.core.threaded_call import run_async_function ##, run_async_call
from brisa import url_fetch_attempts, url_fetch_attempts_interval, __skip_service_xml__, __skip_soap_service__, __tolerate_service_parse_failure__, __enable_logging__, __enable_webserver_logging__, __enable_offline_mode__, __enable_events_logging__

import sys
import os
import time
import re
import urllib
import ConfigParser
import xml.dom
from xml.dom import minidom
from xml.dom.minidom import parseString
from xml.sax.saxutils import escape, unescape
import datetime
import pprint
pp = pprint.PrettyPrinter(indent=4)
from xml.etree.ElementTree import Element, SubElement, dump
from xml.etree.ElementTree import _ElementInterface
from xml.etree import cElementTree as ElementTree

from control_point_sonos import ControlPointSonos
from sonos_service import AvailableServices

from optparse import OptionParser


enc = sys.getfilesystemencoding()
ZPlist = []

###############################################################################
# ControlPointEvent class
###############################################################################

class ControlPointEvent(object):

    ###########################################################################
    # class vars
    ###########################################################################

    current_renderer_events_rc = {}
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
    rc_subscription_ids = {}
    rc_service =  {}
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

    current_renderer_output_fixed = {}
    current_volume = {}
    volume_fixed = {}
    volume_mute = {}
    
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
        ws_port = int(config.get('INI', 'events_port'))
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
#            print variable
#            print service.get_state_variable(variable)
            service.subscribe_for_variable(variable, self._event_variable_callback)
        except:
            raise Exception("Error occured during subscribe for variable")
        
    def _event_variable_callback(self, name, value):
#        print "Event message!"
#        print 'State variable:', name
#        print 'Variable value:', value
        pass

#    def renew_device_subscription(self, device, service):
#        try:
#            device.services[service].event_renew(self.control_point.event_host, self._event_renewal_callback, None)
#        except:
#            raise Exception("Error occured during device subscription renewal")

    def _event_subscribe_callback(self, cargo, subscription_id, timeout):
        log.debug('Event subscribe done cargo=%s sid=%s timeout=%s', cargo, subscription_id, timeout)
        udn, servicetype, service, name = cargo
        uuid = udn[5:]
        if servicetype == 'RendereringControl':
            self.rc_subscription_ids[subscription_id] = udn
            self.rc_service[subscription_id] = service
            self.current_renderer_output_fixed[subscription_id] = None
            self.current_volume[subscription_id] = None
            self.volume_fixed[subscription_id] = None
            self.volume_mute[subscription_id] = None
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
#            root_device.devices = []
            device_list.append(root_device)
            device_list.extend(device_object.devices.values())
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
                # only process for Zoneplayers, not Dock etc
                # - assume player if it has embedded devices
                if device_object.devices:
                    self.on_new_zone_player(device_item)
                    newmediarenderer = self.on_new_media_renderer(device_item)
                else:
                    pass
                
            log.debug('new device fn: %s' % str(device_item.friendly_name))                                    

    def on_new_zone_player(self, device_object):
        self.known_zone_players[device_object.udn] = device_object
        self.zoneattributes[device_object.udn] = self.get_zone_details(device_object)
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
        volMon = False
        
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
    

        # check it is a LastChange event
        zpSid = sid.split('_')
        
        if 'LastChange' in changed_vars and changed_vars['LastChange'] != None and changed_vars['LastChange'] != 'NOT_IMPLEMENTED' and changed_vars['LastChange'] != '0':
            if zpSid[1] in sid:
                volMon = True
                
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
                
            if sid in self.rc_subscription_ids:
                # DEBUG - turn me back on to monitor an event
#                print "rc LastChange: " + changed_vars['LastChange']
                '''
rc: <Event xmlns="urn:schemas-upnp-org:metadata-1-0/RCS/">
<InstanceID val="0">
<Volume channel="Master" val="39"/>
<Volume channel="LF" val="100"/>
<Volume channel="RF" val="100"/>
<Mute channel="Master" val="0"/>
<Mute channel="LF" val="0"/>
<Mute channel="RF" val="0"/>
<Bass val="0"/>
<Treble val="0"/>
<Loudness channel="Master" val="1"/>
<OutputFixed val="0"/>
<HeadphoneConnected val="0"/>
<SpeakerSize val="3"/>
<SubGain val="0"/>
<SubCrossover val="0"/>
<SubPolarity val="0"/>
<SubEnabled val="1"/>
<SonarEnabled val="0"/>
<SonarCalibrationAvailable val="0"/>
<PresetNameList val="FactoryDefaults"/>
</InstanceID></Event>
                '''

                ZP = self.zoneattributes[self.rc_subscription_ids[sid]]['CurrentZoneName']
                if ZP not in ZPlist:
                    # write zones to GUIpref so we can add widgets for them
                    ZPlist.append(str(ZP))
                    config = ConfigParser.ConfigParser()
                    config.optionxform = str
                    config.read('gui/GUIpref.ini')       
                    if config.has_section("volume") == False:
                        config.add_section("volume")
                    config.set("volume", "zonelist", ZPlist)
                    with open('gui/GUIpref.ini', 'wb') as configfile:
                        config.write(configfile)                    
                # event from RenderingControl
                ns = "{urn:schemas-upnp-org:metadata-1-0/RCS/}"
                elt = self.from_string(changed_vars['LastChange'])
                self.remove_namespace(elt, ns)            

                # check if it is initial event message
                if self.current_renderer_events_rc == {}:
                    # save all tags
                    self.process_event_tags_rc(elt, self.current_renderer_events_rc)
#                    print 'events_rc: %s' % self.current_renderer_events_rc

                    '''
events_rc: 
{'Volume_RF': '100', 
'Treble': '0', 
'Bass': '0', 
'InstanceID': '0', 
'HeadphoneConnected': '0', 
'Mute_LF': '0', 
'SubGain': '0', 
'SonarCalibrationAvailable': '0', 
'OutputFixed': '0', 
'Mute_RF': '0', 
'Volume_Master': '29', 
'SpeakerSize': '-1', 
'SubPolarity': '0', 
'SonarEnabled': '0', 
'Loudness_Master': '0', 
'PresetNameList': 
'FactoryDefaults', 
'Mute_Master': '0', 
'SubCrossover': '0', 
'Volume_LF': '100', 
'SubEnabled': '1'}
                    '''
    
                    # get volume details
                    if 'OutputFixed' in self.current_renderer_events_rc.keys():
                        self.current_renderer_output_fixed[sid] = self.current_renderer_events_rc['OutputFixed']
                    else:
                        self.current_renderer_output_fixed[sid] = '0'

                    if 'Volume_Master' in self.current_renderer_events_rc.keys():
                        if self.current_renderer_output_fixed[sid] == '0':
                            self.current_volume[sid] = float(self.current_renderer_events_rc['Volume_Master'])
                            self.volume_fixed[sid] = 0

                    if self.current_renderer_output_fixed[sid] == '1':
                            self.volume_fixed[sid] = 1

                    if 'Mute_Master' in self.current_renderer_events_rc.keys():
                        self.volume_mute[sid] = self.current_renderer_events_rc['Mute_Master']

                else:
                    # not initial message, update vars
                    tag_list = {}                    
                    self.process_event_tags_rc(elt, tag_list)
                    # process changed tags                    
#                    log.debug('tl: %s' % tag_list)
                    for key, value in tag_list.iteritems():
                        self.current_renderer_events_rc[key] = value
                        
                        if key == 'Volume_Master':
                            if self.current_renderer_output_fixed[sid] == '0':
                                self.current_volume[sid] = float(value)
                                self.volume_fixed[sid] = 0
                        elif key == 'Mute_Master':
                            self.volume_mute[sid] = value
                        elif key == 'OutputFixed':
                            # TODO: check whether we need to move the next line out of the if statement
                            self.current_renderer_output_fixed[sid] = value
                            self.current_volume[sid] = float(value)
                            if self.current_renderer_output_fixed[sid] == '1':
                                    self.volume_fixed[sid] = 1
                                    
                #DEBUG - turn me back on to print out volume changes                
                #print "  volume change: %s in zone: %s" % (self.current_volume[sid], ZP)
                
                # Run the volume monitor
                    volMon = True
                    
        if volMon == True:
            # Check to see if the SID is in rc_service. We need this to deal
            # with track changes, since they are stored in at_service and
            # have a different sid (usually +- 1 from rc_service)
            rcKey = [ v for k,v in self.rc_service.items() if zpSid[1] in k ]
            #print "ZP:\t%s\t\t%s" % (ZP, sid)
            #print "rcKey: %s" % rcKey[0].event_sid
            try:
                self.mon_volume(ZP, rcKey[0].event_sid)  
                volMon = False
            except:
                pass

    def process_event_tags_avt(self, elt, event_list):
        # save values
        InstanceID = elt.find('InstanceID')
        if InstanceID != None:
            event_list['InstanceID'] = InstanceID.get('val')    # not checking this at present, assuming zero
            for child in elt.findall('InstanceID/*'):
                nodename = child.tag
                val = child.get('val')
                event_list[nodename] = val

    def process_event_tags_rc(self, elt, event_list):
        # save values
        InstanceID = elt.find('InstanceID')
        if InstanceID != None:
            event_list['InstanceID'] = InstanceID.get('val')    # not checking this at present, assuming zero
            for child in elt.findall('InstanceID/*'):
                nodename = child.tag                
                nodechannel = child.get('channel')
                if nodechannel != None:
                    nodename += '_' + nodechannel
                val = child.get('val')
                event_list[nodename] = val

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

    def set_volume(self, rc, volume):
        rc.SetVolume(InstanceID=0, Channel='Master', DesiredVolume=volume)
    
    def mon_volume(self, ZP, sid):
        config = ConfigParser.ConfigParser()
        config.optionxform = str
        config.read('gui/GUIpref.ini')

        if config.has_section(ZP):
            if config.getboolean(ZP, 'monitor') == True:
                maxVol = int(config.get(ZP, 'max_volume'))

                curTime = datetime.datetime.now().strftime("%H:%M")                        

                # Is our zone predetermined to be 'muted?'                 
                muteTimeStart = config.get(ZP, 'mute_start')
                muteTimeStop = config.get(ZP, 'mute_stop')
                
                if muteTimeStart is not '' and muteTimeStop is not '':
                    if (curTime >= muteTimeStart) and (curTime <= muteTimeStop):
                        maxVol = 0    
                
                # Are we supposed to be quiet?
                quietTimeStart = config.get(ZP, 'quiet_start')
                quietTimeStop = config.get(ZP, 'quiet_stop')
                
                if quietTimeStart is not '' and quietTimeStop is not '':
                    if (curTime >= quietTimeStart) and (curTime <= quietTimeStop):
                        maxVol = int(config.get(ZP, 'quiet_volume'))    
                        
                if int(self.current_volume[sid]) > maxVol:
                    self.set_volume(self.rc_service[sid], maxVol)
    
    def _main_quit(self):
#        print "cancelling subscriptions, please wait..."
        self.cancel_subscriptions()
#        print "subscriptions cancelled."
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
        web = ControlPointEvent()
        reactor.main()
    except KeyboardInterrupt, e:
        pass
    finally:
        web._main_quit()
        web.control_point.destroy()

if __name__ == "__main__":
    main()
    
