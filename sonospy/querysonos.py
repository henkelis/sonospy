#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# pycpoint
#
# pycpoint and sonospy copyright (c) 2009-2013 Mark Henkelis
# BRisa copyright (c) Brisa Team <brisa-develop@garage.maemo.org> (BRisa is licenced under the MIT License)
# web2py copyright (c) Massimo Di Pierro <mdipierro@cs.depaul.edu> (web2py is Licensed under GPL version 2.0)
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

###############################################################################
# imports
###############################################################################

import sys
fenc = sys.getfilesystemencoding()
#print sys.getdefaultencoding()

import signal
import time

from brisa.core.reactors import SelectReactor
reactor = SelectReactor()

import os
import uuid

import ConfigParser
import StringIO
import codecs
import urllib

from brisa.core import log
from brisa.core.log import modcheck

import brisa

import threading

#from brisa.core import webserver

import re

from xml.sax.saxutils import escape, unescape

#from Queue import Queue, Empty
#from threading import Lock
import datetime
    
from brisa.upnp.control_point.service import Service, SubscribeRequest

import xml.dom
from xml.dom import minidom
from xml.dom.minidom import parseString
from xml.etree.ElementTree import Element, SubElement, dump
from xml.etree.ElementTree import _ElementInterface
from xml.etree import cElementTree as ElementTree

from control_point_sonos import ControlPointSonos
from brisa.upnp.didl.didl_lite import *     # TODO: fix this
from brisa.core.network import parse_xml
from brisa.core.threaded_call import run_async_function, run_async_call

#from music_items import music_item, dump_element, prettyPrint, getAlbumArtURL

from optparse import OptionParser

#from brisa import url_fetch_attempts, url_fetch_attempts_interval, __skip_service_xml__, __skip_soap_service__, __tolerate_service_parse_failure__, __enable_logging__, __enable_webserver_logging__, __enable_offline_mode__, __enable_events_logging__

###############################################################################
# ControlPointWeb class
###############################################################################

class ControlPointWeb(object):

    ###########################################################################
    # class vars
    ###########################################################################

    known_zone_players = {}
   
    zoneattributes = {}
    
    subscriptions = []

    querylist = {}

    playlistsdumped = False

    browseresults = {}
    playlistresults = {}
    
    playlists = {}

    files = []
    
    LOGFILE = 'querysonos.log'
    PLAYLISTTYPE = 'M3U'

    ###########################################################################
    # command line parser
    ###########################################################################

    usage = "usage: %prog [options] arg"
    parser = OptionParser(usage)
    
    parser.add_option("-m", "--module", action="append", type="string", dest="modcheckmods")
    parser.add_option("-d", "--debug", action="store_true", dest="debug")
    parser.add_option("-q", "--quiet", action="store_true", dest="quiet")
    parser.add_option("-z", "--zpip", type="string", dest="zpip")
    parser.add_option("-w", "--wait", type="string", dest="wait")
    parser.add_option("-v", "--verbose", action="store_true", dest="verbose")

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
    ini = ''
    f = codecs.open('pycpoint.ini', encoding=fenc)
    for line in f:
        ini += line
    config.readfp(StringIO.StringIO(ini))

    # get port to use
    qq_port = 50100
    try:        
        qq_port = int(config.get('INI', 'query_port'))
    except ConfigParser.NoOptionError:
        pass

    # get wait time
    wait_time = 5
    ini_wait_time = None
    try:        
        ini_wait_time = config.get('INI', 'query_wait')
    except ConfigParser.NoOptionError:
        pass
    if options.wait:
        new_wait_time = options.wait
    else:
        new_wait_time = ini_wait_time
    if new_wait_time:
        try:
            wait_time = int(new_wait_time)
        except ValueError:
            pass

    filefolder = 'playlists'

    ###########################################################################
    # __init__
    ###########################################################################

    def __init__(self):

        log.debug("__init__")

        self.writefile(self.LOGFILE, "Command line arguments: %s" % self.options)
        self.writefile(self.LOGFILE, "Ini settings:")
        self.writefile(self.LOGFILE, "    query_port: %s" % self.qq_port)
        self.writefile(self.LOGFILE, "    query_wait: %s" % self.ini_wait_time)
        self.writefile(self.LOGFILE, "Used settings:")
        self.writefile(self.LOGFILE, "    wait_time: %s" % self.wait_time)

        self.control_point = ControlPointSonos(self.qq_port)
        
        # subscribe to new device event of controlpoint
        # don't bother to subscribe to updates from devices, except device removal
        self.control_point.subscribe("new_device_event", self.on_new_device)
        self.control_point.subscribe("removed_device_event", self.on_del_device)
