#!/usr/bin/env python
# -*- coding: UTF-8 -*-
#
# pycpoint
#
# pycpoint and sonospy copyright (c) 2009-2010 Mark Henkelis
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

################################################################################
# TODO:
################################################################################
#
# 3) Don't process devices that aren't mediaservers, mediarenderers or control points
# 5) Queue manipulation
# 6) Add more details to media list when displaying a queue

    # TODO: save returned media server items in temp list, then post process them to:
    # 1) Suppress duplicates, choosing which to display from a list based on type (e.g. FLAC vs MP3)
    # 2) Display extra info for duplicates (e.g. location)
    # 3) Other things?
    # Make this/these options selectable via a config option



# fix this
#DEBUG	sonos                         :2329:_event_renewal_callback() Event renew done cargo=None sid=uuid:EISBCPGQBFTOWBIKEJF timeout=1800
#DEBUG	sonos                         :2329:_event_renewal_callback() Event renew done cargo=None sid=uuid:RINCON_000E5823A88A01400_sub0000000058 timeout=1800
#DEBUG	sonos                         :2329:_event_renewal_callback() Event renew done cargo=None sid=uuid:RINCON_000E5830D2F001400_sub0000000036 timeout=1800
#DEBUG	sonos                         :2329:_event_renewal_callback() Event renew done cargo=None sid=uuid:HHYIWSGZOTJHPKGSYED timeout=1800
#DEBUG	sonos                         :2329:_event_renewal_callback() Event renew done cargo=None sid=uuid:RINCON_000E5823A88A01400_sub0000000059 timeout=1800
#DEBUG	sonos                         :2329:_event_renewal_callback() Event renew done cargo=None sid=uuid:RINCON_000E5830D2F001400_sub0000000037 timeout=1800
#DEBUG	sonos                         :2329:_event_renewal_callback() Event renew done cargo=None sid=uuid:RINCON_000E5830D2F001400_sub0000000038 timeout=1800
#DEBUG	sonos                         :2329:_event_renewal_callback() Event renew done cargo=None sid=uuid:RINCON_000E5830D2F001400_sub0000000039 timeout=1800
#DEBUG	sonos                         :2329:_event_renewal_callback() Event renew done cargo=None sid= timeout=0
#DEBUG	sonos                         :2329:_event_renewal_callback() Event renew done cargo=None sid= timeout=0

#regresp message is bin.base64
#Need to event reg and val messages (render will subscribe and look for them)
#What about cert requests?

#Eventing for volume - maximum rate or minimum delta?

# Deactivate stop button when already stopped etc
# When stopping a track that has been paused, if it's the last track in a queue the Sonos returns to the first track in the queue - but we haven't set the metadata for that. ACTUALLY seems to be related to the return of a playlist class.
# Need to subscribe to zone player events (e.g. if the zone name is changed)
# Need to tidy up new classes and rest of code

###############################################################################
# imports
###############################################################################

import sys
fenc = sys.getfilesystemencoding()
#print sys.getdefaultencoding()

from brisa.core.reactors import SelectReactor
reactor = SelectReactor()

import os
import uuid

import ConfigParser
import StringIO
import codecs

from data import ListDataController, GetDataController, PlayController, GetDeviceController, SetRendererController, PollRendererController, ActionRendererController, PollServerController, PollQueueController

#import log
from brisa.core import log
from brisa.core.log import modcheck

import brisa

import threading

from brisa.core.network import get_active_ifaces, get_ip_address

from brisa.core import webserver

import re

from xml.sax.saxutils import escape, unescape

from Queue import Queue, Empty
from threading import Lock
import datetime
    
from brisa.upnp.control_point.service import Service, SubscribeRequest

from proxy import Proxy

import pprint
pp = pprint.PrettyPrinter(indent=4)

import xml.dom
from xml.dom import minidom
from xml.dom.minidom import parseString

from xml.etree.ElementTree import Element, SubElement, dump

from xml.etree.ElementTree import _ElementInterface
from xml.etree import cElementTree as ElementTree

from control_point_sonos import ControlPointSonos
from brisa.upnp.didl.didl_lite import *     # TODO: fix this
from brisa.core.network import parse_xml
from brisa.core.network import parse_url, url_fetch
from brisa.core.threaded_call import run_async_function, run_async_call

from brisa.utils.looping_call import LoopingCall

from music_items import music_item, dump_element, prettyPrint, getAlbumArtURL

from sonos_service import radiotimeMediaCollection, radiotimeMediaMetadata

from brisa.upnp.soap import HTTPTransport, HTTPError, parse_soap_call, parse_soap_fault

from optparse import OptionParser

from brisa import url_fetch_attempts, url_fetch_attempts_interval, __skip_service_xml__, __skip_soap_service__, __tolerate_service_parse_failure__, __enable_logging__, __enable_webserver_logging__, __enable_offline_mode__, __enable_events_logging__

###############################################################################
# ControlPointWeb class
###############################################################################

class ControlPointWeb(object):

    ###########################################################################
    # class vars
    ###########################################################################

    current_media_id = None
    current_media_list = []
    current_media_xml = ''
    current_media_type = ''
    current_renderer_events_avt = {}
    current_renderer_events_rc = {}

    current_browse_id = None

    now_playing = ''
    now_extras = ''
    now_playing_dict = {}
    now_extras_dict = {}
    now_playing_pos = ''
    now_playing_percent = ''
    processing_event = False
    event_queue = Queue()
    last_event_seq = {}
    event_lock = Lock()
    album_art = ''

    info = ''

    current_position = {}
    current_track = '-1'
    current_track_duration = ''
    current_track_URI = ''
    current_track_metadata = ''
    current_track_relative_time_position = ''
    messagebar = ''

    prev_now_playing_dict = {}
    prev_now_extras_dict = {}
    prev_now_playing_pos = '-'
    prev_now_playing_percent = '-'
    prev_current_volume = '-'
    prev_volume_fixed = '-'
    prev_volume_mute = '-'
    prev_play_state = '-'
    prev_album_art = '-'

    queue_updateid = ''
    prev_queue_updateid = '-'

    current_queue_length = -1
    current_queue_updateid = -1
    
    current_music_item = music_item()

    music_services = {}
    music_services_type = {}
    AvailableServiceTypeList = ''
    AvailableServiceListVersion = ''
    test = None

    napster_loggedin = False
    napster_username = ''
    napster_password = ''
    napster_UDN = ''

    muted = 0
    play_state = ''
    current_renderer_output_fixed = '1'
    current_renderer_output_fixed_volume = 50.0
    current_volume = 50.0
    volume_fixed = 1
    volume_mute = 1

    media_list = []

    known_zone_players = {}
    known_zone_names = {}
    known_media_servers = {}
    known_media_renderers = {}
    known_media_renderers_extras = {}

    thirdpartymediaservers = {}
    services = {}
    rootids = {}
    msrootids = {}
    
    proxies = []
    upnpproxy = []
    wmpproxy = []
    wmpfound = False
    sonospyproxies = {}
    
    zoneattributes = {}
    
    subscriptions = []

    current_server_search_capabilities = {}
    current_server_sort_capabilities = {}
    current_server_sort = ''
    current_server_filter = 'dc:title,res,dc:creator,upnp:artist,upnp:album,upnp:albumArtURI'      # TODO: make this server specific

    library_search = ['Artist', 'Album', 'Tracks', 'Composer', 'ALL']
    library_search_ids = {}
    library_root = []
    library_search_string = ''
    library_search_title = 'Search Library'
    LSS_BASE = 'LSS'

    napster_search = ['Artist', 'Album', 'Track']
    napster_search_ids = {}
    napster_root = []
    napster_search_string = ''
    napster_search_title = 'Search Napster'
    NSS_BASE = 'NSS'

    mediaserver_search = []
    mediaserver_search_ids = {}
    mediaserver_root = []
    mediaserver_search_string = ''
    mediaserver_search_title = 'Search %s'
    mediaserver_search_type = 'MusicServerSearch_ROOT'
    MSS_BASE = 'MSS'
    mediaserver_search_vars = (mediaserver_search, mediaserver_root, mediaserver_search_string, mediaserver_search_title, mediaserver_search_type, MSS_BASE)

    sonospyserver_search = []
    sonospyserver_search_ids = {}
    sonospyserver_root = []
    sonospyserver_search_string = ''
    sonospyserver_search_title = 'Search %s'
    sonospyserver_search_type = 'SonospyServerSearch_ROOT'
    SSS_BASE = 'SSS'
    sonospyserver_search_vars = (sonospyserver_search, sonospyserver_root, sonospyserver_search_string, sonospyserver_search_title, sonospyserver_search_type, SSS_BASE)

    global_search = ['Artist', 'Album', 'Track']
    global_root = []
    global_search_string = ''
    global_search_title = 'Global Search'
    global_search_type = 'SonosGlobalSearch_ROOT'
    GSS_BASE = 'GSS'
    global_search_vars = (global_search, global_root, global_search_string, global_search_title, global_search_type, GSS_BASE)

    ms_search_operators = {
        # MS Media Player
        '@id' : '=,!=' ,
        '@refID' : 'exists' ,
        '@restricted' : '=,!=,contains' ,
        'dc:creator' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'dc:date' : '<,<=,>=,>,=,!=' ,
        'dc:description' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'dc:language' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'dc:publisher' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'dc:title' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'microsoft:artistAlbumArtist' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'microsoft:artistConductor' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'microsoft:artistPerformer' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'microsoft:authorComposer' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'microsoft:authorOriginalLyricist' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'microsoft:authorWriter' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'microsoft:serviceProvider' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'microsoft:userEffectiveRating' : '<,<=,>=,>,=,!=' ,
        'microsoft:userEffectiveRatingInStars' : '<,<=,>=,>,=,!=' ,
        'microsoft:userRating' : '<,<=,>=,>,=,!=' ,
        'microsoft:userRatingInStars' : '<,<=,>=,>,=,!=' ,
        'res@bitrate' : '<,<=,>=,>,=,!=' ,
        'res@duration' : '<,<=,>=,>,=,!=' ,
        'res@protection' : '=,contains' ,
        'res@protocolInfo' : '=,contains,!=,doesNotContain' ,
        'res@size' : '<,<=,>=,>,=,!=' ,
        'upnp:actor' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'upnp:album' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'upnp:artist' : 'contains,=' ,
        'upnp:artist@role' : 'contains,=' ,
        'upnp:author' : 'contains,=' ,
        'upnp:author@role' : 'contains,=' ,
        'upnp:class' : '=,derivedfrom' ,
        'upnp:director' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'upnp:genre' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'upnp:originalTrackNumber' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'upnp:producer' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'upnp:rating' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'upnp:toc' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        'upnp:userAnnotation' : 'contains,exists,<,<=,>=,>,=,!=,derivedfrom,doesnotContain' ,
        # Twonky specific
        '@protocolInfo' : '=,contains,!=,doesNotContain' ,      # move to ini
        }

    ms_operator_codes = {'lt' : '<' ,
                         'le' : '<=',
                         'ge' : '>=',
                         'gt' : '>' ,
                         'eq' : '=' ,
                         'ne' : '!='}
    
    msms_root_items = []
    msms_root_items.append(['All Music', '4'])
    msms_root_items.append(['Genre', '5'])
    msms_root_items.append(['Artist', '6'])
    msms_root_items.append(['Album', '7'])
    msms_root_items.append(['Playlists', 'F'])
    msms_root_items.append(['Folders', '14'])
    msms_root_items.append(['Contributing Artists', '100'])
    msms_root_items.append(['Album Artist', '107'])
    msms_root_items.append(['Composer', '108'])
    msms_root_items.append(['Rating', '101'])

    msms_rating_items = []
    msms_rating_items.append(['1 or more stars', '102'])
    msms_rating_items.append(['2 or more stars', '103'])
    msms_rating_items.append(['3 or more stars', '104'])
    msms_rating_items.append(['4 or more stars', '105'])
    msms_rating_items.append(['5 or more stars', '106'])

    msms_search_lookup = { '4' : 'upnp:class derivedfrom "object.item.audioItem"',
                           '5' : 'upnp:class = "object.container.genre.musicGenre"',
                           '6' : 'upnp:class = "object.container.person.musicArtist"',
                           '7' : 'upnp:class = "object.container.album.musicAlbum"',
                           'F' : 'upnp:class = "object.container.playlistContainer"',
                           '14' : 'upnp:class = "object.container.storageFolder"',
                           '100' : 'upnp:class = "object.container.person.musicArtist"',
                           '107' : 'upnp:class = "object.container.person.musicArtist"',
                           '108' : 'upnp:class = "object.container.person.musicArtist"',
                           '101' : '' }     # dummy, entries are manually created

    # msms_search_lookup_item is not configured correctly at the moment - only the first call will be a search, thereafter calls will be browses
    # (so it works but it is not exactly Sonos controller-like)

    msms_search_lookup_item = { '4' : '',   # dummy, higher search returns items
                                '5' : 'BROWSE',
#                                '6' : 'upnp:artist = "%s"',
                                '6' : 'BROWSE',
                                '7' : 'BROWSE',
                                'F' : 'BROWSE',
                                '14' : 'BROWSE',
                                '100' : 'BROWSE',
                                '107' : 'BROWSE',
                                '108' : 'BROWSE',
                                '101' : 'BROWSE' }

    # translations to emulate what Sonos does in WMP search
    sonospy_search_lookup = {
                             '5' : 'upnp:class = "object.container.genre.musicGenre"',
                             '6' : 'upnp:class = "object.container.person.musicArtist"',
                             '7' : 'upnp:class = "object.container.album.musicAlbum"',
                             'F' : 'upnp:class = "object.container.playlistContainer"',
                             '99' : 'upnp:class derivedfrom "object.item.audioItem"',
                             '100' : 'upnp:class = "object.container.person.musicArtist"',
                             '107' : 'upnp:class = "object.container.person.musicArtist"',
                             '108' : 'upnp:class = "object.container.person.musicArtist"',
                             '101' : '',         # dummy, entries are manually created
                            }

    sonospy_search_lookup_item = {
                                  '6' : '107',
                                  '100' : '100',
                                  '7' : '0',
                                  '108' : '108',
                                  '5' : '0',
                                  '99' : '0',
                                  'F' : '0',
                                 }
    sonospy_search_lookup_item2 = {
                                   'ARTIST' : '0',
                                   'ARTIST_ALBUM' : '0',
                                   'ALBUMARTIST' : '0',
                                   'ALBUMARTIST_ALBUM' : '0',
                                   'CONTRIBUTINGARTIST' : '0',
                                   'CONTRIBUTINGARTIST_ALBUM' : '0',
                                   'COMPOSER' : '0',
                                   'COMPOSER_ALBUM' : '0',
                                   'GENRE' : '107',
                                   'GENRE_ARTIST' : '0',
                                   'GENRE_ARTIST_ALBUM' : '0',
                                   'GENRE_ALBUMARTIST' : '0',
                                   'GENRE_ALBUMARTIST_ALBUM' : '0',
                                  }
    # search comes in with this key, so value is for next search down tree
    sonospy_search_lookup_item3 = {
                                   'ARTIST' : ('upnp:class = "object.container.album.musicAlbum" and @refID exists false and microsoft:artistAlbumArtist = "%s"', 1),
                                   'ARTIST_ALBUM' : ('upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:artistAlbumArtist = "%s" and upnp:album = "%s"', 2),
                                   'ALBUMARTIST' : ('upnp:class = "object.container.album.musicAlbum" and @refID exists false and microsoft:artistAlbumArtist = "%s"', 1),
                                   'ALBUMARTIST_ALBUM' : ('upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:artistAlbumArtist = "%s" and upnp:album = "%s"', 2),
                                   'CONTRIBUTINGARTIST' : ('upnp:class = "object.container.album.musicAlbum" and @refID exists false and microsoft:artistPerformer = "%s"', 1),
                                   'CONTRIBUTINGARTIST_ALBUM' : ('upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:artistPerformer = "%s" and upnp:album = "%s"', 2),
                                   'COMPOSER' : ('upnp:class = "object.container.album.musicAlbum" and @refID exists false and microsoft:authorComposer = "%s"', 1),
                                   'COMPOSER_ALBUM' : ('upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:authorComposer = "%s" and upnp:album = "%s"', 2),
                                   'GENRE' : ('upnp:class = "object.container.person.musicArtist" and @refID exists false and upnp:genre = "%s"', 1),
                                   'GENRE_ARTIST' : ('upnp:class = "object.container.album.musicAlbum" and @refID exists false and upnp:genre = "%s" and microsoft:artistAlbumArtist = "%s"', 2),
                                   'GENRE_ARTIST_ALBUM' : ('upnp:class derivedfrom "object.item.audioItem" and @refID exists false and upnp:genre = "%s" and microsoft:artistAlbumArtist = "%s" and upnp:album = "%s"', 3),
                                   'GENRE_ALBUMARTIST' : ('upnp:class = "object.container.album.musicAlbum" and @refID exists false and upnp:genre = "%s" and microsoft:artistAlbumArtist = "%s"', 2),
                                   'GENRE_ALBUMARTIST_ALBUM' : ('upnp:class derivedfrom "object.item.audioItem" and @refID exists false and upnp:genre = "%s" and microsoft:artistAlbumArtist = "%s" and upnp:album = "%s"', 3),
                                  }

    '''
#upnp:class = "object.container.person.musicArtist" and @refID exists false
upnp:class = "object.container.album.musicAlbum" and @refID exists false and microsoft:artistAlbumArtist = "Green Day•0"
upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:artistAlbumArtist = "%s" and upnp:album = "%s"

#upnp:class = "object.container.person.musicArtist" and @refID exists false
upnp:class = "object.container.album.musicAlbum" and @refID exists false and microsoft:artistPerformer = "White Day•0"
upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:artistPerformer = "%s" and upnp:album = "%s"

#upnp:class = "object.container.genre.musicGenre" and @refID exists false
upnp:class = "object.container.person.musicArtist" and @refID exists false and upnp:genre = "%s"
upnp:class = "object.container.album.musicAlbum" and @refID exists false and upnp:genre = "%s" and microsoft:artistAlbumArtist = "%s"
upnp:class derivedfrom "object.item.audioItem" and @refID exists false and upnp:genre = "%s" and microsoft:artistAlbumArtist = "%s" and upnp:album = "%s"
    '''


    msms_search_browse_sortcriteria = { '4' : '',
                                        '5' : '',
                                        '6' : '',
                                        '7' : '+upnp:originalTrackNumber',
                                        'F' : '',
                                        '14' : '',
                                        '100' : '',
                                        '107' : '',
                                        '108' : '',
                                        '101' : '',
                                        'DEFAULT' : '+upnp:originalTrackNumber'}

    '''
Music/All Music             4       object.item.audioItem                   Contains all of the music items in the Music container
                                    object.item.audioItem.musicTrack
Music/Genre                 5       object.container.genre.musicGenre       Contains genre information for all music items that have genre metadata
Music/Artist                6       object.container.person.musicArtist     Contains artist names for all music items that have artist metadata
Music/Album                 7       object.container.album.musicAlbum       Contains album titles for all music items that have album metadata
Music/Playlists             F       object.container.playlistContainer      Contains playlists for all music items
Music/Folders               14      object.container.storageFolder
Music/Contributing Artists  100     object.container.person.musicArtist     Contains artist names for all music items that have contributing artist metadata
Music/Album Artist          107     object.container.person.musicArtist     Contains artist names for all music items that have album artist metadata
Music/Composer              108     object.container.person.musicArtist     Contains artist names for all music items that have composer metadata
Music/Rating                101     object.container
    '''

#dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber    

#Search("0", upnp:class = "object.container.person.musicArtist", "", "*", 0, 0, "")
#Search("0", upnp:class = "object.container.person.musicArtist", "", "*", 0, 10, "")
#Search("0", upnp:class = "object.container.album.musicAlbum" and upnp:artist = "Artist 1", "", "*", 0, 10, "")
#Browse(RESULT, "BrowseDirectChildren", "", 0, 10, "")

    ###########################################################################
    # command line parser
    ###########################################################################

    usage = "usage: %prog [options] arg"
    parser = OptionParser(usage)
    
    parser.add_option("-m", "--module", action="append", type="string", dest="modcheckmods")
    parser.add_option("-d", "--debug", action="store_true", dest="debug")
    parser.add_option("-q", "--quiet", action="store_true", dest="quiet")
    parser.add_option("-n", "--nogui", action="store_true", dest="nogui")
    parser.add_option("-p", "--proxyonly", action="store_true", dest="proxyonly")
    parser.add_option("-u", "--upnpproxy", action="append", type="string", dest="upnpproxies")
    parser.add_option("-w", "--wmpproxy", action="append", type="string", dest="wmpproxies")

    (options, args) = parser.parse_args()

    print "Args:"
    if options.debug:
        print "option.debug: " + str(options.debug)
        modcheck['all'] = True
    if options.quiet:
        print "option.quiet: " + str(options.quiet)
    if options.modcheckmods:
        for m in options.modcheckmods:
            print "    module: " + str(m)
            modcheck[m] = True
    if options.nogui:
        print "option.nogui: " + str(options.nogui)
    if options.proxyonly:
        print "option.proxyonly: " + str(options.proxyonly)
    if options.upnpproxies:
        for u in options.upnpproxies:
            print "    UPnP proxy: " + str(u)
            upnpproxy.append(u)
    if options.wmpproxies:
        for w in options.wmpproxies:
            print "    WMP proxy: " + str(w)
            wmpproxy.append(w)

    __enable_webserver_logging__ = True
    __enable_events_logging__ = True

    ###########################################################################
    # ini parser
    ###########################################################################

    config = ConfigParser.ConfigParser()
    config.optionxform = str
#    config.read('pycpoint.ini')
    ini = ''
    f = codecs.open('pycpoint.ini', encoding=fenc)
    for line in f:
        ini += line
    config.readfp(StringIO.StringIO(ini))


    # IP volume ini vars

    VOLUME_UP     = 'Volume Up'
    VOLUME_DOWN   = 'Volume Down'
    VOLUME_MUTE   = 'Volume Mute'
    VOLUME_UNMUTE = 'Volume UnMute'

    rooms_volumes = {}
    rooms = []
    ir_ip = ''
    ir_port = 0
    
    try:        
        ip_volumes = config.items('IP Volume')
        for k, v in ip_volumes:
            if k == 'IR_IP':
                ir_ip = v
            elif k == 'IR_PORT':
                ir_port = int(v)
            else:
                f = open(v, 'r')
                rooms_volumes[k] = f.read()
                f.close()
                keystring = k.split(',')
                if not keystring[0] in rooms:
                    rooms.append(keystring[0])
    except ConfigParser.NoSectionError:
        pass

#    print "rooms_volumes: " + str(rooms_volumes)
#    print "rooms: " + str(rooms)
#    print "ir ip: " + ir_ip
#    print "ir port: " + str(ir_port)

    # port ini vars

    # get ports to use
    ws_port = 50101
    proxy_port = 50102
    wmp_proxy_port = 10243
    wmp_internal_port = 10244
    internal_proxy_udn = None
    try:        
        ws_port = int(config.get('INI', 'controlpoint_port'))
    except ConfigParser.NoOptionError:
        pass
    try:        
        proxy_port = int(config.get('INI', 'proxy_port'))
    except ConfigParser.NoOptionError:
        pass
    try:        
        wmp_proxy_port = int(config.get('INI', 'wmp_proxy_port'))
    except ConfigParser.NoOptionError:
        pass
    try:        
        wmp_internal_port = int(config.get('INI', 'wmp_internal_port'))
    except ConfigParser.NoOptionError:
        pass
    try:        
        internal_proxy_udn = config.get('INI', 'internal_proxy_udn')
    except ConfigParser.NoOptionError:
        pass

    ###########################################################################
    # __init__
    ###########################################################################

    def __init__(self):

        log.debug("__init__")

        if not self.options.proxyonly:

            self.control_point = ControlPointSonos(self.ws_port)
            self.control_point.subscribe("new_device_event", self.on_new_device)
            self.control_point.subscribe("removed_device_event", self.on_del_device)
    #        self.control_point.subscribe('device_event', self.on_device_event)
            self.control_point.subscribe('device_event_seq', self.on_device_event_seq)
            self.control_point.start()


        # proxy internally if it has been requested
        internal_count = 0
        for wmpstring in self.wmpproxy:
            wmpsplit = wmpstring.split('=')
            if len(wmpsplit) == 1:
                wmp = wmpsplit[0]
                wmpname = ''
                dbname = ''
            else:
                wmp = wmpsplit[0]
                if ',' in wmpsplit[1]:
                    namesplit = wmpsplit[1].split(',')
                    wmpname = namesplit[0]
                    dbname = namesplit[1]
                else:
                    wmpname = wmpsplit[1]
                    dbname = ''

            if wmp.lower() == 'sonospy':
                if wmpname == '':
                    friendly = 'WMP Library'
                else:
                    friendly = wmpname
                ip = self._get_ip()  ############ TEMP
                port = self.wmp_internal_port + internal_count
                scheme = "http://"
                listen_url = scheme + ip + ':' + str(port)
                serve_url = scheme + ip + ':' + str(self.wmp_proxy_port)
                wmptrans = 'Sonospy'
                name = friendly
                if self.internal_proxy_udn == None:
                    proxyuuid = 'uuid:' + str(uuid.uuid4())
                elif internal_count > 0:
                    hic = '%02x' % (internal_count)
                    lasttwo = self.internal_proxy_udn[-2:]
                    if hic == lasttwo.lower():
                        hic = "00"  # can't conflict as internal_count can't be 0 for this case
                    proxyuuid = "%s%s" % (self.internal_proxy_udn[:-2], hic)
                else:
                    proxyuuid = self.internal_proxy_udn
                if internal_count == 0:
                    # only need WMP server for one proxy instance
                    startwmp = True
                    wmpcontroller = None
                    wmpcontroller2 = None
                else:
                    startwmp = False
                print "Proxy. Name: " + name
                proxy = Proxy(name, 'WMP', wmptrans, proxyuuid, self.config, None,
                              createwebserver=True, webserverurl=listen_url, wmpurl=serve_url, startwmp=startwmp, dbname=dbname, wmpudn=self.internal_proxy_udn, wmpcontroller=wmpcontroller, wmpcontroller2=wmpcontroller2)
                proxy.start()
                wmpcontroller = proxy.wmpcontroller                              
                wmpcontroller2 = proxy.wmpcontroller2                              
                '''                
                if internal_count == 0:

                    from brisa.core import webserver, network

                    p = network.parse_url(serve_url)
                    self.wmpwebserver = webserver.WebServer(host=p.hostname, port=p.port)
                    self.wmplocation = self.wmpwebserver.get_listen_url()
                    self.wmpwebserver.get_render = proxy.get_render
                    self.wmpwebserver.start()
                '''
                self.proxies.append(proxy)
                self.sonospyproxies[proxyuuid[5:]] = name
                self.wmpfound = True
                internal_count += 1





        #######################################################################
        # webserver resources to serve data
        #######################################################################

        # TODO: replace this option with noweb and don't serve data if it's set