#        self.control_point.subscribe('device_event_seq', self.on_device_event_seq)
        self.control_point.start()

can we just search for these?
    ST: urn:schemas-upnp-org:device:ZonePlayer:1
    
M-SEARCH * HTTP/1.1
HOST: 239.255.255.250:1900
MAN: "ssdp:discover"
MX: 1
ST: urn:schemas-upnp-org:device:ZonePlayer:1
X-RINCON-HOUSEHOLD: HHID_PqS8N7XZPvbmHWl5D3KHkgq2DKu    

        # start MSEARCH
#        self.control_point.start_search(600.0, "ssdp:all")
        run_async_function(self.control_point.start_search, (600.0, "ssdp:all"), 0.001)

        # wait for ZPs to reply before querying
        self.writefile(self.LOGFILE, "Waiting %s seconds for MSEARCH..." % self.wait_time)
        run_async_function(self.process_zoneplayers, (), self.wait_time)

    ###########################################################################
    # device registration functions
    ###########################################################################

    def on_new_device(self, device_object):
        log.debug('got new device: %s' % str(device_object))

        log.debug('fn: %s' % str(device_object.friendly_name.encode('ascii', 'ignore')))
        log.debug('loc: %s' % str(device_object.location))
        log.debug('add: %s' % str(device_object.address))

#        print ">>>> new device: " + str(device_object.friendly_name) + " at " + str(device_object.address) + "  udn: " + str(device_object.udn)

        device_list = []
        if device_object.devices:
#            log.debug('HAS child devices')
            root_device = device_object
            root_device.devices = []
            device_list.append(root_device)
            device_list.extend(device_object.devices)
        else:
#            log.debug('NO child devices')
            device_list.append(device_object)

        for device_item in device_list:

            log.debug('new device: %s' % str(device_item))
            log.debug('new device type: %s' % str(device_item.device_type))
            log.debug('new device udn: %s' % str(device_item.udn))                                    
            log.debug('new device services: %s' % str(device_item.services))
            
            # assumes root device is processed first so that zone name is known
            t = device_item.device_type
            m = ''
            try:
                m = device_item.model_number
            except:
                pass
            if 'ZonePlayer' in t and not 'WD100' in m:

                if device_object.udn in self.known_zone_players.keys():
                    continue
                self.known_zone_players[device_object.udn] = device_object

                self.zoneattributes[device_object.udn] = self.get_zone_details(device_object)
                log.debug('new zone player - %s' % self.zoneattributes[device_object.udn]['CurrentZoneName'])

                self.writefile(self.LOGFILE, 'found zone player - %s (%s, %s)' % (self.zoneattributes[device_object.udn]['CurrentZoneName'], str(device_object.friendly_name), device_object.udn))

    def on_del_device(self, udn):
        # TODO: unsubscribe from events from deleted device (for whose benefit?)
        if udn in self.known_zone_players:
            del self.known_zone_players[udn]
    
    def get_zone_details(self, device):
        return self.control_point.get_zone_attributes(device)

    ###########################################################################
    # query functions
    ###########################################################################

    def writefile(self, setkey, data):

        if setkey.startswith('uuid:RINCON'):
            filename = setkey[5:]
        elif setkey == 'playlists':
            filename = setkey
        else:
            filename = setkey

        if filename == self.LOGFILE and self.options.verbose:
            print data

        if not filename in self.files:
            mode = 'w'
        else:
            mode = 'a'
        self.files.append(filename)

        # note not multi-platform
        local_location = os.path.normpath(self.filefolder + '/' + filename)
#        full_location = os.path.join(os.getcwd(), local_location)

        f = open(local_location, mode)
        f.write(data + '\n')
        f.close()

    def process_zoneplayers(self):

        # extract queue from each zoneplayer in list
        # extract playlists too - only the first zp will be processed

        self.writefile(self.LOGFILE, 'Querying ZonePlayers')            
        for udn, device_object in self.known_zone_players.iteritems():

            # subscribe to events from this device
#            self.subscribe_to_device(self.control_point.get_zt_service(device_object))

            self.dumpqueue(device_object)
            self.dumpplaylists(device_object)

    def dumpqueue(self, device_object):
        self.writefile(device_object.udn, 'extracting queue for zone player - %s' % (self.zoneattributes[device_object.udn]['CurrentZoneName']))
        self.querylist[device_object.udn] = False
        self.browse_sonos_library_async('Q:0', newtype="SONOSLIBRARY", sequence=0, count=100, setkey=device_object.udn, device=device_object)

    def dumpplaylists(self, device_object):
        if self.playlistsdumped == False:
            self.writefile(self.LOGFILE, 'Extracting sonos playlists')
            self.querylist['playlists'] = False
            self.playlistsdumped = True
            self.browse_sonos_library_async('SQ:', newtype="SONOSLIBRARY", sequence=0, count=100, setkey='playlists', device=device_object)
#            self.browse_sonos_library_async('A:ALBUM', newtype="SONOSLIBRARY", sequence=0, count=100, setkey='playlists', device=device_object)

    def dumpplaylistentries(self, device_object):
        self.writefile(self.LOGFILE, 'Extracting sonos playlist entries')
        
        # sort results in case queries came back in wrong order
        resultlist = sorted([k for k in self.playlistresults.keys()])
#        print resultlist

        # combine multiple results (processing
        # them in order via the sorted list)
        # all the entries are playlists
        combinedresultlist = []
        for key in resultlist:
        
            items = self.playlistresults[key]
            combinedresultlist += items

        # TEMP
#        combinedresultlist = combinedresultlist[:10]

        # now process each entry in list
        self.writefile(self.LOGFILE, 'Number of playlists: %s' % len(combinedresultlist))
        for count, item in enumerate(combinedresultlist):
            time.sleep(0.5)
            title = item.title.encode('ascii', 'ignore')
            self.writefile(self.LOGFILE, 'Playlist entry: %s: %s: %s' % (count, item.id, title))
            self.querylist[str(count)] = False
            self.browse_sonos_library_async(item.id, newtype="SONOSLIBRARY", sequence=0, count=100, setkey=str(count), device=device_object)

        # now set processed flag yet for playlists parent,
        # and check whether we've finished
        self.querylist['playlists'] = True
        self.process_all_results()

    def browse_sonos_library_async(self, id, newtype=None, sequence=0, count=-1, setkey='', device=None):
        log.debug("#### browse_sonos_library_async: %s", id)

        self.writefile(setkey, "initial browse: id=%s, sequence=%s, count=%s, setkey=%s" % (id, sequence, count, setkey))
        
        id_param = id

        # set up for browsing
        returned = 0    # seed returned count, which is also starting index
        if count == -1: count = 100     # initial count to retrieve so first call is fast
        filter = '*'
        sort = ''
        search = ''
        searchstring = ''
        self.current_browse_id = id_param

        # run the first call synchronously so this thread waits for the return
        result = self.control_point.browse(id_param, 'BrowseDirectChildren', filter, 0, count, sort, device=device)
        
        # process the results returned
        cargo = (id_param, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey, device)
        self.process_library_result(result, cargo)

    def browse_sonos_library_async_browse(self, id, returned, count, sequence, filter, sort, search, searchstring, newtype, setkey, device):
        # call browse asynchronously
        self.writefile(setkey, "subsequent browse: id=%s, sequence=%s, count=%s, setkey=%s" % (id, sequence, count, setkey))
        run_async_call(self.control_point.browse,
                       success_callback=self.process_library_result,
                       error_callback=self.process_library_result,
                       success_callback_cargo=(id, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey, device), 
                       error_callback_cargo=(id, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey, device),
                       delay=0, 
                       object_id=id,
                       browse_flag='BrowseDirectChildren',
                       filter=filter,
                       starting_index=returned,
                       requested_count=count,
                       sort_criteria=sort,
                       device=device)

    def process_library_result(self, browse_result, cargo):

        # TODO - fix so that error_callback goes to an error routine and not here!

#        print '@@@@@@@@ %s' % (str(cargo))
        id, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey, device = cargo

        error = False
        if 'faultcode' in browse_result:
            error = True
        elif not 'Result' in browse_result:
            error = True

        if not error:
            items = browse_result['Result']
            total = int(browse_result['TotalMatches'])
            thisreturned = int(browse_result['NumberReturned'])
            returned += thisreturned
            
            if setkey == 'playlists':
                self.playlistresults[(setkey, returned)] = items
            else:
                self.browseresults[(setkey, returned)] = items

            # if we haven't got all the results, set another call off
            if returned < total:
                self.browse_sonos_library_async_browse(id, returned, count, sequence+1, filter, sort, search, searchstring, newtype, setkey, device)

        if error or returned >= total:
            # process the full result list
            if setkey == 'playlists':
                # note - don't set processed flag yet for this setkey,
                #        do it after the playlists have been processed
                self.dumpplaylistentries(device)
            else:
                self.querylist[setkey] = True
                self.process_all_results()

    def process_all_results(self):

#        print '********* %s' % self.querylist
        complete = all(v == True for v in self.querylist.itervalues())
        
        if not complete:
            return