#        if not self.options.nogui:

        if not self.options.proxyonly:

            self.data_delim = '_|_'
            self.search_delim = ':::'
            self.extras_delim = '::::'
    ##        self.escape_entities = {'"' : '&quot;', "'" : '&apos;'}

            self.devicedata = []
            self.devicedatakeys = {}
            self.servermetadata = []

            self.rendererdata = []
            self.renderermetadata = []

            self.queuedata = []
            self.queuedatakeys = {}
    #        self.queuedata_lastindex = 0
            
            self.rootdata = []
            self.rootdatakeys = {}
            self.rootdata_lastindex = 0
            self.rootdatanames = {}
            self.rootdatatype = {}

            self.rootmenus = []
            
            self.gdatasets = {}
            self.gdatakeys = {}
            self.gdataparentkey = {}
            self.gdatatracks = {}
            self.gdata_lastindex = {}
            self.gdataparent = {}

            self.queue_entry = None
            
            getdevicecontroller = GetDeviceController(self.devicedata, 'deviceData')
            setrenderercontroller = SetRendererController(self.renderermetadata, 'rendererData', self.setrenderer)
            pollrenderercontroller = PollRendererController(self.rendererdata, 'rendererPoll', self.pollrenderer)
            actionrenderercontroller = ActionRendererController(self.rendererdata, 'rendererAction', self.actionrenderer)
            pollservercontroller = PollServerController(self.servermetadata, 'serverPoll', self.pollserver)
            pollqueuecontroller = PollQueueController(self.queuedata, 'queuePoll', self.pollqueue)
            rootdatacontroller = GetDataController(self.rootdata, 'rootData', self.getrootdata)
            rootmenucontroller = GetDataController(self.rootmenus, 'rootMenus', self.getrootmenus)
            getdatacontroller = GetDataController(None, 'getData', self.getdata)
            playcontroller = PlayController('playData', self.playdata)

            ws = self.control_point._event_listener.srv
            res = webserver.CustomResource('data')
            res.add_resource(getdevicecontroller)
            res.add_resource(setrenderercontroller)
            res.add_resource(pollrenderercontroller)
            res.add_resource(actionrenderercontroller)
            res.add_resource(pollservercontroller)
            res.add_resource(pollqueuecontroller)
            res.add_resource(rootdatacontroller)
            res.add_resource(rootmenucontroller)
            res.add_resource(getdatacontroller)
            res.add_resource(playcontroller)
            ws.add_resource(res)

            # start MSEARCH

    #        self.control_point.start_search(600.0, "ssdp:all")
    #        run_async_function(self.control_point.start_search, (600.0, "ssdp:all"), 1)
            run_async_function(self.control_point.start_search, (600.0, "ssdp:all"), 0.001)

            #  control proxy
            # TEMP - example simple use of proxy to serve as controller
    #        from controlproxy import ControlProxy
    #        controlproxy = ControlProxy('ControlSink', 'WMP', '', 'uuid:' + str(uuid.uuid4()), self.control_point, '', self.config)
    #        controlproxy.start()
    #        self.proxies.append(controlproxy)

    ###########################################################################
    # webserver resource functions
    ###########################################################################

    # TODO: the data getter routines are not threadsafe, fix them

    def make_utf8(self, text):
        if type(text) is unicode:
            text = text.encode('utf-8')
        return text

    def update_devices(self, device_name, device_type, device_udn):
        ## add item to list
        entry = device_type + '::' + device_name
        self.devicedata.append(entry + self.data_delim)
        self.devicedata.sort()
        self.devicedatakeys[entry] = device_udn

    def update_devices_remove(self, device_name, device_type, device_udn):
        # remove item from list
        entry = device_type + '::' + device_name
        self.devicedata.remove(entry + self.data_delim)
        del self.devicedatakeys[entry]

    def getrootmenus(self, param):
        query = param.split('=')
        entry = query[1]
        udn = self.devicedatakeys[entry]
        del self.rootmenus[:]
        if udn in self.known_zone_players:
            self.rootmenus = self.get_server_menu_options("ZP")
        else:
            self.rootmenus = self.get_server_menu_options("SERVER")
        return self.rootmenus

    def getrootdata(self, param):
        # param will be in utf-8, whereas data is stored in unicode
        param = param.decode('utf-8', 'replace')
        # param may contain escaped chars
        param = unescape(param)

        query = param.split('=')
        entry = query[1]
        udn = self.devicedatakeys[entry]
        device = self.known_media_servers[udn]
        del self.rootdata[:]
        self.rootdatakeys.clear()
        self.rootdata_lastindex = 0
        self.gdatasets.clear()
        self.set_server_device(device)
        # sort the root data
        self.rootdata = sorted(self.rootdata, key=self.gettitle)
        # reassign the keys
        self.rootdata, self.rootdatakeys, self.rootdatanames, self.rootdatatype = self.reassignkeys(self.rootdata, self.rootdatakeys, self.rootdatanames, self.rootdatatype)
        # add the message        
        self.rootdata.append("MESSAGE::" + self.messagebar + self.data_delim)
        return self.rootdata

    def gettitle(self, entry):
        colonpos = entry.rfind('::')
        return entry[colonpos+2:].lower()

    def reassignkeys(self, ilist, ikeys, inames, itypes):
        key = 1
        newlist = []
        newkeys = {}
        newnames = {}
        newtypes = {}
        delimlen = 0 - len(self.data_delim)
        for item in ilist:
            colonpos = item.find('::')
            newentry = str(key) + item[colonpos:]
            newlist.append(newentry)
            newkeys[newentry[:delimlen]] = ikeys[item[:delimlen]]
            newtypes[str(key)] = ikeys[item[:delimlen]]
            newnames[str(key)] = inames[item[:colonpos]]
            key += 1
        return newlist, newkeys, newnames, newtypes

    def update_rootdata(self, title, id, type):
        ref = str(self.rootdata_lastindex+1)
        menu = self.get_server_menu_type(id, type)
        new_entry = ref + "::" + 'R'  + "::" + menu + "::" + title
        self.rootdata.append(new_entry + self.data_delim)
        self.rootdatatype[ref] = (id, type)
        self.rootdatakeys[new_entry] = (id, type)
        self.rootdata_lastindex += 1
        self.rootdatanames[ref] = title

    def update_queuedata(self, title, id, type, ref):
        menu = self.get_server_menu_type(id, type)
        new_entry = ref + "::" + 'R'  + "::" + menu + "::" + title
        self.queuedata.append(new_entry + self.data_delim)
        self.queuedatakeys[new_entry] = (id, type)
        return new_entry

    def getdata(self, param):
        # param will be in utf-8, whereas data is stored in unicode
        param = param.decode('utf-8', 'replace')
        # param may contain escaped chars
        param = unescape(param)
        # param will contain an equals, but can contain more than one (if the operator includes one)

        log.debug(param)

        eqpos = param.find('=')
        entry = param[eqpos+1:]
        if self.search_delim in entry:
            # this entry contains a search string (as entry search_delim searchstring)
            allentries = entry.split(self.search_delim)
            entry = allentries[0]
            searchstring = allentries[1]
            if '::' in searchstring:
                # searchstring contains an operator
                allsearch = searchstring.split('::')
                searchstring = allsearch[0]
                searchoperator = allsearch[1]
                # operator may be coded
                searchoperator = self.decodeoperators(searchoperator)
            else:
                searchoperator = ''
        else:
            searchstring = ''
            searchoperator = ''
        entries = entry.split('::')
        entryref = entries[0]
        entrysid = None
        if '|||' in entryref:
            entryrefs = entryref.split('|||')
            entryref = entryrefs[0]
            entrysid = entryrefs[1]
#        entrytype = entries[1]
#        entrymenu = entries[2]
        hierarchynames = entries[3]
        entryname = hierarchynames.split('|||')[-1]

        # remove hierarchy from entry
        # FIXME: reconstruct entry rather than using replace
        entry = entry.replace(hierarchynames, entryname)

        # special case where id and type are passed from client
        id_passed = False
        next_pos = 4
        if len(entries) >= 6:
            s_id = entries[4]
            s_type = entries[5]
            id_passed = True
            next_pos = 6

        entrydata = entries[next_pos]
        datas = entrydata.split(',')
        dataseq = int(datas[0])
        datastart = int(datas[1])
        datacount = int(datas[2])

        # process dataseq
        if dataseq == 0:
            # special case - do not browse on first call as it's already been done
            first_call = False
            dataseq = 1
        elif dataseq == 1:
            first_call = True
        elif dataseq > 1:
            first_call = False

        setparent = entryref
        if first_call == True:
            self.gdata_lastindex[setparent] = 0

        # remove data from end of entry
        colpos = entry.rfind('::')
        entrykey = entry[:colpos]
        if len(entries) == 6:
            colpos = entrykey.rfind('::')
            entrykey = entrykey[:colpos]
            colpos = entrykey.rfind('::')
            entrykey = entrykey[:colpos]

        # get type
        rootref = self.getrootref(entryref)
        
        log.debug(rootref)
        log.debug(self.rootdatatype)

        if rootref in self.rootdatatype:
            id, type = self.rootdatatype[rootref]
        else:
            id = type = None

        log.debug(id)
        log.debug(type)

        if type == 'SonospyMediaServer_ROOT' or type == 'SonospyServerSearch_ROOT':
            if '_' in entryref:
                type = 'SONOSPYMEDIASERVER'

        log.debug(type)

        if type == 'SONOSPYMEDIASERVER' or type == 'SonospyMediaServer_ROOT' or type == 'SonospyServerSearch_ROOT':

            # special case - internal mediaserver, don't cache

            hierarchynames = hierarchynames.split('|||')
            log.debug(hierarchynames)

            current_server = self.control_point.get_current_server()
            current_udn = current_server.udn[5:]
            if current_udn in self.sonospyproxies.keys():
                # are browsing a sonospy server direct
                spdevice = current_server
                spname = None
            else:
                # are browsing via a ZP
                spdevice = None
                spname = self.sonospyproxies[id]
                # remove the top element, it's a top level container
                hierarchynames = hierarchynames[1:]

            if entrysid:
                id = entrysid
            else:
                if not current_udn in self.sonospyproxies.keys():
                    id = '0'
                    
            root = None
            if type == 'SonospyMediaServer_ROOT':
                root = 'root'
            return self.search_sonospy_media_server_batch(id, spname, spdevice, root=root, entryref=entryref, searchstring=searchstring, searchoperator=searchoperator, start=datastart, count=datacount, hierarchynames=hierarchynames)

        # get set key
        setkey = entryref + ':' + str(dataseq)

        if entrykey in self.rootdatakeys:
            id, type = self.rootdatakeys[entrykey]
        elif entrykey in self.queuedatakeys:
            id, type = self.queuedatakeys[entrykey]
        elif entrykey in self.gdatakeys:
            id, type = self.gdatakeys[entrykey]
        else:
            # check for special case (after checking in key stores in case they have more up to date info)
            if id_passed == True:
                id = s_id
                type = s_type
            else:
                print "entry '" + str(entrykey) + "' not found in rootdata/queuedata/gdata."
                return []
        
        # save queue entry if queue
        if id == 'Q:0' and first_call == True:
            self.queue_entry = entry
            
        # get name of root entry (only need this for a couple of browses, consider moving it to process_browse)
        rootref = self.getrootref(entryref)
        if rootref in self.rootdatanames:
            rootname = self.rootdatanames[rootref]
        else:
            rootname = ''

        print "************************************"
        print "setkey: " + str(setkey)
        print "first_call: " + str(first_call)
        print "dataseq: " + str(dataseq)
        if setkey in self.gdatasets:
            print "len: " + str(len(self.gdatasets[setkey]))
        
        if first_call == True:
            # first time through, process the browse
            self.process_browse(type, id, searchstring=searchstring, searchoperator=searchoperator, name=rootname, sequence=dataseq, count=datacount, setkey=setkey, entryname=entryname)
            return self.gdatasets[setkey]
        else:
            # not first time, check if the data is ready from the first browse initiated async calls
            if setkey in self.gdatasets:
                if dataseq == 1:
                    # special case where initial browse has already been done - don't know count so just return what we have
                    return self.gdatasets[setkey]
                setsize = len(self.gdatasets[setkey])
                if setsize == datacount + 1:    # +1 to cater for the result entry
                    # data for this set is complete, return it
                    return self.gdatasets[setkey]
                elif setsize == datacount + 2:    # +1 to cater for the result entry, plus Napster index starts at zero and affects the last set in a multiple return
                    # TODO: make this Napster specific
                    # data for this set is complete, return it
                    return self.gdatasets[setkey]
            # not ready, return wait with count so far
            dataset = ['NOTREADY' + self.data_delim]
            return dataset

    def browse_queue(self, param):

        # param will be in utf-8, whereas data is stored in unicode
        param = param.decode('utf-8', 'replace')
        # param may contain escaped chars
        param = unescape(param)
        # param will contain an equals, but can contain more than one (if the operator includes one)
        eqpos = param.find('=')
        entry = param[eqpos+1:]
        if self.search_delim in entry:
            # this entry contains a search string (as entry search_delim searchstring)
            allentries = entry.split(self.search_delim)
            entry = allentries[0]
            searchstring = allentries[1]
            if '::' in searchstring:
                # searchstring contains an operator
                allsearch = searchstring.split('::')
                searchstring = allsearch[0]
                searchoperator = allsearch[1]
                # operator may be coded
                searchoperator = self.decodeoperators(searchoperator)
            else:
                searchoperator = ''
        else:
            searchstring = ''
            searchoperator = ''
        entries = entry.split('::')
        entryref = entries[0]
#        entrytype = entries[1]
#        entrymenu = entries[2]
#        entryname = entries[3]

        entrydata = entries[4]
        datas = entrydata.split(',')
        dataseq = int(datas[0])
        datastart = int(datas[1])
        datacount = int(datas[2])

        # remove data from end of entry
        colpos = entry.rfind('::')
        entrykey = entry[:colpos]

        # get set key
        setkey = entryref + ':' + str(dataseq)
        setparent = entryref

        if entrykey in self.rootdatakeys:
            id, type = self.rootdatakeys[entrykey]
        elif entrykey in self.queuedatakeys:
            id, type = self.queuedatakeys[entrykey]
        elif entrykey in self.gdatakeys:
            id, type = self.gdatakeys[entrykey]
        else:
            print "entry '" + str(entrykey) + "' not found in rootdata/queuedata/gdata."
            return

        # get name of root entry (only need this for a couple of browses, consider moving it to process_browse)
        rootref = self.getrootref(entryref)
        if rootref in self.rootdatanames:
            rootname = self.rootdatanames[rootref]
        else:
            rootname = ''
        
        # process the browse
        self.gdata_lastindex[setparent] = 0
        self.process_browse(type, id, searchstring=searchstring, searchoperator=searchoperator, name=rootname, sequence=dataseq, count=datacount, setkey=setkey)

    def getentrytitle(self, gdatakeys, ref):
        ref += '::'
        for entry in gdatakeys.keys():
            if entry.startswith(ref):
                entries = entry.split('::')
                entryname = entries[3]
                return entryname
        return None

    def getrootref(self, ref):
        if '_' in ref:
            ulpos = ref.find('_')
            rootref = ref[:ulpos]
        else:
            rootref = ref
        return rootref

    def getparentref(self, ref):
        if '_' in ref:
            # remove last facet of ref
            ulpos = ref.rfind('_')
            parentref = ref[:ulpos]
        else:
            parentref = '0'
        return parentref

    def update_gdata(self, title, id, type, res=None, xml=None, searchtype=None, searchtitle=None, searchoperators=None, sequence=0, setkey='', parentid=None, extras=None):
        setparent = setkey.split(':')[0]
        ref = self.gdataparent[setparent] + '_' + str(self.gdata_lastindex[setparent]+1)
        if res != None:
            entrytype = 'T'
        else:
            if searchtype != None:
                entrytype = 'S'
            else:
                if type == 'DUMMY':
                    entrytype = 'N'
                else:
                    entrytype = 'C'
        menu = self.get_server_menu_type(id, type)
        new_entry = ref + '::' + entrytype + '::' + menu + '::' + title

        self.gdatakeys[new_entry] = (id, type)
        if parentid != None:
            self.gdataparentkey[id] = parentid
        if res != None:
            self.gdatatracks[new_entry] = (res, xml)

        # append id and type in case receiver is caching
        new_entry += '::' + id + '::' + type

        # append any search criteria to end of entry (but not to the keys/tracks)
        if searchtype != None:
            new_entry += self.search_delim + searchtype + '::' + searchtitle
        if searchoperators != None:
            operators = self.codeoperators(searchoperators)
            new_entry += '::' + operators
        # append any extras to end of entry    
        if extras != None:
            new_entry += self.extras_delim + extras
        self.gdata_lastindex[setparent] += 1

        if sequence != 0:
            self.gdatasets[setkey].append(new_entry + self.data_delim)


    def initialise_gdata_dataset(self, sequence=0, setkey=''):
        if sequence != 0:
            setparent = setkey.split(':')[0]
            self.gdatasets[setkey] = []
            self.gdataparent[setparent] = setparent

    def finalise_gdata_dataset(self, sequence=0, returned=0, total=0, setkey=''):
        if sequence != 0:
            if len(self.gdatasets[setkey]) == 0:
                # nothing was returned, add a dummy entry for display
                self.update_gdata('Nothing found', 'DUMMY', 'DUMMY', sequence=sequence, setkey=setkey)
            self.gdatasets[setkey].append("RETURN::" + str(returned) + ':' + str(total) + self.data_delim)

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

    def setrenderer(self, param):
        # param will be in utf-8, whereas data is stored in unicode
        param = param.decode('utf-8', 'replace')
        # param may contain escaped chars
        param = unescape(param)

        query = param.split('=')
        entry = query[1]
        entries = entry.split('::')
        entrytype = entries[0]
        entryname = entries[1]
        
        # TODO: currently assumes renderer is correct one - need to process one passed
        udn = self.devicedatakeys[entry]
        device = self.known_media_renderers[udn]
        self.set_renderer_device(device)

        del self.renderermetadata[:]

        if udn in self.known_zone_players:
            # manually add queue entry to root data list
            new_entry = self.update_queuedata('Current Queue', 'Q:0', "SonosCurrentQueue_ROOT", 'QQ')
            # return queue entry name
            self.renderermetadata.append("QUEUE::" + new_entry + self.data_delim)
        else:
            # no metadata (pass none so call succeeds)
            self.renderermetadata.append("NONE::NONE" + self.data_delim)
            
        return self.renderermetadata

    def clearprevrendererdata(self):
        self.prev_now_playing_dict.clear()
        self.prev_now_extras_dict.clear()
        self.prev_now_playing_pos = '-'
        self.prev_now_playing_percent = '-'
        self.prev_current_volume = '-'
        self.prev_volume_fixed = '-'
        self.prev_volume_mute = '-'
        self.prev_play_state = '-'
        self.prev_album_art = '-'

    def clearprevrenderermetadata(self):
        self.prev_queue_updateid = '-'

    def pollrenderer(self, param):
        # param will be in utf-8, whereas data is stored in unicode
        param = param.decode('utf-8', 'replace')
        # param may contain escaped chars
        param = unescape(param)

        query = param.split('=')
        entry = query[1]
        entries = entry.split('::')
        entrytype = entries[0]
        entryname = entries[1]
        # NOTE - at the moment we aren't using the passed renderer data to 
        # get info for that specific renderer...
#        udn = self.devicedatakeys[entry]
#        device = self.known_media_renderers[udn]
        self.update_position()
        self.get_renderer_data()
        return self.rendererdata

    def actionrenderer(self, param):
        # param will be in utf-8, whereas data is stored in unicode
        param = param.decode('utf-8', 'replace')
        # param may contain escaped chars
        param = unescape(param)

        query = param.split('=')
        action = query[1]
        if '::' in action:
            actions = action.split('::')
            action = actions[0]
            value = actions[1]
        if action == 'PLAY' or action == 'PAUSE':
            self.do_play()
        elif action == 'STOP':
            self.stop()
        elif action == 'PREVIOUS':
            self.previous()
        elif action == 'NEXT':
            self.next()
        elif action == 'MUTE' or action == 'UNMUTE':
            self.do_mute()
        elif action == 'VOLUME':
            self.do_volume(value)
        self.update_position()
        self.get_renderer_data()
        # add any return from action here
#        new_entry = 'ACTION' + "::" + str(self.@@@@)
#        self.rendererdata.append(new_entry + self.data_delim)
        return self.rendererdata

    def pollserver(self, param):
        # param will be in utf-8, whereas data is stored in unicode
        param = param.decode('utf-8', 'replace')
        # param may contain escaped chars
        param = unescape(param)

        query = param.split('=')
        entry = query[1]
        entries = entry.split('::')
        entrytype = entries[0]
        entryname = entries[1]
        # NOTE - at the moment we aren't using the passed server data to 
        # get info for that specific server...
        udn = self.devicedatakeys[entry]
        device = self.known_media_servers[udn]
        self.get_server_data()
        return self.servermetadata

    def pollqueue(self, param):
        # param will be in utf-8, whereas data is stored in unicode
        param = param.decode('utf-8', 'replace')
        # param may contain escaped chars
        param = unescape(param)
#        print "pollqueue: " + str(param)
        query = param.split('=')
        entry = query[1]
        entries = entry.split('::')
#        entrytype = entries[1]
#        entryname = entries[3]
#        deviceentry = entrytype + '::' + entryname
        
#        # NOTE - at the moment we aren't using the passed server data to 
#        # get info for that specific server...
#        udn = self.devicedatakeys[deviceentry]
#        device = self.known_media_servers[udn]
        self.get_queue_data()
        return self.queuedata

    def get_renderer_data(self):
        # TODO:
        #   this will only cater for a single controlpoint at the moment
        #   - need to pass a controlpoint identifier otherwise a new
        #     controlpoint won't get data that hasn't changed since the last call
        #     (alternately we can return all data instead)
        del self.rendererdata[:]
        for k,v in self.now_playing_dict.iteritems():
            if (not k in self.prev_now_playing_dict) or self.prev_now_playing_dict[k] != v:
                new_entry = k + "::" + v
                self.rendererdata.append(new_entry + self.data_delim)
                self.prev_now_playing_dict[k] = v
        for k,v in self.now_extras_dict.iteritems():
            if (not k in self.prev_now_extras_dict) or self.prev_now_extras_dict[k] != v:
                new_entry = k + "::" + v
                self.rendererdata.append(new_entry + self.data_delim)
                self.prev_now_extras_dict[k] = v
        if self.now_playing_pos != self.prev_now_playing_pos:
            new_entry = 'POSITION' + "::" + self.now_playing_pos
            self.rendererdata.append(new_entry + self.data_delim)
            self.prev_now_playing_pos = self.now_playing_pos
        if self.now_playing_percent != self.prev_now_playing_percent:
            new_entry = 'PERCENT' + "::" + self.now_playing_percent
            self.rendererdata.append(new_entry + self.data_delim)
            self.prev_now_playing_percent = self.now_playing_percent
        current_volume = ("%.0f" % self.current_volume)
        if current_volume != self.prev_current_volume:
            new_entry = 'VOLUME' + "::" + current_volume
            self.rendererdata.append(new_entry + self.data_delim)
            self.prev_current_volume = current_volume
        if self.volume_fixed != self.prev_volume_fixed:
            new_entry = 'VOLUME_FIXED' + "::" + str(self.volume_fixed)
            self.rendererdata.append(new_entry + self.data_delim)
            self.prev_volume_fixed = self.volume_fixed
        if self.volume_mute != self.prev_volume_mute:
            new_entry = 'MUTE' + "::" + str(self.volume_mute)
            self.rendererdata.append(new_entry + self.data_delim)
            self.prev_volume_mute = self.volume_mute
        if self.play_state != self.prev_play_state:
            new_entry = 'STATE' + "::" + str(self.play_state)
            self.rendererdata.append(new_entry + self.data_delim)
            self.prev_play_state = self.play_state
        if self.album_art != self.prev_album_art:
            new_entry = 'ART' + "::" + str(self.album_art)
            self.rendererdata.append(new_entry + self.data_delim)
            self.prev_album_art = self.album_art
        if self.rendererdata == []:
            self.rendererdata.append("NOCHANGE::0" + self.data_delim)

    def get_server_data(self):
        # TODO:
        #   this will only cater for a single controlpoint at the moment
        #   - need to pass a controlpoint identifier otherwise a new
        #     controlpoint won't get data that hasn't changed since the last call
        #     (alternately we can return all data instead)
        del self.servermetadata[:]
#        if self.queue_updateid != self.prev_queue_updateid:
#            new_entry = 'QUEUE' + "::" + self.queue_updateid
#            self.servermetadata.append(new_entry + self.data_delim)
#            self.prev_queue_updateid = self.queue_updateid
        if self.servermetadata == []:
            self.servermetadata.append("NOCHANGE::0" + self.data_delim)
            
    def get_queue_data(self):
        # TODO:
        #   this will only cater for a single controlpoint at the moment
        #   - need to pass a controlpoint identifier otherwise a new
        #     controlpoint won't get data that hasn't changed since the last call
        #     (alternately we can return all data instead)
        del self.queuedata[:]
        if self.queue_updateid != self.prev_queue_updateid:
            new_entry = 'QUEUE' + "::" + self.queue_updateid
            self.queuedata.append(new_entry + self.data_delim)
            self.prev_queue_updateid = self.queue_updateid
        if self.queuedata == []:
            self.queuedata.append("NOCHANGE::0" + self.data_delim)
            
    def playdata(self, param):
        # param will be in utf-8, whereas data is stored in unicode
        param = param.decode('utf-8', 'replace')
        # param may contain escaped chars
        param = unescape(param)

        query = param.split('=')
        request = query[1]

        # check for multi
        if request[0:5] == 'MULTI':
        
            # string is MULTI:::option:::data
            # where data is :::: separated list of entries
            delimpos = request[8:].find(':::')
            option = request[8:8+delimpos]

            del self.current_media_list[:]    
            entrylist = request[8+delimpos+3:].split('::::')
            for entry in entrylist:
                entries = entry.split('::')
                entryref = entries[0]
                type = self.get_root_type(entryref)
#                if type != 'SONOSPYMEDIASERVER' and type != 'SonospyMediaServer_ROOT':
                if type != 'SONOSPYMEDIASERVER' and type != 'SonospyMediaServer_ROOT' and type != 'SonospyServerSearch_ROOT':
                    id, type = self.gdatakeys[entry]
                if entry in self.gdatatracks.keys():
                    res, xml = self.gdatatracks[entry]
                else:
                    res = ''
                    xml = ''
                print "entry: " + str(entry)
                self.current_media_list.append(('', 0, res, '', xml))

        else:        
        
            elements = request.split(self.search_delim)
            entry = elements[0]
            option = elements[1]
            entries = entry.split('::')
            entryref = entries[0]

            entrysid = None
            if '|||' in entryref:
                entryrefs = entryref.split('|||')
                entryref = entryrefs[0]
                entrysid = entryrefs[1]
            hierarchynamelist = entries[3]
            hierarchynames = hierarchynamelist.split('|||')
            entryname = hierarchynames[-1]

            entry = entry.replace(hierarchynamelist, entryname)

            print "entry: " + str(entry)
            type = self.get_root_type(entryref)
            if type == 'SONOSPYMEDIASERVER' or type == 'SonospyMediaServer_ROOT' or type == 'SonospyServerSearch_ROOT':
                id = entrysid
            else:
                id, type = self.gdatakeys[entry]
            print "id: " + str(id)
            print "type: " + str(type)
            if entry in self.gdatatracks.keys():
                res, xml = self.gdatatracks[entry]
            else:
                res = ''
                xml = ''
            print "res: " + str(res)
            print "xml: " + str(xml)
            self.current_media_id = res
            self.current_media_xml = xml
            self.current_media_type = type
            
            del self.current_media_list[:]    
            if self.current_media_id == '' or self.check_for_playlist(self.current_media_id) == True:
                # we're trying to play a container that hasn't provided a URI
                # or has provided a playlist
                # TODO: playlists may be ok for non-Sonos
                # - we need to browse the container and get the URIs for 
                #   its contents
                self.browse_container(id, type, entryref, title=hierarchynames)        

        log.debug(self.current_media_list)
            
        if type == 'SONOSCURRENTQUEUE':
            # special case - playing queue
            option = "PIQ"
            self.current_media_id = self.get_queueURI()
            self.current_media_xml = ''
            ids = id.split('/')
            position = ids[1]
            
            print "option: " + str(option)
            print "current_media_id: " + str(self.current_media_id)
            print "current_media_xml: " + str(self.current_media_xml)
            print "ids: " + str(ids)
            print "position: " + str(position)
            
        else:

            if type != 'SONOSPYMEDIASERVER' and type != 'SonospyMediaServer_ROOT':

                # get id of the server we are serving from        
                rootid = None
                rootref = self.getrootref(entryref)
                if rootref in self.rootdatanames:
                    rootname = self.rootdatanames[rootref]
                    if rootname in self.rootids:
                        rootid = self.rootids[rootname]
                self.fix_metadata(type, rootid)

        log.debug(self.current_media_list)

        print "option: " + str(option)
        
        if option == "PNDQ":
            self.clearprevrendererdata()
            self.play_now_noqueue()
        elif option == "PNAQ":
            self.clearprevrendererdata()
            self.play_now_queue()
        elif option == "AQN":
            self.add_queue('NEXT')
        elif option == "AQE":
            self.add_queue('END')
        elif option == "PS":
            self.clearprevrendererdata()
            self.play_sample_noqueue()
        elif option == "PIQ":            
            self.clearprevrendererdata()
            self.play_in_queue(position)
            


        '''

        elif option == "Rename playlist":
            (model, iter) = treeview.get_selection().get_selected()
            # TODO: save title and id from earlier call
            title = model.get_value(iter, 0)
            id = model.get_value(iter, 1)
# replace with browser edit            success, newtitle = editBox('New playlist name:','Rename playlist', title, 20).ret
            if success == True:
                ret = self.update_playlist_name(id, title, newtitle)
                if ret == True:
                    self.container_treestore.set_value(iter, 0, newtitle)
                else:
                    self.set_messagebar('Unable to rename playlist')

            # TODO: check result

#note - if queue is changed need to retrieve it and update the list if it's in there (either that or invalidate it so it is re-fetched)
#note - need to add same functionality to renderer window
#note - also need to be selective when we can queue/play something (e.g. can we from the root?)

        '''


    def get_root_type(self, entryref):
        rootref = self.getrootref(entryref)
        rootid, roottype = self.rootdatatype[rootref]
        return roottype


    def make_device_name(self, device_object):
        if device_object.udn in self.known_zone_names:
            device_name = self.known_zone_names[device_object.udn] + ' (ZP)'
        else:
            device_name = device_object.friendly_name
            if self.check_full_wmp_clone(device_object) == True:
                device_name += ' (WMP)'
        return device_name
                

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

    def stop_proxies(self):
        log.debug("Stopping proxies")
        for proxy in self.proxies:
            proxy.stop()

    def get_zone_details(self, device):
        return self.control_point.get_zone_attributes(device)

    def radiotime_getlastupdate(self):
        log.debug("#### radiotime_getlastupdate:")
        '''
        <?xml version="1.0" encoding="utf-8"?>
        <soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
          <soap:Body>
            <getLastUpdateResponse xmlns="http://www.sonos.com/Services/1.1">
              <getLastUpdateResult>
                <catalog>string</catalog>
                <favorites>string</favorites>
                <pollInterval>int</pollInterval>
              </getLastUpdateResult>
            </getLastUpdateResponse>
          </soap:Body>
        </soap:Envelope>
        '''
        service = self.control_point.get_rt_service()
        rt_result = service.getLastUpdate()
        log.debug("radiotime_getlastupdate browse_result: %s", rt_result)
        log.debug("radiotime_getlastupdate result: %s", rt_result['Result'])

    def radiotime_getmediaURI(self, id):
        log.debug("#### radiotime_getmediaURI:")
        service = self.control_point.get_rt_service()
        rt_result = service.getMediaURI(id=id)
        log.debug("radiotime_getlastupdate browse_result: %s", rt_result)
        return rt_result
        
    def radiotime_getmediaURL(self, rtURI):
        if rtURI == '' or rtURI == None:
            return 'No RadioTime URI to dereference'
        else:
            try:
                fd = url_fetch(rtURI)
    #        except HTTPError as detail:    # this is 2.6    
            except HTTPError:
                return (None, HTTPError)
            try:
                data = fd.read()
            except:
                log.debug("#### radiotime_getmediaURL fd is invalid")
                return 'radiotime_getmediaURL fd is invalid'
            return data


    def run_test(self, id, root=None):

        log.debug("#### run_test: %s", id)

        win = False
        cd = False
        dp = False
        sp = False

        if win:

            addr = 'http://192.168.0.8:1400/msprox?uuid=02286246-a968-4b5b-9a9a-defd5e9237e0'
            data = '<?xml version="1.0" encoding="utf-8"?><s:Envelope s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><ns0:Browse xmlns:ns0="urn:schemas-upnp-org:service:ContentDirectory:1">'
            data += '<ObjectID>0</ObjectID>'
#            data += '<BrowseFlag>BrowseDirectChildren</BrowseFlag>'
            data += '<BrowseFlag>BrowseMetadata</BrowseFlag>'
            data += '<Filter>*</Filter>'
            data += '<RequestedCount>20</RequestedCount>'
            data += '<StartingIndex>0</StartingIndex>'
#            data += '<SortCriteria>+dc:title</SortCriteria>'
            data += '<SortCriteria></SortCriteria>'
            data += '</ns0:Browse></s:Body></s:Envelope>'
            namespace = "urn:schemas-upnp-org:service:ContentDirectory:1"
            soapaction = "urn:schemas-upnp-org:service:ContentDirectory:1#Browse"
            encoding='utf-8'

            res = HTTPTransport().call(addr, data, namespace, soapaction, encoding)

            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            print "Windows MS Browse:"
            print res            
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"

        if cd:
        
            service = self.control_point.get_cd_service()

            test_result = service.GetSystemUpdateID()
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            print "GetSystemUpdateID:"
            print test_result
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"

            test_result = service.GetAllPrefixLocations(ObjectID='G:')
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            print "GetAllPrefixLocations:"
            print test_result
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
				
    #				FindPrefix
    #					Prefix 

        if dp:
					 
            service = self.control_point.get_dp_service()

            test_result = service.GetHouseholdID()
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            print "GetHouseholdID:"
            print test_result
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            
            test_result = service.GetZoneInfo()
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            print "GetZoneInfo:"
            print test_result
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
            print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"

        if sp:

            service = self.control_point.get_sp_service()
            
            tests = 'R_AudibleActivation', \
                    'R_UpdatePreference', \
                    'R_CustomerID', \
                    'R_RadioPreference', \
                    'R_ShowRhapUPnP', \
                    'R_BrowseByFolderSort', \
                    'R_AudioInEncodeType', \
                    'R_AvailableSvcTrials', \
                    'R_RadioLocation', \
                    'R_ForceReIndex', \
                    'R_PromoVersion', \
                    'RINCON_AssociatedZPUDN'

            for t in tests:
                test_result = service.GetString(VariableName=t)
                print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
                print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
                print "var = " + t
                print test_result
                print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"
                print "TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST TEST"



       






    def browse_napster_async(self, id, root=None, newtype=None, searchstring='', searchoperator='', sequence=0, count=-1, setkey=''):

        service = self.control_point.get_np_service()

        if self.napster_loggedin == False:

            self.set_messagebar("Logging in to Napster...")

            # get Napster prefix
            prefix = self.music_services_type['Napster']

            # get service details for that prefix
            for servicename, servicedetails in self.services.items():

                if servicename.startswith(prefix):
                    # TODO: work out which un/pw details are pertinent
                    self.napster_username = servicedetails['Username0']
                    self.napster_password = servicedetails['Password0']
                    self.napster_UDN      = servicename
                    break

            if self.napster_username == '':
                self.set_messagebar('Napster username not found')
                return
                        
            self.napster_loggedin = service.login(self.napster_username, self.napster_password)

            self.set_messagebar("")

            if self.napster_loggedin == False:
                self.set_messagebar('Unable to log in to Napster')
                return

        log.debug("#### browse_napster: %s", id)

        # initialise dataset
        self.initialise_gdata_dataset(sequence, setkey)

        search = False
        if root != None:
        
            # root items - need to add search option
            self.napster_root = [self.NSS_BASE]
            self.update_gdata('Search Napster', self.NSS_BASE, newtype, sequence=sequence, setkey=setkey)

        elif id == self.NSS_BASE:
        
            # search - manually create search options list
            optioncount = len(self.napster_search)

            for i in range(optioncount):
                searchid = self.NSS_BASE + str(i)
                self.napster_search_ids[searchid] = i
                self.update_gdata(self.napster_search[i], searchid, newtype, searchtype=self.napster_search[i], searchtitle=self.napster_search_title, sequence=sequence, setkey=setkey)
                
            # finalise dataset
            self.finalise_gdata_dataset(sequence, optioncount, optioncount, setkey)

            return
            
        else:

            if self.check_napster_search(id) == True:
            
                # if we get here then the user has sent a search string from the client
                searchtype = self.napster_search[self.napster_search_ids[id]]
                searchid = 'search:' + searchtype.lower()
                self.napster_search_string = searchstring
                search = True

        if root == None:
            id_param = id
        else:
            id_param = root

        # set up for browsing
        returned = 0    # seed returned count, which is also starting index
        if count == -1: count = 100     # initial count to retrieve so first call is fast
        self.current_browse_id = id_param

        # run the first call synchronously so this thread waits for the return
        if search == True:
            result = service.search(id=searchid, term=self.napster_search_string, index=0, count=count)
        else:
            result = service.getMetadata(id=id_param, index=0, count=count)

        # process the results returned
        cargo = (service, id_param, root, count, returned, sequence, search, searchstring, newtype, setkey)
        self.show_napster_result(result, cargo)

    def browse_napster_async_browse(self, service, id, root, returned, count, sequence, search, searchstring, newtype, setkey):
        # call browse asynchronously
        run_async_call(service.getMetadata,
                       success_callback=self.show_napster_result,
                       error_callback=self.show_napster_result,
                       success_callback_cargo=(service, id, root, count, returned, sequence, search, searchstring, newtype, setkey), 
                       error_callback_cargo=(service, id, root, count, returned, sequence, search, searchstring, newtype, setkey),
                       delay=0, 
                       id=id,
                       index=returned,
                       count=count)
           
    def browse_napster_async_search(self, service, id, root, returned, count, sequence, search, searchstring, newtype, setkey):
        # call search asynchronously
        run_async_call(service.search,
                       success_callback=self.show_napster_result,
                       error_callback=self.show_napster_result,
                       success_callback_cargo=(service, id, root, count, returned, sequence, search, searchstring, newtype, setkey), 
                       error_callback_cargo=(service, id, root, count, returned, sequence, search, searchstring, newtype, setkey),
                       delay=0, 
                       id=id,
                       term=searchstring,
                       index=returned,
                       count=count)
           
    def show_napster_result(self, browse_result, cargo):

        result = browse_result
        service, id, root, count, returned, sequence, search, searchstring, newtype, setkey = cargo

#        if id != self.current_browse_id:
#            # another browse has been started, abandon this one
#            return

        success = result['success']
        if success != '1':
            self.set_messagebar('Error returned from Napster')
            return

        items = result['collections']
        ns = '{%s}' % service.serviceversion
        index = int(result[ns + 'index'])
        ncount = int(result[ns + 'count'])
        thisreturned = ncount
        returned += thisreturned
        total = int(result[ns + 'total'])

        # if we haven't got all the results, set another call off
        if returned < total:
            newsetkey = setkey[:setkey.find(':')+1] + str(sequence+1)
            if search == True:
                self.browse_napster_async_search(service, id, root, returned, count, sequence+1, search, searchstring, newtype, newsetkey)
            else:
                self.browse_napster_async_browse(service, id, root, returned, count, sequence+1, search, searchstring, newtype, newsetkey)

        if sequence > 1:
            # initialise dataset (already done for first pass)
            self.initialise_gdata_dataset(sequence, setkey)

        for item in items:

            id = item.find(ns + 'id').text
            title = item.find(ns + 'title').text     # TODO: cater for language using stringId
            itemType = item.find(ns + 'itemType').text

            if root != None:
                # save root id's
                self.napster_root.append(id)

            if itemType == 'other' or itemType == 'artist' or itemType == 'album' or itemType == 'playlist':
            
                extras = None
                if itemType == 'album':
                    artist = item.find(ns + 'artist').text
                    art = item.find(ns + 'albumArtURI').text
                    extras = 'creator=' + ustr(artist) + '::' + 'art=' + str(art)
            
                self.update_gdata(title, id, newtype, sequence=sequence, setkey=setkey, extras=extras)

            elif itemType == 'error':

                self.update_gdata(title, id, newtype, res='', xml='', sequence=sequence, setkey=setkey)

            elif itemType == 'stream':

#                radiotype = radiotimeMediaMetadata().from_element(item)

                id = id.replace(':', '%3a')

                uri = 'x-sonos-mms:' + id + '?sid=' + self.music_services['Napster'].Id + '&flags=32'

                parentid = id

                parentid = parentid.replace(':', '%3a')

                xml =  '<item id="' + '10030020' + id + '" parentID="' + '1004006c' + parentid + '" restricted="true">'
                xml += '<dc:title>' + title + '</dc:title>'
                xml += '<upnp:class>object.item.audioItem.musicTrack</upnp:class>'
                xml += '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">' + self.napster_UDN + '</desc>'
                xml += '</item>'

###                title = self.get_napster_track_details(ns, item)

                extras = None
                trackmetadata = item.find(ns + 'trackMetadata')
                if trackmetadata != None:   # TODO: check this
                    artist = trackmetadata.find(ns + 'artist').text
                    album = trackmetadata.find(ns + 'album').text
                    art = trackmetadata.find(ns + 'albumArtURI').text
                    extras = 'creator=' + ustr(artist) + '::' + 'album=' + str(album) + '::' + 'art=' + str(art)

                self.update_gdata(title, id, newtype, res=uri, xml=xml, sequence=sequence, setkey=setkey, extras=extras)

            else:

                # TODO: also need to cater for 'program'

                print "HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP"
                print "HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP"
                print "HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP"

                print "Unknown itemType " + str(itemType) + " in browseNapster!"

                print "HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP"
                print "HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP"
                print "HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP"

        # finalise dataset
        self.finalise_gdata_dataset(sequence, thisreturned, total, setkey)







###    def get_napster_track_details(self, ns, item):
###
###        title = escape(item.find(ns + 'title').text)
###        metadata = item.find(ns + 'trackMetadata')
###        album = escape(metadata.find(ns + 'album').text)
###        artist = escape(metadata.find(ns + 'artist').text)
###        
###        return title + '\n    <span foreground="blue"><small>Album: ' + album + '</small></span>\n    <span foreground="red"><small>Artist: ' + artist + '</small></span>'


###    def get_library_track_details(self, item):
###
###        title = album = artist = ''
###        if hasattr(item, 'title'): title = escape(item.title)
###        if hasattr(item, 'album'): album = escape(item.album)
###        if hasattr(item, 'creator'): artist = escape(item.creator)
###
###        return title + '\n    <span foreground="blue"><small>Album: ' + album + '</small></span>\n    <span foreground="red"><small>Artist: ' + artist + '</small></span>'


###    def get_mediaserver_track_details(self, item):
###
###        title = album = artist = ''
###        if hasattr(item, 'title'): title = escape(item.title)
###        if hasattr(item, 'album'): album = escape(item.album)
###        if hasattr(item, 'artists'): artist = escape(item.artists[0])
###
###        return title + '\n    <span foreground="blue"><small>Album: ' + album + '</small></span>\n    <span foreground="red"><small>Artist: ' + artist + '</small></span>'


    def check_napster_search(self, id):
        nsearch = False
        if id in self.napster_search_ids:
            nsearch = True
        return nsearch

    def check_library_search(self, id):
        lsearch = False
        if id in self.library_search_ids:
            lsearch = True
        return lsearch

    def check_mediaserver_search(self, id):
        msearch = False
        if id in self.mediaserver_search_ids:
            msearch = True
        return msearch

    def check_sonospyserver_search(self, id):
        ssearch = False
        if id in self.sonospyserver_search_ids:
            ssearch = True
        return ssearch

    def browse_deezer(self, id, root=None):
        self.set_messagebar('Browsing Deezer is not yet supported by pycpoint')

    def browse_twitter(self, id, root=None):
        self.set_messagebar('Browsing Twitter is not yet supported by pycpoint')


    def browse_radiotime(self, id, root=None, newtype=None, sequence=0, setkey=''):

        radiotimecount = 2000
        
        log.debug("#### browse_radiotime: %s", id)
        
        service = self.control_point.get_rt_service()

        if root == None:
            id_param = id
            browse_result = service.getMetadata(id=id_param, index=0, count=radiotimecount)
        else:
            id_param = root
            if id_param == 'root':
#                browse_result = service.getMetadata(id=id_param, index=0, count=97)
                browse_result = service.getMetadata(id=id_param, index=0, count=radiotimecount)
            else:
                browse_result = service.getMetadata(id=id_param, index=0, count=radiotimecount)
        
        items = browse_result['Result']
        index = int(browse_result['{http://www.sonos.com/Services/1.1}index'])
        count = int(browse_result['{http://www.sonos.com/Services/1.1}count'])
        returned = count
        total = int(browse_result['{http://www.sonos.com/Services/1.1}total'])
        log.debug("browse_radiotime: index=%s count=%s total=%s", index, count, total)

        self.set_messagebar("Returned %d of %d." % (returned, total))

        if total > radiotimecount:
            while returned < total:
                b = service.getMetadata(id=id_param, index=returned, count=radiotimecount)

                index = int(b['{http://www.sonos.com/Services/1.1}index'])
                count = int(b['{http://www.sonos.com/Services/1.1}count'])
# Radiotime reduces the number of results available as you query and increases the index
#                total = int(b['{http://www.sonos.com/Services/1.1}total'])
                for item in b['Result'].getchildren():
                    items.append(item)
                returned += count
                log.debug("browse_radiotime: index=%s count=%s total=%s", index, count, total)

                self.set_messagebar("Returned %d of %d." % (returned, total))

        # initialise dataset
        self.initialise_gdata_dataset(sequence, setkey)
                
        for item in items.getchildren():
            '''
			<mediaCollection>
				<id>y1</id>
				<title>Music</title>
				<itemType>container</itemType>
				<authRequired>false</authRequired>
				<canPlay>false</canPlay>
				<canEnumerate>true</canEnumerate>
				<canCache>true</canCache>
				<homogeneous>false</homogeneous>
				<canAddToFavorite>false</canAddToFavorite>
				<canScroll>false</canScroll>
			</mediaCollection>

			<mediaCollection>
				<id>p115805</id>
				<title>104.1 Music</title>
				<itemType>show</itemType>
				<authRequired>false</authRequired>
				<canPlay>false</canPlay>
				<canEnumerate>true</canEnumerate>
				<canCache>false</canCache>
				<homogeneous>false</homogeneous>
				<canAddToFavorite>false</canAddToFavorite>
				<canScroll>false</canScroll>
			</mediaCollection>
			
            <mediaMetadata>
                <id>s1254</id>
                <title>Radio Cook Islands 630 (Community)</title>
                <itemType>stream</itemType>
                <language>en</language>
                <country>COK</country>
                <genreId>g249</genreId>
                <genre>Community</genre>
                <twitterId/>
                <liveNow>true</liveNow>
                <onDemand>false</onDemand>
                <streamMetadata>
                    <bitrate>16</bitrate>
                    <reliability>55</reliability>
                    <logo>http://radiotime-logos.s3.amazonaws.com/s1254q.gif</logo>
                    <title>630 AM</title>
                    <subtitle>Avarua, Cook Islands</subtitle>
                    <secondsRemaining>0</secondsRemaining>
                    <secondsToNextShow>0</secondsToNextShow>
                    <nextShowSeconds>0</nextShowSeconds>
                </streamMetadata>
            </mediaMetadata>

			<mediaMetadata>
                <id>p115805:schedule</id>
                <title>Next available in 6 hours 59 minutes</title>
                <itemType>other</itemType>
                <language>en</language>
                <country>USA</country>
                <genreId>g115</genreId>
                <genre>Modern Rock</genre>
                <twitterId>1041itjustrocks</twitterId>
                <liveNow>false</liveNow>
                <onDemand>false</onDemand>
                <streamMetadata>
                    <currentShowId>p115805</currentShowId>
                    <currentShow>104.1 Music</currentShow>
                    <currentHost/>
                    <bitrate>0</bitrate>
                    <reliability>0</reliability>
                    <logo>http://radiotime-logos.s3.amazonaws.com/s32717q.gif</logo>
                    <secondsRemaining>0</secondsRemaining>
                    <secondsToNextShow>25145</secondsToNextShow>
                    <nextShowStationId>s32717</nextShowStationId>
                    <nextShowSeconds>3600</nextShowSeconds>
                </streamMetadata>
			</mediaMetadata>
            
			<mediaMetadata>
				<id>t31332491:p116360</id>
				<title>the neapolitan revival</title>
                <mimeType>audio/vnd.radiotime</mimeType>
                <itemType>track</itemType>
                <liveNow>false</liveNow>
                <onDemand>true</onDemand>
                <trackMetadata>
                    <artist>John Aielli</artist>
                    <albumArtURI>http://radiotime-logos.s3.amazonaws.com/p0q.gif</albumArtURI>
                    <genre>Music Talk</genre>
                    <duration>0</duration>
                    <associatedShow>Aielli Unleashed podcast</associatedShow>
                    <associatedHost>John Aielli</associatedHost>
                </trackMetadata>
			</mediaMetadata>
            
            '''

            element = ElementTree.fromstring(item.text)

            id = element.find('{http://www.sonos.com/Services/1.1}id').text
            title = element.find('{http://www.sonos.com/Services/1.1}title').text
            itemType = element.find('{http://www.sonos.com/Services/1.1}itemType').text

            if itemType == 'container':
                self.update_gdata(title, id, newtype, sequence=sequence, setkey=setkey)

            elif itemType == 'show':
                self.update_gdata(title, id, newtype, sequence=sequence, setkey=setkey)

            elif itemType == 'other':
                xml = None    # cannnot play these future items

                self.update_gdata(title, id, newtype, res='', xml=xml, sequence=sequence, setkey=setkey)

                
            elif itemType == 'track':
            
                radiotype = radiotimeMediaMetadata().from_element(element)

                res = 'x-sonosapi-stream:' + id + '?sid=' + self.music_services['RadioTime'].Id + '&flags=32'

                parentid = id_param

                xml =  '<item id="' + 'F00030020' + radiotype.id + '" parentID="' + 'F000b0064' + parentid + '" restricted="true">'
                xml += '<dc:title>' + radiotype.title + '</dc:title>'
                xml += '<upnp:class>object.item.audioItem.musicTrack.recentShow</upnp:class>'
                xml += '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">RINCON_AssociatedZPUDN</desc>'
                xml += '</item>'

                self.update_gdata(title, id, newtype, res=res, xml=xml, sequence=sequence, setkey=setkey)
                
            elif itemType == 'stream':

                radiotype = radiotimeMediaMetadata().from_element(element)

                res = 'x-sonosapi-stream:' + id + '?sid=' + self.music_services['RadioTime'].Id + '&flags=32'

                # TODO:
                # find out where other attribs come from

                parentid = id_param

                xml =  '<item id="' + 'F00090020' + radiotype.id + '" parentID="' + 'F00080064' + parentid + '" restricted="true">'
                xml += '<dc:title>' + radiotype.title + '</dc:title>'
                xml += '<upnp:class>object.item.audioItem.audioBroadcast</upnp:class>'
                xml += '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">RINCON_AssociatedZPUDN</desc>'
                xml += '</item>'

                self.update_gdata(title, id, newtype, res=res, xml=xml, sequence=sequence, setkey=setkey)

            else:

                # TODO: also need to cater for 'program'

                print "HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP"
                print "HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP"
                print "HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP"

                print "Unknown itemType " + str(itemType) + " in browseRadiotime!"

                print "HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP"
                print "HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP"
                print "HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP HELP"

        # finalise dataset
        self.finalise_gdata_dataset(sequence, total, total, setkey)















    def get_queue_length(self, id, server):
        mscount = 2
        browse_result = self.control_point.simplebrowse(id, 'BrowseDirectChildren', '*', 0, mscount, '+dc:title', server)
        self.current_queue_length = int(browse_result['TotalMatches'])
        self.current_queue_updateid = int(browse_result['UpdateID'])
        log.debug("#### get_queue_length: %s", self.current_queue_length)




    def browse_sonos_library_async(self, id, root=None, newtype=None, searchstring='', searchoperator='', sequence=0, count=-1, setkey=''):
        log.debug("#### browse_sonos_library: %s", id)

        print "bsla:"
        print "    id: " + str(id)
        print "    root: " + str(root)
        print "    newtype: " + str(newtype)
        print "    searchstring: " + str(searchstring)
        print "    searchoperator: " + str(searchoperator)
        print "    sequence: " + str(sequence)
        print "    count: " + str(count)
        
        # TODO: only get sort and search caps first time through
        
        search_caps = self.control_point.get_search_capabilities()
        log.debug("#### browse_sonos_library search capabilities: %s", search_caps)

        sort_caps = self.control_point.get_sort_capabilities()
        log.debug("#### browse_sonos_library sort capabilities: %s", sort_caps)
        if 'SortCaps' in sort_caps:
            sort_capabilities =  sort_caps['SortCaps']
        else:
            sort_capabilities =  ''
        if re.search('dc:title', sort_capabilities) != None:
            sort = '+dc:title'
        else:
            sort = ''

        # initialise dataset
        self.initialise_gdata_dataset(sequence, setkey)

        search = False
        if root != None:
            # root items - need to add search option
            self.library_root = [self.LSS_BASE]
            self.update_gdata('Search Library', self.LSS_BASE, newtype, sequence=sequence, setkey=setkey)
            
        elif id == self.LSS_BASE:
            # search - manually create search options list
            optionscount = len(self.library_search)
            for i in range(optionscount):
                searchid = self.LSS_BASE + str(i)
                self.library_search_ids[searchid] = i
                self.update_gdata(self.library_search[i], searchid, newtype, searchtype=self.library_search[i], searchtitle=self.library_search_title, sequence=sequence, setkey=setkey)
            # finalise dataset
            self.finalise_gdata_dataset(sequence, optionscount, optionscount, setkey)
            return
            
        else:
        
            if self.check_library_search(id) == True:
            
                # if we get here then the user has sent a search string from the client
                searchtype = self.library_search[self.library_search_ids[id]]
                self.library_search_string = searchstring
                searchstring = 'A:' + searchtype.upper() + ':' + self.library_search_string
                search = True
                
        if search == True:
            id_param = searchstring
        else:
            if root == None:
                id_param = id
            else:
                id_param = 'A:'

        # set up for browsing
        returned = 0    # seed returned count, which is also starting index
        if count == -1: count = 100     # initial count to retrieve so first call is fast
        filter = '*'
        self.current_browse_id = id_param

        # run the first call synchronously so this thread waits for the return
        result = self.control_point.browse(id_param, 'BrowseDirectChildren', filter, 0, count, sort)
        
        # process the results returned
        cargo = (id_param, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey)
        self.show_library_result(result, cargo)

    def browse_sonos_library_async_browse(self, id, returned, count, sequence, filter, sort, search, searchstring, newtype, setkey):
        # call browse asynchronously
        run_async_call(self.control_point.browse,
                       success_callback=self.show_library_result,
                       error_callback=self.show_library_result,
                       success_callback_cargo=(id, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey), 
                       error_callback_cargo=(id, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey),
                       delay=0, 
                       object_id=id,
                       browse_flag='BrowseDirectChildren',
                       filter=filter,
                       starting_index=returned,
                       requested_count=count,
                       sort_criteria=sort)

    def show_library_result(self, browse_result, cargo):

        # TODO - fix so that error_callback goes to an error routine and not here!

        id, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey = cargo