#        print '######################### results'
        
        # sort results in case queries came back in wrong order
        resultlist = sorted([k for k in self.browseresults.keys()])
#        print resultlist

        # combine multiple results for same uid (processing
        # them in order via the sorted list)
        combinedresultlist = {}
        for key in resultlist:
        
#            print key
            uid, index = key
            items = self.browseresults[key]
            
            # append if uid already encountered
            if uid in combinedresultlist.keys():
                items = combinedresultlist[uid] + items

            combinedresultlist[uid] = items

        # now process each uid
        for key, items in combinedresultlist.iteritems():
            
            items = combinedresultlist[key]
            
            playlist = []
            for item in items:

                xml = item.to_string()
                xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
                xml = xml.replace('ns0:','')

                if item.resources:
                    res = item.resources[0].value
                    dur = makeseconds(item.resources[0].duration)
                else:
                    res = ''
                    dur = 0

                title = item.title.encode('ascii', 'ignore')

                self.writefile(self.LOGFILE, '%s: %s: %s: %s' % (item.id, title, xml, res))

                playlist.append((title, str(dur), res, item.id, xml))

            playlisttext = self.make_playlist(playlist, key, type=self.PLAYLISTTYPE)
            playlistfile = '%s.%s' % (key, self.PLAYLISTTYPE)
            self.writefile(playlistfile, playlisttext)

        self.writefile(self.LOGFILE, 'Finished')
        os.kill(os.getpid(), signal.SIGINT)

    def make_playlist(self, entries, name, type='M3U'):

        if type == 'M3U':

            playlist_name = '%s.m3u' % name
    
            playlist = '#EXTM3U\n'
            for title, duration, res, id, xml in entries:
                playlist += '#EXTINF:' + str(duration) + ',' + title + '\n'
                playlist += res + '\n'

        elif type == 'ASX':

            playlist_name = '%s.asx' % name

            playlist = '<asx version="3.0">\n'
            playlist += '<title>Green Day - 21st Century Breakdown</title>\n'

            for title, duration, res, id, xml in entries:
                playlist += '<entry><title>' + title + '</title>'
                playlist += '<ref href="' + res + '" /></entry>\n'

            playlist += '</asx>\n'

        elif type == 'PLS':

            playlist_name = '%s.pls' % name

            playlist = '[playlist]\n'

            count = 0
            for title, duration, res, id, xml in entries:
                count += 1
                strcount = str(count)
                playlist += 'Title' + strcount + '=' + title + '\n'
                playlist += 'File' + strcount + '=' + res + '\n'
                playlist += 'Length' + strcount + '=' + duration + '\n'

            playlist += 'NumberOfEntries=' + strcount + '\n'
            playlist += 'Version=2\n'

        elif type == 'XML':

            playlist_name = '%s.rsq' % name

            playlist = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:dlna="urn:schemas-dlna-org:metadata-1-0/" xmlns:pv="http://www.pv.com/pvns/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'

            for title, duration, res, id, xml in entries:
                playlist += xml

            playlist += '</DIDL-Lite>'

        # temp
        return playlist

#        self.control_point._event_listener.srv.add_static_file(webserver.StaticFile(playlist_name, playlist_path))

        uri = 'http://' + self.control_point._event_listener.srv.host + ':' + str(self.control_point._event_listener.srv.port) + '/' + playlist_name

        return uri

    def convert_item_to_uridata(self, item):

        if item.resources != []:
            uri = item.resources[0].value
        else:
            uri = ''