#        if id != self.current_browse_id:
#            # another browse has been started, abandon this one
#            return
        if 'faultcode' in browse_result:
            self.set_messagebar(browse_result['detail'])
            return
        elif not 'Result' in browse_result:
            self.set_messagebar('Unknown response from browse request')
            return
        
        items = browse_result['Result']
        total = int(browse_result['TotalMatches'])
        thisreturned = int(browse_result['NumberReturned'])
        returned += thisreturned

        # if we haven't got all the results, set another call off
        if returned < total:
            newsetkey = setkey[:setkey.find(':')+1] + str(sequence+1)
            self.browse_sonos_library_async_browse(id, returned, count, sequence+1, filter, sort, search, searchstring, newtype, newsetkey)

        if sequence > 1:
            # initialise dataset (already done for first pass)
            self.initialise_gdata_dataset(sequence, setkey)

        for item in items:

#            print "sonos library item: " + str(item)
#            print "  title: " + str(item.title)
#            if isinstance(item, MusicAlbum):
#                print "  creator: " + str(item.creator)
#                print "  date: " + str(item.date)
#                print "  artists: " + str(item.artists)
#                print "  album_art_uri: " + str(item.album_art_uri)
#                print "  description: " + str(item.description)
#                print "  contributors: " + str(item.contributors)
 
            if isinstance(item, Container):

#                data = self.convert_item_to_uridata(item)
                # adjust the items to display
                if item.id == "A:ARTIST":
                    item.title = "DO NOT DISPLAY"
                else:
                    # let everything else through
                    pass

                if not item.title == "DO NOT DISPLAY":
                
                    extras = None
                    if isinstance(item, MusicAlbum):
                    
                        album_art = getAlbumArtURL(self.control_point.get_cd_service(), item.album_art_uri)

                        extras = 'creator=' + ustr(item.creator) + '::' + 'art=' + str(album_art)

                    self.update_gdata(item.title, item.id, newtype, sequence=sequence, setkey=setkey, extras=extras)

            else:

                xml = item.to_string()
                xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
                xml = xml.replace('ns0:','')

                if item.resources:
                    res = item.resources[0].value
                else:
                    res = ''

###                title = self.get_library_track_details(item)

                if search == True:
                    album = creator = ''
                    if hasattr(item, 'album'): album = item.album
                    if hasattr(item, 'creator'): creator = item.creator
                    extras = 'creator=' + ustr(creator) + '::' + 'album=' + ustr(album)
                    self.update_gdata(item.title, item.id, newtype, res=res, xml=xml, sequence=sequence, setkey=setkey, extras=extras)
                else:
                    self.update_gdata(item.title, item.id, newtype, res=res, xml=xml, sequence=sequence, setkey=setkey)

        # finalise dataset
        self.finalise_gdata_dataset(sequence, thisreturned, total, setkey)
















           
    def browse_media_server_root(self, searchvars=None):
        '''
        This special case browse is only called on selecting a media server for the first time
        '''
    
        log.debug("#### browse_media_server_root: %s", id)

        server_search, server_root, server_search_string, server_search_title, server_search_type, server_search_id = searchvars
        
        id_param = 0
        mscount = 200

        search_caps = self.control_point.get_search_capabilities()
        # {'SearchCaps': 'dc:title,dc:creator,upnp:artist,upnp:genre,upnp:album,dc:date,upnp:originalTrackNumber,upnp:class,@id,@refID,@protocolInfo'}
        self.current_server_search_capabilities = search_caps['SearchCaps']
# for testing        self.current_server_search_capabilities = '@id,@refID,@restricted,dc:creator,dc:date,dc:description,dc:language,dc:publisher,dc:title,microsoft:artistAlbumArtist,microsoft:artistConductor,microsoft:artistPerformer,microsoft:authorComposer,microsoft:authorOriginalLyricist,microsoft:authorWriter,microsoft:serviceProvider,microsoft:userEffectiveRating,microsoft:userEffectiveRatingInStars,microsoft:userRating,microsoft:userRatingInStars,res@bitrate,res@duration,res@protection,res@protocolInfo,res@size,upnp:actor,upnp:album,upnp:artist,upnp:artist@role,upnp:author,upnp:author@role,upnp:class,upnp:director,upnp:genre,upnp:originalTrackNumber,upnp:producer,upnp:rating,upnp:toc,upnp:userAnnotation,@protocolInfo'

        # reset search options unless it's a zoneplayer (which are hardcoded)
        current_server = self.control_point.get_current_server()
        if not current_server.udn in self.known_zone_players:
            del server_search[:]

        if '%s' in server_search_title:
            server_search_title = server_search_title % current_server.friendly_name
            
        for cap in self.current_server_search_capabilities.split(','):
            if cap != '':
                server_search.append(cap)
        log.debug("#### browse_media_server search capabilities: %s", search_caps)
        
        sort_caps = self.control_point.get_sort_capabilities()
        log.debug("#### browse_media_server sort capabilities: %s", sort_caps)
        # {'SortCaps': 'dc:title,dc:creator,upnp:artist,upnp:genre,upnp:album,dc:date,upnp:originalTrackNumber,Philips:shuffle,pv:rating'}
        if 'SortCaps' in sort_caps:
            sort_capabilities =  sort_caps['SortCaps']
        else:
            sort_capabilities =  ''
        if re.search('dc:title', sort_capabilities) != None:
            sort = '+dc:title'
        else:
            sort = ''
        self.current_server_sort_capabilities = sort_capabilities
        self.current_server_sort = sort

        # default XML to have nothing to play
        xml = [None, None]

        browse_result = self.control_point.browse(id_param, 'BrowseDirectChildren', '*', 0, mscount, sort)
        
        if 'faultcode' in browse_result:
            self.set_messagebar(browse_result['detail'])
            return
        elif not 'Result' in browse_result:
            self.set_messagebar('UNKNOWN RESPONSE FROM BROWSE REQUEST')
            return
        
        items = browse_result['Result']
        total = int(browse_result['TotalMatches'])
        returned = int(browse_result['NumberReturned'])

        # check whether we're at the root of a music server (music/pictures/video/playlists)              
        serverroot = True
        for item in items:
            if item.id != '1' and item.id != '2' and item.id != '3' and item.id != '12':
                serverroot = False
                break
        if serverroot == True:
            # at root - browse again for Music (1)
            id_param = 1
            browse_result = self.control_point.browse(id_param, 'BrowseDirectChildren', '*', 0, mscount, sort)
            if 'faultcode' in browse_result:
                self.set_messagebar(browse_result['detail'])
                return
            elif not 'Result' in browse_result:
                self.set_messagebar('UNKNOWN RESPONSE FROM BROWSE REQUEST')
                return
            items = browse_result['Result']
            total = int(browse_result['TotalMatches'])
            returned = int(browse_result['NumberReturned'])

        # should not get lots of entries at root level, but just in case
        if total > mscount:
            while returned < total:
                b = self.control_point.browse(id_param, 'BrowseDirectChildren', '*', returned, mscount, sort)
                items = items + b['Result']
                returned += int(b['NumberReturned'])

        log.debug("browse_media_server_root: %s items, %s total, %s returned", items, total, returned)

        # only allow search if it's supported
        if server_search != []:
            if searchvars != None:
                server_root = [server_search_id]
                self.update_rootdata(server_search_title, server_search_id, server_search_type)

        for item in items:

            if isinstance(item, Container):

                data = self.convert_item_to_uridata(item)

                # check if current server is a zone player
                current_server = self.control_point.get_current_server()
                if current_server.udn in self.known_zone_players:
                    # as it's a Sonos, adjust the items to display when at the root level
                    if item.id == "A:":
                        # this is the root of the Sonos Library
                        item.title = "Music Library"
                        type = "SonosLibrary_ROOT"
                    elif item.id == "S:":
                        # this is the music shares root
                        type = "SonosShares_ROOT"
                    elif item.id == "Q:":
                        # this is the current queue root
                        # for the current queue, there is a single child avt 0 that is the queue
#                        item.id = "Q:0"                    
#                        item.title = "Current Queue"
#                        type = "SonosCurrentQueue_ROOT"

                        # do not pass this through, queue is associated with renderer
                        item.title = "DO NOT DISPLAY"

                    elif item.id == "SQ:":
                        # this is the saved queues root
                        item.title = "Sonos Playlists"
                        type = "SonosSavedQueues_ROOT"
                    elif item.id == "R:":
                        # this is the old internet radio container
                        item.title = "DO NOT DISPLAY"
                    elif item.id == "G:":
                        # this is Now Playing
                        item.title = "DO NOT DISPLAY"
                    elif item.id == "AI:":
                        # this is the Audio Inputs root
                        item.title = "Line-In"
                        type = "LineIn_ROOT"
                    elif item.id == "EN:":
                        # this is the Entire Network root
                        item.title = "DO NOT DISPLAY"
                    else:
                        # let everything else through - ought not to be any unless Sonos have changed something
                        type = "SonosOther_ROOT"

                    if not item.title == "DO NOT DISPLAY":
                        # add the container to the list
                        self.update_rootdata(item.title, item.id, type)

                else:

                    log.debug("browse_media_server_root container: title:%s id:%s", item.title, item.id)
                    if current_server.manufacturer == 'Henkelis' and current_server.model_name == 'Windows Media Player Sharing':
#                        self.update_rootdata(item.title, item.id, "SonospyMediaServer_ROOT")
                        self.update_rootdata(item.title, item.id, "SONOSPYMEDIASERVER")
                    else:
                        # assume generic music server
                        self.update_rootdata(item.title, item.id, "MusicServer_ROOT")

            else:

                # TODO: fix this
                # currently rootdata cannot hold item res and xml data, plus the web client
                # will create an accordion and we don't want items in that
                '''

                # there ought not to be non-container items at root level, but just in case
                xml = item.to_string()
                xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
                xml = xml.replace('ns0:','')

                if item.resources:
                    res = item.resources[0].value
                else:
                    res = ''

###                title = self.get_mediaserver_track_details(item)

                # check if current server is a zone player
                current_server = self.control_point.get_current_server()
                if current_server.udn in self.known_zone_players:
                    self.update_rootdata(item.title, item.id, 'SONOSMUSICSERVER')
                else:
                    log.debug("browse_media_server_root item: title:%s id:%s", item.title, item.id)
###                    self.update_rootdata(item.title, item.id, 'MUSICSERVER', res=res, xml=xml)
                    self.update_rootdata(item.title, item.id, 'MUSICSERVER')
                '''

        # if current server is a zone player, append any available services
        current_server = self.control_point.get_current_server()
        if current_server.udn in self.known_zone_players:
            
            service_result = self.control_point.get_music_services()
            log.debug("get_music_services result: %s", service_result)
            
            # <AvailableServiceTypeList>7,11,519</AvailableServiceTypeList>
            self.AvailableServiceTypeList = service_result['AvailableServiceTypeList']
            availableservicetypes = self.AvailableServiceTypeList.split(',')
            
            items = service_result['AvailableServiceDescriptorList']
            itemcount = 0
            
            xml = [None, None]    # nothing to play at this level

            for item in items:
                self.update_rootdata(item.Name, item.Id, item.Name + "_ROOT")
                self.music_services[item.Name] = item
                
                # there appear to be more service entries than types
                suffix = ''
                if itemcount < len(availableservicetypes):
                    suffix = availableservicetypes[itemcount]
                    itemcount += 1
                    
                self.music_services_type[item.Name] = 'SA_RINCON' + suffix + '_'

                '''                    
                <AvailableServiceDescriptorList>
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
                </AvailableServiceDescriptorList>
                ''' 
                    
            '''
            <AvailableServiceListVersion>RINCON_000E5823A88A01400:236</AvailableServiceListVersion>
            '''
            self.AvailableServiceListVersion = service_result['AvailableServiceListVersion']

        # if current server is a zone player, append any third party media servers
        current_server = self.control_point.get_current_server()
        if current_server.udn in self.known_zone_players:
            zt_sid = self.control_point.get_zt_service(current_server).event_sid

            # TODO: check whether this can occur
            if self.thirdpartymediaservers == {}:
                return

#            print "~~~~~~~~~~~~~~~~~~~~~~~~~"
#            print "third party media servers"
            
            mediaservers = self.thirdpartymediaservers[zt_sid]
            xml = [None, None]    # nothing to play at this level

            for num, mediaserver in mediaservers.items():

#                print "MS: " + str(mediaserver['Name'])

                if mediaserver['UDN'] in self.sonospyproxies.keys():
                    type = 'SonospyMediaServer_ROOT'
                else:
                    if mediaserver['Name'].find('Windows Media') != -1:
                        type = 'MSMediaServer_ROOT'
                    else:
                        type = 'ThirdPartyMediaServer_ROOT'
                self.update_rootdata(mediaserver['Name'], mediaserver['UDN'], type)

#                print mediaserver['Name']
#                print mediaserver['UDN']
#                print type
#                print

                # save udn's of third party media servers, unless already set from device discovery
                if not mediaserver['Name'] in self.rootids:
                    self.rootids[mediaserver['Name']] = mediaserver['UDN']

                # save udn's of MS media servers
                if type == 'MSMediaServer_ROOT':
                    self.msrootids[mediaserver['UDN']] = mediaserver['Name']

#            print "~~~~~~~~~~~~~~~~~~~~~~~~~"
       

    def browse_media_server(self, id, root=None, searchstring='', searchoperator='', setkey=''):
        '''
        Generic browse routine
        '''
        log.debug("#### browse_media_server: %s", id)
        mscount = 2000
        sort = self.current_server_sort

        # default XML to have nothing to play
        xml = [None, None]

        mssearch = False
        check_search = False
        if root != None:
            # root specified - may need to add search option
            # only allow it if it's supported
            if self.mediaserver_search != []:
                check_search = True

        elif id == self.MSS_BASE:
        
            # search - manually create search options list
            for i in range(len(self.mediaserver_search)):
                searchid = self.MSS_BASE + str(i)
                self.mediaserver_search_ids[searchid] = i
                searchtype = self.mediaserver_search[i]
                self.update_gdata(searchtype, searchid, 'MUSICSERVER', searchtype=searchtype, searchtitle=self.mediaserver_search_title, searchoperators=self.ms_search_operators[searchtype], setkey=setkey)

            count = len(self.mediaserver_search)
            self.set_messagebar("Returned %d of %d." % (count, count))
            return

        else:

            if self.check_mediaserver_search(id) == True:
        
                # if we get here then the user has sent a search string from the client
                searchtype = self.mediaserver_search[self.mediaserver_search_ids[id]]
                self.mediaserver_search_string = searchstring
                searchstring = searchtype + ' ' + searchoperator + ' "' + self.mediaserver_search_string + '"'
                print searchstring
                mssearch = True

        # root has already been browsed in browse_media_server_root, so no need to browse as 0
        id_param = id

        if mssearch == True:
            self.search_media_server(id, searchtype, searchstring)
            return
            
        browse_result = self.control_point.browse(id_param, 'BrowseDirectChildren', '*', 0, mscount, sort)
        
        if 'faultcode' in browse_result:
            self.set_messagebar(browse_result['detail'])
            return
        elif not 'Result' in browse_result:
            self.set_messagebar('UNKNOWN RESPONSE FROM BROWSE REQUEST')
            return
        
        items = browse_result['Result']
        total = int(browse_result['TotalMatches'])
        returned = int(browse_result['NumberReturned'])
#        log.debug("browse_media_server: %s items, %s total, %s returned", items, total, returned)

        self.set_messagebar("Returned %d of %d." % (returned, total))

        if total > mscount:
            while returned < total:
                b = self.control_point.browse(id_param, 'BrowseDirectChildren', '*', returned, mscount, sort)
                items = items + b['Result']
                returned += int(b['NumberReturned'])
                self.set_messagebar("Returned %d of %d." % (returned, total))

        # check whether we're at the root of the music server (music/pictures/video/playlists)              
        # if so, we don't want to add a search here
        if check_search == True:
            serverroot = True
            for item in items:
                if item.id != '1' and item.id != '2' and item.id != '3' and item.id != '12':
                    serverroot = False
                    break
            if serverroot == False:
                self.mediaserver_root = [self.MSS_BASE]
                self.update_gdata(self.mediaserver_search_title, self.MSS_BASE, 'SONOSMUSICSERVER', setkey=setkey)
                
        for item in items:

            # filter out 2 (video) and 3 (pictures) for non-Sonos
            current_server = self.control_point.get_current_server()
            if not current_server.udn in self.known_zone_players:
                if item.id == "2" or item.id == "3":
                    continue

            if isinstance(item, Container):

                data = self.convert_item_to_uridata(item)

                # TODO: only need this code first time through

                # check if current server is a zone player
                current_server = self.control_point.get_current_server()
                if current_server.udn in self.known_zone_players:
                    self.update_gdata(item.title, item.id, 'SONOSMUSICSERVER', setkey=setkey)

                else:
                    # if not ZP, assume generic music server
                    self.update_gdata(item.title, item.id, 'MUSICSERVER', setkey=setkey)

            else:

                # TODO: save items in temp list, then post process them to:
                # 1) Suppress duplicates, choosing which to display from a list based on type (e.g. FLAC vs MP3)
                # 2) Display extra info for duplicates (e.g. location)
                # 3) Other things?
                # Make this/these options selectable via a config option

                xml = item.to_string()
                xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
                xml = xml.replace('ns0:','')

                if item.resources:
                    res = item.resources[0].value
                else:
                    res = ''