#            uri = 'x-rincon-playlist:RINCON_000E5830D2F001400#' + item.id

        root = ElementTree.Element('item')
        root.attrib['id'] = item.id
        root.attrib['parentID'] = item.parent_id
        if item.restricted:
            root.attrib['restricted'] = 'true'
        else:
            root.attrib['restricted'] = 'false'

        ElementTree.SubElement(root, 'dc:title').text = item.title
        ElementTree.SubElement(root, 'upnp:class').text = item.upnp_class
        desc = ElementTree.SubElement(root, 'desc')
        desc.attrib['id'] = "cdudn"
        desc.attrib['nameSpace'] = "urn:schemas-rinconnetworks-com:metadata-1-0/"
        desc.text = 'RINCON_AssociatedZPUDN'
        
        xml = ElementTree.tostring(root)
        xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
        xml = xml.replace('ns0:','')
    
        data = uri, xml

        return uri, xml




    def play_now_queue(self):

        # TODO: track updates to queue UpdateID so we know if it has changed since we started and need to re-fetch
        
        desiredfirsttrack = 0
        enqueuenext = 1

        queue = self.queue_gen()
        played = False
        for item in queue:
            uri, xml, index, total = item
            self.control_point.add_uri_to_queue(uri, xml, desiredfirsttrack, enqueuenext)

            log.debug(uri)
            log.debug(xml)

            # HACK - sort this out        
            self.current_queue_length += 1

            if played == False:
                self.control_point.set_avtransport_uri(uri, xml)
                unit = 'TRACK_NR'
                target = self.current_queue_length
                self.control_point.seek(unit, target)
                self.play()
                played = True

    

    
    def add_queue(self, position):

        if position == 'NEXT':
            desiredfirsttrack = self.current_queue_length + 1       # CHECK WHETHER THIS IS CORRECT
            enqueuenext = 1
        elif position == 'END':
            desiredfirsttrack = 0
            enqueuenext = 0

        queue = self.queue_gen()
        for item in queue:
            uri, xml, index, total = item
            
            print uri
            print xml
            print
            
            self.set_messagebar("Queuing item %d of %d." % (index, total))
            self.control_point.add_uri_to_queue(uri, xml, desiredfirsttrack, enqueuenext)

            # HACK - sort this out        
            self.current_queue_length += 1
            

    def queue_gen(self):

        plist = []
        if len(self.current_media_list) == 0:
            plist.append(('', 0, self.current_media_id, '', self.current_media_xml))
        else:
            plist += self.current_media_list
        
        index = 1
        total = len(plist)
        for title, duration, uri, id, xml in plist:
            yield (uri, xml, index, total)
            index += 1



    def update_playlist_name(self, id, currenttagvalue, newtagvalue):

        currenttagvalue = '<dc:title>' + currenttagvalue + '</dc:title>'
        newtagvalue = '<dc:title>' + newtagvalue + '</dc:title>'
        res = self.control_point.update_object(id, currenttagvalue, newtagvalue)
        if res == {}:
            return True
        else:
            return False









    
    '''
    ###########################################################################
    # subscription functions
    ###########################################################################

    def subscribe_to_device(self, service):
        try:
            service.event_subscribe(self.control_point.event_host, self._event_subscribe_callback, None, True, self._event_renewal_callback)
            self.subscriptions.append(service)
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
#            log.debug("#### RENEW_DEVICE_SUBSCRIPTION BEFORE")
#            device.services[service].event_renew(self.control_point.event_host, self._event_renewal_callback, None)
#            log.debug("#### RENEW_DEVICE_SUBSCRIPTION AFTER")
#        except:
#            raise Exception("Error occured during device subscription renewal")

    def unsubscribe_from_device(self, service):
        try:
            service.event_unsubscribe(self.control_point.event_host, self._event_unsubscribe_callback, None)
        except:
            raise Exception("Error occured during unsubscribe from device")

    def cancel_subscriptions(self):
        log.debug("Cancelling subscriptions")
        for service in self.subscriptions:
            log.debug("Service: %s", service)
            self.unsubscribe_from_device(service)

    def _event_subscribe_callback(self, cargo, subscription_id, timeout):
        log.debug('Event subscribe done cargo=%s sid=%s timeout=%s', cargo, subscription_id, timeout)

    def _event_renewal_callback(self, cargo, subscription_id, timeout):
# TODO: add error processing for if renewal fails - basically resubscribe. NEW - check if this is catered for in 0.10.0
        log.debug('Event renew done cargo=%s sid=%s timeout=%s', cargo, subscription_id, timeout)

    def _event_unsubscribe_callback(self, cargo, subscription_id):
        log.debug('Event unsubscribe done cargo=%s sid=%s', cargo, subscription_id)

    '''

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

    def make_utf8(self, text):
        if type(text) is unicode:
            text = text.encode('utf-8')
        return text

    def codeoperators(self, operators):
        # replace symbol operators with symbol=code
        # some operators are subsets of others, so match with surrounding characters
        newoperators = ',' + operators + ','
        for code, op in self.ms_operator_codes.items():
            newoperators = newoperators.replace(','+op+',',','+op+':'+code+',')
        newoperators = newoperators[1:-1]
        return newoperators

    def decodeoperators(self, operator):
        # get operator symbol for code
        try:
            symbol = self.ms_operator_codes[operator]
            return symbol
        except KeyError, k:
            return operator

    def _main_quit(self):
#        self.cancel_subscriptions()
        reactor.main_quit()

def makeseconds(time):
    if not ':' in time:
        return 0
    h, m, s = time.split(':')
    return (int(h)*60*60 + int(m)*60 +int(float(s)))

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

def main():

    web = ControlPointWeb()
    reactor.main()
    web._main_quit()
    web.control_point.destroy()

if __name__ == "__main__":

    main()
    