###                title = self.get_mediaserver_track_details(item)

                # check if current server is a zone player
                current_server = self.control_point.get_current_server()
                if current_server.udn in self.known_zone_players:
                    
                    self.update_gdata(item.title, item.id, 'SONOSMUSICSERVER', res=res, xml=xml, setkey=setkey)
                    
                else:

                    self.update_gdata(item.title, item.id, 'MUSICSERVER', res=res, xml=xml, setkey=setkey)


















    def browse_media_server_async(self, id, root=None, newtype=None, searchstring='', searchoperator='', sequence=0, count=-1, setkey='', device=None):
        '''
        Generic async browse routine
        Assumes that search has been initialised from browse_media_server_root
        '''
        log.debug("#### browse_media_server_async: %s", id)

        print "bmsa:"
        print "    id: " + str(id)
        print "    sequence: " + str(sequence)
        print "    setkey: " + str(setkey)

        search = False
        if id == self.MSS_BASE:

            # initialise dataset
            self.initialise_gdata_dataset(sequence, setkey)
        
            # search - manually create search options list
            optioncount = len(self.mediaserver_search)
            for i in range(optioncount):
                searchid = self.MSS_BASE + str(i)
                self.mediaserver_search_ids[searchid] = i
                searchtype = self.mediaserver_search[i]
                self.update_gdata(searchtype, searchid, newtype, searchtype=searchtype, searchtitle=self.mediaserver_search_title, searchoperators=self.ms_search_operators[searchtype], sequence=sequence, setkey=setkey)

            # finalise dataset
            self.finalise_gdata_dataset(sequence, optioncount, optioncount, setkey)

            return

        else:
        
            if self.check_mediaserver_search(id) == True:

                # if we get here then the user has sent a search string from the client
                searchtype = self.mediaserver_search[self.mediaserver_search_ids[id]]
                self.mediaserver_search_string = searchstring
                searchstring = searchtype + ' ' + searchoperator + ' "' + self.mediaserver_search_string + '"'
                search = True

        # set up for browsing
        returned = 0    # seed returned count, which is also starting index
        if count == -1: count = 100     # initial count to retrieve so first call is fast
        filter = self.current_server_filter
        sort = self.current_server_sort
        self.current_browse_id = id

        # run the first call synchronously so this thread waits for the return
        if search == False:
            result = self.control_point.browse(id, 'BrowseDirectChildren', filter, 0, count, sort, device=device)
        else:
            result = self.control_point.search(1, searchstring, '*', 0, count, sort, device=device)
        
        # process the results returned
        cargo = (id, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey, device)
        self.show_browse_result(result, cargo)

    def browse_media_server_async_browse(self, id, returned, count, sequence, filter, sort, search, searchstring, newtype, setkey, device):
        # call browse asynchronously
        run_async_call(self.control_point.browse,
                       success_callback=self.show_browse_result,
                       error_callback=self.show_browse_result,
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
           
    def browse_media_server_async_search(self, id, returned, count, sequence, filter, sort, search, searchstring, newtype, setkey, device):
        # call search asynchronously
        run_async_call(self.control_point.search,
                       success_callback=self.show_browse_result,
                       error_callback=self.show_browse_result,
                       success_callback_cargo=(id, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey, device), 
                       error_callback_cargo=(id, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey, device),
                       delay=0, 
                       container_id=1,
                       search_criteria=searchstring,
                       filter=filter,
                       starting_index=returned,
                       requested_count=count,
                       sort_criteria=sort,
                       device=device)

    def show_browse_result(self, browse_result, cargo):

        id, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey, device = cargo

        print "sbr:"
        print "    sequence: " + str(sequence)
        print "    setkey: " + str(setkey)

#        if id != self.current_browse_id:
#            # another browse has been started, abandon this one
#            return
        if 'faultcode' in browse_result:
            self.set_messagebar(browse_result['detail'])
            return
        elif not 'Result' in browse_result:
            self.set_messagebar('Unknown response from browse request')
            return
        
        items = browse_result['Result']
        total = int(browse_result['TotalMatches'])
        thisreturned = int(browse_result['NumberReturned'])
        returned += thisreturned

        # if we haven't got all the results, set another call off
        if returned < total:
            newsetkey = setkey[:setkey.find(':')+1] + str(sequence+1)
            if search == False:
                self.browse_media_server_async_browse(id, returned, count, sequence+1, filter, sort, search, searchstring, newtype, newsetkey, device)
            else:
                self.browse_media_server_async_search(id, returned, count, sequence+1, filter, sort. search, searchstring, newtype, newsetkey, device)

        # initialise dataset
        self.initialise_gdata_dataset(sequence, setkey)

        for item in items:

            if isinstance(item, Container):

                extras = None
                if isinstance(item, MusicAlbum):
                
                    album_art = getAlbumArtURL(self.control_point.get_cd_service(), item.album_art_uri)
                
                    extras = 'creator=' + ustr(item.creator) + '::' + 'art=' + str(album_art)

#                data = self.convert_item_to_uridata(item)
                self.update_gdata(item.title, item.id, newtype, sequence=sequence, setkey=setkey, extras=extras)

            else:

                xml = item.to_string()
                xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
                xml = xml.replace('ns0:','')

                if item.resources:
                    res = item.resources[0].value
                else:
                    res = ''

###                title = self.get_mediaserver_track_details(item)

                title = ''
#                if hasattr(item, 'title'): title = escape(item.title)
                if hasattr(item, 'title'): title = item.title

                extras = None
                if isinstance(item, MusicTrack):
                    album = artist = ''
#                    if hasattr(item, 'album'): album = escape(item.album)
#                    if hasattr(item, 'creator'): creator = escape(item.creator)
                    if hasattr(item, 'album'): album = item.album
                    if hasattr(item, 'creator'): creator = item.creator
                    extras = 'creator=' + ustr(creator) + '::' + 'album=' + ustr(album)

#                self.update_gdata(item.title, item.id, newtype, res=res, xml=xml, sequence=sequence, setkey=setkey)
                self.update_gdata(title, item.id, newtype, res=res, xml=xml, sequence=sequence, setkey=setkey, extras=extras)



        # finalise dataset
        self.finalise_gdata_dataset(sequence, thisreturned, total, setkey)











    def browse_media_server_children(self, id):
        '''
        Generic browse routine to get all children of supplied id
        '''
        log.debug("#### browse_media_server_children: %s", id)
        mscount = 2000
        sort = self.current_server_sort
        self.set_messagebar("Creating playlist...")

        browse_result = self.control_point.browse(id, 'BrowseDirectChildren', '*', 0, mscount, sort)
        
        if 'faultcode' in browse_result:
            self.set_messagebar(browse_result['detail'])
            return
        elif not 'Result' in browse_result:
            self.set_messagebar('UNKNOWN RESPONSE FROM BROWSE REQUEST')
            return
        
        items = browse_result['Result']
        total = int(browse_result['TotalMatches'])
        returned = int(browse_result['NumberReturned'])
        log.debug("browse_media_server_children: %s items, %s total, %s returned", items, total, returned)

        self.set_messagebar("Returned %d of %d." % (returned, total))

        if total > mscount:
            while returned < total:
                b = self.control_point.browse(id, 'BrowseDirectChildren', '*', returned, mscount, sort)
                items = items + b['Result']
                returned += int(b['NumberReturned'])
                self.set_messagebar("Returned %d of %d." % (returned, total))

        playlist = []

        for item in items:

            if isinstance(item, Container):

                # child is a container, need to browse that too
                playlist += self.browse_media_server_children(item.id)

            else:

                xml = item.to_string()
                xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
                xml = xml.replace('ns0:','')

                if item.resources:
                    res = item.resources[0].value
                    dur = self.makeseconds(item.resources[0].duration)
                else:
                    res = ''
                    dur = 0

                playlist.append((item.title, str(dur), res, item.id, xml))

        return playlist


    def make_playlist(self, entries, type='M3U'):

        if type == 'M3U':

            playlist_name = 'playlist.m3u'
    
            playlist = '#EXTM3U\n'
            for title, duration, res, id, xml in entries:
                playlist += '#EXTINF:' + str(duration) + ',' + title + '\n'
                playlist += res + '\n'

        elif type == 'ASX':

            playlist_name = 'playlist.asx'

            playlist = '<asx version="3.0">\n'
            playlist += '<title>Green Day - 21st Century Breakdown</title>\n'

            for title, duration, res, id, xml in entries:
                playlist += '<entry><title>' + title + '</title>'
                playlist += '<ref href="' + res + '" /></entry>\n'

            playlist += '</asx>\n'

        elif type == 'PLS':

            playlist_name = 'playlist.pls'

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

            playlist_name = 'playlist.rsq'

            playlist = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:dlna="urn:schemas-dlna-org:metadata-1-0/" xmlns:pv="http://www.pv.com/pvns/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'

            for title, duration, res, id, xml in entries:
                playlist += xml

            playlist += '</DIDL-Lite>'

        print playlist

        local_path = 'playlists/'
        local_location = local_path + playlist_name

        f = open(local_location, 'w')
        f.write(playlist)
        f.close()

        playlist_path = os.path.join(os.getcwd(), local_path, playlist_name)
        self.control_point._event_listener.srv.add_static_file(webserver.StaticFile(playlist_name, playlist_path))

        uri = 'http://' + self.control_point._event_listener.srv.host + ':' + str(self.control_point._event_listener.srv.port) + '/' + playlist_name

#        uri = 'file:///home/mark/UPnP/pycpoint-0.6.7/playlists/playlist.rsq'

        return uri










    def search_media_server(self, id, searchtype, searchstring, setkey=''):
        '''
        Generic search routine
        '''
        
        log.debug("#### search_media_server: %s", id)
        mscount = 200
        sort = self.current_server_sort
        
        self.set_messagebar("Searching...")

        # default XML to have nothing to play
        xml = [None, None]

        search_result = self.control_point.search(1, searchstring, '*', 0, mscount, sort)

#        print search_result
        
        if 'faultcode' in search_result:
            self.set_messagebar(browse_result['detail'])
            return
        elif not 'Result' in search_result:
            self.set_messagebar('UNKNOWN RESPONSE FROM BROWSE REQUEST')
            return
        
        items = search_result['Result']
        total = int(search_result['TotalMatches'])
        returned = int(search_result['NumberReturned'])
#        log.debug("search_media_server: %s items, %s total, %s returned", items, total, returned)

        self.set_messagebar("Returned %d of %d." % (returned, total))

        if total > mscount:
            while returned < total:
                b = self.control_point.search(1, searchcriteria, '*', returned, mscount, sort)
                items = items + b['Result']
                returned += int(b['NumberReturned'])
                self.set_messagebar("Returned %d of %d." % (returned, total))

        for item in items:

            # filter out 2 (video) and 3 (pictures) for non-Sonos
            current_server = self.control_point.get_current_server()
            if not current_server.udn in self.known_zone_players:
                if item.id == "2" or item.id == "3":
                    continue

            if isinstance(item, Container):

                data = self.convert_item_to_uridata(item)

                # TODO: only need this code first time through

                # check if current server is a zone player
                current_server = self.control_point.get_current_server()
                if current_server.udn in self.known_zone_players:
                    self.update_gdata(item.title, item.id, 'SONOSMUSICSERVER', setkey=setkey)
                else:
                    # if not ZP, assume generic music server
                    self.update_gdata(item.title, item.id, 'MUSICSERVER', setkey=setkey)

            else:

                # TODO: save items in temp list, then post process them to:
                # 1) Suppress duplicates, choosing which to display from a list based on type (e.g. FLAC vs MP3)
                # 2) Display extra info for duplicates (e.g. location)
                # 3) Other things?
                # Make this/these options selectable via a config option

                xml = item.to_string()
                xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
                xml = xml.replace('ns0:','')

                if item.resources:
                    res = item.resources[0].value
                else:
                    res = ''

###                title = self.get_mediaserver_track_details(item)

                # check if current server is a zone player
                current_server = self.control_point.get_current_server()
                if current_server.udn in self.known_zone_players:

                    self.update_gdata(item.title, item.id, 'SONOSMUSICSERVER', res=res, xml=xml, setkey=setkey)
                else:

                    self.update_gdata(item.title, item.id, 'MUSICSERVER', res=res, xml=xml, setkey=setkey)























    def browse_thirdparty_media_server(self, name, id, root=None, setkey=''):
        log.debug("#### browse_thirdparty_media_server: %s", id)
        
        tpmscount = 2000

        sort_caps = self.control_point.get_sort_capabilities()
        log.debug("#### browse_media_server sort capabilities: %s", sort_caps)
#       {'SortCaps': 'dc:title,dc:creator,upnp:artist,upnp:genre,upnp:album,dc:date,upnp:originalTrackNumber,Philips:shuffle,pv:rating'}
        if 'SortCaps' in sort_caps:
            sort_capabilities =  sort_caps['SortCaps']
        else:
            sort_capabilities =  ''
        if re.search('dc:title', sort_capabilities) != None:
            sort = '+dc:title'
        else:
            sort = ''
        
        if root == None:
            id_param = id
        else:
            id_param = '0'

        browse_result = self.control_point.browsetpms(name, id_param, 'BrowseDirectChildren', '*', 0, tpmscount, sort)
        
        if 'faultcode' in browse_result:
            self.set_messagebar(browse_result['detail'])
            return
        elif not 'Result' in browse_result:
            self.set_messagebar('UNKNOWN RESPONSE FROM BROWSE REQUEST')
            return
        
        
        items = browse_result['Result']
        total = int(browse_result['TotalMatches'])
        returned = int(browse_result['NumberReturned'])
#        log.debug("browse_media_server: %s items, %s total, %s returned", items, total, returned)

        self.set_messagebar("Returned %d of %d." % (returned, total))

        if total > tpmscount:
            while returned < total:
                b = self.control_point.browsetpms(name, id_param, 'BrowseDirectChildren', '*', returned, tpmscount, sort)
                items = items + b['Result']
                returned += int(b['NumberReturned'])

                self.set_messagebar("Returned %d of %d." % (returned, total))
                
        for item in items:

            # filter out 2 (video) and 3 (pictures) for Sonos TPMS
            if item.id == "2" or item.id == "3":
                continue

            if isinstance(item, Container):

#                data = self.convert_item_to_uridata(item)
                self.update_gdata(item.title, item.id, 'THIRDPARTYMEDIASERVER', setkey=setkey)

            else:

                xml = item.to_string()
                xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
                xml = xml.replace('ns0:','')

                if item.resources:
                    res = item.resources[0].value
                else:
                    res = ''

                self.update_gdata(item.title, item.id, 'THIRDPARTYMEDIASERVER', res=res, xml=xml, setkey=setkey)















    def browse_thirdparty_media_server_async(self, name, id, root=None, newtype=None, searchstring='', searchoperator='', sequence=0, count=-1, setkey=''):

        print "tpms:"
        print "    name: " + str(name)
        print "    id: " + str(id)
        print "    root: " + str(root)
        print "    newtype: " + str(newtype)

        # THESE RELATE TO THE ZP NOT THE TPMS!       
        # TODO: only need to do this the first time through
        sort_caps = self.control_point.get_sort_capabilities()
        if 'SortCaps' in sort_caps:
            sort_capabilities =  sort_caps['SortCaps']
        else:
            sort_capabilities =  ''
        if re.search('dc:title', sort_capabilities) != None:
            sort = '+dc:title'
        else:
            sort = ''
        
        if root == None:
            id_param = id
        else:
            id_param = '0'

        # set up for browsing
        returned = 0    # seed returned count, which is also starting index
        if count == -1: count = 100     # initial count to retrieve so first call is fast
        filter = '*'
        self.current_browse_id = id_param
        search = False

        # run the first call synchronously so this thread waits for the return
        result = self.control_point.browsetpms(name, id_param, 'BrowseDirectChildren', filter, 0, count, sort)
        
        # process the results returned
        cargo = (name, id_param, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey)
        self.show_tpms_result(result, cargo)

    def browse_thirdparty_media_server_async_browse(self, name, id, returned, count, sequence, filter, sort, search, searchstring, newtype, setkey):
        # call browse asynchronously
        run_async_call(self.control_point.browsetpms,
                       success_callback=self.show_tpms_result,
                       error_callback=self.show_tpms_result,
                       success_callback_cargo=(name, id, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey), 
                       error_callback_cargo=(name, id, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey),
                       delay=0,
                       name=name, 
                       object_id=id,
                       browse_flag='BrowseDirectChildren',
                       filter=filter,
                       starting_index=returned,
                       requested_count=count,
                       sort_criteria=sort)

    def show_tpms_result(self, browse_result, cargo):

        name, id, count, returned, sequence, filter, sort, search, searchstring, newtype, setkey = cargo

#        if id != self.current_browse_id:
#            # another browse has been started, abandon this one
#            return
        if 'faultcode' in browse_result:
            self.set_messagebar(browse_result['detail'])
            return
        elif not 'Result' in browse_result:
            self.set_messagebar('Unknown response from browse request')
            return
        
        items = browse_result['Result']
        total = int(browse_result['TotalMatches'])
        thisreturned = int(browse_result['NumberReturned'])
        returned += thisreturned

        # if we haven't got all the results, set another call off
        if returned < total:
            newsetkey = setkey[:setkey.find(':')+1] + str(sequence+1)
            self.browse_thirdparty_media_server_async_browse(name, id, returned, count, sequence+1, filter, sort, search, searchstring, newtype, newsetkey)

        # initialise dataset
        self.initialise_gdata_dataset(sequence, setkey)

        for item in items:

##            # filter out 2 (video) and 3 (pictures) for Sonos TPMS
##            if item.id == "2" or item.id == "3":
##                continue

            if isinstance(item, Container):

                extras = None
                if isinstance(item, MusicAlbum):
                
                    album_art = getAlbumArtURL(self.control_point.get_cd_service(), item.album_art_uri)
                
                    extras = 'creator=' + ustr(item.creator) + '::' + 'art=' + str(album_art)

                self.update_gdata(item.title, item.id, newtype, sequence=sequence, setkey=setkey, extras=extras)

            else:

                xml = item.to_string()
                xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
                xml = xml.replace('ns0:','')

                if item.resources:
                    res = item.resources[0].value
                else:
                    res = ''

                self.update_gdata(item.title, item.id, newtype, res=res, xml=xml, sequence=sequence, setkey=setkey)

        # finalise dataset
        self.finalise_gdata_dataset(sequence, thisreturned, total, setkey)


    def browse_thirdparty_media_server_children(self, name, id):
        log.debug("#### browse_thirdparty_media_server_children: %s", id)
        
        tpmscount = 2000

        sort_caps = self.control_point.get_sort_capabilities()
        log.debug("#### browse_media_server sort capabilities: %s", sort_caps)
        if 'SortCaps' in sort_caps:
            sort_capabilities =  sort_caps['SortCaps']
        else:
            sort_capabilities =  ''
        if re.search('dc:title', sort_capabilities) != None:
            sort = '+dc:title'
        else:
            sort = ''
        
        self.set_messagebar("Creating playlist...")

        browse_result = self.control_point.browsetpms(name, id, 'BrowseDirectChildren', '*', 0, tpmscount, sort)
        
        if 'faultcode' in browse_result:
            self.set_messagebar(browse_result['detail'])
            return
        elif not 'Result' in browse_result:
            self.set_messagebar('UNKNOWN RESPONSE FROM BROWSE REQUEST')
            return
        
        items = browse_result['Result']
        total = int(browse_result['TotalMatches'])
        returned = int(browse_result['NumberReturned'])
        log.debug("browse_media_server_children: %s items, %s total, %s returned", items, total, returned)

        self.set_messagebar("Returned %d of %d." % (returned, total))

        if total > tpmscount:
            while returned < total:
                b = self.control_point.browsetpms(name, id, 'BrowseDirectChildren', '*', returned, tpmscount, sort)
                items = items + b['Result']
                returned += int(b['NumberReturned'])

                self.set_messagebar("Returned %d of %d." % (returned, total))
                
        playlist = []

        for item in items:

            if isinstance(item, Container):

                # child is a container, need to browse that too
                playlist += self.browse_thirdparty_media_server_children(name, item.id)

            else:

                xml = item.to_string()
                xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
                xml = xml.replace('ns0:','')

                if item.resources:
                    res = item.resources[0].value
                    dur = self.makeseconds(item.resources[0].duration)
                else:
                    res = ''
                    dur = 0

                playlist.append((item.title, str(dur), res, item.id, xml))

        return playlist


    def search_thirdparty_media_server(self, name, id, root=None, setkey=''):
        log.debug("#### search_thirdparty_media_server: %s", id)
        
        tpmscount = 2000
        
        if root == None:
            id_param = id
        else:
            id_param = '0'

        self.set_messagebar("Searching...")

        searchcriteria = ''
        sortcriteria = ''
#        filter = 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber'
        filter = ''
        browse_result = self.control_point.searchtpms(name, None, id_param, searchcriteria, filter, 0, tpmscount, sortcriteria)
        
        if 'faultcode' in browse_result:
            self.set_messagebar(browse_result['detail'])
            return
        elif not 'Result' in browse_result:
            self.set_messagebar('UNKNOWN RESPONSE FROM BROWSE REQUEST')
            return
        
        items = browse_result['Result']
        total = int(browse_result['TotalMatches'])
        returned = int(browse_result['NumberReturned'])
#        log.debug("browse_media_server: %s items, %s total, %s returned", items, total, returned)

        self.set_messagebar("Returned %d of %d." % (returned, total))

        if total > tpmscount:
            while returned < total:
                b = self.control_point.searchtpms(name, None, id_param, searchcriteria, filter, 0, tpmscount, sortcriteria)
                items = items + b['Result']
                returned += int(b['NumberReturned'])

                self.set_messagebar("Returned %d of %d." % (returned, total))
                
        for item in items:

            if isinstance(item, Container):

#                data = self.convert_item_to_uridata(item)
                self.update_gdata(item.title, item.id, 'THIRDPARTYMEDIASERVER', setkey=setkey)

            else:

                xml = item.to_string()
                xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
                xml = xml.replace('ns0:','')

                self.update_gdata(item.title, item.id, 'THIRDPARTYMEDIASERVER', res=item.resources[0].value, xml=xml, setkey=setkey)


    def search_ms_media_server(self, name, id, root=None, sequence=0, setkey=''):

        log.debug("#### search_ms_media_server: %s", id)
        
        msmscount = 2000

        # default XML to have nothing to play
        xml = [None, None]
        
        if root != None:
        
            # initialise dataset
            self.initialise_gdata_dataset(sequence, setkey)
                    
            # root items - manually create list
            for item in self.msms_root_items:
                self.update_gdata(item[0], item[1], 'MSMEDIASERVER', sequence=sequence, setkey=setkey, parentid=id)

            # finalise dataset
            count = len(self.msms_root_items)
            self.finalise_gdata_dataset(sequence, count, count, setkey)

            return

        elif id == '101':

            # initialise dataset
            self.initialise_gdata_dataset(sequence, setkey)
                    
            # rating items - manually create list
            for item in self.msms_rating_items:
                self.update_gdata(item[0], item[1], 'MSMEDIASERVER', sequence=sequence, setkey=setkey, parentid=id)

            # finalise dataset
            count = len(self.msms_rating_items)
            self.finalise_gdata_dataset(sequence, count, count, setkey)

            return

        # not special processing, use SOAP action            
        id_param = id

        action = 'SEARCH'
        if id in self.msms_search_lookup:
            searchcriteria = self.msms_search_lookup[id]
            searchcriteria += ' and @refID exists false'
            # HACK: storageFolder does not seem to work with search
            if id == '14':
                action = 'BROWSE'
                sortcriteria = self.msms_search_browse_sortcriteria['DEFAULT']
        else:
            parentid = self.gdataparentkey[id]
            if parentid in self.msms_search_lookup_item.keys():
                searchitem = self.msms_search_lookup_item[parentid]
            else:
                searchitem = 'BROWSE'
            if searchitem == 'BROWSE':
                # we are at object level, so Browse instead
                action = 'BROWSE'
                if parentid in self.msms_search_browse_sortcriteria.keys():
                    sortcriteria = self.msms_search_browse_sortcriteria[parentid]
                else:
                    sortcriteria = self.msms_search_browse_sortcriteria['DEFAULT']
            else:
                searchcriteria = self.msms_search_lookup[parentid] + " and " + searchitem
                searchcriteria += ' and @refID exists false'

        if action == 'SEARCH':
            log.debug("Searchcriteria: %s" % searchcriteria)
            browse_result = self.control_point.searchtpms(name, None, id_param, searchcriteria, 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber', 0, msmscount, '+dc:title')
        else:
            browse_result = self.control_point.browsetpms(name, None, id_param, 'BrowseDirectChildren', 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber', 0, msmscount, sortcriteria)

        if 'faultcode' in browse_result:
            self.set_messagebar(browse_result['detail'])
            return
        elif not 'Result' in browse_result:
            self.set_messagebar('UNKNOWN RESPONSE FROM BROWSE REQUEST')
            return
        
        items = browse_result['Result']
        total = int(browse_result['TotalMatches'])
        returned = int(browse_result['NumberReturned'])

        self.set_messagebar("Returned %d of %d." % (returned, total))

        if total > msmscount:
            while returned < total:
                if action == 'SEARCH':
                    b = self.control_point.searchtpms(name, None, id_param, searchcriteria, 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber', 0, msmscount, '+dc:title')
                else:
                    b = self.control_point.browsetpms(name, None, id_param, 'BrowseDirectChildren', 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber', 0, msmscount, sortcriteria)
                items = items + b['Result']
                returned += int(b['NumberReturned'])
                self.set_messagebar("Returned %d of %d." % (returned, total))

        # initialise dataset
        self.initialise_gdata_dataset(sequence, setkey)
                
        for item in items:

            if isinstance(item, Container):

#                data = self.convert_item_to_uridata(item)
                self.update_gdata(item.title, item.id, 'MSMEDIASERVER', sequence=sequence, setkey=setkey, parentid=id)

            else:

                xml = item.to_string()
                xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
                xml = xml.replace('ns0:','')
                
                self.update_gdata(item.title, item.id, 'MSMEDIASERVER', res=item.resources[0].value, xml=xml, sequence=sequence, setkey=setkey, parentid=id)

        # finalise dataset
        self.finalise_gdata_dataset(sequence, returned, total, setkey)


    def search_ms_media_server_children(self, name, id):

        log.debug("#### search_ms_media_server_children: %s", id)
        
        msmscount = 2000

        self.set_messagebar("Creating Playlist...")

        action = 'SEARCH'
        if id in self.msms_search_lookup:
            searchcriteria = self.msms_search_lookup[id]
            searchcriteria += ' and @refID exists false'
            # HACK: storageFolder does not seem to work with search
            if id == '14':
                action = 'BROWSE'
                sortcriteria = self.msms_search_browse_sortcriteria['DEFAULT']
        else:
            parentid = self.gdataparentkey[id]
            if parentid in self.msms_search_lookup_item.keys():
                searchitem = self.msms_search_lookup_item[parentid]
            else:
                searchitem = 'BROWSE'
            if searchitem == 'BROWSE':
                # we are at object level, so Browse instead
                action = 'BROWSE'
                if parentid in self.msms_search_browse_sortcriteria.keys():
                    sortcriteria = self.msms_search_browse_sortcriteria[parentid]
                else:
                    sortcriteria = self.msms_search_browse_sortcriteria['DEFAULT']
            else:
                searchcriteria = self.msms_search_lookup[parentid] + " and " + searchitem
                searchcriteria += ' and @refID exists false'

        if action == 'SEARCH':
            browse_result = self.control_point.searchtpms(name, None, id, searchcriteria, 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber', 0, msmscount, '+dc:title')
        else:
            browse_result = self.control_point.browsetpms(name, None, id, 'BrowseDirectChildren', 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber', 0, msmscount, sortcriteria)
        
        if 'faultcode' in browse_result:
            self.set_messagebar(browse_result['detail'])
            return
        elif not 'Result' in browse_result:
            self.set_messagebar('UNKNOWN RESPONSE FROM BROWSE REQUEST')
            return
        
        items = browse_result['Result']
        total = int(browse_result['TotalMatches'])
        returned = int(browse_result['NumberReturned'])

        self.set_messagebar("Returned %d of %d." % (returned, total))

        if total > msmscount:
            while returned < total:
                if action == 'SEARCH':
                    b = self.control_point.searchtpms(name, None, id, searchcriteria, 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber', 0, msmscount, '+dc:title')
                else:
                    b = self.control_point.browsetpms(name, None, id, 'BrowseDirectChildren', 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber', 0, msmscount, sortcriteria)
                items = items + b['Result']
                returned += int(b['NumberReturned'])
                self.set_messagebar("Returned %d of %d." % (returned, total))
                
        playlist = []

        for item in items:

            if isinstance(item, Container):

                # child is a container, need to browse that too
                playlist += self.search_ms_media_server_children(name, item.id)

            else:

                xml = item.to_string()
                xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
                xml = xml.replace('ns0:','')

                if item.resources:
                    res = item.resources[0].value
                    dur = self.makeseconds(item.resources[0].duration)
                else:
                    res = ''
                    dur = 0

                playlist.append((item.title, str(dur), res, item.id, xml))

        return playlist





    def search_sonospy_media_server_batch(self, id, name, device, root=None, entryref=None, searchstring=None, searchoperator=None, start=0, count=-1, hierarchynames=[]):

        log.debug("#### search_sonospy_media_server_batch id: %s", id)
        log.debug("#### name: %s", name)
        log.debug("#### device: %s", device)
        log.debug("#### root: %s", root)
        log.debug("#### entryref: %s", entryref)
        log.debug("#### searchstring: %s", searchstring)
        log.debug("#### searchoperator: %s", searchoperator)
        log.debug("#### start: %s", start)
        log.debug("#### count: %s", count)
        log.debug("#### hierarchynames: %s", hierarchynames)

        spdatareturn = []
        
        if count == -1: count = 100

        # default XML to have nothing to play
        xml = [None, None]

        # TODO: only get sort and search caps first time through

        if name:
            # are browsing via a ZP
            search_caps = self.control_point.get_tpms_service(name).GetSearchCapabilities()
        else:            
            search_caps = self.control_point.get_search_capabilities()
        self.current_server_search_capabilities = search_caps['SearchCaps']
        del self.sonospyserver_search[:]
        for cap in self.current_server_search_capabilities.split(','):
            if cap != '':
                self.sonospyserver_search.append(cap)
        log.debug("#### search_sonospy_media_server_batch search capabilities: %s", search_caps)

        if name:
            sort_caps = self.control_point.get_tpms_service(name).GetSortCapabilities()
        else:            
            sort_caps = self.control_point.get_sort_capabilities()
        log.debug("#### search_sonospy_media_server_batch sort capabilities: %s", sort_caps)
        if 'SortCaps' in sort_caps:
            sort_capabilities =  sort_caps['SortCaps']
        else:
            sort_capabilities =  ''
        if re.search('dc:title', sort_capabilities) != None:
            sort = '+dc:title'
        else:
            sort = ''

        # initialise ref
        self.gdataparent[entryref] = entryref

        search = False
        if root != None:
            # root items - need to add search option
            self.sonospyserver_root = [self.SSS_BASE]
            spdata = self.get_spdata(self.sonospyserver_search_title % name, self.SSS_BASE, 'SONOSPYMEDIASERVER', setparent=entryref)
            spdatareturn.append(spdata)

        elif id == self.SSS_BASE:
            # search - manually create search options list
            optionscount = len(self.sonospyserver_search)
            for i in range(optionscount):
                searchid = self.SSS_BASE + str(i)
                self.sonospyserver_search_ids[searchid] = i
                spdata = self.get_spdata(self.sonospyserver_search[i], searchid, 'SONOSPYMEDIASERVER', searchtype=self.sonospyserver_search_type, searchtitle=self.sonospyserver_search_title % name, searchoperators=None, setparent=entryref)
                spdatareturn.append(spdata)
            # finalise dataset
            spdatareturn.append("RETURN::" + str(optionscount) + ':' + str(optionscount) + self.data_delim)
            return spdatareturn
            
        else:
        
            if self.check_sonospyserver_search(id) == True:
            
                # if we get here then the user has sent a search string from the client
                searchtype = self.sonospyserver_search[self.sonospyserver_search_ids[id]]
                search = True

        id_param = id

        action = 'SEARCH'
        if search:
        
            searchcriteria = 'SEARCH::' + searchtype + '::' + searchstring
        
        elif id in self.sonospy_search_lookup:
        
            searchcriteria = self.sonospy_search_lookup[id]
            searchcriteria += ' and @refID exists false'
            
            # HACK: replace id with value Sonos uses for search
            if id_param in self.sonospy_search_lookup_item.keys():
                id_param = self.sonospy_search_lookup_item[id_param]
            
        elif '__' in id:

            # separate out the type
            idstart = id.split('__')[0]

            # need to construct the search string
            if idstart in self.sonospy_search_lookup_item3.keys():
                log.debug(self.sonospy_search_lookup_item3[idstart])
                statement, values = self.sonospy_search_lookup_item3[idstart]
                hierarchynames = hierarchynames[len(hierarchynames)-values:]   # remove elements that are not needed (will have come from GUI)
                log.debug(hierarchynames)
                searchcriteria = statement % tuple(hierarchynames)
                log.debug(searchcriteria)
            else:
                action = 'BROWSE'

            # HACK: replace id with value Sonos uses for search
            if idstart in self.sonospy_search_lookup_item2.keys():
                id_param = self.sonospy_search_lookup_item2[idstart]
            else:
                action = 'BROWSE'

        else:
            if id in self.sonospy_search_lookup_item.keys():
                searchitem = self.sonospy_search_lookup_item[id]
            else:
                searchitem = 'BROWSE'
            if searchitem == 'BROWSE':
                # we are at object level, so Browse instead
                action = 'BROWSE'
            else:
                searchcriteria = self.sonospy_search_lookup[id] + " and " + searchitem
                searchcriteria += ' and @refID exists false'

        if action == 'SEARCH':
            log.debug("Searchcriteria: %s" % searchcriteria)
            log.debug("Container: %s" % id_param)
            browse_result = self.control_point.searchtpms(name, device, id_param, searchcriteria, 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber', start, count, '+dc:title')
        else:
            sortcriteria = ''
            browse_result = self.control_point.browsetpms(name, device, id_param, 'BrowseDirectChildren', 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber', start, count, sortcriteria)

        if 'faultcode' in browse_result:
            self.set_messagebar(browse_result['detail'])
            return
        elif not 'Result' in browse_result:
            self.set_messagebar('UNKNOWN RESPONSE FROM BROWSE REQUEST')
            return
        
        items = browse_result['Result']
        total = int(browse_result['TotalMatches'])
        returned = int(browse_result['NumberReturned'])

        self.set_messagebar("Returned %d of %d." % (returned, total))

#        # initialise ref
#        self.gdataparent[entryref] = entryref
                
        for item in items:

            log.debug(item)
            
            if isinstance(item, Container):

#                data = self.convert_item_to_uridata(item)
                spdata = self.get_spdata(item.title, item.id, 'SONOSPYMEDIASERVER', setparent=entryref)
                spdatareturn.append(spdata)

            else:

                xml = item.to_string()
                xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
                xml = xml.replace('ns0:','')

                log.debug(xml)
                log.debug(item.resources[0])
                
                spdata = self.get_spdata(item.title, item.id, 'SONOSPYMEDIASERVER', res=item.resources[0].value, setparent=entryref)
                spdatareturn.append(spdata)

        # finalise dataset
        if len(items) == 0:
            # nothing was returned, add a dummy entry for display
            spdata = self.get_spdata('Nothing found', 'DUMMY', 'DUMMY', setparent=entryref)
            spdatareturn.append(spdata)

        spdatareturn.append("RETURN::" + str(returned) + ':' + str(total) + self.data_delim)

        return spdatareturn


    def get_spdata(self, title, id, type, res=None, searchtype=None, searchtitle=None, searchoperators=None, setparent='', extras=None):
        log.debug("#### title: %s", title)
        log.debug("#### id: %s", id)
        log.debug("#### type: %s", type)
        log.debug("#### searchtype: %s", searchtype)
        log.debug("#### searchtitle: %s", searchtitle)
        log.debug("#### searchoperators: %s", searchoperators)
        log.debug("#### setparent: %s", setparent)
        log.debug("#### extras: %s", extras)
        
        ref = self.gdataparent[setparent] + '_' + str(self.gdata_lastindex[setparent]+1)
        
        if res != None:
            entrytype = 'T'
        else:
            if searchtype != None:
                entrytype = 'S'
            else:
                if type == 'DUMMY':
                    entrytype = 'N'
                else:
                    entrytype = 'C'
        menu = self.get_server_menu_type(id, type)
        new_entry = ref + '|||' + id + '::' + entrytype + '::' + menu + '::' + title
        log.debug(new_entry)

        # append id and type in case receiver is caching
        new_entry += '::' + id + '::' + type

        # append any search criteria to end of entry (but not to the keys/tracks)
        if searchtype != None:
            new_entry += self.search_delim + searchtype + '::' + searchtitle
        if searchoperators != None:
            operators = self.codeoperators(searchoperators)
            new_entry += '::' + operators
        # append any extras to end of entry    
        if extras != None:
            new_entry += self.extras_delim + extras
        self.gdata_lastindex[setparent] += 1

        return new_entry + self.data_delim


    def search_sonospy_media_server_children(self, spname, spdevice, id, hierarchynames=None):

        log.debug("#### search_sonospy_media_server_children: %s", id)
        log.debug(hierarchynames)
        
        spmscount = 2000

        self.set_messagebar("Creating Playlist...")

        action = 'SEARCH'
        if id in self.sonospy_search_lookup:
        
            searchcriteria = self.sonospy_search_lookup[id]
            searchcriteria += ' and @refID exists false'
            
            # HACK: replace id with value Sonos uses for search
            if id in self.sonospy_search_lookup_item.keys():
                id = self.sonospy_search_lookup_item[id]
            
        elif '__' in id:

            # separate out the type
            idstart = id.split('__')[0]

            # need to construct the search string
            if idstart in self.sonospy_search_lookup_item3.keys():
                log.debug(self.sonospy_search_lookup_item3[idstart])
                statement, values = self.sonospy_search_lookup_item3[idstart]
                hierarchynames = hierarchynames[len(hierarchynames)-values:]   # remove elements that are not needed (will have come from GUI)
                searchcriteria = statement % tuple(hierarchynames)
                log.debug(searchcriteria)
            else:
                action = 'BROWSE'

            # HACK: replace id with value Sonos uses for search
            if idstart in self.sonospy_search_lookup_item2.keys():
                id = self.sonospy_search_lookup_item2[idstart]
            else:
                action = 'BROWSE'

        else:
            if id in self.sonospy_search_lookup_item.keys():
                searchitem = self.sonospy_search_lookup_item[id]
            else:
                searchitem = 'BROWSE'
            if searchitem == 'BROWSE':
                # we are at object level, so Browse instead
                action = 'BROWSE'
            else:
                searchcriteria = self.sonospy_search_lookup[id] + " and " + searchitem
                searchcriteria += ' and @refID exists false'

        current_server = self.control_point.get_current_server()

        if action == 'SEARCH':
            browse_result = self.control_point.searchtpms(spname, spdevice, id, searchcriteria, 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber', 0, spmscount, '+dc:title')
        else:
            sortcriteria = ''
            browse_result = self.control_point.browsetpms(spname, spdevice, id, 'BrowseDirectChildren', 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber', 0, spmscount, sortcriteria)
        
        if 'faultcode' in browse_result:
            self.set_messagebar(browse_result['detail'])
            return
        elif not 'Result' in browse_result:
            self.set_messagebar('UNKNOWN RESPONSE FROM BROWSE REQUEST')
            return
        
        items = browse_result['Result']
        total = int(browse_result['TotalMatches'])
        returned = int(browse_result['NumberReturned'])

        self.set_messagebar("Returned %d of %d." % (returned, total))

        if total > spmscount:
            while returned < total:
                if action == 'SEARCH':
                    b = self.control_point.searchtpms(spname, spdevice, id, searchcriteria, 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber', returned, spmscount, '+dc:title')
                else:
                    b = self.control_point.browsetpms(spname, spdevice, id, 'BrowseDirectChildren', 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber', returned, spmscount, sortcriteria)

                items = items + b['Result']
                returned += int(b['NumberReturned'])
                self.set_messagebar("Returned %d of %d." % (returned, total))
                
        playlist = []

        for item in items:

            if isinstance(item, Container):

                # child is a container, need to browse that too
                hierarchynames.append(item.title)
                playlist += self.search_sonospy_media_server_children(spname, spdevice, item.id, hierarchynames)

            else:

                xml = item.to_string()
                xml = xml.replace('xmlns:ns0="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"','')
                xml = xml.replace('ns0:','')

                if item.resources:
                    res = item.resources[0].value
                    dur = self.makeseconds(item.resources[0].duration)
                else:
                    res = ''
                    dur = 0

                playlist.append((item.title, str(dur), res, item.id, xml))

        return playlist









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


    def remove_non_sonos_elements(self, data, type=None):

#        print "--------------------------------------------------"
#        print "remove_non_sonos_elements"
#        print type
#        print data
#        print "--------------------------------------------------"

        # Sonos has a problem with the length of the item string on NOTIFY - it seems
        # only to return 1024 chars max
        # Multiple res elements or extraneous (not used by Sonos) elements can blow the limit
        
        # Remove all but the correct audio res (if they exist)
        # TODO: Asset sends multiple audio res - for now use the first, but need to know which to select
        # TODO: keep the items we want (rather than deleting some known not-wants) as we don't know what else will be passed
        '''
        NAS
            <res duration="00:04:52" nrAudioChannels="2" protocolInfo="http-get:*:audio/x-ms-wma:DLNA.ORG_PN=WMABASE;DLNA.ORG_OP=01" sampleFrequency="44100">http://192.168.0.4:58080/mshare/1/10004:ca8:primary/%28I%20Got%20That%29%20Boom%20Boom.wma</res>
            <res protocolInfo="http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_TN;DLNA.ORG_OP=01;DLNA.ORG_CI=1">http://192.168.0.4:58080/mshare/1/10004:ca8:albumart/%28I%20Got%20That%29%20Boom%20Boom.jpg</res>
            <res protocolInfo="http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_TN;DLNA.ORG_OP=01;DLNA.ORG_CI=1">http://192.168.0.4:58080/mshare/1/10004:ca8:thumbnail/%28I%20Got%20That%29%20Boom%20Boom.jpg</res>
        Asset
            <res bitrate="128000" bitsPerSample="16" duration="00:03:18.000" nrAudioChannels="2" protocolInfo="http-get:*:audio/mpeg:DLNA.ORG_PN=MP3;DLNA.ORG_OP=01" sampleFrequency="44100" size="3176490">http://192.168.0.10:50041/content/c2/b16/f44100/6819.mp3</res>
            <res bitrate="128000" bitsPerSample="16" duration="00:03:18.000" nrAudioChannels="2" protocolInfo="http-get:*:audio/wav:DLNA.ORG_PN=WAV;DLNA.ORG_OP=01" sampleFrequency="44100" size="3176490">http://192.168.0.10:50041/content/c2/b16/f44100/6819.wav</res>
            <res bitrate="128000" bitsPerSample="16" duration="00:03:18.000" nrAudioChannels="2" protocolInfo="http-get:*:audio/L16;rate=44100;channels=2:DLNA.ORG_PN=LPCM;DLNA.ORG_OP=01" sampleFrequency="44100" size="3176490">http://192.168.0.10:50041/content/c2/b16/f44100/6819.l16</res>
            <res bitrate="128000" bitsPerSample="16" duration="00:03:18.000" nrAudioChannels="2" protocolInfo="http-get:*:audio/mpeg:DLNA.ORG_PN=MP3;DLNA.ORG_OP=01" sampleFrequency="44100" size="3176490">http://192.168.0.10:50041/content/c2/b16/f44100/6819.mp3</res>
        '''

        if type == None:

            # remove all but first res - assumes res are consecutive
            firstres = re.search('<res[^<]*</res>', data)
            if firstres != None:
                data = re.sub('<res.*</res>' , firstres.group(), data)
            
            # for now remove extra artist info, genre and date
            firstart = re.search('<upnp:artist[^<]*</upnp:artist>', data)
            if firstart != None:
                data = re.sub('<upnp:artist.*</upnp:artist>' , firstart.group(), data)

            data = re.sub('<upnp:genre.*</upnp:genre>' , '', data)

            data = re.sub('<dc:date.*</dc:date>' , '', data)

        elif type == 'LIST':

            # to force Sonos to set track name in queue,
            # only want item, title, class and desc

#        xml =  '<item id="15-au775.mp3" parentID="au775" refID="" restricted="true" >'
#        xml += '<dc:title>  1   Song Of The Century [Album Version]/Album Version</dc:title>'
#        xml += '<upnp:class>object.item.audioItem.musicTrack</upnp:class>'
#        xml += '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">b68dd228-957b-4cfe-abcd-123456789abc</desc></item>'

            xml = ''

            item = re.search('<item[^>]*>', data)
            if item != None:                    
                xml += item.group()

            title = re.search('<dc:title[^<]*</dc:title>', data)
            if title != None:                    
                xml += title.group()
                
            uclass = re.search('<upnp:class[^<]*</upnp:class>', data)
            if uclass != None:                    
                xml += uclass.group()

            desc = re.search('<desc[^<]*</desc>', data)
            if desc != None:                    
                xml += desc.group()
                
            if item != None:                    
                xml += '</item>'

            data = xml

        elif type == 'WMP_LIST':

#<item id="SCPI:{FE5D13D8-263C-4B81-B64C-4C0DC62882B7}.0.BF25973D" parentID="SCPB:1+upnp:originalTrackNumber/BF25973D" restricted="true">

            xml = ''
            item = re.search('<item[^>]*>', data)
            if item != None:                    
                xml += item.group()
                
                xml = xml.replace('item id="', 'item id="SCPI:')
#                xml = xml.replace(' parentID="', ' parentID="SCPB:1+upnp:originalTrackNumber/')

                parent = re.search(' parentID="[^ ]*', data)
                if parent != None:                    
                    parent = parent.group()

                    xml = xml.replace(parent, ' parentID="SCPA:ALBUM"')

            title = re.search('<dc:title[^<]*</dc:title>', data)
            if title != None:                    
                xml += title.group()
                
            uclass = re.search('<upnp:class[^<]*</upnp:class>', data)
            if uclass != None:                    
                xml += uclass.group()

            desc = re.search('<desc[^<]*</desc>', data)
            if desc != None:                    
                xml += desc.group()
                
            if item != None:                    
                xml += '</item>'

            data = xml

        return data




    def update_position(self):

        '''
        {'AbsTime': 'NOT_IMPLEMENTED'
         'Track': '1'
         'TrackDuration': '0:02:50'
         'TrackURI': 'x-file-cifs://NAS/Music/Clannad/Past%20Present/11%20Robin%20(The%20Hooded%20Man).flac'
         'AbsCount': '2147483647'
         'TrackMetaData': '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"><item id="-1" parentID="-1" restricted="true"><res protocolInfo="x-file-cifs:*:audio/flac:*" duration="0:02:50">x-file-cifs://NAS/Music/Clannad/Past%20Present/11%20Robin%20(The%20Hooded%20Man).flac</res><r:streamContent></r:streamContent><dc:title>Robin (The Hooded Man)</dc:title><upnp:class>object.item.audioItem.musicTrack</upnp:class><dc:creator>Clannad</dc:creator><upnp:album>Past Present</upnp:album><upnp:originalTrackNumber>11</upnp:originalTrackNumber><r:albumArtist>Clannad</r:albumArtist></item></DIDL-Lite>'
         'RelCount': '2147483647'
         'RelTime': '0:01:29'}
        '''
        pos = self.control_point.get_position_info()
        reltime = ''
        if 'RelTime' in pos:
            if pos['RelTime'] != 'NOT_IMPLEMENTED':
                reltime = pos['RelTime']
        trackduration = ''
        if 'TrackDuration' in pos:
            if pos['TrackDuration'] != 'NOT_IMPLEMENTED':
                trackduration = pos['TrackDuration']

        td = re.sub('0', '', trackduration)
        td = re.sub(':', '', td)
        if td == '':
            trackduration = ''

        if reltime != '' and trackduration != '':
            self.now_playing_percent = "%.1f" % ((self.makeseconds(reltime) * 100) / self.makeseconds(trackduration))
        else:
            self.now_playing_percent = '0.0'
                
        if reltime != '':
            self.now_playing_pos = reltime
        if reltime != '' and trackduration != '':
            self.now_playing_pos += " / "
        if trackduration != '':
            self.now_playing_pos += trackduration

        
    def do_play(self):
        # check if already playing:
        #     if playing, pause
        #     if paused, unpause (play)
        # else
        #     unpause (i.e. play without setting AVTransport


#            self.play_state = self.control_point.GetTransportInfo()



#            state = self.control_point.get_transport_state()
#            log.debug("play state: %s", state)
#transportStates = [ 'STOPPED', 'PLAYING', 'TRANSITIONING', 'PAUSED_PLAYBACK', 'PAUSED_RECORDING', 'RECORDING', 'NO_MEDIA_PRESENT' ]
        if self.play_state == 'PLAYING' or self.play_state == 'TRANSITIONING':
            self.pause()
        elif self.play_state == 'PAUSED_PLAYBACK':
            self.unpause()
        else:
            # we want to play without setting AVTransport, which is what unpause does
            self.unpause()

    def pause(self):
        try:
            self.control_point.pause()
            self.play_state = 'PAUSED_PLAYBACK'
        except Exception, e:
            log.info('Choose a Renderer to pause Music. Specific problem: %s' % \
                     str(e))

    def unpause(self):
        try:
            self.control_point.unpause()
            self.play_state = 'PLAYING'
        except Exception, e:
            log.info('Choose a Renderer to unpause Music. Specific problem: %s' % \
                     str(e))


    def play_now_noqueue(self):

        uri = self.current_media_id
        xml = self.current_media_xml
        
        print "uri: " + str(uri)
        print "xml: " + str(xml)
        
        self.control_point.set_avtransport_uri(uri, xml)
        
        print "after avt"
        
        self.play()


    def play_now_queue(self):

        # TODO: track updates to queue UpdateID so we know if it has changed since we started and need to re-fetch
        
        desiredfirsttrack = 0
        enqueuenext = 1

        queue = self.queue_gen()
        played = False
        for item in queue:
            uri, xml, index, total = item
            self.set_messagebar("Queuing item %d of %d." % (index, total))
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

    
    def play_in_queue(self, position):

        uri = self.current_media_id
        xml = self.current_media_xml

        self.control_point.set_avtransport_uri(uri, xml)
        unit = 'TRACK_NR'
        target = position
        self.control_point.seek(unit, target)
        self.play()

    
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


    def play_sample_noqueue(self):

        unit = 'REL_TIME'
        target = "0:00:20"

        uri = self.current_media_id
        xml = self.current_media_xml
        self.control_point.set_avtransport_uri(uri, xml)
        self.control_point.seek(unit, target)
        self.play()

        # TODO: some tracks don't play for several seconds - need to wait for them to start playing before setting the timeout
        wait = 5
        renderer = self.control_point.get_current_renderer()
        run_async_function(self.sample_stop, (renderer, uri, target, wait), wait)


    def sample_stop(self, renderer, uri, start, wait):
        # stop playing on renderer that sample was started on, if track is same and wait has expired
        if renderer == self.control_point.get_current_renderer():
            self.get_position_info()
            if uri == self.current_track_URI:
                startsecs = self.makeseconds(start)
                endsecs = startsecs + wait
                currsecs = self.makeseconds(self.current_track_relative_time_position)
                delta = endsecs - currsecs
                # allow +- 1 sec 
                if delta <= 1 and delta >= -1:
                    self.stop()


    def update_playlist_name(self, id, currenttagvalue, newtagvalue):

        currenttagvalue = '<dc:title>' + currenttagvalue + '</dc:title>'
        newtagvalue = '<dc:title>' + newtagvalue + '</dc:title>'
        res = self.control_point.update_object(id, currenttagvalue, newtagvalue)
        if res == {}:
            return True
        else:
            return False


    def makeseconds(self, time):
        if not ':' in time:
            return 0
        h, m, s = time.split(':')
        return (int(h)*60*60 + int(m)*60 +int(float(s)))


    def fix_metadata(self, type=None, rootid=None):

        # we will either get a single entry in current_media_id or a list in current_media_list
        # with a list we could also get an old current_media_id, so check for list first
        nolist = False
        if len(self.current_media_list) == 0:
            # no list supplied, will be single item - make dummy entry for it
            self.current_media_list.append(('', 0, self.current_media_id, '', self.current_media_xml))
            nolist = True

        # process the list (or the dummy entry)
        processed_list = []
        for title, duration, self.current_media_id, id, self.current_media_xml in self.current_media_list:
    
            if self.current_media_id != None and self.current_media_xml != '':

                # we need to make sure any desc specified points to the current server
                current_server = self.control_point.get_current_server()
                udn = current_server.udn.replace('uuid:', '')

                # if current server is a zone player and we are serving from a third party server via it, get that udn instead
                if current_server.udn in self.known_zone_players:
                    if rootid != None:
                        udn = rootid.replace('uuid:', '')
                        print udn
#                        udn = 'RINCON_AssociatedZPUDN'
#                        print udn
                
                if '<desc' in self.current_media_xml:
                    # desc already present - if it points to ZP, change to server
#                    self.current_media_xml = self.current_media_xml.replace('RINCON_AssociatedZPUDN', udn)
                    rincon = re.search('RINCON_[^<]*', self.current_media_xml)
                    if rincon != None:
                        self.current_media_xml = re.sub(rincon.group(), udn, self.current_media_xml)
                    
                else:
                    # no desc - add one pointing to server
                    desc =  '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">'
                    desc += udn + '</desc>'
                    self.current_media_xml = self.current_media_xml.replace('</item>', desc + '</item>')

                # if current renderer is Sonos, need to remove extraneous elements from the XML
                # otherwise we could blow the item length limit when returned on NOTIFY
                # note that this is not foolproof as we still manage to blow some elements
                
                # check if current renderer is a zoneplayer
                current_renderer = self.control_point.get_current_renderer()
                if current_renderer.udn in self.known_zone_players:

                    # for non-WMP servers, we need to minimise the XML so that Sonos uses the track name
                    # for WMP servers, we need to use Sonos encoding
                    
                    # WHAT ABOUT THE SONOS LIBRARY - THAT OUGHT NOT TO GET HERE AS A URI WILL BE PROVIDED

                    current_server = self.control_point.get_current_server()
                    if self.check_full_wmp_clone(current_server) == True or udn in self.msrootids.keys():
                        self.current_media_xml = self.remove_non_sonos_elements(self.current_media_xml, type='WMP_LIST')
                    else:
                        self.current_media_xml = self.remove_non_sonos_elements(self.current_media_xml, type='LIST')

                else:

                    # if current renderer is not a zoneplayer, need to replace Sonos protocol type with standard
                    if self.current_media_id.startswith('x-file-cifs:'):

                        renderer_platform = self.known_media_renderers_extras[current_renderer.udn]['PLATFORM']
                        if renderer_platform == 'Windows':
                            self.current_media_id = self.current_media_id.replace('%20', ' ')   # foobar won't process these
                            self.current_media_id = self.current_media_id.replace('/', '\\')
                            self.current_media_id = re.sub('x-file-cifs:', 'file://', self.current_media_id)
                        else:
                            # assume all other platforms can handle smb
                            self.current_media_id = re.sub('x-file-cifs:', 'smb:', self.current_media_id)

                    elif self.current_media_id.startswith('x-sonosapi-stream'):
                        # TODO: work out which URL to use
                        self.current_media_id = self.music_item_station_url.split('\n')[0]
                
                # if current renderer is not on the local machine and the data refers to localhost, replace with external IP
                # TODO: at the moment we don't check whether renderer is local...

                '''            
                ip = self._get_ip()
                print "@@@@@@@@@@@@@@@@@"
                print "@@@@@@@@@@@@@@@@@"
                print "@@@@@@@@@@@@@@@@@"
                print "@@@@ before: " + str(self.current_media_id)
                self.current_media_id = re.sub('127.0.0.1', ip, self.current_media_id)
                print "@@@@ after : " + str(self.current_media_id)
                print "@@@@@@@@@@@@@@@@@"
                print "@@@@@@@@@@@@@@@@@"
                print "@@@@@@@@@@@@@@@@@"
                '''

            processed_list.append((title, duration, self.current_media_id, id, self.current_media_xml))

        del self.current_media_list[:]
        self.current_media_list = processed_list

        if nolist == True:
            # clear up
            title, duration, self.current_media_id, id, self.current_media_xml = self.current_media_list[0]
            del self.current_media_list[:]


    def get_queueURI(self):

        # make URI point to the Sonos queue
        current_renderer = self.control_point.get_current_renderer()
        udn = current_renderer.udn.replace('uuid:', '')
        if not udn.startswith('RINCON_'): udn = 'RINCON_' + udn
        uri = 'x-rincon-queue:' + udn + '#0'
            
        return uri


    def check_full_wmp_clone(self, server):
        # note that Asset pretends to be WMP but doesn't support everything it needs to for that
        # TODO: move the string(s) to exclude for WMP test to the ini file
        full_clone = False
        if server.model_name.startswith('Windows Media Player'):
            full_clone = True
            if server.friendly_name.startswith('Asset'):
                full_clone = False
        return full_clone
            

    def _get_ip(self):
        ifaces = get_active_ifaces()
        if ifaces:
            host = get_ip_address(ifaces[0])
        else:
            host = 'localhost'
        return host


    def play(self):
        try:

            # TODO: check the result of play - this seems to be returned in the NOTIFY...
            self.control_point.play()

            # brisa renderer is not eventing lastchange - until we fix that send a dummy event
            current_renderer = self.control_point.get_current_renderer()
            if current_renderer.udn not in self.known_zone_players:

                # send the equivalent of a NOTIFY - call device_event with a dummy lastchange

                xml = self.current_media_xml
                # HACK: need to send either DIDL-Lite or item
                if xml.startswith('<DIDL-Lite'):
                    metadata = xml
                else:
                    metadata = '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">' + xml + '</DIDL-Lite>'

                    # metadata needs converting to reference form for embedding
                    # TODO: fix this with Python method
                    metadata = metadata.replace("&","&amp;")
                    metadata = metadata.replace("\"","&quot;")
                    metadata = metadata.replace("'","&apos;")
                    metadata = metadata.replace("<","&lt;")
                    metadata = metadata.replace(">","&gt;")
                    
                change = {}
                changexml = '<Event xmlns="urn:schemas-upnp-org:metadata-1-0/AVT/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"><InstanceID val="0">'
                changexml += '<TransportState val="PLAYING"/><CurrentPlayMode val="NORMAL"/>'
                changexml += '<CurrentTrackMetaData val="' + metadata + '"/>'
                changexml += '</InstanceID></Event>'
                change['LastChange'] = changexml

                sid = self.control_point.get_at_service().event_sid
                if sid == '':
                    sid = current_renderer.udn  # event_sid is not set as eventing is not working
                
                run_async_function(self.on_device_event_seq, (sid, -1, change), 0.001)

        except Exception, e:
            log.info('Choose a Renderer to play Music. Specific problem: %s' % \
                     str(e))


    def stop(self):
#        print "@@@ play_state: " + str(self.play_state)
        if self.play_state != '' and self.play_state != 'STOPPED':
            try:
                self.control_point.stop()
                self.play_state = 'STOPPED'
            except Exception, e:
                log.info('Choose a Renderer to stop Music. Specific problem: %s' % \
                         str(e))


    def set_play(self, state):
        self.play_state = state
        if state == 'PLAYING' or state == 'TRANSITIONING':
            state_label = 'Pause'
        elif state == 'PAUSED_PLAYBACK':
            state_label = 'Resume'
        elif state == 'STOPPED':
            state_label = 'Play'

    def set_messagebar(self, text):
        print "Messagebar: " + str(text)
        self.messagebar = text
        return

    def set_messagebar_async(self, text):
        print "Messagebar_async: " + str(text)
        return

    def mute(self):
        try:
            self.control_point.mute(self.volume_mute)
        except Exception, e:
            log.info('Choose a Renderer to mute Music. Specific problem: %s' % \
                     str(e))

    def next(self):
        self.control_point.next()

    def previous(self):
        self.control_point.previous()

    def volume(self, volume):
        try:
            self.control_point.set_volume(volume)
        except Exception, e:
            log.info('Choose a Renderer to change volume. Specific problem: %s' % \
                     str(e))



    def get_server_menu_options(self, type):

        menuitems = { "PN"   : "Play now",
                      "PNDQ" : "Play now don't queue",
                      "PNAQ" : "Play now add to queue",
                      "AQN"  : "Add to queue next", 
                      "AQE"  : "Add to end of queue",
                      "PS"   : "Play sample", 
                      "RP"   : "Rename playlist",
                      "SN"   : "Search Napster", 
                      "SL"   : "Search Library", 
                      "SM"   : "Search MediaServer", 
                      "SP"   : "Search Sonospy", 
                      "SEP"  : "SEP",   # separator
        }

        if type == "ZP":

            # 1 default action(s) and 10 menus (=11)

            options = ["11",
                       "1", "DEFAULT", "PNAQ", menuitems["PNAQ"], 
            
                       "1", "ZP_QUEUE", "PN", menuitems["PN"], 
                       "6", "ZP_LIST", "PNDQ", menuitems["PNDQ"], "PNAQ", menuitems["PNAQ"], "AQN", menuitems["AQN"], "AQE", menuitems["AQE"], "SEP", menuitems["SEP"], "RP", menuitems["RP"],
                       "4", "ZP_PLAY", "PNDQ", menuitems["PNDQ"], "PNAQ", menuitems["PNAQ"], "AQN", menuitems["AQN"], "AQE", menuitems["AQE"], 

                       "1", "ZP_NAPSTER_SEARCH", "SN", menuitems["SN"], 
                       "4", "ZP_NAPSTER_PLAY", "PNDQ", menuitems["PNDQ"], "PNAQ", menuitems["PNAQ"], "AQN", menuitems["AQN"], "AQE", menuitems["AQE"],

                       "1", "ZP_LIBRARY_SEARCH", "SL", menuitems["SL"], 
                       "5", "ZP_LIBRARY_PLAY", "PNDQ", menuitems["PNDQ"], "PNAQ", menuitems["PNAQ"], "AQN", menuitems["AQN"], "AQE", menuitems["AQE"], "PS", menuitems["PS"],

                       "5", "ZP_MS_PLAY", "PNDQ", menuitems["PNDQ"], "PNAQ", menuitems["PNAQ"], "AQN", menuitems["AQN"], "AQE", menuitems["AQE"], "PS", menuitems["PS"],

                       "5", "SP_PLAY", "PNDQ", menuitems["PNDQ"], "PNAQ", menuitems["PNAQ"], "AQN", menuitems["AQN"], "AQE", menuitems["AQE"], "PS", menuitems["PS"],
                       "1", "SP_SEARCH", "SP", menuitems["SP"], 
                      ]

        else:
            # 1 default action(s) and 4 menus (=5)
            # first menu has 1 option - menu type is MS_SEARCH, option is "Search MediaServer"
            # second menu has 4 options - menu type is MS_PLAY, options are "Play now don't queue", "Play now add to queue", "Add to queue next", "Add to end of queue"

            options = ["5",
                       "1", "DEFAULT", "PNDQ", menuitems["PNDQ"], 
                       "1", "MS_SEARCH", "SM", menuitems["SM"], 
                       "5", "MS_PLAY", "PNDQ", menuitems["PNDQ"], "PNAQ", menuitems["PNAQ"], "AQN", menuitems["AQN"], "AQE", menuitems["AQE"], "PS", menuitems["PS"],
                       "5", "SP_PLAY", "PNDQ", menuitems["PNDQ"], "PNAQ", menuitems["PNAQ"], "AQN", menuitems["AQN"], "AQE", menuitems["AQE"], "PS", menuitems["PS"],
                       "1", "SP_SEARCH", "SP", menuitems["SP"], 
                      ]

        for index in range(len(options)):
            options[index] += "_|_"
            
        return options

    def get_server_menu_type(self, id, type):

        # all types other than stated will have no popup
        menutype = 'NONE'

        if id == 'SQ:':
            # no menu at this level for playlists
            pass

        elif id.startswith('SQ:'):
            menutype = "ZP_LIST"

        elif id == "Q:0":
            menutype = "ZP_QUEUE"

        elif type == "NAPSTER":
            if self.check_napster_search(id) == True:
                menutype = "ZP_NAPSTER_SEARCH"
            else:
                if not id in self.napster_root:
                    menutype = "ZP_NAPSTER_PLAY"

        elif type == "SONOSLIBRARY":
            if self.check_library_search(id) == True:
                menutype = "ZP_LIBRARY_SEARCH"
            else:
                if not id in self.library_root:
                    menutype = "ZP_LIBRARY_PLAY"

        elif type == "SONOSMUSICSERVER" or \
             type == "THIRDPARTYMEDIASERVER" or \
             type == "MSMEDIASERVER":
            menutype = "ZP_MS_PLAY"

        elif type == "SONOSPYMEDIASERVER":
            if self.check_sonospyserver_search(id) == True:
                menutype = "SP_SEARCH"
            else:
                menutype = "SP_PLAY"
            
        elif type == "MUSICSERVER":
            if self.check_mediaserver_search(id) == True:
                menutype = "MS_SEARCH"
            else:
                if not id in self.mediaserver_root:
                    menutype = "MS_PLAY"

        return menutype




    def browse_container(self, id, type, ref, title=[]):

        rootref = self.getrootref(ref)
        rootname = self.rootdatanames[rootref]
        
        if type == "THIRDPARTYMEDIASERVER":
            children = self.browse_thirdparty_media_server_children(rootname, id)
        elif type == 'SONOSPYMEDIASERVER' or type == 'SonospyMediaServer_ROOT' or type == 'SonospyServerSearch_ROOT':
            current_server = self.control_point.get_current_server()
            current_udn = current_server.udn[5:]
            if current_udn in self.sonospyproxies.keys():
                # are browsing a sonospy server direct
                spdevice = current_server
                spname = None
            else:
                # are browsing via a ZP
                spdevice = None
                spname = unicode(rootname)
            children = self.search_sonospy_media_server_children(spname, spdevice, id, title)
        elif type == "MSMEDIASERVER":
            children = self.search_ms_media_server_children(rootname, id)
        else:
            children = self.browse_media_server_children(id)

        self.current_media_list = children

        # tests, uncomment to use them
        test = 0
#                test = 'object.track'
#                test = 'object.playlist'
#                test = 'playlist'
        
        if test == 'object.track':

            # create object on mediaserver - track (has multiple tracks but only first works)

            elements = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            for title, duration, res, id, xml in children:
#                    elements += '<res protocolInfo="http-get:*:audio/x-mpegurl:*" >' + res + '</res>'
                elements += xml

            elements += '</DIDL-Lite>'

            print '@@@@@@@@@@@@@@@@@@@@@@@@'
            print elements
            print '@@@@@@@@@@@@@@@@@@@@@@@@'

            result = self.control_point.create_object('DLNA.ORG_AnyContainer', elements)
            
            print '@@@@@@@@@@@@@@@@@@@@@@@@'
            print result
            print '@@@@@@@@@@@@@@@@@@@@@@@@'

            return

        elif test == 'object.playlist':

            # create object on mediaserver - playlist, fails

            children_uri = self.make_playlist(children, type='M3U')

            self.current_media_xml  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            self.current_media_xml += '<container id="playlist" parentID="p" restricted="true">'
            self.current_media_xml += '<dc:title>XML Playlist</dc:title>'
            self.current_media_xml += '<upnp:class>object.container.playlistContainer</upnp:class>'
            self.current_media_xml += '<res protocolInfo="http-get:*:audio/x-mpegurl:*" >' + children_uri
            self.current_media_xml += '</res>'
            self.current_media_xml += '</container>'
            self.current_media_xml += '</DIDL-Lite>'

            result = self.control_point.create_object('DLNA.ORG_AnyContainer', self.current_media_xml)
            
            print '@@@@@@@@@@@@@@@@@@@@@@@@'
            print result
            print '@@@@@@@@@@@@@@@@@@@@@@@@'

            return

        elif test == 'playlist':

            # create a playlist

#                children_uri = self.make_playlist(children, type='XML')
            children_uri = self.make_playlist(children, type='M3U')

            self.current_media_id = children_uri
#                self.current_media_xml = self.current_media_xml.replace('object.container.album.musicAlbum', 'object.container.playlistContainer')

            self.current_media_xml  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
#                self.current_media_xml += '<item id="SQ:25" parentID="SQ:" restricted="true">'
            self.current_media_xml += '<container id="playlist" parentID="p" restricted="true">'
            self.current_media_xml += '<dc:title>XML Playlist</dc:title>'
            self.current_media_xml += '<upnp:class>object.container.playlistContainer</upnp:class>'
            self.current_media_xml += '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">RINCON_AssociatedZPUDN</desc>'

#                self.current_media_xml += '<res protocolInfo="http-get:*:audio/x-mpegurl:*" >' + children_uri
            self.current_media_xml += '<res protocolInfo="http-get:*:audio/m3u:*" >' + children_uri
            self.current_media_xml += '</res>'


    #<container id="1$11$207905896" parentID="1$11" childCount="3" restricted="1" searchable="1">
    #<dc:title>GD</dc:title>
    #<dc:date>2009-01-01</dc:date>
    #<upnp:artist>Green Day</upnp:artist>
    #<dc:creator>Unknown</dc:creator>
    #<upnp:genre>Rock</upnp:genre>
    #<res protocolInfo="http-get:*:audio/x-mpegurl:*">http://192.168.0.10:9000/m3u/1$11$207905896.m3u</res>
    #<upnp:class>object.container.playlistContainer</upnp:class>
    #</container>

    #x-rincon:*:*:*
    #x-rincon-mp3radio:*:*:*
    #x-rincon-playlist:*:*:*
    #x-rincon-queue:*:*:*
    #x-rincon-stream:*:*:*
    #x-sonosapi-stream:*:*:*
    #x-sonosapi-radio:*:audio/x-sonosapi-radio:*
    #x-rincon-cpcontainer:*:*:*

            self.current_media_xml += '</container>'
            self.current_media_xml += '</DIDL-Lite>'

            udn = self.control_point.get_current_server().udn.replace('uuid:', '')

#                self.current_media_xml = self.current_media_xml.replace('RINCON_AssociatedZPUDN', udn)

            print "ID: " + str(self.current_media_id)
            print "XML: " + str(self.current_media_xml)
            
            desiredfirsttrack = 0
            enqueuenext = 0

            self.control_point.add_uri_to_queue(self.current_media_id, self.current_media_xml, desiredfirsttrack, enqueuenext)
        
            return

            '''

            udn = self.control_point.get_current_server().udn.replace('uuid:', '')

            self.current_media_id = 'x-rincon-cpcontainer:SCPA:ALBARTIST/Green%20Day/21st%20Century%20Breakdown'

            self.current_media_xml =  '<item id="SCPA:ALBARTIST/Green%20Day/21st%20Century%20Breakdown" parentID="SCPA:ALBARTIST/Green%20Day" restricted="true">'
            self.current_media_xml += '<dc:title>21st Century Breakdown</dc:title>'
            self.current_media_xml += '<upnp:class>object.container.album.musicAlbum</upnp:class>'
            self.current_media_xml += '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">'
            self.current_media_xml += udn
            self.current_media_xml += '</desc>'
            self.current_media_xml += '</item>'


<EnqueuedURI>x-rincon-cpcontainer:SCPA:ALBARTIST/Manic%20Street%20Preachers</EnqueuedURI>
<EnqueuedURIMetaData>
<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">
<item id="SCPA:ALBARTIST/Manic%20Street%20Preachers" parentID="SCPA:ALBARTIST" restricted="true">
<dc:title>Manic Street Preachers</dc:title>
<upnp:class>object.container.person.musicArtist</upnp:class>
<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">02286246-a968-4b5b-9a9a-defd5e9237e0</desc>
</item>
</DIDL-Lite>
</EnqueuedURIMetaData>

<EnqueuedURI>x-rincon-cpcontainer:SCPA:ALBARTIST/Green%20Day/21st%20Century%20Breakdown</EnqueuedURI>
<EnqueuedURIMetaData>
<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">
<item id="SCPA:ALBARTIST/Green%20Day/21st%20Century%20Breakdown" parentID="SCPA:ALBARTIST/Green%20Day" restricted="true">
<dc:title>21st Century Breakdown</dc:title>
<upnp:class>object.container.album.musicAlbum</upnp:class>
<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">02286246-a968-4b5b-9a9a-defd5e9237e0</desc>
</item>
</DIDL-Lite>
</EnqueuedURIMetaData>

<EnqueuedURI>x-rincon-cpcontainer:SCPB:0/3BAF3B40</EnqueuedURI>
<EnqueuedURIMetaData>
<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">
<item id="SCPB:0/3BAF3B40" parentID="SCPA:PLAYLISTS" restricted="true">
                '''
                





    def check_for_playlist(self, media_id):
        playlist_extns = ['m3u', 'asx', 'pls']
        playlist = False
        for extn in playlist_extns:
            if media_id.lower().endswith(extn):
                playlist = True
                break
        return playlist



    def set_server_device(self, server):
        log.debug(server)
        self.music_services = {}
        self.music_services_type = {}
        self.control_point.set_current_server(server)
        
        if server.udn in self.known_zone_players:
            self.control_point.set_current_zoneplayer(server)
            searchvars = self.global_search_vars
        elif server.udn[5:] in self.sonospyproxies.keys():
            searchvars = self.sonospyserver_search_vars
        else:
            searchvars = self.mediaserver_search_vars
        # get the root entries                                    
        self.browse_media_server_root(searchvars)



    def set_renderer_device(self, renderer):

        # unsubscribe from events from previous renderer
        current_renderer = self.control_point.get_current_renderer()

        self.clearprevrendererdata()
        self.clearprevrenderermetadata()
        
        if current_renderer != renderer:
       
            if current_renderer != None:
#                self.renew_loop.stop()
                self.unsubscribe_from_device(self.control_point.get_at_service(current_renderer))
                self.unsubscribe_from_device(self.control_point.get_rc_service(current_renderer))
                # check if current renderer is a zoneplayer
                if current_renderer.udn in self.known_zone_players:
                    self.unsubscribe_from_device(self.control_point.get_cd_service(current_renderer))
                self.current_renderer_events_avt = {}
                self.current_renderer_events_rc = {}
                self.now_playing = ''
                self.now_extras = ''
                self.now_playing_dict = {}
                self.now_extras_dict = {}
                self.now_playing_pos = ''
                self.now_playing_percent = ''
                self.album_art = ''
                self.clear_position_info()
                self.last_event_seq = {}
                self.current_queue_length = -1
                self.current_queue_updateid = -1
                self.messagebar = ''
            # set new renderer
            self.control_point.set_current_renderer(renderer)
            current_renderer = self.control_point.get_current_renderer()
            # subscribe to events from this device
            self.subscribe_to_device(self.control_point.get_at_service(current_renderer))
            self.subscribe_to_device(self.control_point.get_rc_service(current_renderer))
            if current_renderer.udn in self.known_zone_players:
                self.subscribe_to_device(self.control_point.get_cd_service(current_renderer))   # this is so we can watch for queue changes from the renderer
            # for Sonos, need to know how many items are in the queue
            if current_renderer.udn in self.known_zone_players:
                self.get_queue_length("Q:0", self.known_zone_players[current_renderer.udn])

        self.get_position_info()




#    def _renew_subscriptions(self):
#        """ Renew subscriptions
#        """
#        self.renew_device_subscription(self.control_point.current_renderer, self.control_point.avt_s)
#        self.renew_device_subscription(self.control_point.current_renderer, self.control_point.rc_s)


    def on_new_device(self, device_object):
        log.debug('got new device: %s' % str(device_object))
#        log.debug('new device type: %s' % str(device_object.device_type))

        log.debug('fn: %s' % str(device_object.friendly_name))
        log.debug('loc: %s' % str(device_object.location))
        log.debug('add: %s' % str(device_object.address))

#        print ">>>>"
        print ">>>> new device: " + str(device_object.friendly_name) + " at " + str(device_object.address) + "  udn: " + str(device_object.udn)

#        print ">>>> new device services: " + str(device_object.services)
#        print ">>>>"

#        log.debug('m : %s' % str(device_object.manufacturer))
#        log.debug('mu: %s' % str(device_object.manufacturer_url))
#        log.debug('md: %s' % str(device_object.model_description))
#        log.debug('mn: %s' % str(device_object.model_name))
#        log.debug('mn: %s' % str(device_object.model_number))
#        log.debug('mu: %s' % str(device_object.model_url))
#        log.debug('sn: %s' % str(device_object.serial_number))
#        log.debug('ud: %s' % str(device_object.udn))
#        log.debug('up: %s' % str(device_object.upc))
#        log.debug('pu: %s' % str(device_object.presentation_url))

#        log.debug('new device udn: %s' % str(device_object.udn))
#        log.debug('new device services: %s' % str(device_object.services))

# TODO: need to check whether we need to cater for multiple child levels
#@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
# it appears that 0.10 brings all services back via the root device - so the zoneplayer has avt, rc etc
# TODO: DO WE NEED TO CHECK FOR CHILD DEVICES ANY MORE?
#@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

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
            newmediaserver = False
            newmediarenderer = False
            t = device_item.device_type
            if 'ZonePlayer' in t:
                self.on_new_zone_player(device_item)
                # now register zoneplayer as server and renderer
                # TODO: check whether is has these capabilities first
                newmediaserver = self.on_new_media_server(device_item)
                newmediarenderer = self.on_new_media_renderer(device_item)
            elif 'MediaServer' in t:
                newmediaserver = self.on_new_media_server(device_item)
            elif 'MediaRenderer' in t:
                newmediarenderer = self.on_new_media_renderer(device_item)

            log.debug('new device fn: %s' % str(device_item.friendly_name))                                    

            if newmediaserver == True and not device_item.friendly_name.startswith('Proxy'):
                for upnp in self.upnpproxy:
                    if re.search(upnp, device_item.friendly_name) != None:
                        friendly = re.sub(r'[^a-zA-Z0-9_\- ]','', device_item.friendly_name)
                        name = 'Proxy UPnP ' + friendly
                        proxyuuid = 'uuid:' + str(uuid.uuid4())
                        print "UPnP proxy UUID: " + str(proxyuuid)
                        proxy = Proxy(name, 'UPnP', '', proxyuuid, self.config, self.proxy_port,
                                      mediaserver=device_item, controlpoint=self.control_point)
                        self.proxy_port += 1
                        proxy.start()
                        self.proxies.append(proxy)
                        
                        # save udn of original server against proxied name
                        self.rootids[name] = device_item.udn
                        
                if not self.wmpfound:
                    for wmpstring in self.wmpproxy:
                        wmpsplit = wmpstring.split('=')
                        if len(wmpsplit) == 1:
                            wmp = wmpsplit[0]
                            wmptrans = ''
                        else:
                            wmp = wmpsplit[0]
                            wmptrans = wmpsplit[1]

                        processwmp = False
                        if re.search(wmp, device_item.friendly_name) != None:
                            friendly = re.sub(r'[^a-zA-Z0-9_\- ]','', device_item.friendly_name)
                            name = 'Proxy WMP ' + friendly
                            proxyuuid = 'uuid:' + str(uuid.uuid4())
                            proxy = Proxy(name, 'WMP', wmptrans, proxyuuid, self.config, self.wmp_proxy_port,
                                      mediaserver=device_item, controlpoint=self.control_point)
                            proxy.start()
                            self.proxies.append(proxy)
                            self.wmpfound = True

                            # save udn of original server against proxied name
                            self.rootids[name] = device_item.udn
                        

    def on_new_zone_player(self, device_object):
        self.known_zone_players[device_object.udn] = device_object
#        self.control_point.set_current_zoneplayer(device_object)
        self.zoneattributes[device_object.udn] = self.get_zone_details(device_object)
        log.debug('new zone player - %s' % self.zoneattributes[device_object.udn]['CurrentZoneName'])
        # subscribe to events from this device
        self.subscribe_to_device(self.control_point.get_zt_service(device_object))
#        # HACK: assuming udn's of children are as below
#        self.known_zone_names[device_object.udn + '_MS'] = self.zoneattributes['CurrentZoneName']
#        self.known_zone_names[device_object.udn + '_MR'] = self.zoneattributes['CurrentZoneName']
        self.known_zone_names[device_object.udn] = self.zoneattributes[device_object.udn]['CurrentZoneName']

    def on_new_media_server(self, device_object):
        if device_object.udn in self.known_media_servers.keys():
            print '>>>> new server device: duplicate'
            return False
        self.known_media_servers[device_object.udn] = device_object
        # subscribe to events from this device
        self.subscribe_to_device(self.control_point.get_cd_service(device_object))
        if 'urn:microsoft.com:service:X_MS_MediaReceiverRegistrar:1' in device_object.services:
            # MS device, probably MS Media Player
            # subscribe to events from MediaReceiverRegistrar
            self.subscribe_to_device(self.control_point.get_mrr_service(device_object))
            # register with service
#            self.control_point.register_with_registrar(device_object)
        device_name = self.make_device_name(device_object)
        self.update_devices(device_name, 'S', device_object.udn)        
        return True

    def on_new_media_renderer(self, device_object):
        if device_object.udn in self.known_media_renderers.keys():
            print '>>>> new renderer device: duplicate'
            return False
        renderer_server = self.get_server_platform(self.control_point._ssdp_server.known_device[device_object.udn + '::upnp:rootdevice']['SERVER'])
        self.known_media_renderers[device_object.udn] = device_object
        self.known_media_renderers_extras[device_object.udn] = {'PLATFORM' : renderer_server}
        print self.known_media_renderers_extras[device_object.udn]
        device_name = self.make_device_name(device_object)
        self.update_devices(device_name, 'R', device_object.udn)
        return True

    def get_server_platform(self, server_string):
        # HACK: only recognises a few types at present
        platform = ''
        if 'Linux' in server_string:
            platform = 'Linux'
        elif 'Windows' in server_string:
            platform = 'Windows'
        elif 'Platinum' in server_string:
            if 'foobar2000' in server_string:
                platform = 'Windows'
        return platform

    def on_del_device(self, udn):
        # TODO: unsubscribe from events from deleted device
        if udn in self.known_media_servers:
            device_object = self.known_media_servers[udn]
            device_name = self.make_device_name(device_object)
            self.update_devices_remove(device_name, 'S', udn)
            del self.known_media_servers[udn]
        if udn in self.known_media_renderers:
            device_object = self.known_media_renderers[udn]
            device_name = self.make_device_name(device_object)
            self.update_devices_remove(device_name, 'R', udn)
            del self.known_media_renderers[udn]
        # do this last so name above can be generated correctly
        # TODO: save name from initial generation
        if udn in self.known_zone_players:
            del self.known_zone_players[udn]
    

    def display_music_location(self):

        if self.current_media_type == 'RADIOTIME':
            id = self.current_media_id
            if 'x-sonosapi-stream' in id:
                id = re.search('[^:]*:([^?]*)\?.*', id)
                if id != None:
                    id = id.group(1)
            self.music_item_station_uri = self.radiotime_getmediaURI(id)
            self.music_item_station_url = self.radiotime_getmediaURL(self.music_item_station_uri)
#            self.music_item_station_url = self.radiotime_getmediaURL(self.music_item_station_uri).split('\n')[0]
            self.info = "URI:\n" + str(self.music_item_station_uri) + '\n' + "URL:\n" + str(self.music_item_station_url)
            self.info += "\n\n" + self.current_media_xml
#            self.update_info()
        else:
            self.info = ''
            for r in re.finditer('<res[^<]*</res>', self.current_media_xml):
                self.info += r.group(0) + "\n\n"
            self.info += "\n" + self.current_media_xml
#            self.update_info()


    def display_container_location(self, name, id, uri, xml):
        if uri == None:
            uri = ''
        if xml == None:
            xml = ''
        self.info = 'Name: ' + name + '\n'
        self.info += 'ID: ' + id + '\n'
        self.info += 'URI: ' + uri + '\n'
        self.info += 'XML: ' + xml
#        self.update_info()




        '''
FAILURE FROM ASSET RT - DIRECT
DEBUG	sonos                         :1573:play() #### ControlPointGUI.play current_media_id: http://192.168.0.10:26125/content/c2/b16/f44100/[INTER-RADIO]24.wav
DEBUG	sonos                         :1574:play() #### ControlPointGUI.play current_media_xml: <item id="[INTER-RADIO]24-au87" parentID="au87" refID="" restricted="true" ><dc:title> Rock FM 97.4 (Top 40-Pop)  [64kbps]</dc:title><upnp:class>object.item.audioItem.audioBroadcast</upnp:class><upnp:writeStatus>NOT_WRITABLE</upnp:writeStatus><res bitsPerSample="16" nrAudioChannels="2" protocolInfo="http-get:*:audio/wav:DLNA.ORG_PN=WAV;DLNA.ORG_OP=01" sampleFrequency="44100">http://192.168.0.10:26125/content/c2/b16/f44100/[INTER-RADIO]24.wav</res><upnp:albumArtURI>http://radiotime-logos.s3.amazonaws.com/s6924q.png</upnp:albumArtURI></item>
DEBUG	sonos                         :1575:play() #### ControlPointGUI.play current_media_type: MUSICSERVER
DEBUG	sonos                         :2058:on_device_event() device_event sid: uuid:RINCON_000E5830D2F001400_sub0000000010
DEBUG	sonos                         :2059:on_device_event() device_event c_v: {'LastChange': '<Event xmlns="urn:schemas-upnp-org:metadata-1-0/AVT/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"><InstanceID val="0"><TransportState val="STOPPED"/><CurrentPlayMode val="NORMAL"/><NumberOfTracks val="1"/><CurrentTrack val="1"/><CurrentSection val="0"/><CurrentTrackURI val="http://192.168.0.10:26125/content/c2/b16/f44100/[INTER-RADIO]24.wav"/><CurrentTrackDuration val="0:00:00"/><CurrentTrackMetaData val="&lt;DIDL-Lite xmlns:dc=&quot;http://purl.org/dc/elements/1.1/&quot; xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot; xmlns:r=&quot;urn:schemas-rinconnetworks-com:metadata-1-0/&quot; xmlns=&quot;urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/&quot;&gt;&lt;item id=&quot;-1&quot; parentID=&quot;-1&quot; restricted=&quot;true&quot;&gt;&lt;res protocolInfo=&quot;http-get:*:application/octet-stream:*&quot;&gt;http://192.168.0.10:26125/content/c2/b16/f44100/[INTER-RADIO]24.wav&lt;/res&gt;&lt;r:streamContent&gt;&lt;/r:streamContent&gt;&lt;r:radioShowMd&gt;&lt;/r:radioShowMd&gt;&lt;dc:title&gt;[INTER-RADIO]24.wav&lt;/dc:title&gt;&lt;upnp:class&gt;object.item&lt;/upnp:class&gt;&lt;/item&gt;&lt;/DIDL-Lite&gt;"/><r:NextTrackURI val=""/><r:NextTrackMetaData val=""/><r:EnqueuedTransportURI val="http://192.168.0.10:26125/content/c2/b16/f44100/[INTER-RADIO]24.wav"/><r:EnqueuedTransportURIMetaData val="&lt;DIDL-Lite xmlns=&quot;urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/&quot; xmlns:dc=&quot;http://purl.org/dc/elements/1.1/&quot; xmlns:r=&quot;urn:schemas-rinconnetworks-com:metadata-1-0/&quot; xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot;&gt;&lt;item id=&quot;[INTER-RADIO]24-au87&quot; parentID=&quot;au87&quot; refID=&quot;&quot; restricted=&quot;true&quot; &gt;&lt;dc:title&gt; Rock FM 97.4 (Top 40-Pop)  [64kbps]&lt;/dc:title&gt;&lt;upnp:class&gt;object.item.audioItem.audioBroadcast&lt;/upnp:class&gt;&lt;upnp:writeStatus&gt;NOT_WRITABLE&lt;/upnp:writeStatus&gt;&lt;res bitsPerSample=&quot;16&quot; nrAudioChannels=&quot;2&quot; protocolInfo=&quot;http-get:*:audio/wav:DLNA.ORG_PN=WAV;DLNA.ORG_OP=01&quot; sampleFrequency=&quot;44100&quot;&gt;http://192.168.0.10:26125/content/c2/b16/f44100/[INTER-RADIO]24.wav&lt;/res&gt;&lt;upnp:albumArtURI&gt;http://radiotime-logos.s3.amazonaws.com/s6924q.png&lt;/upnp:albumArtURI&gt;&lt;/item&gt;&lt;/DIDL-Lite&gt;"/><PlaybackStorageMedium val="NETWORK"/><AVTransportURI val="http://192.168.0.10:26125/content/c2/b16/f44100/[INTER-RADIO]24.wav"/><AVTransportURIMetaData val="&lt;DIDL-Lite xmlns=&quot;urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/&quot; xmlns:dc=&quot;http://purl.org/dc/elements/1.1/&quot; xmlns:r=&quot;urn:schemas-rinconnetworks-com:metadata-1-0/&quot; xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot;&gt;&lt;item id=&quot;[INTER-RADIO]24-au87&quot; parentID=&quot;au87&quot; refID=&quot;&quot; restricted=&quot;true&quot; &gt;&lt;dc:title&gt; Rock FM 97.4 (Top 40-Pop)  [64kbps]&lt;/dc:title&gt;&lt;upnp:class&gt;object.item.audioItem.audioBroadcast&lt;/upnp:class&gt;&lt;upnp:writeStatus&gt;NOT_WRITABLE&lt;/upnp:writeStatus&gt;&lt;res bitsPerSample=&quot;16&quot; nrAudioChannels=&quot;2&quot; protocolInfo=&quot;http-get:*:audio/wav:DLNA.ORG_PN=WAV;DLNA.ORG_OP=01&quot; sampleFrequency=&quot;44100&quot;&gt;http://192.168.0.10:26125/content/c2/b16/f44100/[INTER-RADIO]24.wav&lt;/res&gt;&lt;upnp:albumArtURI&gt;http://radiotime-logos.s3.amazonaws.com/s6924q.png&lt;/upnp:albumArtURI&gt;&lt;/item&gt;&lt;/DIDL-Lite&gt;"/><CurrentTransportActions val="Play, Stop, Pause, Seek, Next, Previous"/></InstanceID></Event>'}
        '''



    def on_device_event_seq(self, sid, seq, changed_vars):

#        print changed_vars

        # check it is a cd event - just pass these through without seq/queueing
        # remember that we subscribe to cd for ZP renderer as well as all servers
        current_renderer = self.control_point.get_current_renderer()
        if current_renderer != None and current_renderer.udn in self.known_zone_players:
            if self.control_point.get_cd_service(current_renderer).event_sid == sid:    
                self.process_cd_event_renderer(sid, seq, changed_vars)
                return
        else:
            if self.control_point.get_current_server() != None:
                if self.control_point.get_cd_service().event_sid == sid:    
                    self.process_cd_event(sid, seq, changed_vars)
                    return

        if self.control_point.get_current_server() != None:
            if self.control_point.get_cd_service().event_sid == sid:    
                self.process_cd_event(sid, seq, changed_vars)
                return
        else:
            current_renderer = self.control_point.get_current_renderer()
            if current_renderer != None and current_renderer.udn in self.known_zone_players:
                if self.control_point.get_cd_service(current_renderer).event_sid == sid:    
                    self.process_cd_event_renderer(sid, seq, changed_vars)
                    return
    
        # check it is an rc event - just pass these through without seq/queueing
        # TODO: add separate queue/seq for these?
        if 'LastChange' in changed_vars and changed_vars['LastChange'] != None:
            if self.control_point.get_rc_service().event_sid == sid:    
                self.process_device_event_seq(sid, seq, changed_vars)
                return
    
        seq = int(seq)
        # don't process events that come late in sequence, unless it's a dummy event (seq=-1)
        if seq != -1:
            for k, v in changed_vars.items():
    #            if k == "LastChange": print str(datetime.datetime.now()) + " @@@@      event=" + str(k) + " seq=" + str(seq) + " sid=" + sid
                if (sid, k) in self.last_event_seq:
    #                if k == "LastChange": print str(datetime.datetime.now()) + " @@@@      last seq=" + str(self.last_event_seq[(sid, k)])
                    if self.last_event_seq[(sid, k)] > seq:
    #                    if k == "LastChange": print str(datetime.datetime.now()) + " @@@@      rejected (seq=" + str(seq) + " last seq=" + str(self.last_event_seq[(sid, k)])
                        self.check_event_queue()
                        return
    #            if k == "LastChange": print str(datetime.datetime.now()) + " @@@@      set seq=" + str(seq)
                self.last_event_seq[(sid, k)] = seq

        # queue up events so they are processed in order
#        if k == "LastChange": print str(datetime.datetime.now()) + " @@@@      queued"
        self.event_queue.put((sid, seq, changed_vars))
        self.check_event_queue()


    def check_event_queue(self):
        # process events from queue one at a time
#        print str(datetime.datetime.now()) + " @@@@@@    ceq called"
        to_process = True
        while to_process == True:
#            print str(datetime.datetime.now()) + " @@@@@@    loop"
            self.event_lock.acquire()
#            print str(datetime.datetime.now()) + " @@@@@@    locked"
            try:
                (sid, seq, changed_vars) = self.event_queue.get(False)
#                print str(datetime.datetime.now()) + " @@@@@@    dequeued"
                self.process_device_event_seq(sid, seq, changed_vars)
#                print str(datetime.datetime.now()) + " @@@@@@    after process"
            except Empty:
                to_process = False
#                print str(datetime.datetime.now()) + " @@@@@@    empty"
            finally:
                self.event_lock.release()
#                print str(datetime.datetime.now()) + " @@@@@@    finally"


    def process_cd_event(self, sid, seq, changed_vars):
        #{'SystemUpdateID': '89', 'ContainerUpdateIDs': 'Q:0,72'}
#        if 'ContainerUpdateIDs' in changed_vars:
#            containerupdate = changed_vars['ContainerUpdateIDs'].split(',')
        pass

    def process_cd_event_renderer(self, sid, seq, changed_vars):

        #{'SystemUpdateID': '89', 'ContainerUpdateIDs': 'Q:0,72'}
        if 'ContainerUpdateIDs' in changed_vars:
            if changed_vars['ContainerUpdateIDs'] != None:
                containerupdate = changed_vars['ContainerUpdateIDs'].split(',')
                if containerupdate[0] == 'Q:0':
                    # queue for a ZP renderer has been updated, re-browse
                    
                    print "cd event: " + str(changed_vars['ContainerUpdateIDs'])
                    
                    if self.queue_entry != None:
                        self.browse_queue(self.queue_entry)
                        self.queue_updateid = containerupdate[1]


    def process_device_event_seq(self, sid, seq, changed_vars):

#        print "changed_vars: " + str(changed_vars)
#        print "sid: " + str(sid)
#        print "seq: " + str(seq)

#        if self.control_point.get_current_renderer() != None:
#            print "  rc sid: " + str(self.control_point.get_rc_service().event_sid)
#            print "  avt sid: " + str(self.control_point.get_at_service().event_sid)
#            print "  services: " + str(self.control_point.get_current_renderer().services)
#            for k,s in self.control_point.get_current_renderer().services.iteritems():
#                print "    k: " + str(k)
#                print "    s: " + str(s)
#                print "    event_sid: " + str(s.event_sid)
 
        # check it is a LastChange event
        if 'LastChange' in changed_vars.keys() and changed_vars['LastChange'] != None and changed_vars['LastChange'] != 'NOT_IMPLEMENTED'  and changed_vars['LastChange'] != '0':
            if self.control_point.get_rc_service().event_sid == sid:
#            if self.control_point.get_current_renderer().get_rc_service().event_sid == sid:
                # event from RenderingControl
                ns = "{urn:schemas-upnp-org:metadata-1-0/RCS/}"
                elt = self.from_string(changed_vars['LastChange'])
                self.remove_namespace(elt, ns)
                # check if it is initial event message
                if self.current_renderer_events_rc == {}:
                    # save all tags
                    self.process_event_tags_rc(elt, self.current_renderer_events_rc)
#                    log.debug('cre_rc: %s' % self.current_renderer_events_rc)
                    # get volume details
                    if 'OutputFixed' in self.current_renderer_events_rc.keys():
                        self.current_renderer_output_fixed = self.current_renderer_events_rc['OutputFixed']
                    else:
                        self.current_renderer_output_fixed = '0'

                    if 'Volume_Master' in self.current_renderer_events_rc.keys():
                        if self.current_renderer_output_fixed == '0':
                            self.current_volume = float(self.current_renderer_events_rc['Volume_Master'])
                            self.volume_fixed = 0

                    if self.current_renderer_output_fixed == '1':
                        if self.get_renderer_friendy_name() in self.rooms:
                            self.current_volume = float(current_renderer_output_fixed_volume)
                            self.volume_fixed = 0
                        else:
                            self.volume_fixed = 1

                    if 'Mute_Master' in self.current_renderer_events_rc.keys():
                        self.volume_mute = self.current_renderer_events_rc['Mute_Master']

                else:
                    # not initial message, update vars
                    tag_list = {}                    
                    self.process_event_tags_rc(elt, tag_list)
                    # process changed tags                    
#                    log.debug('tl: %s' % tag_list)
                    for key, value in tag_list.iteritems():
                        self.current_renderer_events_rc[key] = value
                        
                        if key == 'Volume_Master':
                            if self.current_renderer_output_fixed == '0':
                                self.current_volume = float(value)
                                self.volume_fixed = 0
                        elif key == 'Mute_Master':
                            self.volume_mute = value
                        elif key == 'OutputFixed':
                            # TODO: check whether we need to move the next line out of the if statement
                            self.current_renderer_output_fixed = value
                            self.current_volume = float(value)
                            if self.current_renderer_output_fixed == '1':
                                if self.get_renderer_friendy_name() in self.rooms:
                                    self.volume_fixed = 0
                                else:
                                    self.volume_fixed = 1

#                return
            elif self.control_point.get_at_service().event_sid == sid or (self.control_point.get_at_service().event_sid == '' and self.control_point.get_current_renderer().udn == sid):
                # event from AVTransport
#                print str(datetime.datetime.now()) + " @@@@@@@@  AVT start"
                # TODO: check if we need to remove the ns, and if it is actually removed anyway
                ns = "{urn:schemas-upnp-org:metadata-1-0/AVT/}"
                elt = self.from_string(changed_vars['LastChange'])
                self.remove_namespace(elt, ns)
                # check if it is initial event message
                if self.current_renderer_events_avt == {}:
                    # save all tags
                    self.process_event_tags_avt(elt, self.current_renderer_events_avt)
                    # set GUI as appropriate
                    self.now_playing, self.now_extras, self.now_playing_dict, self.now_extras_dict, aaURI = self.current_music_item.unwrap_metadata(self.current_renderer_events_avt)
                            # HACK: sending avt service of current renderer in case current_server is not selected - uses same URL...
                            # TODO: can we get this from zone player instead?
                    self.album_art = getAlbumArtURL(self.control_point.get_at_service(), aaURI)
                    # transport state
                    if 'TransportState' in self.current_renderer_events_avt.keys():
                        self.set_play(self.current_renderer_events_avt['TransportState'])
                else:
                    # not initial message, update vars
                    tag_list = {}
                    self.process_event_tags_avt(elt, tag_list)
#                    log.debug('tl: %s' % tag_list)
                    # save changed tags                    
                    for key, value in tag_list.iteritems():
                        self.current_renderer_events_avt[key] = value
                    # process changed tags (after saving them as need all related ones to be updated too)
                    for key, value in tag_list.iteritems():
                        # set GUI as appropriate
                        if key == 'CurrentTrackMetaData':
                            self.now_playing, self.now_extras, self.now_playing_dict, self.now_extras_dict, aaURI = self.current_music_item.unwrap_metadata(self.current_renderer_events_avt)
                                    # HACK: sending avt service of current renderer in case current_server is not selected - uses same URL...
                                    # TODO: can we get this from zone player instead?
                            self.album_art = getAlbumArtURL(self.control_point.get_at_service(), aaURI)
                        elif key == 'TransportState':
                            self.set_play(value)
#                print str(datetime.datetime.now()) + " @@@@@@@@  AVT end"
#                return
            
        elif 'ThirdPartyMediaServers' in changed_vars:

            # for these, need to associate them with each zoneplayer
            # - use sid

            elt = self.from_string(changed_vars['ThirdPartyMediaServers'])
            '''
            'ThirdPartyMediaServers':
            <MediaServers>
                <Ex 
                    CURL="http://192.168.0.3:1400/msprox?uuid=02286246-a968-4b5b-9a9a-defd5e9237e0" 
                    EURL="http://192.168.0.10:2869/upnphost/udhisapi.dll?event=uuid:02286246-a968-4b5b-9a9a-defd5e9237e0+urn:upnp-org:serviceId:ContentDirectory"
                    T="2"
                    EXT="1"/>
                <MediaServer 
                    Name="Windows Media (Henkelis)" 
                    UDN="02286246-a968-4b5b-9a9a-defd5e9237e0" 
                    Location="http://192.168.0.10:2869/upnphost/udhisapi.dll?content=uuid:02286246-a968-4b5b-9a9a-defd5e9237e0"/>
                <Ex 
                    CURL="http://192.168.0.10:56043/ContentDirectory/50565062-8a5b-7f33-c3de-168e9401eaee/control.xml" 
                    EURL="http://192.168.0.10:56043/ContentDirectory/50565062-8a5b-7f33-c3de-168e9401eaee/event.xml" 
                    T="1" 
                    EXT=""/>
                <MediaServer 
                    Name="Asset UPnP: HENKELIS" 
                    UDN="50565062-8a5b-7f33-c3de-168e9401eaee" 
                    Location="http://192.168.0.10:56043/DeviceDescription.xml"/>
                <Service UDN="UDN_USERNAME" Md="" Password="PASSWORD" NumAccounts="1" Username0="USERNAME" Md0="" Password0="PASSWORD"/>
            </MediaServers>
            '''
            mediaserver = {}
            mediaservers = {}
            c = 0
            for entry in elt:
                log.debug("changed_vars %s", changed_vars)
                log.debug("entry %s", entry)
                # assumes Ex entry comes before MediaServer entry!
                if entry.tag == 'Ex':
                    mediaserver['CURL'] = entry.attrib['CURL']
                    mediaserver['EURL'] = entry.attrib['EURL']
                    mediaserver['T'] = entry.attrib['T']
                    mediaserver['EXT'] = entry.attrib['EXT']
                if entry.tag == 'MediaServer':
#                    mediaserver['Name'] = "Sonos: " + entry.attrib['Name']
                    mediaserver['Name'] = entry.attrib['Name']
                    mediaserver['UDN'] = entry.attrib['UDN']
                    mediaserver['Location'] = entry.attrib['Location']
                    
                    
                    # check if we have already created this mediaserver for one of the zoneplayers
                    found = False
#                    print " "
#                    print ">>>>>>>>>> UDN: " + str(mediaserver['UDN'])
                    for ssid, sserver in self.thirdpartymediaservers.iteritems():
                        if found:
                            break
#                        print ">>>>>>>>>> sserver: " + str(sserver)
                        for i, mserver in sserver.items():
#                            print ">>>>>>>>>> mserver: " + str(mserver)
                            if mediaserver['UDN'] == mserver['UDN']:
#                                print ">>>>>>>>>> found"
#                                print ">>>>>>>>>> found"
#                                print ">>>>>>>>>> found"
                                found = True
                                break

#                    print ">>>>>>>>>> sid: " + str(sid) + "  Name: " + str(mediaserver['Name'])

                    if not found:
                        # not already created so create service
                        self.control_point.make_third_party_mediaserver_service(mediaserver)
#                        print ">>>>>>>>>>     make server."
                    
                    # save list anew each time in case anything has changed
                    mediaservers[c] = mediaserver
                    c += 1
                    mediaserver = {}
                   
                if entry.tag == 'Service':
                    services = {}
                    for name, value in entry.items():
                        services[name] = value
#                    services['UDN']         = entry.attrib['UDN']
#                    services['Md']          = entry.attrib['Md']
#                    services['Password']    = entry.attrib['Password']
                    
                    self.services[entry.attrib['UDN']] = services

            self.thirdpartymediaservers[sid] = mediaservers
#            print ">>>>>>>>> tpms after : " + str(self.thirdpartymediaservers[sid])

            '''
            ZoneGroupTopology
            <e:propertyset xmlns:e="urn:schemas-upnp-org:event-1-0">
                <e:property>
                    <ZoneGroupState>
                        <ZoneGroups>
                            <ZoneGroup Coordinator="RINCON_000E5830D2F001400" ID="RINCON_000E5830D2F001400:1">
                                <ZoneGroupMember UUID="RINCON_000E5830D2F001400" Location="http://192.168.0.3:1400/xml/zone_player.xml" ZoneName="Kitchen" Icon="x-rincon-roomicon:kitchen" SoftwareVersion="11.7-19141" MinCompatibleVersion="10.20-00000" BootSeq="136"/>
                            </ZoneGroup>
                            <ZoneGroup Coordinator="RINCON_000E5823A88A01400" ID="RINCON_000E5823A88A01400:3">
                                <ZoneGroupMember UUID="RINCON_000E5823A88A01400" Location="http://192.168.0.14:1400/xml/zone_player.xml" ZoneName="Living Room" Icon="x-rincon-roomicon:living" SoftwareVersion="11.7-19141" MinCompatibleVersion="10.20-00000" BootSeq="84"/>
                            </ZoneGroup>
                        </ZoneGroups>
                    </ZoneGroupState>
                </e:property>
                <e:property>
                    <ThirdPartyMediaServers>
                        <MediaServers>
                            <Service UDN="USERNAME" Md="" Password="PASSWORD"/>
                        </MediaServers>
                    </ThirdPartyMediaServers>
                </e:property>
                <e:property>
                    <AvailableSoftwareUpdate>
                        <UpdateItem xmlns="urn:schemas-rinconnetworks-com:update-1-0" Type="Software" Version="11.7-19141" UpdateURL="http://update.sonos.com/firmware/Gold/v3.0-Hendrix-GC2_Gold/^11.7-19141" DownloadSize="0"/>
                    </AvailableSoftwareUpdate>
                </e:property>
                <e:property>
                    <AlarmRunSequence>RINCON_000E5823A88A01400:84:0</AlarmRunSequence>
                </e:property>
            </e:propertyset>

            'ThirdPartyMediaServers':
            <MediaServers>
                <Ex CURL="http://192.168.0.7:1400/msprox?uuid=02286246-a968-4b5b-9a9a-defd5e9237e0" 
                    EURL="http://192.168.0.10:2869/upnphost/udhisapi.dll?event=uuid:02286246-a968-4b5b-9a9a-defd5e9237e0+urn:upnp-org:serviceId:ContentDirectory" 
                    T="2" 
                    EXT="1"/>
                <MediaServer Name="Windows Media (Henkelis)" 
                             UDN="02286246-a968-4b5b-9a9a-defd5e9237e0" 
                             Location="http://192.168.0.10:2869/upnphost/udhisapi.dll?content=uuid:02286246-a968-4b5b-9a9a-defd5e9237e0"/>
                <Service UDN="USERNAME" Md="" Password="PASSWORD"/>
            </MediaServers>

            ContentDirectory
            <e:propertyset xmlns:e="urn:schemas-upnp-org:event-1-0">
                <e:property><SystemUpdateID>9</SystemUpdateID></e:property>
                <e:property><ContainerUpdateIDs>S:,3</ContainerUpdateIDs></e:property>
                <e:property><ShareListRefreshState>NOTRUN</ShareListRefreshState></e:property>
                <e:property><ShareIndexInProgress>0</ShareIndexInProgress></e:property>
                <e:property><ShareIndexLastError></ShareIndexLastError></e:property>
                <e:property><UserRadioUpdateID>RINCON_000E5823A88A01400,11</UserRadioUpdateID></e:property>
                <e:property><SavedQueuesUpdateID>RINCON_000E5830D2F001400,6</SavedQueuesUpdateID></e:property>
                <e:property><ShareListUpdateID>RINCON_000E5823A88A01400,195</ShareListUpdateID></e:property>
                <e:property><RecentlyPlayedUpdateID>RINCON_000E5823A88A01400,0</RecentlyPlayedUpdateID></e:property>
            </e:propertyset>

            '''


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
#                print "rc: " + str(nodename) + " = " + str(val)
                
    def process_event_tags_avt(self, elt, event_list):
        # save values
        
        print "elt: " + str(elt)
        
        InstanceID = elt.find('InstanceID')
        
        print "InstanceID: " + str(InstanceID)
        
        if InstanceID != None:
            event_list['InstanceID'] = InstanceID.get('val')    # not checking this at present, assuming zero
            
            print "val: " + event_list['InstanceID']
            
            for child in elt.findall('InstanceID/*'):
                nodename = child.tag
                val = child.get('val')
                event_list[nodename] = val
#                print "avt: " + str(nodename) + " = " + str(val)
                # check for metadata associated with tag
                if nodename.endswith('MetaData'):
                    if val != '' and val != 'NOT_IMPLEMENTED':
    #                    log.debug('PROCESS EVENT TAGS AVT val: %s' % val)
                        # get the item element from within the DIDL-lite element
                        
                        # Sonos has an issue with returning more than 1024 characters in the val attrib of
                        # r:EnqueuedTransportURIMetaData and AVTransportURIMetaData in a NOTIFY
                        # (strangely there is no problem with CurrentTrackMetaData)
                        # NOTE - when Sonos sets those itself it doesn't set some elements so they don't exceed 1024
                        # - if those elements are not complete, ignore them (TODO: work out whether that affects 
                        # any further processing we do that needs them)
                        # TODO: work out how to stop these attribs exceeding 1024 chars

                        if val.endswith('</DIDL-Lite>'):

                            # sometimes an empty DIDL-Lite is returned
                            eitem = ElementItem().from_string(val)
                            if eitem:

                                item = eitem[0]
                                # get the class of the item
                                upnp_class = find(item, 'upnp', 'class').text

                                # check if current renderer is a zone player
                                current_renderer = self.control_point.get_current_renderer()

                                is_sonos = False
                                if current_renderer.udn in self.known_zone_players:
                                    is_sonos = True
                                    # as it's a Sonos, parse the attributes into a Sonos object to capture the extended elements
                                    if upnp_class == 'object.item.audioItem.audioBroadcast':
                                        elt = SonosAudioBroadcast()
                                    elif upnp_class == 'object.item.audioItem.musicTrack':
                                        elt = SonosMusicTrack()
                                    elif upnp_class == 'object.item.audioItem.musicTrack.recentShow':
                                        elt = SonosMusicTrackShow()
                                    elif upnp_class == 'object.item':
                                        elt = SonosItem()
                                        '''                                    
                                        <r:EnqueuedTransportURI val="x-rincon-playlist:RINCON_000E5830D2F001400#A:ALBUMARTIST/Jeff%20Buckley/"/>
                                        <r:EnqueuedTransportURIMetaData val="<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">
                                            <item id="A:ALBUMARTIST/Jeff%20Buckley/" parentID="A:ALBUMARTIST/Jeff%20Buckley" restricted="true">
                                                <dc:title>All</dc:title>
                                                <upnp:class>object.container.playlistContainer.sameArtist</upnp:class>
                                                <desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">RINCON_AssociatedZPUDN</desc>
                                            </item>
                                        </DIDL-Lite>                                    
                                        '''
    # XML created by selecting all from artist
    # THIS NEEDS TESTING...                                    
                                    elif upnp_class.startswith('object.container.playlistContainer'):
                                        elt = PlaylistContainer()
                                    else:
                                        # oops, don't know what we're dealing with - pass to non-sonos processing
                                        # TODO: decide which other classes we need to Sonos-ise
                                        is_sonos = False
                                    if is_sonos:
                                        elt.from_element(item)

                                if not is_sonos:
                                    # not a Sonos or we don't recognise the class, get the outer class name
                                    # TODO: do we want to move this to didl-lite (so it recognises the classes from there)?
                                    names = upnp_class.split('.')
                                    class_name = names[-1]
                                    class_name = "%s%s" % (class_name[0].upper(), class_name[1:])
                                    try:
                                        upnp_class = eval(class_name)
                                        elt = upnp_class()
                                        elt.from_element(item)
    #                                    print "@@ elt: " + str(elt)
                                    except Exception, e:
                                        raise UnknownClassError('Unknown upnp class: ' + upnp_class) 

                                event_list[nodename] = elt


    def get_position_info(self):
        self.current_position = self.control_point.get_position_info()
        self.current_track = self.current_position['Track']
        self.current_track_duration = self.current_position['TrackDuration']
        self.current_track_URI = self.current_position['TrackURI']
        self.current_track_metadata = self.current_position['TrackMetaData']
        self.current_track_relative_time_position = self.current_position['RelTime']

    def clear_position_info(self):
        self.current_position = {}
        self.current_track = '-1'
        self.current_track_duration = ''
        self.current_track_URI = ''
        self.current_track_metadata = ''
        self.current_track_relative_time_position = ''




    def get_renderer_friendy_name(self):
        current_renderer = self.control_point.get_current_renderer()
        if current_renderer.udn in self.known_zone_names:
            friendly_name = self.known_zone_names[current_renderer.udn]
        else:
            friendly_name = current_renderer.friendly_name
        return friendly_name




    def _event_subscribe_callback(self, cargo, subscription_id, timeout):
        log.debug('Event subscribe done cargo=%s sid=%s timeout=%s', cargo, subscription_id, timeout)

    def _event_renewal_callback(self, cargo, subscription_id, timeout):
# TODO: add error processing for if renewal fails - basically resubscribe. NEW - check if this is catered for in 0.10.0
        log.debug('Event renew done cargo=%s sid=%s timeout=%s', cargo, subscription_id, timeout)

    def _event_unsubscribe_callback(self, cargo, subscription_id):
        log.debug('Event unsubscribe done cargo=%s sid=%s', cargo, subscription_id)

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

    def _on_refresh_clicked(self, button):
        log.debug('refresh clicked')

        run_async_function(self.control_point.force_discovery, ())

#        self.control_point.force_discovery()
#        rt = RefreshThread(self.control_point.force_discovery)
#        rt.start()


    def process_browse(self, type, id, searchstring='', searchoperator='', name='', sequence=0, count=-1, setkey='', entryname='', hierarchynames=[]):

        print "process_browse:"
        print "             type: " + type
        print "               id: " + id
        print "             name: " + name
        print "              seq: " + str(sequence)
#        print "        entryname: " + str(entryname)
        print "            count: " + str(count)
        print "     searchstring: " + str(searchstring)
        print "   searchoperator: " + str(searchoperator)

        # TODO: replace these literals with items from various lists - remember we need to know what type they are....
        if type == "RadioTime_ROOT":
            self.radiotime_getlastupdate()
            self.browse_radiotime(id, "root", newtype="RADIOTIME", sequence=sequence, setkey=setkey)
        elif type == "RADIOTIME":
            self.browse_radiotime(id, newtype="RADIOTIME", sequence=sequence, setkey=setkey)

        elif type == "Napster_ROOT":
#            self.browse_napster(id, "root", searchstring=searchstring)
            self.browse_napster_async(id, "root", newtype="NAPSTER", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count, setkey=setkey)
        elif type == "NAPSTER":
#            self.browse_napster(id, searchstring=searchstring)
            self.browse_napster_async(id, newtype="NAPSTER", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count, setkey=setkey)

        elif type == "Deezer_ROOT":
            self.browse_deezer(id, "root")

        elif type == "Twitter_ROOT":
            self.browse_twitter(id, "root")

        elif type == "SonosLibrary_ROOT":
#            self.browse_sonos_library(id, "root", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count)
            self.browse_sonos_library_async(id, "root", newtype="SONOSLIBRARY", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count, setkey=setkey)
        elif type == "SONOSLIBRARY":
#            self.browse_sonos_library(id, searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count)
            self.browse_sonos_library_async(id, newtype="SONOSLIBRARY", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count, setkey=setkey)
            
        elif type == "SONOSMUSICSERVER":
            self.browse_media_server_async(id, newtype="SONOSMUSICSERVER", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count, setkey=setkey)
            
        elif type == "SonosShares_ROOT":
#            self.browse_media_server(id)
            self.browse_media_server_async(id, newtype="SONOSMUSICSERVER", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count, setkey=setkey)

        elif type == "SonosCurrentQueue_ROOT":
            # TODO: fix this
            current_renderer = self.control_point.get_current_renderer()
            self.browse_media_server_async(id, newtype="SONOSCURRENTQUEUE", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count, setkey=setkey, device=current_renderer)

        elif type == "SONOSCURRENTQUEUE":
            # TODO: fix this
            current_renderer = self.control_point.get_current_renderer()
            self.browse_media_server_async(id, newtype="SONOSCURRENTQUEUE", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count, setkey=setkey, device=current_renderer)

        elif type == "SonosSavedQueues_ROOT":
#            self.browse_media_server(id)
            self.browse_media_server_async(id, newtype="SONOSMUSICSERVER", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count, setkey=setkey)

        elif type == "SonosGlobalSearch_ROOT":
            self.browse_media_server(id)

        elif type == "ThirdPartyMediaServer_ROOT":
##            self.search_thirdparty_media_server(name, id, "root")
#            self.browse_thirdparty_media_server(name, id, "root")
            self.browse_thirdparty_media_server_async(name, id, "root", newtype="THIRDPARTYMEDIASERVER", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count, setkey=setkey)
        elif type == "THIRDPARTYMEDIASERVER":
#            self.browse_thirdparty_media_server(name, id)
            self.browse_thirdparty_media_server_async(name, id, newtype="THIRDPARTYMEDIASERVER", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count, setkey=setkey)

        elif type == "MSMediaServer_ROOT":
            self.search_ms_media_server(name, id, "root", sequence=sequence, setkey=setkey)
        elif type == "MSMEDIASERVER":
            self.search_ms_media_server(name, id, sequence=sequence, setkey=setkey)
            
        elif type == "MusicServer_ROOT":
            self.browse_media_server_async(id, "root", newtype="MUSICSERVER", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count, setkey=setkey)

        elif type == "MUSICSERVER":
            self.browse_media_server_async(id, newtype="MUSICSERVER", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count, setkey=setkey)

        elif type == "MusicServerSearch_ROOT":
            self.browse_media_server_async(id, "root", newtype="MUSICSERVER", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count, setkey=setkey)

        elif type == "LineIn_ROOT":
            self.browse_media_server_async(id, "root", newtype="MUSICSERVER", searchstring=searchstring, searchoperator=searchoperator, sequence=sequence, count=count, setkey=setkey)

        elif type == "TEST_ROOT":
            self.run_test(id, "root")

        else:
            print type
            self.set_messagebar('The item you selected is not currently supported by pycpoint')







    def _on_play_clicked(self, play_button, *args, **kwargs):
        self.do_play()

    def _on_stop_clicked(self, stop_button, *args, **kwargs):
        self.stop()

    def _on_next_clicked(self, next_button, *args, **kwargs):
        self.next()

    def _on_previous_clicked(self, previous_button, *args, **kwargs):
        self.previous()

    def _on_mute_clicked(self, mute_button, *args, **kwargs):
        self.do_mute()

    def do_mute(self):
        print "do_mute. volume_mute: " + str(self.volume_mute)
        if self.volume_mute == '0': self.volume_mute = '1'
        else: self.volume_mute = '0'
        if self.current_renderer_output_fixed == '1':
            if self.get_renderer_friendy_name() in self.rooms:
                if self.volume_mute == '0':
                    self.ip_volume_change(self.VOLUME_MUTE)
                else:
                    self.ip_volume_change(self.VOLUME_UNMUTE)
            return
        self.mute()

    def _on_volume_changed(self, volume_button, *args, **kwargs):
        volume = args[0]
        self.do_volume(volume)

    def do_volume(self, volume):            
        if self.current_renderer_output_fixed == '1':
            if self.get_renderer_friendy_name() in self.rooms:
                if volume > self.current_renderer_output_fixed_volume:
                    self.ip_volume_change(self.VOLUME_UP)
                else:
                    self.ip_volume_change(self.VOLUME_DOWN)
                self.current_renderer_output_fixed_volume = volume
            return
#        log.debug('VOLUME: %s' % volume)
        self.volume(volume=volume)

    def _on_about_activated(self, widget):
        pass # TODO

    def ip_volume_change(self, volume_change):
        print 'VOLUME CHANGE: ' + volume_change
        key = self.get_renderer_friendy_name() + "," + volume_change
        change_data = self.rooms_volumes[key]
#        print 'CHANGE DATA: ' + change_data
        self.control_point._ssdp_server.udp_transport.send_data(change_data, self.ir_ip, self.ir_port)
        print "DATA SENT"

    def _main_quit(self):
        self.cancel_subscriptions()
        self.stop_proxies()
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

#def main():
#    try:
#        gui = ControlPointGUI()
#    except KeyboardInterrupt, e:
#        quit()
def main():

    web = ControlPointWeb()
    reactor.main()
#    raw_input("Press Enter to terminate")
    web._main_quit()
    if not web.options.proxyonly:
        web.control_point.destroy()

#        import traceback        
#        traceback.print_stack()

if __name__ == "__main__":
#    import profile
#    profile.run('main()')
    main()
    
