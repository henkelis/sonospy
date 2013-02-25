#
# MediaServer
#
# Copyright (c) 2013 Mark Henkelis
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

import sys
import os
import re
import time
import datetime
import ConfigParser
import sqlite3
import codecs
import operator
import datetime

from brisa.core import log
from brisa.core import webserver
from brisa.utils.looping_call import LoopingCall

from transcode import checktranscode, checksmapitranscode, checkstream

from dateutil.parser import parse as parsedate
from dateutil.relativedelta import relativedelta as datedelta

from xml.sax.saxutils import escape, unescape

enc = sys.getfilesystemencoding()

MULTI_SEPARATOR = '\n'

DEFAULTYEAR = 1
DEFAULTMONTH = 1
DEFAULTDAY = 1
DEFAULTDATE = datetime.datetime(DEFAULTYEAR, DEFAULTMONTH, DEFAULTDAY)

class MediaServer(object):

    # constants

    noitemsfound = 'No items found'

    id_length     = 100000000
    id_range      = 99999999
    half_id_start = 50000000

    user_parentid               = 000000000
    contributingartist_parentid = 100000000
    artist_parentid             = 200000000
    album_parentid              = 300000000
    composer_parentid           = 400000000
    genre_parentid              = 500000000
    genre_artist_parentid       = 600000000
    track_parentid              = 700000000
    playlist_parentid           = 800000000
    favourite_parentid          = 900000000
    favouritetrack_parentid    = 1000000000
    dynamic_parentid_start     = 1100000000
    
    # default values, overriden by caller

    containerstart = {
                      'album':               album_parentid,
                      'artist':              artist_parentid,
                      'composer':            composer_parentid,
                      'contributingartist':  contributingartist_parentid,
                      'favourite':           favourite_parentid,
                      'genre':               genre_parentid,
                      'playlist':            playlist_parentid,
                      'track':               track_parentid,
                      'usersearch':          user_parentid,
                     }

    statichierarchy = {
                       'album':               'track',
                       'artist':              'album',
                       'contributingartist':  'album',
                       'composer':            'album',
                       'genre':               'artist',
                       'playlist':            'track',
                       'track':               'leaf',
                      }

    tracktypes = [
                  favouritetrack_parentid,  # Favourite track
                  track_parentid,           # Track
                 ]

    flatrootitems = [
                     ('%s' % album_parentid, 'Albums'),
                     ('%s' % artist_parentid, 'Artists'),
                     ('%s' % composer_parentid, 'Composers'),
                     ('%s' % contributingartist_parentid, 'Contributing Artists'),
                     ('%s' % genre_parentid, 'Genres'),
                     ('%s' % playlist_parentid, 'Playlists'),
                     ('%s' % track_parentid, 'Tracks'),
                    ]

    artist_class = 'object.container.person.musicArtist'
##    contributingartist_class = ''
    album_class = 'object.container.album.musicAlbum'
    composer_class = 'object.container.person.musicArtist'
    genre_class = 'object.container.person.musicArtist'
    track_class = 'object.item.audioItem.musicTrack'
    playlist_class = 'object.container.playlistContainer'

    def __init__(self, proxy, dbspec, structure, proxyaddress, webserverurl, wmpurl):

        log.debug('MediaServer.__init__ structure: %s' % structure)

        self.proxy = proxy
        self.dbspec = dbspec
        dbpath, self.dbname = os.path.split(dbspec)
        self.structure = structure
        self.proxyaddress = proxyaddress
        self.webserverurl = webserverurl
        self.wmpurl = wmpurl

        # always need container options from Proxy
        # get ini settings for Proxy
        self.load_proxy_ini()

        # if hierarchical, need container options from SMAPI
        # if hierarchical_default, don't need ones from ini
        # note - this will overwrite entries such as simplesorts
        if self.structure == 'HIERARCHY_DEFAULT':
            self.structure == 'HIERARCHY'
            self.load_smapi_default()
        elif self.structure == 'HIERARCHY':
            # get ini settings for SMAPI
            self.load_smapi_ini()
        
        self.prime_cache()

        self.containerupdateid = 0
        self.playlistupdateid = 0

    ######################
    # Proxy ini processing
    ######################

    def load_proxy_ini(self):

        # get path replacement strings
        try:
            self.pathreplace = self.proxy.config.get('INI', 'network_path_translation')
            if ',' in self.pathreplace:
                valuestring = self.pathreplace.split(',')
                self.pathbefore = valuestring[0]
                self.pathafter = valuestring[1]
                log.debug("pathbefore: %s", self.pathbefore)
                log.debug("pathafter: %s", self.pathafter)
        except ConfigParser.NoSectionError:
            self.pathreplace = None
        except ConfigParser.NoOptionError:
            self.pathreplace = None

        # get art preference
        self.prefer_folderart = False
        try:
            prefer_folderart_option = self.proxy.config.get('INI', 'prefer_folderart')
            if prefer_folderart_option.lower() == 'y':
                self.prefer_folderart = True
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        # get albumartist setting
        self.use_albumartist = False
        try:
            ini_albumartist = self.proxy.config.get('INI', 'use_albumartist')
            if ini_albumartist.lower() == 'y':
                self.use_albumartist = True
        except ConfigParser.NoSectionError:
            self.use_albumartist = False
        except ConfigParser.NoOptionError:
            self.use_albumartist = False

        # get album identification setting
        self.album_distinct_artist = 'album'        # default
        self.album_distinct_albumartist = 'album'   # default
        self.album_groupby_artist = 'album'         # default
        self.album_groupby_albumartist = 'album'    # default
        self.album_group = ['album']                # default
        try:
            ini_album_identification = self.proxy.config.get('INI', 'album_identification')
            flags = ini_album_identification.lower().split(',')
            ident_flags = []
            for i in flags:
                ident_flags.append(i.strip())
            if 'artist' in ident_flags or 'albumartist' in ident_flags:
                self.album_distinct_artist += ' || artist'
                self.album_groupby_artist += ', artist'
                self.album_distinct_albumartist += ' || albumartist'
                self.album_groupby_albumartist += ', albumartist'
                if self.use_albumartist:
                    self.album_group.append('albumartist')
                else:
                    self.album_group.append('artist')
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        # get albumartist setting
        self.show_separate_albums = False
        try:
            ini_show_separate_albums = self.proxy.config.get('INI', 'show_separate_albums')
            if ini_show_separate_albums.lower() == 'y':
                self.show_separate_albums = True
        except ConfigParser.NoSectionError:
            self.show_separate_albums = False
        except ConfigParser.NoOptionError:
            self.show_separate_albums = False

        # get duplicates setting
        self.show_duplicates = False
        try:
            ini_duplicates = self.proxy.config.get('INI', 'show_duplicates')
            if ini_duplicates.lower() == 'y':
                self.show_duplicates = True
        except ConfigParser.NoSectionError:
            self.show_duplicates = False
        except ConfigParser.NoOptionError:
            self.show_duplicates = False
        if self.show_duplicates:
            self.album_distinct_duplicate = ' || aa.duplicate'
            self.album_groupby_duplicate = ', aa.duplicate'
            self.album_where_duplicate = ''
            self.album_and_duplicate = ''
        else:
            self.album_distinct_duplicate = ''
            self.album_groupby_duplicate = ''
            self.album_where_duplicate = ' where aa.duplicate = 0'
            self.album_and_duplicate = ' and aa.duplicate = 0'

        # make distinct and groupby settings
        self.distinct_albumartist = '%s%s' % (self.album_distinct_albumartist, self.album_distinct_duplicate)
        self.groupby_albumartist = '%s%s' % (self.album_groupby_albumartist, self.album_groupby_duplicate)
        self.distinct_artist = '%s%s' % (self.album_distinct_artist, self.album_distinct_duplicate)
        self.groupby_artist = '%s%s' % (self.album_groupby_artist, self.album_groupby_duplicate)
        self.distinct_composer = '%s%s' % ('album', self.album_distinct_duplicate)
        self.groupby_composer = '%s%s' % ('album', self.album_groupby_duplicate)

        # get virtual display settings
        self.display_virtuals_in_album_index = True
        try:
            ini_display_virtuals_in_album_index = self.proxy.config.get('virtuals', 'display_virtuals_in_album_index')
            if ini_display_virtuals_in_album_index[:1].lower() == 'n':
                self.display_virtuals_in_album_index = False
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        self.display_virtuals_in_artist_index = True
        try:
            ini_display_virtuals_in_artist_index = self.proxy.config.get('virtuals', 'display_virtuals_in_artist_index')
            if ini_display_virtuals_in_artist_index[:1].lower() == 'n':
                self.display_virtuals_in_artist_index = False
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        self.display_virtuals_in_contributingartist_index = True
        try:
            ini_display_virtuals_in_contributingartist_index = self.proxy.config.get('virtuals', 'display_virtuals_in_contributingartist_index')
            if ini_display_virtuals_in_contributingartist_index[:1].lower() == 'n':
                self.display_virtuals_in_contributingartist_index = False
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        self.display_virtuals_in_composer_index = True
        try:
            ini_display_virtuals_in_composer_index = self.proxy.config.get('virtuals', 'display_virtuals_in_composer_index')
            if ini_display_virtuals_in_composer_index[:1].lower() == 'n':
                self.display_virtuals_in_composer_index = False
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        # get work display settings
        self.display_works_in_album_index = True
        try:
            ini_display_works_in_album_index = self.proxy.config.get('works', 'display_works_in_album_index')
            if ini_display_works_in_album_index[:1].lower() == 'n':
                self.display_works_in_album_index = False
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        self.display_works_in_artist_index = True
        try:
            ini_display_works_in_artist_index = self.proxy.config.get('works', 'display_works_in_artist_index')
            if ini_display_works_in_artist_index[:1].lower() == 'n':
                self.display_works_in_artist_index = False
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        self.display_works_in_contributingartist_index = True
        try:
            ini_display_works_in_contributingartist_index = self.proxy.config.get('works', 'display_works_in_contributingartist_index')
            if ini_display_works_in_contributingartist_index[:1].lower() == 'n':
                self.display_works_in_contributingartist_index = False
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        self.display_works_in_composer_index = True
        try:
            ini_display_works_in_composer_index = self.proxy.config.get('works', 'display_works_in_composer_index')
            if ini_display_works_in_composer_index[:1].lower() == 'n':
                self.display_works_in_composer_index = False
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        # get albumtypes
        self.album_albumtypes = self.get_possible_albumtypes('ALBUM')
        self.artist_album_albumtypes = self.get_possible_albumtypes('ARTIST_ALBUM')
        self.albumartist_album_albumtypes = self.get_possible_albumtypes('ALBUMARTIST_ALBUM')
        self.contributingartist_album_albumtypes = self.get_possible_albumtypes('CONTRIBUTINGARTIST_ALBUM')
        self.composer_album_albumtypes = self.get_possible_albumtypes('COMPOSER_ALBUM')
        self.album_albumtype_where = self.get_albumtype_where(self.album_albumtypes)
        self.artist_album_albumtype_where = self.get_albumtype_where(self.artist_album_albumtypes)
        self.albumartist_album_albumtype_where = self.get_albumtype_where(self.albumartist_album_albumtypes)
        self.contributingartist_album_albumtype_where = self.get_albumtype_where(self.contributingartist_album_albumtypes)
        self.composer_album_albumtype_where = self.get_albumtype_where(self.composer_album_albumtypes)

        # get sorts setting
        ini_alternative_index_sorting = 'N'
        try:
            ini_alternative_index_sorting = self.proxy.config.get('sort index', 'alternative_index_sorting')
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        ini_alternative_index_sorting = ini_alternative_index_sorting[:1].upper().strip()
        if ini_alternative_index_sorting in ('', 'N'):
            ais = 'N'
        else:
            ais = ini_alternative_index_sorting
            if ais in ('S', 'Y'):
                ais = 'S'
            elif ais == 'A':
                pass
            else:
                ais = 'N'
        self.alternative_index_sorting = ais
        log.debug(self.alternative_index_sorting)
        self.simple_sorts = self.get_proxy_simple_sorts()
        log.debug(self.simple_sorts)
        self.advanced_sorts = self.get_advanced_sorts()
        log.debug(self.advanced_sorts)

        # get separator settings
        self.show_chunk_separator = False
        try:
            ini_show_chunk_header = self.proxy.config.get('index section headers', 'show_section_header')
            if ini_show_chunk_header.lower() == 'y':
                self.show_chunk_separator = True
        except ConfigParser.NoSectionError:
            self.show_chunk_separator = False
        except ConfigParser.NoOptionError:
            self.show_chunk_separator = False

        self.show_chunk_separator_single = False
        try:
            ini_show_chunk_header_single = self.proxy.config.get('index section headers', 'show_section_header_on_single')
            if ini_show_chunk_header_single.lower() == 'y':
                self.show_chunk_separator_single = True
        except ConfigParser.NoSectionError:
            self.show_chunk_separator_single = False
        except ConfigParser.NoOptionError:
            self.show_chunk_separator_single = False

        self.show_chunk_header_empty = False
        try:
            ini_show_chunk_header_empty = self.proxy.config.get('index section headers', 'show_section_header_when_empty')
            if ini_show_chunk_header_empty.lower() == 'y':
                self.show_chunk_header_empty = True
        except ConfigParser.NoSectionError:
            self.show_chunk_header_empty = False
        except ConfigParser.NoOptionError:
            self.show_chunk_header_empty = False

        # override headers if sorts is off
        if self.alternative_index_sorting == 'N':
            self.show_chunk_separator = False
            self.show_chunk_separator_single = False
            self.show_chunk_header_empty = False

        self.chunk_separator_prefix = '-----'
        try:
            self.chunk_separator_prefix = self.proxy.config.get('index section headers', 'section_header_prefix')
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        self.chunk_separator_suffix = '-----'
        try:
            self.chunk_separator_suffix = self.proxy.config.get('index section headers', 'section_header_suffix')
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        self.prefix_sep = u'\u00a0'
        self.suffix_sep = u'\u007f'

        # get chunk metadata characters
        prefix_start, self.chunk_metadata_delimiter_prefix_start = self.get_delim('entry_prefix_start_separator', '[', self.prefix_sep)
        prefix_end, self.chunk_metadata_delimiter_prefix_end = self.get_delim('entry_prefix_end_separator', ']', self.prefix_sep, 'after')

#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('entry_prefix_start_separator', '[', 'before', u'\u0092')
#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('entry_prefix_start_separator', '[', 'before', u'\u200B\u034F\u0082\u0083\u0091\u0092\u2007\u2060\uFEFF\uFE00')
#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('entry_prefix_start_separator', '[', 'before', u'\u2029\u2028\u202f\u2061\u2062\u2063\uE000\uE001')
#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('entry_prefix_start_separator', '[', 'before', u'1 \uF7002 \uF7013 \uF85D4 \uF85C5 \uF8D76 \u000a7 \u000d')
#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('entry_prefix_start_separator', '[', 'before', u'1 \u000d')
#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('entry_prefix_start_separator', '[', 'before', u'\u007f')
#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('entry_prefix_start_separator', '[', 'before', u'\u0f0c')
#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('entry_prefix_start_separator', '[', 'before', u'\u007f \u232b \u0080 \u000a \u000d \u001b \u009f')
#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('entry_prefix_start_separator', '[')

        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('entry_suffix_start_separator', '[', self.suffix_sep, 'before')
        suffix_end, self.chunk_metadata_delimiter_suffix_end = self.get_delim('entry_suffix_end_separator', ']', self.suffix_sep)

        missing, self.chunk_metadata_empty = self.get_delim('entry_extras_empty', '_', self.prefix_sep)

        self.dont_display_separator_for_empty_prefix = False
        try:
            ini_dont_display_separator_for_empty_prefix = self.proxy.config.get('index section headers', 'dont_display_separator_for_empty_prefix')
            if ini_dont_display_separator_for_empty_prefix.lower() == 'y':
                self.dont_display_separator_for_empty_prefix = True
        except ConfigParser.NoSectionError:
            self.dont_display_separator_for_empty_prefix = False
        except ConfigParser.NoOptionError:
            self.dont_display_separator_for_empty_prefix = False

        self.dont_display_separator_for_empty_suffix = False
        try:
            ini_dont_display_separator_for_empty_suffix = self.proxy.config.get('index section headers', 'dont_display_separator_for_empty_suffix')
            if ini_dont_display_separator_for_empty_suffix.lower() == 'y':
                self.dont_display_separator_for_empty_suffix = True
        except ConfigParser.NoSectionError:
            self.dont_display_separator_for_empty_suffix = False
        except ConfigParser.NoOptionError:
            self.dont_display_separator_for_empty_suffix = False


        dateformat, self.chunk_metadata_date_format = self.get_delim('entry_extras_date_format', '%d/%m/%Y', self.prefix_sep)

        self.searchre_pre = '%s[^%s]*%s' % (prefix_start, prefix_end, prefix_end)
        if not suffix_end:
            self.searchre_suf = '%s.*' % (suffix_start)
        else:
            self.searchre_suf = '%s[^%s]*%s' % (suffix_start, suffix_end, suffix_end)

        self.multi_pre = '^(%s){%s}' % (self.searchre_pre, '%s')
        self.multi_suf = '(%s){%s}$' % (self.searchre_suf, '%s')

        self.replace_pre = '%s%s%s' % (self.chunk_metadata_delimiter_prefix_start, '%s', self.chunk_metadata_delimiter_prefix_end)
        self.replace_suf = '%s%s%s' % (self.chunk_metadata_delimiter_suffix_start, '%s', self.chunk_metadata_delimiter_suffix_end)

        # get album to display
        self.now_playing_album_selected_default = 'last'
        self.now_playing_album = 'selected'    # default
        try:
            self.now_playing_album = self.proxy.config.get('INI', 'now_playing_album')
            self.now_playing_album = self.now_playing_album.lower()
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        if not self.now_playing_album in ['all', 'first', 'last', 'selected']: self.now_playing_album = 'selected'

        self.now_playing_album_combiner = '/'    # default
        try:
            self.now_playing_album_combiner = self.proxy.config.get('INI', 'now_playing_album_combiner')
            if self.now_playing_album_combiner.startswith("'") and self.now_playing_album_combiner.endswith("'"):
                self.now_playing_album_combiner = self.now_playing_album_combiner[1:-1]
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        # get artist to display
        self.now_playing_artist_selected_default = 'last'
        self.now_playing_artist = 'selected'    # default
        try:
            self.now_playing_artist = self.proxy.config.get('INI', 'now_playing_artist')
            self.now_playing_artist = self.now_playing_artist.lower()
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        if not self.now_playing_artist in ['all', 'first', 'last', 'selected']: self.now_playing_artist = 'selected'

        self.now_playing_artist_combiner = '/'    # default
        try:
            self.now_playing_artist_combiner = self.proxy.config.get('INI', 'now_playing_artist_combiner')
            if self.now_playing_artist_combiner.startswith("'") and self.now_playing_artist_combiner.endswith("'"):
                self.now_playing_artist_combiner = self.now_playing_artist_combiner[1:-1]
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        # get virtual and work album/artist to display
        self.virtual_now_playing_album = False    # default
        try:
            ini_virtual_now_playing_album = self.proxy.config.get('INI', 'virtual_now_playing_album')
            if ini_virtual_now_playing_album.lower() == 'y':
                self.virtual_now_playing_album = True
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        self.virtual_now_playing_artist = False    # default
        try:
            ini_virtual_now_playing_artist = self.proxy.config.get('INI', 'virtual_now_playing_artist')
            if ini_virtual_now_playing_artist.lower() == 'y':
                self.virtual_now_playing_artist = True
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        self.work_now_playing_album = False    # default
        try:
            ini_work_now_playing_album = self.proxy.config.get('INI', 'work_now_playing_album')
            if ini_work_now_playing_album.lower() == 'y':
                self.work_now_playing_album = True
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        self.work_now_playing_artist = False    # default
        try:
            ini_work_now_playing_artist = self.proxy.config.get('INI', 'work_now_playing_artist')
            if ini_work_now_playing_artist.lower() == 'y':
                self.work_now_playing_artist = True
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

    ######################
    # SMAPI ini processing
    ######################

    def load_smapi_ini(self):

        # reset user id count
        self.next_user_id = self.user_parentid + 1

        # load user index data
        self.user_index_entries = self.load_user_indexes()
        log.debug('user_index_entries: %s' % self.user_index_entries)

        # load root and hierarchy data
        self.hierarchy_order, self.hierarchy_data, self.hierarchy_lookup, self.hierarchy_ini = self.load_hierarchy()
        self.debugout('hierarchy_order', self.hierarchy_order)
        self.debugout('hierarchy_data', self.hierarchy_data)
        self.debugout('hierarchy_lookup', self.hierarchy_lookup)
        self.debugout('hierarchy_ini', self.hierarchy_ini)
        self.rootitems = []
        dynamic_value = self.dynamic_parentid_start
        self.dynamichierarchy = {}
        self.hierarchies = {}
        self.hierarchytype = {}
        for entry in self.hierarchy_order:
            # get hierarchy
            entrystring, hierarchy = self.hierarchy_data[entry]
            # check if hierarchy supported statically, or needs creating dynamically

            # TODO: add list of valid fields to be set in ini

            nextnode = None
            prevnode = None
            static = True
            for node in hierarchy:

                if nextnode and node != nextnode:
                    # current node is not second node of a known static hierarchy
                    if prevnode not in self.dynamichierarchy:
                        # current node is not second node of a known dynamic hierarchy
                        static = False
                        self.dynamichierarchy[prevnode] = node
                if node in self.statichierarchy:
                    nextnode = self.statichierarchy[node]
                elif node in self.dynamichierarchy:
                    static = False
                    nextnode = self.dynamichierarchy[node]
                else:
                    # current node is not known, must be top level node
                    static = False
                    nextnode = 'dummy'

                prevnode = node

                if node not in self.containerstart:
                    value = dynamic_value
                    self.containerstart[node] = value
                    dynamic_value += self.id_length

            self.hierarchies[entry] = hierarchy
            self.hierarchytype[entry] = static
            self.rootitems += [(str(self.containerstart[entry]), entrystring)]

        # load user search data
        self.user_search_entries, self.user_search_ini = self.load_user_searches()
        self.debugout('user_search_entries', self.user_search_entries)
        self.debugout('user_search_ini', self.user_search_ini)

        # create search entries for user defined search entries
        self.searchitems = []
        for searchid, (searchtype, searchname, searchroot, searchfields) in self.user_search_entries.iteritems():
            # TODO: fix the fixed width of the format string below
            self.searchitems += [('%09i' % searchid, searchname)]

        # create further search entries for all except user defined root entries
        for (rootstart, rootname) in self.rootitems:
            firstindex = self.hierarchy_lookup[rootname][0]
            if firstindex not in self.user_index_entries.keys():
                self.searchitems += [(rootstart, rootname)]

        self.containername = {}
        for k,v in self.containerstart.iteritems():
            self.containername[v] = k

        self.debugout('statichierarchy', self.statichierarchy)
        self.debugout('dynamichierarchy', self.dynamichierarchy)
        self.debugout('hierarchies', self.hierarchies)
        self.debugout('hierarchytype', self.hierarchytype)
        self.debugout('containerstart', self.containerstart)
        self.debugout('containername', self.containername)
        self.debugout('rootitems', self.rootitems)
        self.debugout('searchitems', self.searchitems)

        dummy, self.smapi_date_format = self.get_delim('smapi_date_format', '%Y/%m/%d', ' ', section='SMAPI formats')

        # get sorts setting
        ini_alternative_index_sorting = 'N'
        try:
            ini_alternative_index_sorting = self.proxy.config.get('SMAPI sort', 'smapi_alternative_index_sorting')
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        ini_alternative_index_sorting = ini_alternative_index_sorting[:1].upper().strip()
        if ini_alternative_index_sorting in ('', 'N'):
            ais = 'N'
        else:
            ais = ini_alternative_index_sorting
            if ais in ('S', 'Y'):
                ais = 'S'
            elif ais == 'A':
                pass
            else:
                ais = 'N'
        self.smapi_alternative_index_sorting = ais
        log.debug(self.smapi_alternative_index_sorting)

        # get sorts settings - THESE WON'T BE USED AS ais = N
        self.smapi_simple_sorts = self.get_smapi_simple_sorts()
        self.debugout('smapi_simple_sorts', self.smapi_simple_sorts)
#        self.advanced_sorts = self.get_advanced_sorts()
#        log.debug(self.advanced_sorts)

    ##############################
    # SMAPI default ini processing
    ##############################

    def load_smapi_default(self):

        # reset user id count
        self.next_user_id = self.user_parentid + 1

        # load user index data
        self.user_index_entries = {}
        log.debug('user_index_entries: %s' % self.user_index_entries)

        # load root and hierarchy data
        self.hierarchy_order = [u'album', u'albumartist', u'composer', u'contributingartist', u'genre', u'playlist', u'track']

        self.hierarchy_data = {
                                'album': (u'Albums', [u'album', u'track']),
                                'playlist': (u'Playlists', [u'playlist', u'track']),
                                'track': (u'Tracks', [u'track']),
                                'contributingartist': (u'Contributing Artists', [u'contributingartist', u'album', u'track']),
                                'albumartist': (u'Artists', [u'albumartist', u'album', u'track']),
                                'composer': (u'Composers', [u'composer', u'album', u'track']),
                                'genre': (u'Genres', [u'genre', u'albumartist', u'album', u'track'])
                              }

        self.hierarchy_lookup = {
                                    'Composers': [u'composer', u'album', u'track'],
                                    'Genres': [u'genre', u'albumartist', u'album', u'track'],
                                    'Playlists': [u'playlist', u'track'],
                                    'Contributing Artists': [u'contributingartist', u'album', u'track'],
                                    'Tracks': [u'track'],
                                    'Artists': [u'albumartist', u'album', u'track'],
                                    'Albums': [u'album', u'track']
                                }

        self.hierarchy_ini = {
                                'Composers': [u'composer', u'album', u'track'],
                                'Genres': [u'genre', u'artist', u'album', u'track'],
                                'Playlists': [u'playlist', u'track'],
                                'Contributing Artists': [u'contributingartist', u'album', u'track'],
                                'Tracks': [u'track'],
                                'Artists': [u'artist', u'album', u'track'],
                                'Albums': [u'album', u'track'],
                             }

        self.debugout('hierarchy_order', self.hierarchy_order)
        self.debugout('hierarchy_data', self.hierarchy_data)
        self.debugout('hierarchy_lookup', self.hierarchy_lookup)
        self.debugout('hierarchy_ini', self.hierarchy_ini)

        self.rootitems = []
        dynamic_value = self.dynamic_parentid_start
        self.dynamichierarchy = {}
        self.hierarchies = {}
        self.hierarchytype = {}
        for entry in self.hierarchy_order:
            # get hierarchy
            entrystring, hierarchy = self.hierarchy_data[entry]
            # check if hierarchy supported statically, or needs creating dynamically

            # TODO: add list of valid fields to be set in ini

            nextnode = None
            prevnode = None
            static = True
            for node in hierarchy:

                if nextnode and node != nextnode:
                    # current node is not second node of a known static hierarchy
                    if prevnode not in self.dynamichierarchy:
                        # current node is not second node of a known dynamic hierarchy
                        static = False
                        self.dynamichierarchy[prevnode] = node
                if node in self.statichierarchy:
                    nextnode = self.statichierarchy[node]
                elif node in self.dynamichierarchy:
                    static = False
                    nextnode = self.dynamichierarchy[node]

                else:
                    # current node is not known, must be top level node
                    static = False
                    nextnode = 'dummy'

                prevnode = node

                if node not in self.containerstart:
                    value = dynamic_value
                    self.containerstart[node] = value
                    dynamic_value += self.id_length

            self.hierarchies[entry] = hierarchy
            self.hierarchytype[entry] = static
            self.rootitems += [(str(self.containerstart[entry]), entrystring)]

        # load user search data
        self.user_search_entries = {}
        self.user_search_ini = {}
        self.debugout('user_search_entries', self.user_search_entries)
        self.debugout('user_search_ini', self.user_search_ini)

        # create search entries for user defined search entries
        self.searchitems = []

        self.containername = {}
        for k,v in self.containerstart.iteritems():
            self.containername[v] = k

        self.debugout('statichierarchy', self.statichierarchy)
        self.debugout('dynamichierarchy', self.dynamichierarchy)
        self.debugout('hierarchies', self.hierarchies)
        self.debugout('hierarchytype', self.hierarchytype)
        self.debugout('containerstart', self.containerstart)
        self.debugout('containername', self.containername)
        self.debugout('rootitems', self.rootitems)
        self.debugout('searchitems', self.searchitems)

        dummy, self.smapi_date_format = self.get_delim('smapi_date_format', '%Y/%m/%d', ' ', section='SMAPI formats')

        # get sorts setting
        ais = 'N'
        self.smapi_alternative_index_sorting = ais
        log.debug(self.smapi_alternative_index_sorting)

        # get sorts settings
        self.smapi_simple_sorts = self.get_smapi_simple_sorts()
        self.debugout('smapi_simple_sorts', self.smapi_simple_sorts)
#        self.advanced_sorts = self.get_advanced_sorts()
#        log.debug(self.advanced_sorts)

    def get_artist_replacements(self):

        if self.use_albumartist:
            artisttypebefore = 'artist'
            artisttypeafter = 'albumartist'
        else:
            artisttypebefore = 'albumartist'
            artisttypeafter = 'artist'
        return artisttypebefore, artisttypeafter

    def load_user_indexes(self):

        user_index_entries = {}

        processing = False
        for line in codecs.open('pycpoint.ini','r','utf-8'):
            line = line.strip()
            if line == '': continue
            if line.startswith('#'): continue
            if line.endswith('\n'): line = line[:-1]
            if line == '[SMAPI user indexes]':
                processing = True
            elif processing and line.startswith('['):
                break
            elif processing:

                # format is:
                #    index = index_entry_name_1 , ... index_entry_field_n

                entry = ''
                entries = line.split('=')
                if entries[0] != '':
                    entry = entries[0]
                indexstring = ''
                if len(entries) > 1:
                    indexstring = entries[1]
                indexentries = indexstring.split(',')
                if entry != '' and indexentries != []:
                    user_index_entries[entry] = indexentries

        return user_index_entries

    def load_user_searches(self):

        user_search_entries = {}
        user_search_ini = {}

        processing = False
        for line in codecs.open('pycpoint.ini','r','utf-8'):
            line = line.strip()
            if line == '': continue
            if line.startswith('#'): continue
            if line.endswith('\n'): line = line[:-1]
            if line == '[SMAPI user search]':
                processing = True
            elif processing and line.startswith('['):
                break
            elif processing:

                # format is:
                #    search = index_entry_name_1 , ... index_entry_field_n
                # or
                #    search = root_entry_name / index_entry_field

                entry = ''
                entries = line.split('=')
                if entries[0] != '':
                    entry = entries[0]
                indexstring = ''
                if len(entries) > 1:
                    indexstring = entries[1]
                if '/' in indexstring:
                    # is a lower level search type
                    indexentries = indexstring.split('/')
                    if len(indexentries) == 2:
                        lookuproot = indexentries[0]
                        # first entry must be in hierarchy lookup
                        if lookuproot in self.hierarchy_ini.keys():
                            lookup_indexes = self.hierarchy_ini[lookuproot]
                            lookupindex = indexentries[1]
                            # second entry must be in that hierarchy's indexes
                            if lookupindex in lookup_indexes:
                                # get position in ini entry
                                indexentrypos = lookup_indexes.index(lookupindex)
                                # get translated index entry name
                                indexentryname = self.hierarchy_lookup[lookuproot][indexentrypos]
                                # get index start
                                indexentrystart = self.containerstart[indexentryname]
                                # save entry
                                user_search_entries[self.next_user_id] = ('lower', entry, lookuproot, [(indexentrystart, lookupindex)])
                                user_search_ini[entry] = (self.next_user_id, self.hierarchy_ini[lookuproot])
                                self.next_user_id += 1

                else:
                    # is a set of search indexes to combine (could be a single one)
                    indexentries = indexstring.split(',')
                    if entry != '' and indexentries != []:
                        # convert entries and get index starts
                        convindexentries = []
                        ini_index_entries = []
                        for rootindex in indexentries:
                            if rootindex in self.hierarchy_lookup.keys():
                                indexentryname = self.hierarchy_lookup[rootindex][0]
                                # get index start
                                indexentrystart = self.containerstart[indexentryname]
                                convindexentries += [(indexentrystart, indexentryname)]
                                ini_index_entries += [self.hierarchy_ini[rootindex][0]]
                        # save entry
                        if convindexentries != []:
                            user_search_entries[self.next_user_id] = ('multi', entry, '', convindexentries)
                            user_search_ini[entry] = (self.next_user_id, ini_index_entries)
                            self.next_user_id += 1

        return user_search_entries, user_search_ini

    def load_hierarchy(self):

        hierarchy_ini = {}
        hierarchy_data = {}
        hierarchy_lookup = {}
        hierarchy_order = []
        hierarchy_entries = {}

        processing = False
        for line in codecs.open('pycpoint.ini','r','utf-8'):
            line = line.strip()
            if line == '': continue
            if line.startswith('#'): continue
            if line.endswith('\n'): line = line[:-1]
            if line == '[SMAPI root]':
                processing = True
            elif processing and line.startswith('['):
                break
            elif processing:

                # format is:
                #    root_index_entry_name = index_entry_level_1_field / ... index_entry_level_n_field

                entries = line.split('=')
                if entries[0] != '':
                    entry = entries[0]
                hierarchystring = ''
                if len(entries) > 1:
                    hierarchystring = entries[1].lower()
                hierarchies_ini = hierarchystring.split('/')
                hierarchystring = self.convertartist(hierarchystring, '/')
                hierarchies = hierarchystring.split('/')
                index = hierarchies[0]
                if index != '':
                    # save settings from ini
                    hierarchy_ini[entry] = hierarchies_ini
                    # make sure root of hierarchy is unique
#                    indexcount = 2
                    indexentry = index
#                    while indexentry in hierarchy_order:
#                        indexentry = '%s_%s' % (index, indexcount)
#                        indexcount += 1
#                    hierarchy_order += [indexentry]
                    newhierarchies = []
                    # make sure rest of hierarchy is unique
                    prev_hierarchyentry = indexentry
                    for hierarchyentry in hierarchies[1:]:
                        entrycount = 2
                        newpreventry = prev_hierarchyentry
                        while newpreventry in hierarchy_entries.keys() and hierarchy_entries[newpreventry] != hierarchyentry:
                            newpreventry = '%s_%s' % (prev_hierarchyentry.split('_')[0], entrycount)
                            entrycount += 1
                        hierarchy_entries[newpreventry] = hierarchyentry
                        newhierarchies += [newpreventry]
                        prev_hierarchyentry = hierarchyentry
                    newhierarchies += [hierarchyentry]
                    hierarchy_data[newhierarchies[0]] = (entry, newhierarchies)
                    hierarchy_lookup[entry] = newhierarchies
                    hierarchy_order += [newhierarchies[0]]

        return hierarchy_order, hierarchy_data, hierarchy_lookup, hierarchy_ini

    smapi_simple_keys = [
        'smapiname=',
        'controller=',
        'range_field=',
        'index_range=',
        'sort_order=',
        'entry_prefix=',
        'entry_suffix=',
        'active=',
        ]

    smapi_advanced_keys = smapi_simple_keys + [
        'section_sequence=',
        'section_albumtype=',
        'section_name=',
        ]

    smapi_simple_key_dict = {
        'smapiname': 'all',
        'controller': 'all',
        'range_field': '',
        'index_range': ('','',''),
        'sort_order': '',
        'entry_prefix': '',
        'entry_suffix': '',
        'active': 'y',
        }

    smapi_advanced_key_dict = smapi_simple_key_dict.copy()
    smapi_advanced_key_dict.update({
        'section_sequence': 1,
        'section_albumtype': 'all',
        'section_name': '',
        })

    def get_smapi_simple_sorts(self):
        simple_sorts = []
        simple_keys = self.smapi_simple_key_dict.copy()
        processing_index = False
        for line in codecs.open('pycpoint.ini','r','utf-8'):
            line == line.strip()
            if line.endswith('\n'): line = line[:-1]
            if line.startswith('[SMAPI ') and line.endswith(' sort index]'):
                log.debug(line)
                if processing_index:
                    if simple_keys != self.smapi_simple_key_dict:
                        simple_sorts.append((index, simple_keys))
                        simple_keys = self.smapi_simple_key_dict.copy()
                indexdata = line[7:-12].strip()
                log.debug(indexdata)
                indexfacets = indexdata.split('/')
                if len(indexfacets) > 1:
                    indexname = indexfacets[0]
                    indexentry = indexfacets[-1].lower()
                    indexcount = 0
                    if ' ' in indexentry:
                        indexparts = indexentry.split(' ')
                        indexentry = indexparts[0]
                        try:
                            indexcount = int(indexparts[-1])
                        except ValueError:
                            pass
                    processing_index = False
                    # find index entry in hierarchy set from ini
                    if indexname in self.hierarchy_ini.keys():
                        inihierarchy = self.hierarchy_ini[indexname]
                        log.debug(inihierarchy)
                        if indexentry in inihierarchy:
                            indexsuffix = ''
                            if indexcount != 0: indexsuffix = str(indexcount)
                            indexentrypos = inihierarchy.index(indexentry)
                            # get translated index entry names
                            hierarchy = self.hierarchy_lookup[indexname]
                            index = '%s_%s%s' % (hierarchy[0], hierarchy[indexentrypos], indexsuffix)
                            processing_index = True
                    elif indexname in self.user_search_ini.keys():
                        usersearchid, iniusersearch = self.user_search_ini[indexname]
                        log.debug(iniusersearch)
                        if indexentry in iniusersearch:
                            indexsuffix = ''
                            if indexcount != 0: indexsuffix = str(indexcount)
                            indexentrypos = iniusersearch.index(indexentry)
                            # get translated index entry names
                            index = '%s_%s%s' % (usersearchid, iniusersearch[indexentrypos], indexsuffix)
                            processing_index = True
                continue
            if processing_index:
                for key in self.smapi_simple_keys:
                    if line.startswith(key):
                        value = line[len(key):].strip().lower()
                        if key == 'index_range=':
                            simple_keys[key[:-1]] = self.convert_range(value)
                        else:
                            value = self.convertartist(value, ',')
                            simple_keys[key[:-1]] = value.lower()
        if processing_index:
            if simple_keys != self.smapi_simple_key_dict:
                simple_sorts.append((index, simple_keys))
        return simple_sorts

    def convert_range(self, rangestring):
        rangestring = rangestring.strip().lower()
        rangestring = " ".join(rangestring.split())
        rangefacets = rangestring.split(' ')
        units = ''
        rangestart = ''
        rangeend = ''
        if len(rangefacets) >= 3:
            if rangefacets[1] == 'to':
                # two values specified
                rangestart = rangefacets[0]
                rangeend = rangefacets[2]
            elif rangefacets[2] == 'to':
                # two values with units specified
                if len(rangefacets) == 5:
                    if rangefacets[1] == rangefacets[4]:
                        units = rangefacets[1]
                        rangestart = rangefacets[0]
                        rangeend = rangefacets[3]
            else:
                # three facets
                units = rangefacets[2]
                rangestart = rangefacets[0]
                rangeend = rangefacets[1]
        return (rangestart, rangeend, units)

    def convertartist(self, artist, delim):
        # assumes comma separated string passed
        artisttypebefore, artisttypeafter = self.get_artist_replacements()
        artistentries = artist.split(delim)
        artistconversions = []
        for entry in artistentries:
            entry = entry.strip()
            if entry == artisttypebefore or entry.startswith('%s ' % artisttypebefore):  # allow for text after the entry (e.g. desc)
                entry = '%s%s' % (artisttypeafter, entry[len(artisttypebefore):])
            artistconversions.append(entry)
        return delim.join(artistconversions)

    ###############
    # query service
    ###############

    def query(self, **kwargs):

        log.debug("Mediaserver.query: %s", kwargs)

        source = kwargs.get('Source', '')
        structure = kwargs.get('Structure', '')
        if source == 'SMAPI':
            structure = 'HIERARCHY'
            return self.hierarchicalQuery(kwargs)
        elif source == 'UPNP':
            if structure == 'HIERARCHY':
                return self.hierarchicalQuery(kwargs)
            elif structure == 'FLAT':
                return self.flatQuery(kwargs)

    def hierarchicalQuery(self, kwargs):

        log.debug("Mediaserver.hierarchicalQuery: %s", kwargs)

        # get name of ID field
        source = kwargs.get('Source', None)
        log.debug("source: %s" % source)
        if source == 'UPNP':
            action = kwargs.get('Action', None)
            if action == 'BROWSE':
                id = 'ObjectID'
            else:
                id = 'ContainerID'
        else: 
            id = 'ID'
        
        objectID = kwargs.get(id, '')
        log.debug("ObjectID: %s" % objectID)
        index = int(kwargs.get('StartingIndex', 0))
        log.debug("index: %s" % index)
        count = int(kwargs.get('RequestedCount', 100))
        log.debug("count: %s" % count)
        structure = kwargs.get('Structure', '')
        log.debug("Structure: %s" % structure)

        # work out what hierarchy data is asking for
        # it's either
        #     the root entry ('root' if from SMAPI, 0/1 if from UPnP)
        #     the search entry
        #     a track
        #     a playlist
        #     a list of IDs (a track or a playlist should be the last entry in a list and not alone)
        
        items = None
        track = False
        playlist = False
        if objectID == 'root' or objectID == '0' or objectID == '1':
            # TODO: process count/index (i.e. take note of how many entries are requested)
            items = self.rootitems
        elif objectID == 'search':
            # TODO: process count/index (i.e. take note of how many entries are requested)
            items = self.searchitems
        elif len(objectID) == 32 and not ':' in objectID:
            # track id is 32 hex chars
            track = True
        elif len(objectID) == 8 and not ':' in objectID:
            # playlist id is 8 hex chars, everything else will be 9 or more
            playlist = True
        elif '__' in objectID:
            # must be track (the only time we pass a faceted ID this way for hierarchical)
            track = True
        else:
            ids = objectID.split(':')
            idvals = []
            for oid in ids:
                try:
                    objectIDval = int(oid)
                    idvals += [objectIDval]
                except ValueError:
                    # shouldn't get here.....
                    pass

        log.debug("items: %s" % items)
        if items != None:

            # TODO: process count/index (i.e. take note of how many entries are requested)

            if source == 'SMAPI':

                total = len(items)

                return items, total, index, 'container'

            else:

                ret  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'

                for (id, title) in items:

                    ret += '<container id="%s" parentID="%s" restricted="true">' % (id, objectID)
                    ret += '<dc:title>%s</dc:title>' % (title)
                    ret += '<upnp:class>object.container</upnp:class>'
                    ret += '</container>'

                ret += '</DIDL-Lite>'
                count = len(items)
                totalMatches = len(items)

                return ret, count, totalMatches

        elif track:
        
            if source == 'SMAPI':

                # not allowed to call getMetadata for track for SMAPI
                # - gets called wrongly from PCDCR with double click on Linux
                return build_soap_error(600, 'Invalid to call getMetadata for track')

            else:

                return self.staticQuery(**kwargs)

        elif playlist:
        
            if source == 'SMAPI':

                # not allowed to call getMetadata for playlist for SMAPI
                return build_soap_error(600, 'Invalid to call getMetadata for playlist')

            else:

                return self.staticQuery(**kwargs)

# TODO: how to process track and playlist for UPnP/Hierarchy

        else:

            # have a list of objectIDvals - are a hierarchy of containers
            log.debug(idvals)

            # if last objectIDval is a key, need to append next container in hierarchy
            lastbrowsetype, lastbrowsebyid = self.get_index(idvals[-1])
            log.debug(lastbrowsetype)
            log.debug(lastbrowsebyid)

            if lastbrowsetype == 'usersearch':

                pass

            elif lastbrowsebyid:
                # but only if it's a container
                lastcontainerstart = self.containerstart[lastbrowsetype]
                log.debug(lastcontainerstart)
                if not lastcontainerstart in self.tracktypes:
                    lastcontainername = self.containername[lastcontainerstart]
                    log.debug(lastcontainername)

                    # get type of hierarchy
                    firstbrowsetype, firstbrowsebyid = self.get_index(idvals[0])

                    log.debug(firstbrowsetype)
                    log.debug(firstbrowsebyid)
                    log.debug(self.hierarchytype)

                    if firstbrowsetype in self.hierarchytype:
                        # first entry is root
                        static = self.hierarchytype[firstbrowsetype]
                    elif firstbrowsetype == 'usersearch':
                        # first browse type is a user search
                        static = False
                    log.debug(static)

                    if static:
                        nextcontainer = self.statichierarchy[lastcontainername]
                    else:
                        # look in dynamic first
                        if lastcontainername in self.dynamichierarchy:
                            nextcontainer = self.dynamichierarchy[lastcontainername]
                        else:
                            nextcontainer = self.statichierarchy[lastcontainername]
                    log.debug(nextcontainer)
                    idvals += [self.containerstart[nextcontainer]]
            log.debug(idvals)
            
            # if recursive requested, replace last item in hierarchy
            # with track
            # (assumes all hierarchies end in track, or at least
            #  that recursive will only be requested for tracks)
            recursive = kwargs.get('recursive', False)
            log.debug("recursive: %s" % recursive)
            if recursive:
            
                # if last entry has a user defined index as a parent,
                # append rather than replace as we need to take account
                # of any range in the user defined index
                append = False
                if len(idvals) > 1:
                    containeridval = idvals[-2]
                    parentidval = self.get_parent(containeridval)
                    if self.containername[parentidval] in self.user_index_entries.keys():
                        append = True
                if append:
                    idvals += [self.containerstart['track']]
                else:
                    idvals[len(idvals) - 1] = self.containerstart['track']
                log.debug(idvals)
            
            # process ids
            idkeys = {}
            hierarchy = ''
            for idval in idvals:
                # get browse type
                browsetype, browsebyid = self.get_index(idval)
                log.debug(browsetype)
                log.debug(browsebyid)
                # build up hierarchy
                hierarchy = ':'.join(filter(None, (hierarchy, browsetype)))
                log.debug(hierarchy)
                # get container offset
                containerstart = self.containerstart[browsetype]
                log.debug(containerstart)
                # create key entry
                idkeys[browsetype] = (idval, browsebyid, containerstart)
            log.debug(idkeys)
            # get type of last item in hierarchy
            lastcontainerstart = self.containerstart[browsetype]
            if lastcontainerstart in self.tracktypes:
                itemtype = 'track'
            else:
                itemtype = 'container'
            log.debug(itemtype)

            if lastbrowsetype != 'usersearch':
                # get first item in hierarchy
                firstbrowsetype, firstbrowsebyid = self.get_index(idvals[0])
                if firstbrowsetype in self.hierarchytype:
                    # first entry is root
                    static = self.hierarchytype[firstbrowsetype]
                elif firstbrowsetype == 'usersearch':
                    # first browse type is a user search
                    static = False
                log.debug(static)

            # if we get this far we have a list of IDs and we need to query the database
            
            controllername = kwargs.get('Controller', '')
            log.debug('Controller: %s' % controllername)
            controlleraddress = kwargs.get('Address', '')
            log.debug('Address: %s' % controlleraddress)
            term = kwargs.get('term', None)
            log.debug("term: %s" % term)

            if lastbrowsetype == 'usersearch' or not static:

                # dynamic
                # create call data to dynamicQuery and call it
                ContainerID = '999'     # dummy
                if term: SearchCriteria = term
                else: SearchCriteria = ''
                StartingIndex = str(index)
                RequestedCount = str(count)
                if lastbrowsetype == 'usersearch' or firstbrowsetype == 'usersearch':
                    SMAPIfull = []
                else:
                    SMAPIfull = self.hierarchies[firstbrowsetype]

                return self.dynamicQuery(Controller=controllername,
                                           Address=controlleraddress,
                                           ContainerID=ContainerID,
                                           SearchCriteria=SearchCriteria,
                                           StartingIndex=StartingIndex,
                                           RequestedCount=RequestedCount,
                                           SMAPIalpha=None,
                                           SMAPI=hierarchy,
                                           SMAPIkeys=idkeys,
                                           SMAPIfull=SMAPIfull,
                                           Source=source)

            else:

                # static
                # create call data to staticQuery and call it
                ID='999'     # dummy
                BrowseFlag = 'BrowseDirectChildren'
                if term: SearchCriteria = 'SEARCH::%s::%s' % (browsetype, term)
                else: SearchCriteria = ''
                StartingIndex = str(index)
                RequestedCount = str(count)

                return self.staticQuery(Controller=controllername,
                                          Address=controlleraddress,
                                          ID=ID,
                                          BrowseFlag=BrowseFlag,
                                          SearchCriteria=SearchCriteria,
                                          StartingIndex=StartingIndex,
                                          RequestedCount=RequestedCount,
                                          SMAPI=hierarchy,
                                          SMAPIkeys=idkeys,
                                          smapiservice=True,
                                          Action='BROWSE',
                                          Source=source,
                                          Structure=structure)


    def flatQuery(self, kwargs):

        log.debug("Mediaserver.flatQuery: %s", kwargs)

        # get name of ID field
        action = kwargs.get('Action', None)
        log.debug("action: %s" % action)
        if action == 'BROWSE':
            id = 'ObjectID'
        else: 
            id = 'ContainerID'
        
        objectID = kwargs.get(id, '')
        log.debug("ObjectID: %s" % objectID)

        searchCriteria = kwargs.get('SearchCriteria', '')
        log.debug('SearchCriteria: %s' % searchCriteria)

        # if root requested return that, otherwise query database
        if (objectID == '0' or objectID == '1') and searchCriteria == '':
        
            # TODO: process count/index (i.e. take note of how many entries are requested)

            ret  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'

## check whether we can return 'search' - and what class it would be...
##                                        or does it get that from search capabilities?
#######################################################################

            for (id, title) in self.flatrootitems:

                ret += '<container id="%s" parentID="%s" restricted="true">' % (id, objectID)
                ret += '<dc:title>%s</dc:title>' % (title)
                ret += '<upnp:class>object.container</upnp:class>'
                ret += '</container>'

            ret += '</DIDL-Lite>'
            count = len(self.flatrootitems)
            totalMatches = len(self.flatrootitems)

            return ret, count, totalMatches

        else:

            return self.staticQuery(**kwargs)



###########################################################################################################################
###########################################################################################################################
###########################################################################################################################



    def staticQuery(self, *args, **kwargs):
#        for key in kwargs:
#            print "another keyword arg: %s: %s" % (key, kwargs[key])

        log.debug("Mediaserver.staticQuery: %s", kwargs)

        '''

        Write up options we can get...
        
        '''

        source = kwargs.get('Source', None)
        log.debug("source: %s" % source)
        action = kwargs.get('Action', None)
        log.debug("action: %s" % action)
        structure = kwargs.get('Structure', '')
        log.debug("Structure: %s" % structure)

        if 'ID' in kwargs.keys():
            queryID = kwargs.get('ID', '')
        elif 'ContainerID' in kwargs.keys():
            queryID = kwargs.get('ContainerID', '')
        elif 'ObjectID' in kwargs.keys():
            queryID = kwargs.get('ObjectID', '')
        log.debug("queryID: %s" % queryID)

# TODO
# TODO: remember to decide what to do with titlesort and how to allow the user to select it (or other tags)
# TODO

        SMAPI = kwargs.get('SMAPI', '')
        log.debug('SMAPI: %s' % SMAPI)
        items = []

        SMAPIhierarchy = SMAPI.split(':')
        log.debug(SMAPIhierarchy)
        SMAPIkeys = kwargs.get('SMAPIkeys', '')
        log.debug(SMAPIkeys)

        smapiservice = kwargs.get('smapiservice', False)

        searchCriteria = kwargs.get('SearchCriteria', '')
        searchCriteria = self.fixcriteria(searchCriteria)
        log.debug('searchCriteria: %s' % searchCriteria.encode(enc, 'replace'))

        # query ID is a dummy for SMAPI
        # check SMAPI special cases for browse
        if SMAPI:
            if SMAPI == 'album:track':
                albumidval, browsebyid, containerstart = SMAPIkeys['album']
                queryID = '%s' % albumidval
            elif SMAPI == 'playlist:track':
                playlistidval, browsebyid, containerstart = SMAPIkeys['playlist']
                queryID = '%s' % playlistidval

        objectEntry = None
        track = False
        playlist = False
        search = False
        if len(queryID) == 32 and not ':' in queryID and not '_' in queryID:
            # track id is 32 hex chars
            track = True
        elif len(queryID) == 8 and not ':' in queryID and not '_' in queryID:
            # playlist id is 8 hex chars, everything else will be 9 or more
            playlist = True
        elif searchCriteria.startswith('SEARCH::'):
            # search requested
            search = True
        else:
            if '__' in queryID:
                objectfacets = queryID.split('__')
                objectTable = objectfacets[0]
                if len(objectfacets) == 2:
                    queryID = objectfacets[1]
                    objectEntry = None
                else:
                    objectEntry = objectfacets[1]
                    queryID = objectfacets[2]

        try:
            queryIDval = int(queryID)
        except ValueError:
            # must be track or playlist
            queryIDval = -1

        browsetype = ''
        log.debug("queryIDval: %s" % queryIDval)

        if queryIDval == 0 or queryIDval == 1:
            browsetype = 'Root'
        elif queryIDval == self.album_parentid:
            browsetype = 'Albums'
        elif queryIDval == self.artist_parentid:
            browsetype = 'Artists'
        elif queryIDval == self.composer_parentid:
            browsetype = 'Composers'
        elif queryIDval == self.contributingartist_parentid:
            browsetype = 'ContributingArtists'
        elif queryIDval == self.genre_parentid:
            browsetype = 'Genres'
        elif queryIDval == self.playlist_parentid:
            browsetype = 'Playlists'
        elif queryIDval == self.track_parentid:
            browsetype = 'Tracks'

        elif queryIDval > self.genre_artist_parentid and queryIDval <= (self.genre_artist_parentid + self.id_range):
            browsetype = 'GenreArtistAlbums'

        elif queryIDval > self.artist_parentid and queryIDval <= (self.artist_parentid + self.id_range):
            browsetype = 'ArtistAlbums'
        elif queryIDval > self.composer_parentid and queryIDval <= (self.composer_parentid + self.id_range):
            browsetype = 'ComposerAlbums'
        elif queryIDval > self.contributingartist_parentid and queryIDval <= (self.contributingartist_parentid + self.id_range):
            browsetype = 'ContributingArtistAlbums'
        elif queryIDval > self.genre_parentid and queryIDval <= (self.genre_parentid + self.id_range):
            browsetype = 'GenreArtists'

        elif queryIDval > self.album_parentid and queryIDval <= (self.album_parentid + self.id_range):
            browsetype = 'Album'
        elif queryIDval > self.playlist_parentid and queryIDval <= (self.playlist_parentid + self.id_range):
            browsetype = 'Playlist'
        elif queryIDval == -1:
            if track:
                browsetype = 'Track'
            elif playlist:
                browsetype = 'Playlist'
            elif search:
                browsetype = 'Search'
            else:
                browsetype = 'Track'

        log.debug("browsetype: %s" % browsetype)

        controllername = kwargs.get('Controller', '')
        controlleraddress = kwargs.get('Address', '')
        log.debug('Controller: %s' % controllername)
        log.debug('Address: %s' % controlleraddress)

        browseFlag = kwargs.get('BrowseFlag', None)
        searchCriteria = kwargs.get('SearchCriteria', '')
        log.debug('BrowseFlag: %s' % browseFlag)
        log.debug('SearchCriteria: %s' % searchCriteria)

        startingIndex = int(kwargs['StartingIndex'])
        requestedCount = int(kwargs['RequestedCount'])
        log.debug('StartingIndex: %s' % startingIndex)
        log.debug('RequestedCount: %s' % requestedCount)

        if browsetype in ['Album', 'Track', 'Playlist']:

            # create call data for browse and call it
            return self.browse(Controller=controllername,
                               Address=controlleraddress,
                               ObjectID='%s' % queryID,
                               objectEntry=objectEntry,
                               objectIDval=queryIDval,
                               StartingIndex=startingIndex,
                               RequestedCount=requestedCount,
                               SMAPI=SMAPI,
                               SMAPIkeys=SMAPIkeys,
                               smapiservice=smapiservice,
                               browse=browsetype,
                               Source=source)

        else:
        
            # note - SMAPI calls except those filtered earlier will fall through to here

            # create call data for search and call it
            return self.search(Controller=controllername,
                               Address=controlleraddress,
                               ContainerID='%s' % queryIDval,
                               SearchCriteria=searchCriteria,
                               StartingIndex=startingIndex,
                               RequestedCount=requestedCount,
                               SMAPI=SMAPI,
                               SMAPIkeys=SMAPIkeys,
                               smapiservice=smapiservice,
                               browse=browsetype,
                               Source=source)



###########################################################################################################################
###########################################################################################################################
###########################################################################################################################



    def browse(self, *args, **kwargs):

        log.debug("Mediaserver.browse: %s", kwargs)

        if self.proxy.db_persist_connection:
            db = self.proxy.db
        else:
            db = sqlite3.connect(self.dbspec)
#        log.debug(db)
        c = db.cursor()

        source = kwargs.get('Source', None)
        controllername = kwargs.get('Controller', '')
        controlleraddress = kwargs.get('Address', '')
        startingIndex = int(kwargs['StartingIndex'])
        requestedCount = int(kwargs['RequestedCount'])
        objectID = kwargs.get('ObjectID', None)
        objectIDval = kwargs.get('objectIDval', None)
        objectEntry = kwargs.get('objectEntry', None)
        browsetype = kwargs.get('browse', None)

        SMAPI = kwargs.get('SMAPI', '')
        log.debug('SMAPI: %s' % SMAPI)
        items = []

        SMAPIhierarchy = SMAPI.split(':')
        log.debug(SMAPIhierarchy)
        SMAPIkeys = kwargs.get('SMAPIkeys', '')
        # SMAPIkeys[browsetype] = (idval, browsebyid, containerstart)
        log.debug(SMAPIkeys)

        smapiservice = kwargs.get('smapiservice', False)

        if browsetype == 'Album':

            ret  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            count = 0

            # album and artist entry positions are passed in
            album_passed = False
            artist_passed = False
            albumartist_passed = False
            if not objectEntry:
                albumposition = 0
                artistposition = 0
                albumartistposition = 0
            else:
                objectEntries = objectEntry.split('_')
                albumposition = int(objectEntries[0])
                artistposition = int(objectEntries[1])
                albumartistposition = int(objectEntries[2])
                album_passed = True
                artist_passed = True
                albumartist_passed = True

            artist_selected = False
            album_selected = False
            if self.now_playing_artist == 'selected': artist_selected = True
            if self.now_playing_album == 'selected': album_selected = True

            # note that there is no way to select discrete tracks from an album
            # that relate to an artist, composer etc with this browse

            # album ID can be in one of two ranges, showing whether it is in the albums or albumsonly table
            if objectIDval >= self.album_parentid + self.half_id_start:
                statement = "select albumlist, artistlist, albumartistlist, duplicate, albumtype, separated from albumsonly where id = '%s'" % (objectID)
            else:
#                statement = "select albumlist, artistlist, albumartistlist, duplicate, albumtype, 0 from albums where id = '%s'" % (objectID)
                statement = "select albumlist, artistlist, albumartistlist, duplicate, albumtype, 1 from albums where id = '%s'" % (objectID)
            log.debug("statement: %s", statement)
            c.execute(statement)
            albumlist, artistlist, albumartistlist, album_duplicate, album_type, separated = c.fetchone()

            log.debug("albumlist: %s", albumlist)
            log.debug("artistlist: %s", artistlist)
            log.debug("albumartistlist: %s", albumartistlist)
            log.debug("album_duplicate: %s", album_duplicate)
            log.debug("album_type: %s", album_type)
            log.debug("separated: %s", separated)

            albumlist = escape_sql(albumlist)
            artistlist = escape_sql(artistlist)
            albumartistlist = escape_sql(albumartistlist)

            albumentry = self.get_entry_at_position(albumposition, albumlist)
            artistentry = self.get_entry_at_position(artistposition, artistlist)
            albumartistentry = self.get_entry_at_position(albumartistposition, albumartistlist)

            if album_type != 10:
                where = "n.dummyalbum='%s'" % albumentry
                if 'artist' in self.album_group:
                    where += " and n.artist='%s'" % artistentry
                if 'albumartist' in self.album_group:
                    where += " and n.albumartist='%s'" % albumartistentry
                if not 'artist' in self.album_group and not 'albumartist' in self.album_group:
                    if self.show_separate_albums and separated:
                        if self.use_albumartist:
                            where += " and n.albumartist='%s'" % albumartistentry
                        else:
                            where += " and n.artist='%s'" % artistentry
            else:
            
                log.debug('self.album_group: %s' % self.album_group)
                log.debug('self.show_separate_albums: %s' % self.show_separate_albums)
                log.debug('separated: %s' % separated)
            
                where = "n.album='%s'" % albumlist
                if 'artist' in self.album_group:
                    where += " and n.artist='%s'" % artistlist
                if 'albumartist' in self.album_group:
                    where += " and n.albumartist='%s'" % albumartistlist
                if not 'artist' in self.album_group and not 'albumartist' in self.album_group:
                    if self.show_separate_albums and separated:
                        if self.use_albumartist:
                            where += " and n.albumartist='%s'" % albumartistlist
                        else:
                            where += " and n.artist='%s'" % artistlist
            if self.show_duplicates:
                where += " and n.duplicate=%s" % album_duplicate
            else:
                where += " and n.duplicate=0"
            if album_type != 10:
                where += " and n.albumtype=%s" % album_type

            if smapiservice:
                sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                log.debug("sorttype: %s", sorttype)
                orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
            else:
                orderbylist = self.get_proxy_orderby('ALBUM', controllername)
            log.debug(orderbylist)
            for orderbyentry in orderbylist:
                orderby, prefix, suffix, albumtype, table, header = orderbyentry
                if not orderby or orderby == '':
                    if album_type != 10:
                        orderby = 'n.tracknumber, t.title'
                    else:
                        orderby = 'discnumber, tracknumber, title'
                state_pre_suf = (orderby, prefix, suffix, albumtype, table, header)

            if album_type != 10:
                # is a work or a virtual album
                countstatement = '''
                                    select count(*) from (select track_id from tracknumbers n where %s group by tracknumber)
                                 ''' % (where, )
                c.execute(countstatement)
                totalMatches, = c.fetchone()
                statement = '''
                                select t.*, n.tracknumber, n.coverart, n.coverartid, n.rowid from tracknumbers n join tracks t
                                on n.track_id = t.rowid
                                where %s
                                group by n.tracknumber
                                order by %s
                                limit %d, %d
                            ''' % (where, orderby, startingIndex, requestedCount)
                log.debug("statement: %s", statement)
                c.execute(statement)
            else:
                # is a normal album
                countstatement = "select count(*) from tracks n where %s" % (where)
                c.execute(countstatement)
                totalMatches, = c.fetchone()
                statement = "select * from tracks n where %s order by %s limit %d, %d" % (where, orderby, startingIndex, requestedCount)
                log.debug("statement: %s", statement)
                c.execute(statement)
            for row in c:
#                log.debug("row: %s", row)
                if album_type != 10:
                    id, id2, duplicate, title, artistshort, artist, album, genre, tracktracknumber, year, albumartistshort, albumartist, composershort, composer, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned, titlesort, albumsort, tracknumber, coverart, coverartid, rowid = row
                    cover, artid = self.choosecover(folderart, trackart, folderartid, trackartid, coverart, coverartid)
                else:
                    id, id2, duplicate, title, artistshort, artist, album, genre, tracknumber, year, albumartistshort, albumartist, composershort, composer, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned, titlesort, albumsort = row
                    cover, artid = self.choosecover(folderart, trackart, folderartid, trackartid)
                mime = fixMime(mime)

                wsfile = filename
                wspath = os.path.join(path, filename)
                path = self.convert_path(path)
                filepath = path + filename
                filepath = encode_path(filepath)
                filepath = escape(filepath, escape_entities)
                protocol = getProtocol(mime)
                contenttype = mime
                filetype = getFileType(filename)

                if SMAPI != '' and source == 'SMAPI':
                    transcode, newtype = checksmapitranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)
                    if transcode:
                        mime = 'audio/mpeg'
                else:
                    transcode, newtype = checktranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)
                if transcode:
                    dummyfile = self.dbname + '.' + id + '.' + newtype
                else:
                    dummyfile = self.dbname + '.' + id + '.' + filetype
                res = self.proxyaddress + '/WMPNSSv3/' + dummyfile
                if transcode:
                    log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s\ntranscodetype: %s' % (dummyfile, wsfile, wspath, contenttype, newtype))
                    dummystaticfile = webserver.TranscodedFileSonos(dummyfile, wsfile, wspath, newtype, contenttype, cover=cover)
                    self.proxy.wmpcontroller.add_transcoded_file(dummystaticfile)
                else:
                    log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s' % (dummyfile, wsfile, wspath, contenttype))
                    dummystaticfile = webserver.StaticFileSonos(dummyfile, wsfile, wspath, contenttype, cover=cover)
                    self.proxy.wmpcontroller.add_static_file(dummystaticfile)

                if cover != '' and not cover.startswith('EMBEDDED_'):
                    cvfile = getFile(cover)
                    cvpath = cover
                    coverfiletype = getFileType(cvfile)
                    dummycoverfile = self.dbname + '.' + str(artid) + '.' + coverfiletype
                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                    dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath)    # TODO: pass contenttype
                    self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)

                iduration = int(length)
                duration = maketime(float(length))

                if artist_passed and artist_selected:
                    albumartist = albumartistentry
                    artist = artistentry
                else:
                    if albumartistlist == '': albumartist = '[unknown albumartist]'
                    if artist_selected:
                        albumartist = self.get_entry(albumartistlist, self.now_playing_artist_selected_default, self.now_playing_artist_combiner)
                    else:
                        albumartistlist = albumartist
                        albumartist = self.get_entry(albumartistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                    albumartistposition = self.get_entry_position(albumartist, albumartistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                    if artistlist == '': artist = '[unknown artist]'
                    if artist_selected:
                        artist = self.get_entry(artistlist, self.now_playing_artist_selected_default, self.now_playing_artist_combiner)
                    else:
                        artistlist = artist
                        artist = self.get_entry(artistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                    artistposition = self.get_entry_position(artist, artistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                if album_passed and album_selected:
                    album = albumentry
                else:
                    if albumlist == '': album = '[unknown album]'
                    if album_selected:
                        album = self.get_entry(albumlist, self.now_playing_album_selected_default, self.now_playing_album_combiner)
                    else:
                        album = self.get_entry(albumlist, self.now_playing_album, self.now_playing_album_combiner)
                    albumposition = self.get_entry_position(album, albumlist, self.now_playing_album, self.now_playing_album_combiner)

                if title == '': title = '[unknown title]'

                orderby, prefix, suffix, albumtype, table, header = state_pre_suf
                p_prefix = self.proxy_makepresuffix(prefix, self.replace_pre, \
                           {'year':year, 'lastplayed':lastplayed, 'playcount':playcount, 'created':created, \
                            'lastmodified':lastmodified, 'inserted':inserted, 'artist':artist, 'albumartist':albumartist, \
                            'composer':composer, 'album':album, 'genre':genre, 'tracknumber':tracknumber, 'length':length, \
                            'path':path, 'filename':filename, \
                           })
                if p_prefix: title = '%s%s' % (p_prefix, title)
                p_suffix = self.proxy_makepresuffix(suffix, self.replace_suf,
                           {'year':year, 'lastplayed':lastplayed, 'playcount':playcount, 'created':created,
                            'lastmodified':lastmodified, 'inserted':inserted, 'artist':artist, 'albumartist':albumartist,
                            'composer':composer, 'album':album, 'genre':genre, 'tracknumber':tracknumber, 'length':length,
                            'path':path, 'filename':filename, \
                           })
                if p_suffix: title = '%s%s' % (title, p_suffix)

                title = escape(title)
                artist = escape(artist)
                albumartist = escape(albumartist)
                album = escape(album)
                tracknumber = self.convert_tracknumber(tracknumber)

                if album_type >= 21 and album_type <= 25:
                    if self.virtual_now_playing_album:
                        albumposition = '%sv%s' % (albumposition, rowid)
                    if self.virtual_now_playing_artist:
                        artistposition = '%sv%s' % (artistposition, rowid)
                        albumartistposition = '%sv%s' % (albumartistposition, rowid)
                elif album_type >= 31 and album_type <= 35:
                    if self.work_now_playing_album:
                        albumposition = '%sw%s' % (albumposition, rowid)
                    if self.work_now_playing_artist:
                        artistposition = '%sw%s' % (artistposition, rowid)
                        albumartistposition = '%sw%s' % (albumartistposition, rowid)


                if SMAPI != '':

                    if cover == '':
                        coverres = ''
                    elif cover.startswith('EMBEDDED_'):
                        coverres = self.proxyaddress + '/WMPNSSv3/' + dummyfile

                    metadatatype = 'track'
#                    metadata = (aristId, artist, composerId, composer, \
#                                albumId, album, albumArtURI, albumArtistId, \
#                                albumArtist, genreId, genre, duration)

                    # fix WMP urls if necessary
                    res = res.replace(self.webserverurl, self.wmpurl)
                    coverres = coverres.replace(self.webserverurl, self.wmpurl)

                    metadata = ('', artist, '', '', \
                                '', album, coverres, '', \
                                albumartist, '', '', iduration)
                    items += [(id, title, mime, res, 'track', metadatatype, metadata)]


                full_id = 'T__%s_%s_%s__%s' % (albumposition, artistposition, albumartistposition, id)

                count += 1
                ret += '<item id="%s" parentID="%s" restricted="true">' % (full_id, self.track_parentid)
                ret += '<dc:title>%s</dc:title>' % (title)
                ret += '<upnp:artist role="AlbumArtist">%s</upnp:artist>' % (albumartist)
                ret += '<upnp:artist role="Performer">%s</upnp:artist>' % (artist)
                ret += '<upnp:album>%s</upnp:album>' % (album)
                if tracknumber != 0:
                    ret += '<upnp:originalTrackNumber>%s</upnp:originalTrackNumber>' % (tracknumber)
                ret += '<upnp:class>%s</upnp:class>' % (self.track_class)
                ret += '<res duration="%s" protocolInfo="%s">%s</res>' % (duration, protocol, res)
#                if cover != '' and not cover.startswith('EMBEDDED_'):
#                    ret += '<upnp:albumArtURI>%s</upnp:albumArtURI>' % (coverres)
                ret += '</item>'
            ret += '</DIDL-Lite>'

        elif browsetype == 'Track':

            ret  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            count = 0

            albumposition = '0'
            artistposition = '0'
            albumartistposition = '0'
            album_passed = False
            artist_passed = False
            albumartist_passed = False
            album_selected = False
            artist_selected = False
            special = False

            # the passed id will either be for a track or a playlist stream entry
            # check tracks first (most likely)

            countstatement = "select count(*) from tracks where id = '%s'" % (objectID)
            c.execute(countstatement)
            totalMatches, = c.fetchone()
            if totalMatches == 1:
                btype = 'TRACK'

                log.debug(btype)

                # album and artist entry positions are passed in
                # - for virtuals/works they can be rowids too
                if objectEntry:
                    objectEntries = objectEntry.split('_')
                    albumposition = objectEntries[0]
                    artistposition = objectEntries[1]
                    albumartistposition = objectEntries[1]
                    album_passed = True
                    artist_passed = True
                    albumartist_passed = True
                if self.now_playing_album == 'selected': album_selected = True
                if self.now_playing_artist == 'selected': artist_selected = True

                # split out virtual/work details if passed
                specialalbumtype = None
                if 'v' in albumposition:
                    specialalbumtype = 'VIRTUAL'
                    ap = albumposition.split('v')
                    albumposition = ap[0]
                    specialalbumrowid = ap[1]
                if 'w' in albumposition:
                    specialalbumtype = 'WORK'
                    ap = albumposition.split('w')
                    albumposition = ap[0]
                    specialalbumrowid = ap[1]
                specialartisttype = None
                if 'v' in artistposition:
                    specialartisttype = 'VIRTUAL'
                    ap = artistposition.split('v')
                    artistposition = ap[0]
                    specialartistrowid = ap[1]
                if 'w' in artistposition:
                    specialartisttype = 'WORK'
                    ap = artistposition.split('w')
                    artistposition = ap[0]
                    specialartistrowid = ap[1]
                specialalbumartisttype = None
                if 'v' in albumartistposition:
                    specialalbumartisttype = 'VIRTUAL'
                    ap = albumartistposition.split('v')
                    albumartistposition = ap[0]
                    specialalbumartistrowid = ap[1]
                if 'w' in albumartistposition:
                    specialalbumartisttype = 'WORK'
                    ap = albumartistposition.split('w')
                    albumartistposition = ap[0]
                    specialalbumartistrowid = ap[1]

                albumposition = int(albumposition)
                artistposition = int(artistposition)
                albumartistposition = int(artistposition)

                # get special details
                if specialalbumtype or specialartisttype:
                    special = True
                    if specialalbumtype: rowid = specialalbumrowid
                    elif specialartisttype: rowid = specialartistrowid
                    elif specialalbumartisttype: rowid = specialalbumartistrowid
                    statement = "select artist, albumartist, dummyalbum from tracknumbers where rowid = '%s'" % (rowid)
                    log.debug("statement: %s", statement)
                    c.execute(statement)
                    for row in c:   # will only be one row
#                        log.debug("row: %s", row)
                        s_artist, s_albumartist, s_album = row

                # get track details
                statement = "select * from tracks where id = '%s'" % (objectID)
                log.debug("statement: %s", statement)
                c.execute(statement)

            else:
                # didn't find track, check for playlist entry
                btype = 'PLAYLIST'
                countstatement = "select count(*) from playlists where track_id = '%s'" % (objectID)
                c.execute(countstatement)
                totalMatches, = c.fetchone()
                statement = "select * from playlists where track_id = '%s'" % (objectID)
                log.debug("statement: %s", statement)
                c.execute(statement)

            for row in c:   # will only be one row
#                log.debug("row: %s", row)
                if btype == 'TRACK':
                    id, id2, duplicate, title, artistshort, artist, album, genre, tracknumber, year, albumartistshort, albumartist, composershort, composer, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned, titlesort, albumsort = row
                else:
                    playlist, pl_id, pl_plfile, pl_trackfile, pl_occurs, pl_track, pl_track_id, pl_track_rowid, pl_inserted, pl_created, pl_lastmodified, pl_plfilecreated, pl_plfilelastmodified, pl_trackfilecreated, pl_trackfilelastmodified, pl_scannumber, pl_lastscanned = row
                    log.debug(pl_trackfile)
                    mime = 'audio/wav'
                    filename = pl_trackfile
                    path = ''
                    length = 0
                    title = pl_trackfile
                    artist = ''
                    albumartist = ''
                    album = ''
                    id = pl_track_id
                    tracknumber = pl_track
                    folderart = trackart = folderartid = trackartid = None
                    titlesort = albumsort = None

                mime = fixMime(mime)
                cover, artid = self.choosecover(folderart, trackart, folderartid, trackartid)

                wsfile = filename
                wspath = os.path.join(path, filename)
                path = self.convert_path(path)
                filepath = path + filename
                filepath = encode_path(filepath)
                filepath = escape(filepath, escape_entities)
                protocol = getProtocol(mime)
                contenttype = mime
                filetype = getFileType(filename)

#                log.debug(filetype)

                '''
                transcode, newtype = checktranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)
                if transcode:
                    dummyfile = self.dbname + '.' + id + '.' + newtype
                else:
                    dummyfile = self.dbname + '.' + id + '.' + filetype
                res = self.proxyaddress + '/WMPNSSv3/' + dummyfile
                if transcode:
                    log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s\ntranscodetype: %s' % (dummyfile, wsfile, wspath, contenttype, newtype))
                    dummystaticfile = webserver.TranscodedFileSonos(dummyfile, wsfile, wspath, newtype, contenttype, cover=cover)
                    self.proxy.wmpcontroller.add_transcoded_file(dummystaticfile)
                '''

                stream, newtype = checkstream(filename, filetype)
                if stream:
                    transcode = False
                else:
                    if SMAPI != '' and source == 'SMAPI':
                        transcode, newtype = checksmapitranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)
                        if transcode:
                            mime = 'audio/mpeg'
                    else:
                        transcode, newtype = checktranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)
                if transcode:
                    dummyfile = self.dbname + '.' + id + '.' + newtype
                elif stream:
                    dummyfile = self.dbname + '.' + id + '.' + newtype
                else:
                    dummyfile = self.dbname + '.' + id + '.' + filetype
                log.debug(dummyfile)
                res = self.proxyaddress + '/WMPNSSv3/' + dummyfile
                if transcode:
                    log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s\ntranscodetype: %s' % (dummyfile, wsfile, wspath, contenttype, newtype))
                    dummystaticfile = webserver.TranscodedFileSonos(dummyfile, wsfile, wspath, newtype, contenttype, cover=cover)
                    self.proxy.wmpcontroller.add_transcoded_file(dummystaticfile)
                elif stream:
                    log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s\ntranscodetype: %s' % (dummyfile, wsfile, wsfile, contenttype, newtype))
                    dummystaticfile = webserver.TranscodedFileSonos(dummyfile, wsfile, wsfile, newtype, contenttype, cover=cover, stream=True)
                    self.proxy.wmpcontroller.add_transcoded_file(dummystaticfile)

                else:
                    log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s' % (dummyfile, wsfile, wspath, contenttype))
                    dummystaticfile = webserver.StaticFileSonos(dummyfile, wsfile, wspath, contenttype, cover=cover)
                    self.proxy.wmpcontroller.add_static_file(dummystaticfile)

                if cover != '' and not cover.startswith('EMBEDDED_'):
                    cvfile = getFile(cover)
                    cvpath = cover
                    coverfiletype = getFileType(cvfile)
                    dummycoverfile = self.dbname + '.' + str(artid) + '.' + coverfiletype
                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                    dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath)    # TODO: pass contenttype
                    self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)

                iduration = int(length)
                duration = maketime(float(length))

                if special:
                    # virtual/work details have been passed in - replace artist/album with those details
                    if specialartisttype:
                        artist = s_artist
                    if specialalbumartisttype:
                        albumartist = s_albumartist
                    if specialalbumtype:
                        album = s_album

                if artist_passed and artist_selected:
                    albumartist = self.get_entry_at_position(albumartistposition, albumartist)
                    artist = self.get_entry_at_position(artistposition, artist)
                else:
                    if albumartist == '': albumartist = '[unknown albumartist]'
                    if artist_selected:
                        albumartist = self.get_entry(albumartist, self.now_playing_artist_selected_default, self.now_playing_artist_combiner)
                    else:
                        albumartist = self.get_entry(albumartist, self.now_playing_artist, self.now_playing_artist_combiner)
                    if artist == '': artist = '[unknown artist]'
                    if artist_selected:
                        artist = self.get_entry(artist, self.now_playing_artist_selected_default, self.now_playing_artist_combiner)
                    else:
                        artist = self.get_entry(artist, self.now_playing_artist, self.now_playing_artist_combiner)
                if album_passed and album_selected:
                    album = self.get_entry_at_position(albumposition, album)
                else:
                    if album == '': album = '[unknown album]'
                    if album_selected:
                        album = self.get_entry(album, self.now_playing_album_selected_default, self.now_playing_album_combiner)
                    else:
                        album = self.get_entry(album, self.now_playing_album, self.now_playing_album_combiner)

                if title == '': title = '[unknown title]'

                title = escape(title)
                albumartist = escape(albumartist)
                artist = escape(artist)
                album = escape(album)
                tracknumber = self.convert_tracknumber(tracknumber)


                if SMAPI != '':

                    if cover == '':
                        coverres = ''
                    elif cover.startswith('EMBEDDED_'):
                        coverres = self.proxyaddress + '/WMPNSSv3/' + dummyfile

                    metadatatype = 'track'
#                    metadata = (aristId, artist, composerId, composer, \
#                                albumId, album, albumArtURI, albumArtistId, \
#                                albumArtist, genreId, genre, duration)

                    # fix WMP urls if necessary
                    res = res.replace(self.webserverurl, self.wmpurl)
                    coverres = coverres.replace(self.webserverurl, self.wmpurl)

                    metadata = ('', artist, '', '', \
                                '', album, coverres, '', \
                                albumartist, '', '', iduration)
                    items += [(id, title, mime, res, 'track', metadatatype, metadata)]


                count += 1
                ret += '<item id="%s" parentID="%s" restricted="true">' % (id, self.track_parentid)
                ret += '<dc:title>%s</dc:title>' % (title)
                ret += '<upnp:artist role="AlbumArtist">%s</upnp:artist>' % (albumartist)
                ret += '<upnp:artist role="Performer">%s</upnp:artist>' % (artist)
                ret += '<upnp:album>%s</upnp:album>' % (album)
                if tracknumber != 0:
                    ret += '<upnp:originalTrackNumber>%s</upnp:originalTrackNumber>' % (tracknumber)
                ret += '<upnp:class>%s</upnp:class>' % (self.track_class)
                ret += '<res duration="%s" protocolInfo="%s">%s</res>' % (duration, protocol, res)
#####                ret += '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">%s</desc>' % (self.wmpudn)
#                if cover != '' and not cover.startswith('EMBEDDED_'):
#                    ret += '<upnp:albumArtURI>%s</upnp:albumArtURI>' % (coverres)
                ret += '</item>'
            ret += '</DIDL-Lite>'

        elif browsetype == 'Playlist':

            ret  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            count = 0

            album_selected = False
            artist_selected = False
            if self.now_playing_album == 'selected': album_selected = True
            if self.now_playing_artist == 'selected': artist_selected = True

            if smapiservice:
                sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
            else:
                orderbylist = self.get_proxy_orderby('PLAYLIST', controllername)
            for orderbyentry in orderbylist:
                orderby, prefix, suffix, albumtype, table, header = orderbyentry
                if not orderby or orderby == '':
                    orderby = 'p.track'
                state_pre_suf = (orderby, prefix, suffix, albumtype, table, header)

            if smapiservice:
                playlistidval, browsebyid, containerstart = SMAPIkeys['playlist']
                rowid = playlistidval - containerstart
                playliststatement = """select id from playlists where rowid=%s""" % rowid
                log.debug(playliststatement)
                c.execute(playliststatement)
                plid, = c.fetchone()
            else:
                plid = objectID

            # playlists can contain stream entries that are not in tracks, so select with outer join

            countstatement = '''select count(*) from playlists p left outer join tracks t on t.rowid = p.track_rowid
                                where p.id = '%s'
                             ''' % plid
            c.execute(countstatement)
            totalMatches, = c.fetchone()

            statement = '''select t.*, p.* from playlists p left outer join tracks t on t.rowid = p.track_rowid
                           where p.id = '%s' order by %s limit %d, %d
                        ''' % (plid, orderby, startingIndex, requestedCount)
            log.debug("statement: %s", statement)
            c.execute(statement)
            for row in c:
#                log.debug("row: %s", row)
                id, id2, duplicate, title, artistlistshort, artistlist, albumlist, genre, tracknumber, year, albumartistlistshort, albumartistlist, composerlistshort, composerlist, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned, titlesort, albumsort, playlist, pl_id, pl_plfile, pl_trackfile, pl_occurs, pl_track, pl_track_id, pl_track_rowid, pl_inserted, pl_created, pl_lastmodified, pl_plfilecreated, pl_plfilelastmodified, pl_trackfilecreated, pl_trackfilelastmodified, pl_scannumber, pl_lastscanned = row

                if not id:
                    # playlist entry with no matching track - assume stream
                    mime = 'audio/wav'
                    filename = pl_trackfile
                    path = ''
                    length = 0
                    title = pl_trackfile
                    artistlist = 'Stream'
                    albumartistlist = 'Stream'
                    albumlist = 'Stream'
                    id = pl_track_id
                    titlesort = albumsort = None

                mime = fixMime(mime)
                cover, artid = self.choosecover(folderart, trackart, folderartid, trackartid)

                wsfile = filename
                wspath = os.path.join(path, filename)
                path = self.convert_path(path)
                filepath = path + filename
                filepath = encode_path(filepath)
                filepath = escape(filepath, escape_entities)
                protocol = getProtocol(mime)
                contenttype = mime
                filetype = getFileType(filename)

                stream, newtype = checkstream(filename, filetype)
                if stream:
                    transcode = False
                else:
                    if SMAPI != '' and source == 'SMAPI':
                        transcode, newtype = checksmapitranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)
                        if transcode:
                            mime = 'audio/mpeg'
                    else:
                        transcode, newtype = checktranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)
                if transcode:
                    dummyfile = self.dbname + '.' + id + '.' + newtype
                elif stream:
                    dummyfile = self.dbname + '.' + id + '.' + newtype
                else:
                    dummyfile = self.dbname + '.' + id + '.' + filetype
                log.debug(dummyfile)
                res = self.proxyaddress + '/WMPNSSv3/' + dummyfile
                if transcode:
                    log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s\ntranscodetype: %s' % (dummyfile, wsfile, wspath, contenttype, newtype))
                    dummystaticfile = webserver.TranscodedFileSonos(dummyfile, wsfile, wspath, newtype, contenttype, cover=cover)
                    self.proxy.wmpcontroller.add_transcoded_file(dummystaticfile)
                elif stream:
                    log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s\ntranscodetype: %s' % (dummyfile, wsfile, wsfile, contenttype, newtype))
                    dummystaticfile = webserver.TranscodedFileSonos(dummyfile, wsfile, wsfile, newtype, contenttype, cover=cover, stream=True)
                    self.proxy.wmpcontroller.add_transcoded_file(dummystaticfile)
                else:
                    log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s' % (dummyfile, wsfile, wspath, contenttype))
                    dummystaticfile = webserver.StaticFileSonos(dummyfile, wsfile, wspath, contenttype, cover=cover)
                    self.proxy.wmpcontroller.add_static_file(dummystaticfile)

                if cover != '' and not cover.startswith('EMBEDDED_'):
                    cvfile = getFile(cover)
                    cvpath = cover
                    coverfiletype = getFileType(cvfile)
                    dummycoverfile = self.dbname + '.' + str(artid) + '.' + coverfiletype
                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                    dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath)    # TODO: pass contenttype
                    self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)

                iduration = int(length)
                duration = maketime(float(length))

                if title == '': title = '[unknown title]'
                if albumartistlist == '': albumartist = '[unknown albumartist]'
                if artist_selected:
                    albumartist = self.get_entry(albumartistlist, self.now_playing_artist_selected_default, self.now_playing_artist_combiner)
                else:
                    albumartist = self.get_entry(albumartistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                albumartistposition = self.get_entry_position(albumartist, albumartistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                if artistlist == '': artist = '[unknown artist]'
                if artist_selected:
                    artist = self.get_entry(artistlist, self.now_playing_artist_selected_default, self.now_playing_artist_combiner)
                else:
                    artist = self.get_entry(artistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                artistposition = self.get_entry_position(artist, artistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                if albumlist == '': album = '[unknown album]'
                if album_selected:
                    album = self.get_entry(albumlist, self.now_playing_album_selected_default, self.now_playing_album_combiner)
                else:
                    album = self.get_entry(albumlist, self.now_playing_album, self.now_playing_album_combiner)
                albumposition = self.get_entry_position(album, albumlist, self.now_playing_album, self.now_playing_album_combiner)

                orderby, prefix, suffix, albumtype, table, header = state_pre_suf
                p_prefix = self.proxy_makepresuffix(prefix, self.replace_pre, \
                           {'year':year, 'lastplayed':lastplayed, 'playcount':playcount, 'created':created, \
                            'lastmodified':lastmodified, 'inserted':inserted, 'artist':artist, 'albumartist':albumartist, \
                            'composer':composerlist, 'album':album, 'genre':genre, 'tracknumber':tracknumber, 'length':length, \
                            'path':path, 'filename':filename, 'playlist':playlist, \
                           })
                if p_prefix: title = '%s%s' % (p_prefix, title)
                p_suffix = self.proxy_makepresuffix(suffix, self.replace_suf,
                           {'year':year, 'lastplayed':lastplayed, 'playcount':playcount, 'created':created,
                            'lastmodified':lastmodified, 'inserted':inserted, 'artist':artist, 'albumartist':albumartist,
                            'composer':composerlist, 'album':album, 'genre':genre, 'tracknumber':tracknumber, 'length':length,
                            'path':path, 'filename':filename, 'playlist':playlist, \
                           })
                if p_suffix: title = '%s%s' % (title, p_suffix)

                title = escape(title)
                albumartist = escape(albumartist)
                artist = escape(artist)
                album = escape(album)
#                tracknumber = self.convert_tracknumber(tracknumber)

                if SMAPI != '':

                    if cover == '':
                        coverres = ''
                    elif cover.startswith('EMBEDDED_'):
                        coverres = self.proxyaddress + '/WMPNSSv3/' + dummyfile

                    metadatatype = 'track'
#                    metadata = (aristId, artist, composerId, composer, \
#                                albumId, album, albumArtURI, albumArtistId, \
#                                albumArtist, genreId, genre, duration)

                    # fix WMP urls if necessary
                    res = res.replace(self.webserverurl, self.wmpurl)
                    coverres = coverres.replace(self.webserverurl, self.wmpurl)

                    metadata = ('', artist, '', '', \
                                '', album, coverres, '', \
                                albumartist, '', '', iduration)
                    items += [(id, title, mime, res, 'track', metadatatype, metadata)]


                full_id = 'T__%s_%s_%s__%s' % (albumposition, artistposition, albumartistposition, id)

                count += 1
                ret += '<item id="%s" parentID="%s" restricted="true">' % (full_id, self.track_parentid)
                ret += '<dc:title>%s</dc:title>' % (title)
                ret += '<upnp:artist role="AlbumArtist">%s</upnp:artist>' % (albumartist)
                ret += '<upnp:artist role="Performer">%s</upnp:artist>' % (artist)
                ret += '<upnp:album>%s</upnp:album>' % (album)
                if tracknumber != 0:
                    ret += '<upnp:originalTrackNumber>%s</upnp:originalTrackNumber>' % (pl_track)
                ret += '<upnp:class>%s</upnp:class>' % (self.track_class)
                ret += '<res duration="%s" protocolInfo="%s">%s</res>' % (duration, protocol, res)
#####                ret += '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">%s</desc>' % (self.wmpudn)
#                if cover != '' and not cover.startswith('EMBEDDED_'):
#                    ret += '<upnp:albumArtURI>%s</upnp:albumArtURI>' % (coverres)
                ret += '</item>'
            ret += '</DIDL-Lite>'

        else:

            ret  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            ret += '</DIDL-Lite>'
            count = 0
            totalMatches = 0

        c.close()
        if not self.proxy.db_persist_connection:
            db.close()

        log.debug("BROWSE ret: %s", ret)

        if source == 'SMAPI':
            return items, totalMatches, startingIndex, 'item'

        return ret, count, totalMatches



###########################################################################################################################
###########################################################################################################################
###########################################################################################################################



    def search(self, *args, **kwargs):

        log.debug("Mediaserver.search: %s", kwargs)

        # TODO: fix error conditions (return zero)

        source = kwargs.get('Source', None)
        controllername = kwargs.get('Controller', '')
        controlleraddress = kwargs.get('Address', '')
        log.debug('Controller: %s' % controllername)
        log.debug('Address: %s' % controlleraddress)

        log.debug("start: %.3f" % time.time())

        containerID = kwargs['ContainerID']
        searchCriteria = kwargs.get('SearchCriteria', '')

        searchCriteria = self.fixcriteria(searchCriteria)

        log.debug('containerID: %s' % str(containerID))
        log.debug('searchCriteria: %s' % searchCriteria.encode(enc, 'replace'))

        SMAPI = kwargs.get('SMAPI', '')
        log.debug('SMAPI: %s' % SMAPI)
        items = []

        SMAPIhierarchy = SMAPI.split(':')
        log.debug(SMAPIhierarchy)
        SMAPIkeys = kwargs.get('SMAPIkeys', '')
        # SMAPIkeys[browsetype] = (idval, browsebyid, containerstart)
        log.debug(SMAPIkeys)

        smapiservice = kwargs.get('smapiservice', False)

        smapialphastatement = """
                                 select count(lower(substr(alpha,1,1))) as count,
                                        lower(substr(alpha,1,1)) as character

                                 from (select %s as alpha from %s)
                                 group by character
                                 order by character
                              """

        browse = kwargs.get('browse', '')
        log.debug('BROWSE: %s' % browse)

        # check if search requested
        searchcontainer = None
        if searchCriteria.startswith('SEARCH::'):
            searchtype = searchCriteria[8:].split('::')[0]
            searchstring = searchCriteria[10+len(searchtype):]
            searchcontainer = searchtype
            if searchcontainer == 'Contributing Artist': searchcontainer = 'Artist'

        if self.proxy.db_persist_connection:
            db = self.proxy.db
        else:
            db = sqlite3.connect(self.dbspec)
#        log.debug(db)

#        cs = db.execute("PRAGMA cache_size;")
#        log.debug('cache_size now: %s', cs.fetchone()[0])

        c = db.cursor()

        startingIndex = int(kwargs['StartingIndex'])
        requestedCount = int(kwargs['RequestedCount'])


        if ((containerID == '107' or containerID == '100') and searchCriteria.startswith('upnp:class = "object.container.person.musicArtist" and @refID exists false')) or \
           searchcontainer == 'Artist' or \
           SMAPI == 'Alphaartist' or \
           SMAPI == 'artist' or \
           SMAPI == 'Alphacontributingartist' or \
           SMAPI == 'contributingartist' or \
           SMAPI == 'genre:artist' or \
           browse == 'Artists' or \
           browse == 'ContributingArtists' or \
           browse == 'GenreArtists':

            # Artist/Contributing Artist containers

            genres = []
            state_pre_suf = []

            if searchCriteria == 'upnp:class = "object.container.person.musicArtist" and @refID exists false' or \
               searchcontainer == 'Artist' or \
               SMAPI == 'Alphaartist' or \
               SMAPI == 'artist' or \
               SMAPI == 'Alphacontributingartist' or \
               SMAPI == 'contributingartist' or \
               browse == 'Artists' or \
               browse == 'ContributingArtists':

                # Artists
                log.debug('artists')
                genres.append('dummy')
                searchtype = 'ARTIST'
                searchwhere = ''
                if containerID == '107' or SMAPI == 'artist' or SMAPI == 'Alphaartist' or browse == 'Artists':
                    if self.use_albumartist:
                        artisttype = 'albumartist'
                        if searchcontainer:
                            searchstring = escape_sql(searchstring)
                            searchwhere = "where albumartist like '%s%%'" % searchstring

                        if searchwhere == '':
                            albumwhere = 'where %s' % self.albumartist_album_albumtype_where
                        else:
                            albumwhere = ' and %s' % self.albumartist_album_albumtype_where

                        countstatement = "select count(distinct albumartist) from AlbumartistAlbum %s%s" % (searchwhere, albumwhere)
                        statement = "select rowid, albumartist, lastplayed, playcount from AlbumartistAlbum %s%s group by albumartist order by orderby limit ?, ?" % (searchwhere, albumwhere)

                        #select distinct (%s) as alpha from %s
                        alphastatement = smapialphastatement % ('albumartist', 'AlbumartistAlbum %s group by albumartist order by %%s' % albumwhere)

                        if smapiservice:
                            sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                            orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
                        else:
                            orderbylist = self.get_proxy_orderby('ALBUMARTIST', controllername)
                        for orderbyentry in orderbylist:
                            orderby, prefix, suffix, albumtype, table, header = orderbyentry
                            if not orderby or orderby == '':
                                orderby = 'albumartist'
                            state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                        id_pre = 'ALBUMARTIST__'
                    else:
                        artisttype = 'artist'
                        if searchcontainer:
                            searchstring = escape_sql(searchstring)
                            searchwhere = "where artist like '%s%%'" % searchstring

                        if searchwhere == '':
                            albumwhere = 'where %s' % self.artist_album_albumtype_where
                        else:
                            albumwhere = ' and %s' % self.artist_album_albumtype_where

                        countstatement = "select count(distinct artist) from ArtistAlbum %s%s" % (searchwhere, albumwhere)
                        statement = "select rowid, artist, lastplayed, playcount from ArtistAlbum %s%s group by artist order by orderby limit ?, ?" % (searchwhere, albumwhere)

                        alphastatement = smapialphastatement % ('artist', 'ArtistAlbum %s group by artist order by %%s' % albumwhere)

                        if smapiservice:
                            sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                            orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
                        else:
                            orderbylist = self.get_proxy_orderby('ARTIST', controllername)
                        for orderbyentry in orderbylist:
                            orderby, prefix, suffix, albumtype, table, header = orderbyentry
                            if not orderby or orderby == '':
                                orderby = 'artist'
                            state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                        id_pre = 'ARTIST__'
                else:
                    artisttype = 'contributingartist'
                    if searchcontainer:
                        searchstring = escape_sql(searchstring)
                        searchwhere = "where artist like '%s%%'" % searchstring

                    if searchwhere == '':
                        albumwhere = 'where %s' % self.contributingartist_album_albumtype_where
                    else:
                        albumwhere = ' and %s' % self.contributingartist_album_albumtype_where

                    countstatement = "select count(distinct artist) from ArtistAlbum %s%s" % (searchwhere, albumwhere)
                    statement = "select rowid, artist, lastplayed, playcount from ArtistAlbum %s%s group by artist order by orderby limit ?, ?" % (searchwhere, albumwhere)

                    alphastatement = smapialphastatement % ('artist', 'ArtistAlbum %s group by artist order by %%s' % albumwhere)

                    if smapiservice:
                        sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                        orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
                    else:
                        orderbylist = self.get_proxy_orderby('CONTRIBUTINGARTIST', controllername)
                    for orderbyentry in orderbylist:
                        orderby, prefix, suffix, albumtype, table, header = orderbyentry
                        if not orderby or orderby == '':
                            orderby = 'artist'
                        state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                    id_pre = 'CONTRIBUTINGARTIST__'
            else:

                criteria = searchCriteria.split('=')

                if SMAPI == 'genre:artist' or \
                   browse == 'GenreArtists' or \
                   criteria[1].endswith('upnp:genre '):

                    # Artists for genre
                    log.debug('artists for genre')
                    searchtype = 'GENRE_ARTIST'

                    if SMAPI == 'genre:artist':
                        genreidval, browsebyid, containerstart = SMAPIkeys['genre']
                        rowid = genreidval
                        genrestatement = """select genre from genre where rowid=%s""" % rowid
                        log.debug(genrestatement)
                        c.execute(genrestatement)
                        genre, = c.fetchone()
                        genre = '"%s"' % genre    # code expects this
                    elif browse == 'GenreArtists':
                        rowid = int(containerID)
                        genrestatement = """select genre from genre where rowid=%s""" % rowid
                        log.debug(genrestatement)
                        c.execute(genrestatement)
                        genre, = c.fetchone()
                        genre = '"%s"' % genre    # code expects this
                    else:
                        genre = criteria[2][1:]

                    genre_options = self.removepresuf(genre, 'GENRE', controllername)
                    for genre in genre_options:
                        if genre == '[unknown genre]': genre = ''
                        log.debug('    genre: %s', genre)
                        genres.append(genre)
                        if self.use_albumartist:
                            artisttype = 'albumartist'
                            albumwhere = 'and %s' % self.albumartist_album_albumtype_where
                            countstatement = "select count(distinct albumartist) from GenreAlbumartistAlbum where genre=? %s" % albumwhere
                            statement = "select rowid, albumartist, lastplayed, playcount from GenreAlbumartistAlbum where genre=? %s group by albumartist order by orderby limit ?, ?" % albumwhere
                            if smapiservice:
                                sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                                orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
                            else:
                                orderbylist = self.get_proxy_orderby('GENRE_ALBUMARTIST', controllername)
                            for orderbyentry in orderbylist:
                                orderby, prefix, suffix, albumtype, table, header = orderbyentry
                                if not orderby or orderby == '':
                                    orderby = 'albumartist'
                                state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                            id_pre = 'GENRE_ALBUMARTIST__'
                        else:
                            artisttype = 'artist'
                            albumwhere = 'and %s' % self.artist_album_albumtype_where
                            countstatement = "select count(distinct artist) from GenreArtistAlbum where genre=? %s" % albumwhere
                            statement = "select rowid, artist, lastplayed, playcount from GenreArtistAlbum where genre=? %s group by artist order by orderby limit ?, ?" % albumwhere
                            if smapiservice:
                                sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                                orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
                            else:
                                orderbylist = self.get_proxy_orderby('GENRE_ARTIST', controllername)
                            for orderbyentry in orderbylist:
                                orderby, prefix, suffix, albumtype, table, header = orderbyentry
                                if not orderby or orderby == '':
                                    orderby = 'artist'
                                state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                            id_pre = 'GENRE_ARTIST__'
                else:
                    print "proxy_search - unknown search criteria, not supported in code"

            res  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            count = 0
            parentid = containerID

            log.debug("count statement: %s", countstatement)
            log.debug("statement: %s", statement)

            # process each fields option across all chunks until we find a match
            matches = {}
            totalMatches = 0
            found_genre = None
            for genre in genres:
                log.debug(state_pre_suf)
                for orderby, prefix, suffix, albumtype, table, header in state_pre_suf:
                    log.debug(table)
                    if not table in matches:
                        if searchtype == 'ARTIST':
                            c.execute(countstatement)
                        elif searchtype == 'GENRE_ARTIST':
                            c.execute(countstatement, (genre, ))
                        tableMatches, = c.fetchone()
                        tableMatches = int(tableMatches)
                        matches[table] = tableMatches
                        totalMatches += tableMatches
                if totalMatches != 0:
                    # have found the entry we want
                    found_genre = genre
                    break

            if totalMatches != 0:

                chunks = len(state_pre_suf)
                if (self.show_chunk_separator and chunks > 1) or (self.show_chunk_separator_single and chunks == 1):
                    show_separator = True
                else:
                    show_separator = False

                count_chunk = []
                chunk_data = []
                for sps in state_pre_suf:
                    orderby, prefix, suffix, albumtype, table, header = sps
                    if matches[table] > 0 or self.show_chunk_header_empty:
                        count_chunk.append((matches[table], 1))
                        chunk_data.append(sps)
                chunkdata, totalMatches = self.chunker(startingIndex, requestedCount, count_chunk, show_separator)

                if SMAPI == 'Alphaartist' or SMAPI == 'Alphacontributingartist':
                    if not show_separator and chunks == 1:

                        orderby, prefix, suffix, albumtype, table, header = state_pre_suf[0]
                        if ',' in orderby: orderby = orderby.split(',')[0]
                        alphastatement = alphastatement % (orderby)
                        log.debug(alphastatement)
                        c.execute(alphastatement)
                        return c.fetchall()
                    else:
                        return None

                for chunk in chunkdata:

                    group, start, end, sep = chunk
                    length = end - start

                    orderby, prefix, suffix, albumtype, table, header = chunk_data[group]

                    if show_separator and sep:
                        count += 1
                        if not header or header == '':
                            header = "%s %s" % ('ordered by', orderby)
                        separator = '%s %s %s' % (self.chunk_separator_prefix, header, self.chunk_separator_suffix)
                        res += '<container id="%s" parentID="%s" restricted="true">' % (id_pre, self.artist_parentid)
                        res += '<dc:title>%s</dc:title>' % (separator)
                        res += '<upnp:class>%s</upnp:class>' % (self.artist_class)
                        res += '</container>'

                    orderstatement = statement.replace('order by orderby', 'order by ' + orderby)
                    log.debug(orderstatement)

                    if searchtype == 'ARTIST':
                        c.execute(orderstatement, (start, length))
                    elif searchtype == 'GENRE_ARTIST':
                        c.execute(orderstatement, (found_genre, start, length))

                    for row in c:
#                        log.debug("row: %s", row)

                        rowid, artist, lastplayed, playcount = row
                        playcount = str(playcount)
                        if artist == '': artist = '[unknown %s]' % artisttype
                        artist = escape(artist)

                        a_prefix = self.proxy_makepresuffix(prefix, self.replace_pre, {'lastplayed':lastplayed, 'playcount':playcount})
                        if a_prefix: artist = '%s%s' % (a_prefix, artist)
                        a_suffix = self.proxy_makepresuffix(suffix, self.replace_suf, {'lastplayed':lastplayed, 'playcount':playcount})
                        if a_suffix: artist = '%s%s' % (artist, a_suffix)

                        count += 1

                        if SMAPI != '':
                            if SMAPI == 'genre:artist':
                                artistidval, browsebyid, containerstart = SMAPIkeys['artist']
                                itemid = "%s:%s" % (genreidval, rowid + containerstart)
                            elif SMAPI == 'artist':
                                artistidval, browsebyid, containerstart = SMAPIkeys['artist']
                                itemid = rowid + containerstart
                            elif SMAPI == 'contributingartist':
                                artistidval, browsebyid, containerstart = SMAPIkeys['contributingartist']
                                itemid = rowid + containerstart
                            items += [(itemid, artist)]
                            id = id_pre + str(itemid)
                        else:
#                           id = id_pre + str(startingIndex + count + self.artist_parentid)  # dummy, sequential
                            id = id_pre + str(rowid + self.artist_parentid)

                        if browse == 'Artists':
                            id = id_pre + str(rowid + self.artist_parentid)
                        elif browse == 'ContributingArtists':
                            id = id_pre + str(rowid + self.contributingartist_parentid)
                        elif browse == 'GenreArtists':
                            id = id_pre + str(rowid + self.genre_artist_parentid)

                        if browse == '':
                            res += '<container id="%s" parentID="%s" restricted="true">' % (id, self.artist_parentid)
                        else:
                            res += '<container id="%s" parentID="%s" restricted="true">' % (id, containerID)
                        res += '<dc:title>%s</dc:title>' % (artist)
                        res += '<upnp:class>%s</upnp:class>' % (self.artist_class)
                        res += '</container>'

            res += '</DIDL-Lite>'

        elif (containerID == '0' and searchCriteria.startswith('upnp:class = "object.container.album.musicAlbum" and @refID exists false')) or \
             searchcontainer == 'Album' or \
             SMAPI == 'Alphaalbum' or \
             SMAPI == 'album' or \
             SMAPI == 'composer:album' or \
             SMAPI == 'artist:album' or \
             SMAPI == 'contributingartist:album' or \
             SMAPI == 'genre:artist:album' or \
             browse == 'Albums' or \
             browse == 'ArtistAlbums' or \
             browse == 'ComposerAlbums' or \
             browse == 'ContributingArtistAlbums' or \
             browse == 'GenreArtistAlbums':

            # Albums class

            genres = []
            fields = []
            state_pre_suf = []
            artisttype = None

            if searchCriteria == 'upnp:class = "object.container.album.musicAlbum" and @refID exists false' or \
               searchcontainer == 'Album' or \
               SMAPI == 'Alphaalbum' or \
               SMAPI == 'album' or \
               browse == 'Albums':

                # Albums

                log.debug('albums')
                searchtype = 'ALBUM'
                artisttype = 'ENTRY'

                albumwhere = self.album_where_duplicate
                if searchcontainer:
                    searchstring = escape_sql(searchstring)
                    if albumwhere == '':
                        albumwhere = "where album like '%s%%'" % searchstring
                    else:
                        albumwhere += " and album like '%s%%'" % searchstring

                genres.append('dummy')     # dummy for albums
                fields.append('dummy')     # dummy for albums

                if self.use_albumartist:
                    album_distinct = self.distinct_albumartist
                    album_groupby = self.groupby_albumartist
                else:
                    album_distinct = self.distinct_artist

                    album_groupby = self.groupby_artist

                # get the sort sequence for this database and query
                if smapiservice:
                    sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                    orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
                else:
                    orderbylist = self.get_proxy_orderby('ALBUM', controllername)

                log.debug(orderbylist)

                # FIXME: this code will use the albumtype from the last entry in the orderbylist

                for orderbyentry in orderbylist:
                    orderby, prefix, suffix, albumtype, table, header = orderbyentry
                    if not orderby or orderby == '':
                        if self.use_albumartist:
                            orderby = self.album_groupby_albumartist
                        else:
                            orderby = self.album_groupby_artist
                    at = self.get_albumtype_where(albumtype, table='aa')
                    if albumwhere == '':
                        albumwhere = 'where %s' % at
                    else:
                        albumwhere += ' and %s' % at

                    if self.use_albumartist:
                        if 'albumartist' in self.album_group:
                            countstatement = "select count(distinct %s) from AlbumartistAlbum aa %s" % (album_distinct, albumwhere)
                        else:
                            separate_albums = ''
                            if self.show_separate_albums: separate_albums = '||albumartist'
                            countstatement = "select count(distinct %s%s) from AlbumartistAlbumsonly aa %s" % (album_distinct, separate_albums, albumwhere)
                    else:
                        if 'artist' in self.album_group:
                            countstatement = "select count(distinct %s) from ArtistAlbum aa %s" % (album_distinct, albumwhere)
                        else:
                            separate_albums = ''
                            if self.show_separate_albums: separate_albums = '||artist'
                            countstatement = "select count(distinct %s%s) from ArtistAlbumsonly aa %s" % (album_distinct, separate_albums, albumwhere)

#                    if controllername == 'PCDCR':
#                        statement = """
#                                       select a.* from
#                                       ( select album, min(tracknumbers) as mintrack, albumtype, duplicate from albums %s group by %s ) as m
#                                       inner join albums as a on a.album = m.album and a.tracknumbers = m.mintrack and a.albumtype = m.albumtype and a.duplicate = m.duplicate
#                                       order by orderby limit ?, ?
#                                    """ % (albumwhere, album_groupby)
#                    else:

                    if self.use_albumartist:
                        if 'albumartist' in self.album_group:
                            statement = """
                                           select album_id, album, '', albumartist, '', a.*, 0 from AlbumartistAlbum aa join albums a on
                                           aa.album_id = a.id
                                           %s group by %s
                                           order by orderby limit ?, ?
                                        """ % (albumwhere, album_groupby)

                            #select %s as alpha from %s
                            alphastatement = smapialphastatement % ('album', 'AlbumartistAlbum aa %s group by %s order by %%s' % (albumwhere, album_groupby))

                        else:
                            artisttype = 'LIST'
                            separate_albums = ''
                            if self.show_separate_albums: separate_albums = ',albumartist'
                            statement = """
                                           select album_id, aa.album, '', aa.albumartist, '', a.* from AlbumartistAlbumsonly aa join albumsonly a on
                                           aa.album_id = a.id
                                           %s group by %s%s
                                           order by orderby limit ?, ?
                                        """ % (albumwhere, album_groupby, separate_albums)

                            alphastatement = smapialphastatement % ('album', 'AlbumartistAlbumsonly aa %s group by %s%s order by %%s' % (albumwhere, album_groupby, separate_albums))

                    else:
                        if 'artist' in self.album_group:
                            statement = """
                                           select album_id, album, artist, '', '', a.*, 0 from ArtistAlbum aa join albums a on
                                           aa.album_id = a.id
                                           %s group by %s
                                           order by orderby limit ?, ?
                                        """ % (albumwhere, album_groupby)

                            alphastatement = smapialphastatement % ('album', 'ArtistAlbum aa %s group by %s order by %%s' % (albumwhere, album_groupby))

                        else:
                            artisttype = 'LIST'
                            separate_albums = ''
                            if self.show_separate_albums: separate_albums = ',artist'
                            statement = """
                                           select album_id, aa.album, aa.artist, '', '', a.* from ArtistAlbumsonly aa join albumsonly a on

                                           aa.album_id = a.id
                                           %s group by %s%s
                                           order by orderby limit ?, ?
                                        """ % (albumwhere, album_groupby, separate_albums)


                            alphastatement = smapialphastatement % ('album', 'ArtistAlbumsonly aa %s group by %s%s order by %%s' % (albumwhere, album_groupby, separate_albums))

                    state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))

                id_pre = 'ALBUM__'

            else:

                criteria = searchCriteria.split('=')
                numcrit = len(criteria)
                if numcrit == 3 or \
                   SMAPI == 'composer:album' or \
                   SMAPI == 'artist:album' or \
                   SMAPI == 'contributingartist:album' or \
                   browse == 'ArtistAlbums' or \
                   browse == 'ComposerAlbums' or \
                   browse == 'ContributingArtistAlbums':

                    #TEMP
                    if numcrit < 3: criteria = ['d','d','d']

                    # searchCriteria: upnp:class = "object.container.album.musicAlbum" and @refID exists false and microsoft:authorComposer = "7 Aurelius"
                    searchtype = 'FIELD_ALBUM'
                    genres.append('dummy')     # dummy for composer/artist/contributingartist
                    if criteria[1].endswith('microsoft:authorComposer ') or \
                       SMAPI == 'composer:album' or \
                       browse == 'ComposerAlbums':

                        # Albums for Composer

                        log.debug('albums for composer')

                        if SMAPI == 'composer:album':
                            composeridval, browsebyid, containerstart = SMAPIkeys['composer']
                            rowid = composeridval - containerstart
                            composerstatement = """select composer from ComposerAlbum where rowid=%s""" % rowid
                            log.debug(composerstatement)
                            c.execute(composerstatement)
                            composer, = c.fetchone()
                            composer = '"%s"' % composer    # code expects this
                        elif browse == 'ComposerAlbums':
                            rowid = int(containerID) - self.composer_parentid
                            composerstatement = """select composer from ComposerAlbum where rowid=%s""" % rowid
                            log.debug(composerstatement)
                            c.execute(composerstatement)
                            composer, = c.fetchone()
                            composer = '"%s"' % composer    # code expects this
                        else:
                            composer = criteria[2][1:]

                        countstatement = "select count(distinct %s) from ComposerAlbum aa where composer=? and albumtypewhere %s" % (self.distinct_composer, self.album_and_duplicate)

#                        statement = "select * from albums where id in (select album_id from ComposerAlbum where composer=? and albumtypewhere %s) group by %s order by orderby limit ?, ?" % (self.album_and_duplicate, self.groupby_composer)
                        statement = """
                                       select album_id, album, '', '', composer, a.*, 0 from ComposerAlbum aa join albums a on
                                       aa.album_id = a.id
                                       where composer=? and albumtypewhere %s
                                       group by %s
                                       order by orderby limit ?, ?
                                    """ % (self.album_and_duplicate, self.groupby_composer)

                        composer_options = self.removepresuf(composer, 'COMPOSER', controllername)
                        for composer in composer_options:
                            if composer == '[unknown composer]': composer = ''
                            log.debug('    composer: %s', composer)
                            fields.append(composer)
                            if smapiservice:
                                sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                                orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
                            else:
                                orderbylist = self.get_proxy_orderby('COMPOSER_ALBUM', controllername)
                            for orderbyentry in orderbylist:
                                orderby, prefix, suffix, albumtype, table, header = orderbyentry
                                if not orderby or orderby == '':
                                    orderby = 'album'
                                state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                            id_pre = 'COMPOSER_ALBUM__'

                    elif criteria[1].endswith('microsoft:artistAlbumArtist ') or \
                         SMAPI == 'artist:album' or \
                         browse == 'ArtistAlbums':

                        # Albums for albumartist

                        log.debug('albums for artist (microsoft:artistAlbumArtist)')

                        if SMAPI == 'artist:album':
                            artistidval, browsebyid, containerstart = SMAPIkeys['artist']
                            rowid = artistidval - containerstart
                            if self.use_albumartist:
                                artiststatement = """select albumartist from AlbumartistAlbum where rowid=%s""" % rowid
                            else:
                                artiststatement = """select albumartist from ArtistAlbum where rowid=%s""" % rowid
                            log.debug(artiststatement)
                            c.execute(artiststatement)
                            artist, = c.fetchone()
                            artist = '"%s"' % artist    # code expects this
                        elif browse == 'ArtistAlbums':
                            rowid = int(containerID) - self.artist_parentid
                            if self.use_albumartist:
                                artiststatement = """select albumartist from AlbumartistAlbum where rowid=%s""" % rowid
                            else:
                                artiststatement = """select albumartist from ArtistAlbum where rowid=%s""" % rowid
                            log.debug(artiststatement)
                            c.execute(artiststatement)
                            artist, = c.fetchone()
                            artist = '"%s"' % artist    # code expects this
                        else:
                            artist = criteria[2][1:]

                        if self.use_albumartist:
#                            countstatement = "select count(distinct %s) from AlbumartistAlbum where albumartist=? and albumtypewhere %s" % (self.distinct_albumartist, self.album_and_duplicate)
#                            statement = "select * from albums where id in (select album_id from AlbumartistAlbum where albumartist=? and albumtypewhere %s) group by %s order by orderby limit ?, ?" % (self.album_and_duplicate, self.groupby_albumartist)

                            countstatement = "select count(distinct %s) from AlbumartistAlbum aa where albumartist=? and albumtypewhere %s" % (self.distinct_albumartist, self.album_and_duplicate)
                            statement = """
                                           select album_id, album, '', albumartist, '', a.*, 0 from AlbumartistAlbum aa join albums a on
                                           aa.album_id = a.id
                                           where albumartist=? and albumtypewhere %s
                                           group by %s
                                           order by orderby limit ?, ?
                                        """ % (self.album_and_duplicate, self.groupby_albumartist)

                            artist_options = self.removepresuf(artist, 'ALBUMARTIST', controllername)
                        else:
#                            countstatement = "select count(distinct %s) from ArtistAlbum where artist=? and albumtypewhere %s" % (self.distinct_artist, self.album_and_duplicate)
#                            statement = "select * from albums where id in (select album_id from ArtistAlbum where artist=? and albumtypewhere %s) group by %s order by orderby limit ?, ?" % (self.album_and_duplicate, self.groupby_artist)

                            countstatement = "select count(distinct %s) from ArtistAlbum aa where artist=? and albumtypewhere %s" % (self.distinct_artist, self.album_and_duplicate)
                            statement = """
                                           select album_id, album, artist, '', '', a.*, 0 from ArtistAlbum aa join albums a on
                                           aa.album_id = a.id

                                           where artist=? and albumtypewhere %s
                                           group by %s
                                           order by orderby limit ?, ?
                                        """ % (self.album_and_duplicate, self.groupby_artist)

                            artist_options = self.removepresuf(artist, 'ARTIST', controllername)
                        for artist in artist_options:
                            if artist == '[unknown artist]': artist = ''
                            log.debug('    artist: %s', artist)
                            fields.append(artist)
                            if self.use_albumartist:
                                if smapiservice:
                                    sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                                    orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
                                else:
                                    orderbylist = self.get_proxy_orderby('ALBUMARTIST_ALBUM', controllername)
                                for orderbyentry in orderbylist:
                                    orderby, prefix, suffix, albumtype, table, header = orderbyentry
                                    if not orderby or orderby == '':
                                        orderby = 'album'
                                    state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                                id_pre = 'ALBUMARTIST_ALBUM__'
                            else:
                                if smapiservice:
                                    sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                                    orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
                                else:
                                    orderbylist = self.get_proxy_orderby('ARTIST_ALBUM', controllername)
                                for orderbyentry in orderbylist:
                                    orderby, prefix, suffix, albumtype, table, header = orderbyentry
                                    if not orderby or orderby == '':
                                        orderby = 'album'
                                    state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                                id_pre = 'ARTIST_ALBUM__'


                    elif criteria[1].endswith('microsoft:artistPerformer ') or \
                         SMAPI == 'contributingartist:album' or \
                         browse == 'ContributingArtistAlbums':
                         
                        # searchCriteria: upnp:class = "object.container.album.musicAlbum" and @refID exists false and microsoft:artistPerformer = "1 Giant Leap"

                        # Albums for contributing artist

                        log.debug('albums for artist (microsoft:artistPerformer)')

                        if SMAPI == 'contributingartist:album':
                            contributingartistidval, browsebyid, containerstart = SMAPIkeys['contributingartist']
                            rowid = contributingartistidval - containerstart
                            contributingartiststatement = """select artist from ArtistAlbum where rowid=%s""" % rowid
                            log.debug(contributingartiststatement)
                            c.execute(contributingartiststatement)
                            artist, = c.fetchone()
                            artist = '"%s"' % artist    # code expects this
                        elif browse == 'ContributingArtistAlbums':
                            rowid = int(containerID) - self.contributingartist_parentid
                            contributingartiststatement = """select artist from ArtistAlbum where rowid=%s""" % rowid
                            log.debug(contributingartiststatement)
                            c.execute(contributingartiststatement)
                            artist, = c.fetchone()
                            artist = '"%s"' % artist    # code expects this
                        else:
                            artist = criteria[2][1:]

#                        countstatement = "select count(distinct %s) from ArtistAlbum where artist=? and albumtypewhere %s" % (self.distinct_artist, self.album_and_duplicate)
#                        statement = "select * from albums where id in (select album_id from ArtistAlbum where artist=? and albumtypewhere %s) group by %s order by orderby limit ?, ?" % (self.album_and_duplicate, self.groupby_artist)

                        countstatement = "select count(distinct %s) from ArtistAlbum aa where artist=? and albumtypewhere %s" % (self.distinct_artist, self.album_and_duplicate)
                        statement = """
                                       select album_id, album, artist, '', '', a.*, 0 from ArtistAlbum aa join albums a on
                                       aa.album_id = a.id
                                       where artist=? and albumtypewhere %s
                                       group by %s
                                       order by orderby limit ?, ?
                                    """ % (self.album_and_duplicate, self.groupby_artist)

                        artist_options = self.removepresuf(artist, 'CONTRIBUTINGARTIST', controllername)
                        for artist in artist_options:
                            if artist == '[unknown artist]': artist = ''
                            log.debug('    artist: %s', artist)
                            fields.append(artist)
                            if smapiservice:
                                sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                                orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
                            else:
                                orderbylist = self.get_proxy_orderby('CONTRIBUTINGARTIST_ALBUM', controllername)
                            for orderbyentry in orderbylist:
                                orderby, prefix, suffix, albumtype, table, header = orderbyentry
                                if not orderby or orderby == '':
                                    orderby = 'album'
                                state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                            id_pre = 'CONTRIBUTINGARTIST_ALBUM__'
                    else:
                        print "proxy_search - unknown search criteria, not supported in code"
                else:
                    # numcrit = 4
                    if SMAPI == 'genre:artist:album' or \
                        browse == 'GenreArtistAlbums' or \
                        (criteria[1].endswith('upnp:genre ') and criteria[2].endswith('microsoft:artistAlbumArtist ')):

                        searchtype = 'GENRE_FIELD_ALBUM'
                        # Albums for genre and artist
                        log.debug('albums for genre and artist')

                        if SMAPI == 'genre:artist:album':
                            genreidval, browsebyid, containerstart = SMAPIkeys['genre']
                            rowid = genreidval
                            genrestatement = """select genre from genre where rowid=%s""" % rowid
                            log.debug(genrestatement)
                            c.execute(genrestatement)
                            genre, = c.fetchone()
                            genre = '"%s"' % genre    # code expects this
                        elif browse == 'GenreArtistAlbums':
                            rowid = int(containerID) - self.genre_artist_parentid
                            if self.use_albumartist:
                                genrestatement = """select genre from GenreAlbumartistAlbum where rowid=%s""" % rowid
                            else:
                                genrestatement = """select genre from GenreArtistAlbum where rowid=%s""" % rowid
                            log.debug(genrestatement)
                            c.execute(genrestatement)
                            genre, = c.fetchone()
                            genre = '"%s"' % genre    # code expects this
                        else:
                            genre = criteria[2][1:-33]

                        if self.use_albumartist:
#                            countstatement = "select count(distinct %s) from GenreAlbumartistAlbum where genre=? and albumartist=? and albumtypewhere %s" % (self.distinct_albumartist, self.album_and_duplicate)
#                            statement = "select * from albums where id in (select album_id from GenreAlbumartistAlbum where genre=? and albumartist=? and albumtypewhere %s) group by %s order by orderby limit ?, ?" % (self.album_and_duplicate, self.groupby_albumartist)

                            countstatement = "select count(distinct %s) from GenreAlbumartistAlbum aa where genre=? and albumartist=? and albumtypewhere %s" % (self.distinct_albumartist, self.album_and_duplicate)
                            statement = """
                                           select album_id, album, '', albumartist, '', a.*, 0 from GenreAlbumartistAlbum aa join albums a on
                                           aa.album_id = a.id
                                           where genre=? and albumartist=? and albumtypewhere %s
                                           group by %s
                                           order by orderby limit ?, ?
                                        """ % (self.album_and_duplicate, self.groupby_albumartist)

                        else:
#                            countstatement = "select count(distinct %s) from GenreArtistAlbum where genre=? and artist=? and albumtypewhere %s" % (self.distinct_artist, self.album_and_duplicate)
#                            statement = "select * from albums where id in (select album_id from GenreArtistAlbum where genre=? and artist=? and albumtypewhere %s) group by %s order by orderby limit ?, ?" % (self.album_and_duplicate, self.groupby_artist)

                            countstatement = "select count(distinct %s) from GenreArtistAlbum aa where genre=? and artist=? and albumtypewhere %s" % (self.distinct_artist, self.album_and_duplicate)
                            statement = """
                                           select album_id, album, artist, '', '', a.*, 0 from GenreArtistAlbum aa join albums a on
                                           aa.album_id = a.id
                                           where genre=? and artist=? and albumtypewhere %s
                                           group by %s
                                           order by orderby limit ?, ?
                                        """ % (self.album_and_duplicate, self.groupby_artist)

                        genre_options = self.removepresuf(genre, 'GENRE', controllername)
                        for genre in genre_options:
                            if genre == '[unknown genre]': genre = ''
                            log.debug('    genre: %s', genre)
                            genres.append(genre)

                            if SMAPI == 'genre:artist:album':
                                artistidval, browsebyid, containerstart = SMAPIkeys['artist']
                                rowid = artistidval - containerstart
                                if self.use_albumartist:
                                    artiststatement = """select albumartist from GenreAlbumartistAlbum where rowid=%s""" % rowid
                                else:
                                    artiststatement = """select albumartist from GenreArtistAlbum where rowid=%s""" % rowid
                                log.debug(artiststatement)
                                c.execute(artiststatement)
                                artist, = c.fetchone()
                                artist = '"%s"' % artist    # code expects this
                            elif browse == 'GenreArtistAlbums':
                                rowid = int(containerID) - self.genre_artist_parentid
                                if self.use_albumartist:
                                    artiststatement = """select albumartist from GenreAlbumartistAlbum where rowid=%s""" % rowid
                                else:
                                    artiststatement = """select albumartist from GenreArtistAlbum where rowid=%s""" % rowid
                                log.debug(artiststatement)
                                c.execute(artiststatement)
                                artist, = c.fetchone()
                                artist = '"%s"' % artist    # code expects this
                            else:
                                artist = criteria[3][1:]

                            if self.use_albumartist:
                                artist_options = self.removepresuf(artist, 'GENRE_ALBUMARTIST', controllername)
                            else:
                                artist_options = self.removepresuf(artist, 'GENRE_ARTIST', controllername)
                            for artist in artist_options:
                                if artist == '[unknown artist]': artist = ''
                                log.debug('    artist: %s', artist)
                                fields.append(artist)
                                if self.use_albumartist:
                                    if smapiservice:
                                        sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                                        orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
                                    else:
                                        orderbylist = self.get_proxy_orderby('ALBUMARTIST_ALBUM', controllername)
                                    for orderbyentry in orderbylist:
                                        orderby, prefix, suffix, albumtype, table, header = orderbyentry
                                        if not orderby or orderby == '':
                                            orderby = 'album'
                                        state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                                    id_pre = 'GENRE_ALBUMARTIST_ALBUM__'
                                else:
                                    if smapiservice:
                                        sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                                        orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
                                    else:
                                        orderbylist = self.get_proxy_orderby('ARTIST_ALBUM', controllername)
                                    for orderbyentry in orderbylist:
                                        orderby, prefix, suffix, albumtype, table, header = orderbyentry
                                        if not orderby or orderby == '':
                                            orderby = 'album'
                                        state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                                    id_pre = 'GENRE_ARTIST_ALBUM__'

                    else:

                        print "proxy_search - unknown search criteria, not supported in code"

            res  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            count = 0
            parentid = '7'

            log.debug("count statement: %s", countstatement)
            log.debug("statement: %s", statement)

            # process each fields option across all chunks until we find a match
            matches = {}
            totalMatches = 0
            found_field = None
            found_genre = None

            log.debug(genres)
            log.debug(fields)
            log.debug(state_pre_suf)

            for genre in genres:
                for field in fields:
                    for orderby, prefix, suffix, albumtype, table, header in state_pre_suf:
                        log.debug(table)
                        log.debug(searchtype)
                        if not table in matches:
                            if searchtype == 'ALBUM':
                                c.execute(countstatement)
                            elif searchtype == 'FIELD_ALBUM':
                                albumtypewhere = self.get_albumtype_where(albumtype, table='aa')
                                loopcountstatement = countstatement.replace('albumtypewhere', albumtypewhere)
                                log.debug(loopcountstatement)
                                c.execute(loopcountstatement, (field, ))
                            elif searchtype == 'GENRE_FIELD_ALBUM':
                                albumtypewhere = self.get_albumtype_where(albumtype, table='aa')
                                loopcountstatement = countstatement.replace('albumtypewhere', albumtypewhere)
                                c.execute(loopcountstatement, (genre, field))
                            tableMatches, = c.fetchone()
                            tableMatches = int(tableMatches)
                            matches[table] = tableMatches
                            totalMatches += tableMatches
                    if totalMatches != 0:
                        # have found the entry we want
                        found_field = field
                        break
                if found_field:
                    found_genre = genre
                    break

            log.debug(totalMatches)
            log.debug(found_field)
            log.debug(found_genre)

            if totalMatches != 0:

                chunks = len(state_pre_suf)
                if (self.show_chunk_separator and chunks > 1) or (self.show_chunk_separator_single and chunks == 1):
                    show_separator = True
                else:
                    show_separator = False

                count_chunk = []
                chunk_data = []
                for sps in state_pre_suf:
                    orderby, prefix, suffix, albumtype, table, header = sps
                    if matches[table] > 0 or self.show_chunk_header_empty:
                        count_chunk.append((matches[table], 1))
                        chunk_data.append(sps)
                chunkdata, totalMatches = self.chunker(startingIndex, requestedCount, count_chunk, show_separator)

                if SMAPI == 'Alphaalbum':
                    if not show_separator and chunks == 1:
                        orderby, prefix, suffix, albumtype, table, header = state_pre_suf[0]
                        if ',' in orderby: orderby = orderby.split(',')[0]

                        alphastatement = alphastatement % (orderby)
                        log.debug(alphastatement)
                        c.execute(alphastatement)
                        return c.fetchall()
                    else:
                        return None

                for chunk in chunkdata:

                    group, start, end, sep = chunk
                    length = end - start

                    orderby, prefix, suffix, albumtype, table, header = chunk_data[group]

                    if show_separator and sep:
                        count += 1
                        if not header or header == '':
                            header = "%s %s" % ('ordered by', orderby)
                        separator = '%s %s %s' % (self.chunk_separator_prefix, header, self.chunk_separator_suffix)
                        res += '<container id="%s" parentID="%s" restricted="true">' % (id_pre, parentid)
                        res += '<dc:title>%s</dc:title>' % (separator)
                        res += '<upnp:class>%s</upnp:class>' % (self.album_class)
                        res += '</container>'

                    orderstatement = statement.replace('order by orderby', 'order by ' + orderby)
                    albumtypewhere = self.get_albumtype_where(albumtype, table='aa')
                    orderstatement = orderstatement.replace('albumtypewhere', albumtypewhere)
                    log.debug(orderstatement)

                    if searchtype == 'ALBUM':
                        c.execute(orderstatement, (start, length))
                    elif searchtype == 'FIELD_ALBUM':
                        c.execute(orderstatement, (found_field, start, length))
                    elif searchtype == 'GENRE_FIELD_ALBUM':
                        c.execute(orderstatement, (found_genre, found_field, start, length))

                    for row in c:
#                        log.debug("row: %s", row)

#                        id, album, artist, year, albumartist, duplicate, cover, artid, inserted, composer, tracknumbers, created, lastmodified, albumtype, lastplayed, playcount, albumsort = row
                        album_id, album, artist, albumartist, composer, id, albumlist, artistlist, year, albumartistlist, duplicate, cover, artid, inserted, composerlist, tracknumbers, created, lastmodified, albumtype, lastplayed, playcount, albumsort, separated = row
                        id = str(id)
                        playcount = str(playcount)

                        log.debug("id: %s", id)
                        log.debug("playcount: %s", playcount)

                        # work out what was passed
                        if id_pre == 'ALBUM__':
                            if self.use_albumartist: passed_artist = 'ALBUMARTIST'
                            else: passed_artist = 'ARTIST'
                        elif id_pre == 'COMPOSER_ALBUM__':
                            passed_artist = None
                        elif id_pre == 'ALBUMARTIST_ALBUM__' or id_pre == 'GENRE_ALBUMARTIST_ALBUM__':
                            passed_artist = 'ALBUMARTIST'
                        elif id_pre == 'ARTIST_ALBUM__' or id_pre == 'CONTRIBUTINGARTIST_ALBUM__' or id_pre == 'GENRE_ARTIST_ALBUM__':
                            passed_artist = 'ARTIST'

                        log.debug("passed_artist: %s", passed_artist)
                        log.debug("artisttype: %s", artisttype)
                        log.debug("self.now_playing_artist: %s", self.now_playing_artist)

                        # get entries/entry positions
                        if passed_artist == 'ALBUMARTIST':
                            if artisttype == 'LIST':
                                if albumartist == '': albumartist = '[unknown albumartist]'
                                if self.now_playing_artist == 'selected':
                                    albumartist = self.get_entry(albumartist, self.now_playing_artist_selected_default, self.now_playing_artist_combiner)
                                else:
                                    albumartist = self.get_entry(albumartist, self.now_playing_artist, self.now_playing_artist_combiner)
                            log.debug("albumartist: %s", albumartist)
                            albumartist_entry = self.get_entry_position(albumartist, albumartistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                            log.debug("albumartist_entry: %s", albumartist_entry)
                            if self.now_playing_artist == 'selected':
                                artist_entry = albumartist_entry
                                artist = self.get_entry_at_position(artist_entry, artistlist)
                            else:
                                artist = self.get_entry(artistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                                log.debug("artist: %s", artist)
                                artist_entry = self.get_entry_position(artist, artistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                                log.debug("artist_entry: %s", artist_entry)
                        elif passed_artist == 'ARTIST':
                            if artisttype == 'LIST':
                                if artist == '': artist = '[unknown artist]'
                                if self.now_playing_artist == 'selected':
                                    artist = self.get_entry(artist, self.now_playing_artist_selected_default, self.now_playing_artist_combiner)
                                else:
                                    artist = self.get_entry(artist, self.now_playing_artist, self.now_playing_artist_combiner)
                            artist_entry = self.get_entry_position(artist, artistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                            if self.now_playing_artist == 'selected':
                                albumartist_entry = artist_entry
                                albumartist = self.get_entry_at_position(albumartist_entry, albumartistlist)
                            else:
                                albumartist = self.get_entry(albumartistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                                albumartist_entry = self.get_entry_position(albumartist, albumartistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                        else:
                            if self.now_playing_artist == 'selected':
                                artist = self.get_entry(artistlist, self.now_playing_artist_selected_default, self.now_playing_artist_combiner)
                            else:
                                artist = self.get_entry(artistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                            artist_entry = self.get_entry_position(artist, artistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                            if self.now_playing_artist == 'selected':
                                albumartist = self.get_entry(albumartistlist, self.now_playing_artist_selected_default, self.now_playing_artist_combiner)

                            else:
                                albumartist = self.get_entry(albumartistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                            albumartist_entry = self.get_entry_position(albumartist, albumartistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                        if album == '': album = '[unknown album]'
                        log.debug("album: %s", album)
                        if self.now_playing_album == 'selected':
                            album_entry = self.get_entry_position(album, albumlist, self.now_playing_album_selected_default, self.now_playing_album_combiner)
                        else:
                            album_entry = self.get_entry_position(album, albumlist, self.now_playing_album, self.now_playing_album_combiner)
                        log.debug("album_entry: %s", album_entry)

                        # NOTE: in this case IDs are real IDs, but because of the group by's they are not necessarily the right ones

                        album = escape(album)
                        artist = escape(artist)
                        albumartist = escape(albumartist)

                        log.debug("album: %s", album)
                        log.debug("artist: %s", artist)
                        log.debug("albumartist: %s", albumartist)

                        if duplicate != 0:
                            album += ' (' + str(duplicate) + ')'

                        a_prefix = self.proxy_makepresuffix(prefix, self.replace_pre, {'year':year, 'lastplayed':lastplayed, 'playcount':playcount, 'created':created, 'lastmodified':lastmodified, 'inserted':inserted, 'artist':artist, 'albumartist':albumartist, 'composer':composer})
                        if a_prefix: album = '%s%s' % (a_prefix, album)
                        a_suffix = self.proxy_makepresuffix(suffix, self.replace_suf, {'year':year, 'lastplayed':lastplayed, 'playcount':playcount, 'created':created, 'lastmodified':lastmodified, 'inserted':inserted, 'artist':artist, 'albumartist':albumartist, 'composer':composer})
                        if a_suffix: album = '%s%s' % (album, a_suffix)

                        if SMAPI != '':
#                            albumidval, browsebyid, containerstart = SMAPIkeys['album']
                            if SMAPI == 'genre:artist:album':
                                itemid = "%s:%s:%s" % (genreidval, artistidval, album_id)
                            elif SMAPI == 'artist:album':
                                itemid = "%s:%s" % (artistidval, album_id)
                            elif SMAPI == 'contributingartist:album':
                                itemid = "%s:%s" % (contributingartistidval, album_id)
                            elif SMAPI == 'composer:album':
                                itemid = "%s:%s" % (composeridval, album_id)
                            else:
                                itemid = album_id
                            items += [(itemid, album)]
                            log.debug("itemid: %s", itemid)

                        log.debug("cover: %s", cover)

                        if cover.startswith('EMBEDDED_'):
                            # art is embedded for this file
                            coverparts = cover.split('_')
                            coveroffsets = coverparts[1]
                            # spec may contain '_'
                            specstart = len('EMBEDDED_') + len(coveroffsets) + 1
                            coverspec = cover[specstart:]
                            cvfile = getFile(coverspec)
                            cvpath = coverspec
                            dummycoverfile = self.dbname + '.' + str(artid) + '.coverart'
                            log.debug("dummycoverfile: %s", dummycoverfile)
        #                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                            coverres = self.proxyaddress + '/wmp/' + dummycoverfile
                            log.debug("coverres: %s", coverres)
                            dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath, cover=cover)
                            log.debug("dummycoverstaticfile: %s", dummycoverstaticfile)
                            self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)
                            log.debug("after add_static_file")
                        elif cover != '':
                            cvfile = getFile(cover)
                            cvpath = cover
                            coverfiletype = getFileType(cvfile)
                            dummycoverfile = self.dbname + '.' + str(artid) + '.' + coverfiletype
        #                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                            coverres = self.proxyaddress + '/wmp/' + dummycoverfile
                            dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath)    # TODO: pass contenttype
                            self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)

                        if smapiservice:
                            id = itemid
                        else:
                            id ='%s%s_%s_%s__%s' % (id_pre, album_entry, artist_entry, albumartist_entry, id)
#                        if browse != '':
#                            id = id_pre + str(album_id)
                        log.debug("id: %s", id)

                        count += 1
#                        res += '<container id="%s" parentID="%s" restricted="true">' % (id, self.track_parentid)
                        if browse == '':
                            res += '<container id="%s" parentID="%s" restricted="true">' % (id, self.artist_parentid)
                        else:
                            res += '<container id="%s" parentID="%s" restricted="true">' % (id, containerID)
                        res += '<dc:title>%s</dc:title>' % (album)
                        res += '<upnp:artist role="AlbumArtist">%s</upnp:artist>' % (albumartist)
                        res += '<upnp:artist role="Performer">%s</upnp:artist>' % (artist)
                        res += '<upnp:class>%s</upnp:class>' % (self.album_class)
                        res += '<upnp:album>%s</upnp:album>' % (album)
                        if cover != '':
                            res += '<upnp:albumArtURI>%s</upnp:albumArtURI>' % (coverres)
                        res += '</container>'

            res += '</DIDL-Lite>'

        elif (containerID == '108' and searchCriteria == 'upnp:class = "object.container.person.musicArtist" and @refID exists false') or \
             searchcontainer == 'Composer' or \
             SMAPI == 'Alphacomposer' or \
             SMAPI == 'composer' or \
             browse == 'Composers':

            # Composer container

            state_pre_suf = []

            searchwhere = ''
            if searchcontainer:
                searchstring = escape_sql(searchstring)
                searchwhere = "where composer like '%s%%'" % searchstring

            if searchwhere == '':
                albumwhere = 'where %s' % self.composer_album_albumtype_where
            else:
                albumwhere = ' and %s' % self.composer_album_albumtype_where

            countstatement = "select count(distinct composer) from ComposerAlbum %s%s" % (searchwhere, albumwhere)
            statement = "select rowid, composer, lastplayed, playcount from ComposerAlbum %s%s group by composer order by orderby limit ?, ?" % (searchwhere, albumwhere)

            alphastatement = smapialphastatement % ('composer', 'ComposerAlbum %s group by composer order by %%s' % albumwhere)

            if smapiservice:
                sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
            else:
                orderbylist = self.get_proxy_orderby('COMPOSER', controllername)
            for orderbyentry in orderbylist:
                orderby, prefix, suffix, albumtype, table, header = orderbyentry
                if not orderby or orderby == '':
                    orderby = 'composer'
                state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
            id_pre = 'COMPOSER__'

            log.debug("count statement: %s", countstatement)
            log.debug("statement: %s", statement)

            res  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            count = 0
            parentid = '108'

            c.execute(countstatement)
            totalMatches, = c.fetchone()
            totalMatches = int(totalMatches)
            if totalMatches != 0:

                chunks = len(state_pre_suf)
                if (self.show_chunk_separator and chunks > 1) or (self.show_chunk_separator_single and chunks == 1):
                    show_separator = True
                else:
                    show_separator = False

                count_chunk = []
                count_chunk.append((totalMatches, chunks))
                chunkdata, totalMatches = self.chunker(startingIndex, requestedCount, count_chunk, show_separator)

                if SMAPI == 'Alphacomposer':
                    if not show_separator and chunks == 1:
                        orderby, prefix, suffix, albumtype, table, header = state_pre_suf[0]
                        if ',' in orderby: orderby = orderby.split(',')[0]
                        alphastatement = alphastatement % (orderby)
                        log.debug(alphastatement)
                        c.execute(alphastatement)
                        return c.fetchall()
                    else:
                        return None

                for chunk in chunkdata:

                    group, start, end, sep = chunk
                    length = end - start

                    orderby, prefix, suffix, albumtype, table, header = state_pre_suf[group]

                    if show_separator and sep:
                        count += 1
                        if not header or header == '':
                            header = "%s %s" % ('ordered by', orderby)
                        separator = '%s %s %s' % (self.chunk_separator_prefix, header, self.chunk_separator_suffix)
                        res += '<container id="%s" parentID="%s" restricted="true">' % (id_pre, parentid)
                        res += '<dc:title>%s</dc:title>' % (separator)
                        res += '<upnp:class>%s</upnp:class>' % (self.composer_class)
                        res += '</container>'

                    orderstatement = statement.replace('order by orderby', 'order by ' + orderby)
                    log.debug(orderstatement)

                    c.execute(orderstatement, (start, length))
                    for row in c:
#                        log.debug("row: %s", row)
                        rowid, composer, lastplayed, playcount = row
                        if composer == '': composer = '[unknown composer]'
                        composer = escape(composer)

                        a_prefix = self.proxy_makepresuffix(prefix, self.replace_pre, {'lastplayed':lastplayed, 'playcount':playcount})
                        if a_prefix: composer = '%s%s' % (a_prefix, composer)
                        a_suffix = self.proxy_makepresuffix(suffix, self.replace_suf, {'lastplayed':lastplayed, 'playcount':playcount})
                        if a_suffix: composer = '%s%s' % (composer, a_suffix)

                        if SMAPI != '':
                            composeridval, browsebyid, containerstart = SMAPIkeys['composer']
                            items += [(rowid + containerstart, composer)]

                        count += 1
#                        id = id_pre + str(startingIndex + count + self.composer_parentid)  # dummy, sequential
                        id = id_pre + str(rowid + self.composer_parentid)

                        if browse == '':
                            res += '<container id="%s" parentID="%s" restricted="true">' % (id, parentid)
                        else:
                            res += '<container id="%s" parentID="%s" restricted="true">' % (id, containerID)
                        res += '<dc:title>%s</dc:title>' % (composer)
        ## test this!                res += '<upnp:artist role="AuthorComposer">%s</upnp:artist>' % (composer)
                        res += '<upnp:class>%s</upnp:class>' % (self.composer_class)
                        res += '</container>'

            res += '</DIDL-Lite>'

        elif containerID == '0' and searchCriteria == 'upnp:class = "object.container.genre.musicGenre" and @refID exists false' or \
             SMAPI == 'Alphagenre' or \
             SMAPI == 'genre' or \
             browse == 'Genres':

            # Genre class

            res  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            count = 0
            parentid = '5'

            state_pre_suf = []

            searchwhere = ''
            if searchcontainer:
                searchstring = escape_sql(searchstring)
                searchwhere = "where genre like '%s%%'" % searchstring

            if self.use_albumartist:

                if searchwhere == '':
                    albumwhere = 'where %s' % self.albumartist_album_albumtype_where
                else:
                    albumwhere = ' and %s' % self.albumartist_album_albumtype_where

                countstatement = "select count(distinct genre) from GenreAlbumartistAlbum %s%s" % (searchwhere, albumwhere)

                statement = """select rowid, genre, lastplayed, playcount from Genre where genre in
                               (select distinct genre from GenreAlbumartistAlbum %s%s)
                               order by orderby limit ?, ?""" % (searchwhere, albumwhere)

                alphastatement = smapialphastatement % ('genre', 'GenreAlbumartistAlbum %s group by genre order by %%s' % albumwhere)

                if smapiservice:
                    sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                    orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
                else:
                    orderbylist = self.get_proxy_orderby('GENRE_AA', controllername)
            else:

                if searchwhere == '':
                    albumwhere = 'where %s' % self.artist_album_albumtype_where
                else:
                    albumwhere = ' and %s' % self.artist_album_albumtype_where

                countstatement = "select count(distinct genre) from GenreArtistAlbum %s%s" % (searchwhere, albumwhere)

                statement = """select rowid, genre, lastplayed, playcount from Genre where genre in

                               (select distinct genre from GenreArtistAlbum %s)
                               order by orderby limit ?, ?"""  % (searchwhere, albumwhere)

                alphastatement = smapialphastatement % ('genre', 'GenreArtistAlbum %s group by genre order by %%s' % albumwhere)

                if smapiservice:
                    sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                    orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
                else:
                    orderbylist = self.get_proxy_orderby('GENRE_A', controllername)
            for orderbyentry in orderbylist:
                orderby, prefix, suffix, albumtype, table, header = orderbyentry
                if not orderby or orderby == '':
                    orderby = 'genre'
                state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
            id_pre = 'GENRE__'

            log.debug("count statement: %s", countstatement)
            log.debug("statements: %s", state_pre_suf)

            c.execute(countstatement)
            totalMatches, = c.fetchone()
            totalMatches = int(totalMatches)
            if totalMatches != 0:

                chunks = len(state_pre_suf)
                if (self.show_chunk_separator and chunks > 1) or (self.show_chunk_separator_single and chunks == 1):
                    show_separator = True
                else:
                    show_separator = False

                count_chunk = []
                count_chunk.append((totalMatches, chunks))
                chunkdata, totalMatches = self.chunker(startingIndex, requestedCount, count_chunk, show_separator)

                if SMAPI == 'Alphagenre':
                    if not show_separator and chunks == 1:
                        orderby, prefix, suffix, albumtype, table, header = state_pre_suf[0]
                        if ',' in orderby: orderby = orderby.split(',')[0]
                        alphastatement = alphastatement % (orderby)
                        log.debug(alphastatement)
                        c.execute(alphastatement)
                        return c.fetchall()
                    else:
                        return None

                for chunk in chunkdata:

                    group, start, end, sep = chunk
                    length = end - start

                    orderby, prefix, suffix, albumtype, table, header = state_pre_suf[group]

                    if show_separator and sep:
                        count += 1
                        if not header or header == '':
                            header = "%s %s" % ('ordered by', orderby)
                        separator = '%s %s %s' % (self.chunk_separator_prefix, header, self.chunk_separator_suffix)
                        res += '<container id="%s" parentID="%s" restricted="true">' % (id_pre, parentid)
                        res += '<dc:title>%s</dc:title>' % (separator)
                        res += '<upnp:class>%s</upnp:class>' % (self.genre_class)
                        res += '</container>'

                    orderstatement = statement.replace('order by orderby', 'order by ' + orderby)
                    log.debug(orderstatement)

                    c.execute(orderstatement, (start, length))
                    for row in c:
#                        log.debug("row: %s", row)
                        rowid, genre, lastplayed, playcount = row
                        playcount = str(playcount)

                        if genre == '': genre = '[unknown genre]'
                        genre = escape(genre)

                        a_prefix = self.proxy_makepresuffix(prefix, self.replace_pre, {'lastplayed':lastplayed, 'playcount':playcount})
                        if a_prefix: genre = '%s%s' % (a_prefix, genre)
                        a_suffix = self.proxy_makepresuffix(suffix, self.replace_suf, {'lastplayed':lastplayed, 'playcount':playcount})
                        if a_suffix: genre = '%s%s' % (genre, a_suffix)

                        if SMAPI != '':
                            items += [(rowid, genre)]

                        count += 1
#                        id = id_pre + str(startingIndex + count + self.genre_parentid)  # dummy, sequential
                        id = id_pre + str(rowid)

                        res += '<container id="%s" parentID="%s" restricted="true">' % (id, containerID)
                        res += '<dc:title>%s</dc:title>' % (genre)
                        res += '<upnp:class>%s</upnp:class>' % (self.genre_class)
                        res += '</container>'

            res += '</DIDL-Lite>'

        elif (containerID == '0' and searchCriteria.startswith('upnp:class derivedfrom "object.item.audioItem" and @refID exists false')) or \
             searchcontainer == 'Track' or \
             SMAPI == 'Alphatrack' or \
             SMAPI == 'track' or \
             SMAPI == 'composer:track' or \
             SMAPI == 'artist:track' or \
             SMAPI == 'contributingartist:track' or \
             SMAPI == 'genre:track' or \
             SMAPI == 'composer:album:track' or \
             SMAPI == 'artist:album:track' or \
             SMAPI == 'contributingartist:album:track' or \
             SMAPI == 'genre:artist:track' or \
             SMAPI == 'genre:artist:album:track' or \
             browse == 'Tracks':

            # Track class

            genres = []
            artists = []
            fields = []
            tracks_type = None
            state_pre_suf = (None, None, None, [10], 'dummy', None)  # TODO: remove (when each option contains code)

            if searchCriteria == 'upnp:class derivedfrom "object.item.audioItem" and @refID exists false' or \
               searchcontainer == 'Track' or \
               SMAPI == 'Alphatrack' or \
               SMAPI == 'track' or \
               browse == 'Tracks':

                # Tracks
                tracks_type = 'TRACKS'
                if self.show_duplicates:
                    where = ""
                else:
                    where = "where duplicate = 0"

                searchwhere = where
                if searchcontainer:
                    searchstring = escape_sql(searchstring)
                    if searchwhere == '':
                        searchwhere = "where title like '%s%%'" % searchstring

                    else:
                        searchwhere += " and title like '%s%%'" % searchstring

                if smapiservice:
                    sorttype = '%s_%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1])
                    orderbylist = self.get_smapi_orderby(sorttype, controllername, proxy=True)
                else:
                    orderbylist = self.get_proxy_orderby('TRACK', controllername)
                log.debug(orderbylist)
                for orderbyentry in orderbylist:
                    orderby, prefix, suffix, albumtype, table, header = orderbyentry
                    if not orderby or orderby == '':
                        orderby = 'title'
                    state_pre_suf = (orderby, prefix, suffix, albumtype, table, header)

                countstatement = "select count(*) from tracks %s" % searchwhere
                statement = "select * from tracks %s order by %s limit %d, %d" % (searchwhere, orderby, startingIndex, requestedCount)

                alphastatement = smapialphastatement % ('title', 'tracks %s order by %%s' % searchwhere)

                c.execute(countstatement)
                totalMatches, = c.fetchone()

            else:

                # all these searches should bring back tracks
                # if one doesn't, then it should be because we have used a dummy album name
                # - we will have appended (n) to the end, where n is the duplicate number
                # so if totalMatches = 0, try again with the (n) removed, using n as the duplicate
                # note we try with the passed album name first in case the (n) is actually part of the album name
                # note also that when searching without album, the first search will bring back tracks

                for album_loop in range(2):

                    log.debug('album_loop: %d' % album_loop)
                    log.debug(SMAPI)

                    # Tracks for class/album or class
                    duplicate_number = '0'
                    criteria = searchCriteria.split('=')

                    if SMAPI == 'composer:track' or \
                       SMAPI == 'artist:track' or \
                       SMAPI == 'contributingartist:track' or \
                       SMAPI == 'genre:track' or \
                       len(criteria) == 2:

                        log.debug('here')

                        tracks_type = 'FIELD'
                        genres.append('dummy')
                        artists.append('dummy')
                        field_is = None

                        if criteria[0].endswith('microsoft:authorComposer ') or \
                           SMAPI == 'composer:track':

                            # tracks for composer
                            # searchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:authorComposer = "A New Found Glory"
                            log.debug('tracks for composer')

                            if SMAPI == 'composer:track':
                                composeridval, browsebyid, containerstart = SMAPIkeys['composer']
                                rowid = composeridval - containerstart
                                composerstatement = """select composer from ComposerAlbum where rowid=%s""" % rowid
                                log.debug(composerstatement)
                                c.execute(composerstatement)
                                composer, = c.fetchone()
                                composer = '"%s"' % composer    # code expects this
                            else:
                                composer = criteria[1][1:]

                            field_is = 'COMPOSER'
                            countstatement = "select count(*) from ComposerAlbumTrack aa where aa.composer=? %s" % (self.album_and_duplicate)
                            statement = "select * from tracks where rowid in (select track_id from ComposerAlbumTrack aa where aa.composer=? %s) order by album, discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)
                            composer_options = self.removepresuf(composer, 'COMPOSER', controllername)
                            for composer in composer_options:
                                if composer == '[unknown composer]': composer = ''
                                fields.append(composer)
                                if album_loop == 1:
                                    # shouldn't get here
                                    break
                                log.debug('    composer: %s', composer)

                        elif criteria[0].endswith('microsoft:artistAlbumArtist ') or \
                             SMAPI == 'artist:track':

                            # tracks for artist
                            # SearchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:artistAlbumArtist = "30 Seconds to Mars"
                            log.debug('tracks for artist')

                            if SMAPI == 'artist:track':
                                artistidval, browsebyid, containerstart = SMAPIkeys['artist']
                                rowid = artistidval - containerstart
                                if self.use_albumartist:
                                    artiststatement = """select albumartist from AlbumartistAlbum where rowid=%s""" % rowid
                                else:
                                    artiststatement = """select albumartist from ArtistAlbum where rowid=%s""" % rowid
                                log.debug(artiststatement)
                                c.execute(artiststatement)
                                artist, = c.fetchone()
                                artist = '"%s"' % artist    # code expects this
                            else:
                                artist = criteria[1][1:]

                            if self.use_albumartist:
                                field_is = 'ALBUMARTIST'
                            else:
                                field_is = 'ARTIST'
                            if self.use_albumartist:
                                countstatement = "select count(*) from AlbumartistAlbumTrack aa where aa.albumartist=? %s" % (self.album_and_duplicate)
                                statement = "select * from tracks where rowid in (select track_id from AlbumartistAlbumTrack aa where aa.albumartist=? %s) order by album, discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)
                                artist_options = self.removepresuf(artist, 'ALBUMARTIST', controllername)
                            else:
                                countstatement = "select count(*) from ArtistAlbumTrack aa where aa.artist=? %s" % (self.album_and_duplicate)
                                statement = "select * from tracks where rowid in (select track_id from ArtistAlbumTrack aa where aa.artist=? %s) order by album, discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)
                                artist_options = self.removepresuf(artist, 'ARTIST', controllername)
                            for artist in artist_options:

                                if artist == '[unknown artist]': artist = ''
                                if artist == '[unknown albumartist]': artist = ''
                                fields.append(artist)
                                if album_loop == 1:
                                    # shouldn't get here
                                    break
                                log.debug('    artist: %s', artist)

                        elif criteria[0].endswith('microsoft:artistPerformer ') or \
                             SMAPI == 'contributingartist:track':

                            # tracks for contributing artist
                            # searchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:artistPerformer = "1 Giant Leap"
                            log.debug('tracks for contributing artist')

                            if SMAPI == 'contributingartist:track':
                                contributingartistidval, browsebyid, containerstart = SMAPIkeys['contributingartist']
                                rowid = contributingartistidval - containerstart
                                contributingartiststatement = """select artist from ArtistAlbum where rowid=%s""" % rowid
                                log.debug(contributingartiststatement)
                                c.execute(contributingartiststatement)
                                artist, = c.fetchone()
                                artist = '"%s"' % artist    # code expects this
                            else:
                                artist = criteria[1][1:]

                            field_is = 'ARTIST'
                            countstatement = "select count(*) from ArtistAlbumTrack aa where aa.artist=? %s" % (self.album_and_duplicate)
                            statement = "select * from tracks where rowid in (select track_id from ArtistAlbumTrack aa where aa.artist=? %s) order by album, discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)
                            artist_options = self.removepresuf(artist, 'CONTRIBUTINGARTIST', controllername)
                            for artist in artist_options:
                                if artist == '[unknown artist]': artist = ''
                                fields.append(artist)
                                if album_loop == 1:
                                    # shouldn't get here
                                    break
                                log.debug('    artist: %s', artist)

                        elif criteria[0].endswith('upnp:genre ') or \
                             SMAPI == 'genre:track':

                            # tracks for genre
                            # searchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and upnp:genre = "Alt. Pop"
                            log.debug('tracks for genre')

                            if SMAPI == 'genre:track':
                                genreidval, browsebyid, containerstart = SMAPIkeys['genre']
                                rowid = genreidval
                                genrestatement = """select genre from genre where rowid=%s""" % rowid
                                log.debug(genrestatement)
                                c.execute(genrestatement)
                                genre, = c.fetchone()
                                genre = '"%s"' % genre    # code expects this
                            else:
                                genre = criteria[1][1:]

                            field_is = 'GENRE'
                            if self.use_albumartist:
                                countstatement = "select count(*) from GenreAlbumartistAlbumTrack aa where aa.genre=? %s" % (self.album_and_duplicate)
                                statement = "select * from tracks where rowid in (select track_id from GenreAlbumartistAlbumTrack aa where aa.genre=? %s) order by albumartist, album, discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)
                            else:
                                countstatement = "select count(*) from GenreArtistAlbumTrack aa where aa.genre=? %s" % (self.album_and_duplicate)
                                statement = "select * from tracks where rowid in (select track_id from GenreArtistAlbumTrack aa where aa.genre=? %s) order by artist, album, discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)
                            genre_options = self.removepresuf(genre, 'GENRE', controllername)
                            for genre in genre_options:
                                if genre == '[unknown genre]': genre = ''
                                fields.append(genre)
                                if album_loop == 1:
                                    # shouldn't get here
                                    break
                                log.debug('    genre: %s', genre)

                    elif SMAPI == 'composer:album:track' or \
                         SMAPI == 'artist:album:track' or \
                         SMAPI == 'contributingartist:album:track' or \
                         SMAPI == 'genre:artist:track' or \
                         len(criteria) == 3:

                        tracks_type = 'ARTIST'
                        genres.append('dummy')
                        not_album = False
                        artist_is = None

                        if criteria[0].endswith('microsoft:authorComposer ') or \
                           SMAPI == 'composer:album:track':

                            # tracks for composer/album
                            # SearchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:authorComposer = "A Lee" and upnp:album = "Fallen"
                            log.debug('tracks for composer/album')

                            if SMAPI == 'composer:album:track':
                                albumidval, browsebyid, containerstart = SMAPIkeys['album']
                                composerstatement = """select composer, album from ComposerAlbum where album_id=%s""" % albumidval
                                log.debug(composerstatement)
                                c.execute(composerstatement)
                                composer, album = c.fetchone()
                                composer = '"%s"' % composer    # code expects this
                                smapialbum = '"%s"' % album    # code expects this
                            else:
                                composer = criteria[1][1:-16]

                            artist_is = 'COMPOSER'
                            composer_options = self.removepresuf(composer, 'COMPOSER', controllername)
                            for composer in composer_options:
                                if composer == '[unknown composer]': composer = ''

                                artists.append(composer)
                                log.debug('    composer: %s', composer)

                                if SMAPI == 'composer:album:track':
                                    album = smapialbum
                                else:
                                    album = criteria[2][1:]

                                album_options = self.removepresuf(album, 'COMPOSER_ALBUM', controllername)
                                for album in album_options:
                                    if album == '[unknown album]': album = ''

                                    if album_loop == 1:
                                        album, duplicate_number = self.process_dummy_album(album)
                                    if not duplicate_number:
                                        break

                                    fields.append(album)
                                    log.debug('    album option: %s', album)

                            albumstatement = "select albumtype from ComposerAlbum where composer=? and album=? and duplicate=%s and %s" % (duplicate_number, self.composer_album_albumtype_where)
                            countstatement = "select count(*) from ComposerAlbumTrack where composer=? and album=? and duplicate=%s" % (duplicate_number)
                            countstatement2 = "select count(*) from (select track_id from tracknumbers where composer=? and dummyalbum=? and duplicate=%s and albumtype=? group by tracknumber)" % (duplicate_number)
                            statement = "select * from tracks where rowid in (select track_id from ComposerAlbumTrack where composer=? and album=? and duplicate=%s) order by discnumber, tracknumber, title limit %d, %d" % (duplicate_number, startingIndex, requestedCount)
                            statement2 = '''
                                            select t.*, n.tracknumber, n.coverart, n.coverartid, n.rowid from tracknumbers n join tracks t
                                            on n.track_id = t.rowid

                                            where n.composer=? and n.dummyalbum=? and n.duplicate=%s and n.albumtype=?
                                            group by n.tracknumber
                                            order by n.tracknumber, t.title
                                            limit %d, %d

                                         ''' % (duplicate_number, startingIndex, requestedCount)

                        elif criteria[0].endswith('microsoft:artistAlbumArtist ') or \
                             SMAPI == 'artist:album:track':

                            # tracks for artist/album
                            # searchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:artistAlbumArtist = "1 Giant Leap" and upnp:album = "1 Giant Leap"
                            log.debug('tracks for artist/album')

                            if SMAPI == 'artist:album:track':
                                albumidval, browsebyid, containerstart = SMAPIkeys['album']
                                if self.use_albumartist:
                                    artiststatement = """select albumartist, album from AlbumartistAlbum where album_id=%s""" % albumidval
                                else:
                                    artiststatement = """select albumartist, album from ArtistAlbum where album_id=%s""" % albumidval
                                log.debug(artiststatement)
                                c.execute(artiststatement)
                                artist, album = c.fetchone()
                                artist = '"%s"' % artist    # code expects this
                                smapialbum = '"%s"' % album    # code expects this
                            else:
                                artist = criteria[1][1:-16]

                            if self.use_albumartist:
                                artist_is = 'ALBUMARTIST'
                            else:
                                artist_is = 'ARTIST'
                            if self.use_albumartist:
                                artist_options = self.removepresuf(artist, 'ALBUMARTIST', controllername)
                            else:
                                artist_options = self.removepresuf(artist, 'ARTIST', controllername)
                            for artist in artist_options:
                                log.debug(artist)
                                if artist == '[unknown artist]': artist = ''
                                artists.append(artist)

                                if SMAPI == 'artist:album:track':
                                    album = smapialbum
                                else:
                                    album = criteria[2][1:]
                                log.debug(album)

                                if self.use_albumartist:
                                    album_options = self.removepresuf(album, 'ALBUMARTIST_ALBUM', controllername)
                                else:
                                    album_options = self.removepresuf(album, 'ARTIST_ALBUM', controllername)
                                for album in album_options:
                                    if album == '[unknown album]': album = ''

                                    if album_loop == 1:
                                        album, duplicate_number = self.process_dummy_album(album)
                                    if not duplicate_number:
                                        break

                                    fields.append(album)
                                    log.debug('    artist: %s', artist)
                                    log.debug('    album: %s', album)

                            if self.use_albumartist:

#                                albumstatement = "select albumtype from albums where albumartist=? and album=? and duplicate=%s and %s" % (duplicate_number, self.albumartist_album_albumtype_where)
                                albumstatement = "select albumtype from AlbumartistAlbum where albumartist=? and album=? and duplicate=%s and %s" % (duplicate_number, self.albumartist_album_albumtype_where)
                                countstatement = "select count(*) from AlbumartistAlbumTrack where albumartist=? and album=? and duplicate=%s" % (duplicate_number)
                                countstatement2 = "select count(*) from (select track_id from tracknumbers where albumartist=? and dummyalbum=? and duplicate=%s and albumtype=? group by tracknumber)" % (duplicate_number)
                                statement = "select * from tracks where rowid in (select track_id from AlbumartistAlbumTrack where albumartist=? and album=? and duplicate=%s) order by discnumber, tracknumber, title limit %d, %d" % (duplicate_number, startingIndex, requestedCount)
                                statement2 = '''
                                                select t.*, n.tracknumber, n.coverart, n.coverartid, n.rowid from tracknumbers n join tracks t

                                                on n.track_id = t.rowid
                                                where n.albumartist=? and n.dummyalbum=? and n.duplicate=%s and n.albumtype=?
                                                group by n.tracknumber

                                                order by n.tracknumber, t.title
                                                limit %d, %d
                                             ''' % (duplicate_number, startingIndex, requestedCount)

                            else:

                                albumstatement = "select albumtype from ArtistAlbum where artist=? and album=? and duplicate=%s and %s" % (duplicate_number, self.artist_album_albumtype_where)
                                countstatement = "select count(*) from ArtistAlbumTrack where artist=? and album=? and duplicate=%s" % (duplicate_number)
                                countstatement2 = "select count(*) from (select track_id from tracknumbers where artist=? and dummyalbum=? and duplicate=%s and albumtype=? group by tracknumber)" % (duplicate_number)
                                statement = "select * from tracks where rowid in (select track_id from ArtistAlbumTrack where artist=? and album=? and duplicate=%s) order by discnumber, tracknumber, title limit %d, %d" % (duplicate_number, startingIndex, requestedCount)
                                statement2 = '''
                                                select t.*, n.tracknumber, n.coverart, n.coverartid, n.rowid from tracknumbers n join tracks t

                                                on n.track_id = t.rowid
                                                where n.artist=? and n.dummyalbum=? and n.duplicate=%s and n.albumtype=?
                                                group by n.tracknumber

                                                order by n.tracknumber, t.title
                                                limit %d, %d
                                             ''' % (duplicate_number, startingIndex, requestedCount)

                        elif criteria[0].endswith('microsoft:artistPerformer ') or \
                             SMAPI == 'contributingartist:album:track':

                            # tracks for contributing artist/album
                            # searchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:artistPerformer = "1 Giant Leap" and upnp:album = "1 Giant Leap"
                            log.debug('tracks for contributing artist/album')

                            if SMAPI == 'contributingartist:album:track':
                                albumidval, browsebyid, containerstart = SMAPIkeys['album']
                                contributingartiststatement = """select artist, album from ArtistAlbum where album_id=%s""" % albumidval
                                log.debug(contributingartiststatement)
                                c.execute(contributingartiststatement)
                                artist, album = c.fetchone()
                                artist = '"%s"' % artist    # code expects this
                                smapialbum = '"%s"' % album    # code expects this
                            else:
                                artist = criteria[1][1:-16]

                            artist_is = 'ARTIST'
                            artist_options = self.removepresuf(artist, 'CONTRIBUTINGARTIST', controllername)
                            for artist in artist_options:
                                if artist == '[unknown artist]': artist = ''
                                artists.append(artist)

                                if SMAPI == 'contributingartist:album:track':
                                    album = smapialbum
                                else:
                                    album = criteria[2][1:]

                                album_options = self.removepresuf(album, 'CONTRIBUTINGARTIST_ALBUM', controllername)
                                for album in album_options:
                                    if album == '[unknown album]': album = ''

                                    if album_loop == 1:
                                        album, duplicate_number = self.process_dummy_album(album)
                                    if not duplicate_number:
                                        break

                                    fields.append(album)
                                    log.debug('    artist: %s', artist)
                                    log.debug('    album: %s', album)

                            albumstatement = "select albumtype from ArtistAlbum where artist=? and album=? and duplicate=%s and %s" % (duplicate_number, self.artist_album_albumtype_where)
                            countstatement = "select count(*) from ArtistAlbumTrack where artist=? and album=? and duplicate=%s" % (duplicate_number)
                            countstatement2 = "select count(*) from (select track_id from tracknumbers where artist=? and dummyalbum=? and duplicate=%s and albumtype=? group by tracknumber)" % (duplicate_number)
                            statement = "select * from tracks where rowid in (select track_id from ArtistAlbumTrack where artist=? and album=? and duplicate=%s) order by discnumber, tracknumber, title limit %d, %d" % (duplicate_number, startingIndex, requestedCount)
                            statement2 = '''
                                            select t.*, n.tracknumber, n.coverart, n.coverartid, n.rowid from tracknumbers n join tracks t

                                            on n.track_id = t.rowid
                                            where n.artist=? and n.dummyalbum=? and n.duplicate=%s and n.albumtype=?
                                            group by n.tracknumber
                                            order by n.tracknumber, t.title

                                            limit %d, %d
                                         ''' % (duplicate_number, startingIndex, requestedCount)

                        elif criteria[0].endswith('upnp:genre ') or \
                             SMAPI == 'genre:artist:track':

                            # tracks for genre/artist
                            # searchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and upnp:genre = "Alt. Rock" and microsoft:artistAlbumArtist = "Elvis Costello"
                            not_album = True
                            log.debug('tracks for genre/artist')

                            if SMAPI == 'genre:artist:track':
                                genreidval, browsebyid, containerstart = SMAPIkeys['genre']
                                rowid = genreidval
                                genrestatement = """select genre from genre where rowid=%s""" % rowid
                                log.debug(genrestatement)
                                c.execute(genrestatement)
                                genre, = c.fetchone()
                                genre = '"%s"' % genre    # code expects this

                                artistidval, browsebyid, containerstart = SMAPIkeys['artist']
                                rowid = artistidval - containerstart
                                if self.use_albumartist:
                                    artiststatement = """select albumartist from GenreAlbumartistAlbum where rowid=%s""" % rowid
                                else:
                                    artiststatement = """select albumartist from GenreArtistAlbum where rowid=%s""" % rowid
                                log.debug(artiststatement)
                                c.execute(artiststatement)
                                artist, = c.fetchone()
                                smapiartist = '"%s"' % artist    # code expects this
                            else:
                                genre = criteria[1][1:-33]

                            if self.use_albumartist:
                                artist_is = 'ALBUMARTIST'
                            else:
                                artist_is = 'ARTIST'
                            genre_options = self.removepresuf(genre, 'GENRE', controllername)
                            for genre in genre_options:
                                if genre == '[unknown genre]': genre = ''
                                artists.append(genre)

                                if SMAPI == 'genre:artist:track':
                                    artist = smapiartist
                                else:
                                    artist = criteria[2][1:]

                                if self.use_albumartist:
                                    artist_options = self.removepresuf(artist, 'ALBUMARTIST', controllername)
                                else:
                                    artist_options = self.removepresuf(artist, 'ARTIST', controllername)
                                for artist in artist_options:
                                    if artist == '[unknown artist]': artist = ''
                                    if album_loop == 1:
                                        # shouldn't get here
                                        break
                                    fields.append(artist)

                                    log.debug('    genre: %s', genre)
                                    log.debug('    artist: %s', artist)

                            if self.use_albumartist:
                                countstatement = "select count(*) from GenreAlbumartistAlbumTrack where genre=? and albumartist=? %s" % (self.album_and_duplicate)
                                statement = "select * from tracks where rowid in (select track_id from GenreAlbumartistAlbumTrack where genre=? and albumartist=? %s) order by discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)
                            else:
                                countstatement = "select count(*) from GenreArtistAlbumTrack where genre=? and artist=? %s" % (self.album_and_duplicate)
                                statement = "select * from tracks where rowid in (select track_id from GenreArtistAlbumTrack where genre=? and artist=? %s) order by discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)

                    else:

                        # len = 4 or SMAPI == 'genre:artist:album:track'
                        # tracks for genre/artist/album
                        log.debug('tracks for genre/artist/album')
                        tracks_type = 'GENRE'
                        not_album = False

                        if SMAPI == 'genre:artist:album:track':
                            genreidval, browsebyid, containerstart = SMAPIkeys['genre']
                            rowid = genreidval
                            genrestatement = """select genre from genre where rowid=%s""" % rowid
                            log.debug(genrestatement)
                            c.execute(genrestatement)
                            genre, = c.fetchone()
                            genre = '"%s"' % genre    # code expects this
                            albumidval, browsebyid, containerstart = SMAPIkeys['album']
                            if self.use_albumartist:
                                artiststatement = """select albumartist, album from GenreAlbumartistAlbum where album_id=%s""" % albumidval
                            else:
                                artiststatement = """select albumartist, album from GenreArtistAlbum where album_id=%s""" % albumidval
                            log.debug(artiststatement)
                            c.execute(artiststatement)
                            artist, album = c.fetchone()
                            smapiartist = '"%s"' % artist    # code expects this
                            smapialbum = '"%s"' % album    # code expects this
                        else:
                            genre = criteria[1][1:-33]

                        if self.use_albumartist:
                            artist_is = 'ALBUMARTIST'
                        else:
                            artist_is = 'ARTIST'
                        genre_options = self.removepresuf(genre, 'GENRE', controllername)
                        for genre in genre_options:
                            if genre == '[unknown genre]': genre = ''
                            genres.append(genre)

                            if SMAPI == 'genre:artist:album:track':
                                artist = smapiartist
                            else:
                                artist = criteria[2][1:-16]

                            if self.use_albumartist:
                                artist_options = self.removepresuf(artist, 'GENRE_ALBUMARTIST', controllername)
                            else:
                                artist_options = self.removepresuf(artist, 'GENRE_ARTIST', controllername)
                            for artist in artist_options:

                                log.debug("artist: %s", artist)

                                if artist == '[unknown artist]': artist = ''
                                artists.append(artist)
                                if SMAPI == 'genre:artist:album:track':
                                    album = smapialbum
                                else:
                                    album = criteria[3][1:]

                                if self.use_albumartist:
                                    album_options = self.removepresuf(album, 'ALBUMARTIST_ALBUM', controllername)
                                else:
                                    album_options = self.removepresuf(album, 'ARTIST_ALBUM', controllername)
                                for album in album_options:

                                    log.debug("album: %s", album)

                                    if album == '[unknown album]': album = ''

                                    if album_loop == 1:
                                        album, duplicate_number = self.process_dummy_album(album)
                                    if not duplicate_number:
                                        break

                                    fields.append(album)
                                    log.debug('    genre: %s', genre)
                                    log.debug('    artist: %s', artist)
                                    log.debug('    album: %s', album)

                        if self.use_albumartist:

                            albumstatement = "select albumtype from GenreAlbumartistAlbum where genre=? and albumartist=? and album=? and duplicate=%s and %s" % (duplicate_number, self.albumartist_album_albumtype_where)
                            countstatement = "select count(*) from GenreAlbumartistAlbumTrack where genre=? and albumartist=? and album=? and duplicate = %s" % (duplicate_number)
                            countstatement2 = "select count(*) from (select track_id from tracknumbers where genre=? and albumartist=? and dummyalbum=? and duplicate=%s and albumtype=? group by tracknumber)" % (duplicate_number)
                            statement = "select * from tracks where rowid in (select track_id from GenreAlbumartistAlbumTrack where genre=? and albumartist=? and album=? and duplicate = %s) order by discnumber, tracknumber, title limit %d, %d" % (duplicate_number, startingIndex, requestedCount)
                            statement2 = '''
                                            select t.*, n.tracknumber, n.coverart, n.coverartid, n.rowid from tracknumbers n join tracks t
                                            on n.track_id = t.rowid
                                            where n.genre=? and n.albumartist=? and n.dummyalbum=? and n.duplicate=%s and n.albumtype=?
                                            group by n.tracknumber
                                            order by n.tracknumber, t.title
                                            limit %d, %d
                                         ''' % (duplicate_number, startingIndex, requestedCount)

                        else:

                            albumstatement = "select albumtype from GenreArtistAlbum where genre=? and artist=? and album=? and duplicate=%s and %s" % (duplicate_number, self.artist_album_albumtype_where)
                            countstatement = "select count(*) from GenreArtistAlbumTrack where genre=? and artist=? and album=? and duplicate = %s" % (duplicate_number)
                            countstatement2 = "select count(*) from (select track_id from tracknumbers where genre=? and artist=? and dummyalbum=? and duplicate=%s and albumtype=? group by tracknumber)" % (duplicate_number)
                            statement = "select * from tracks where rowid in (select track_id from GenreArtistAlbumTrack where genre=? and artist=? and album=? and duplicate = %s) order by discnumber, tracknumber, title limit %d, %d" % (duplicate_number, startingIndex, requestedCount)
                            statement2 = '''
                                            select t.*, n.tracknumber, n.coverart, n.coverartid, n.rowid from tracknumbers n join tracks t
                                            on n.track_id = t.rowid
                                            where n.genre=? and n.artist=? and n.dummyalbum=? and n.duplicate=%s and n.albumtype=?
                                            group by n.tracknumber
                                            order by n.tracknumber, t.title
                                            limit %d, %d
                                         ''' % (duplicate_number, startingIndex, requestedCount)

                    # process each fields option across all levels until we find a match
                    matches = {}
                    totalMatches = 0

                    found_field = None
                    found_artist = None
                    found_genre = None
                    for genre in genres:
                        for artist in artists:
                            for field in fields:
                                if tracks_type == 'FIELD':
                                    bindvars = (field, )
                                    log.debug("countstatement: %s", countstatement)
                                    log.debug("vars: %s", bindvars)
                                    c.execute(countstatement, bindvars)
                                elif tracks_type == 'ARTIST':
                                    if not_album:
                                        bindvars = (artist, field)
                                        log.debug("countstatement: %s", countstatement)
                                        log.debug("vars: %s", bindvars)
                                        c.execute(countstatement, bindvars)
                                    else:
                                        bindvars = (artist, field)
                                        log.debug("albumstatement: %s", albumstatement)
                                        log.debug("vars: %s", bindvars)
                                        c.execute(albumstatement, bindvars)
                                        albumtype, = c.fetchone()
                                        if albumtype == 10:
                                            bindvars = (artist, field)
                                            log.debug("countstatement: %s", countstatement)
                                            log.debug("vars: %s", bindvars)
                                            c.execute(countstatement, bindvars)
                                        else:
                                            bindvars = (artist, field, albumtype)
                                            log.debug("countstatement2: %s", countstatement2)
                                            log.debug("vars: %s", bindvars)
                                            c.execute(countstatement2, bindvars)
                                elif tracks_type == 'GENRE':
                                    bindvars = (genre, artist, field)
                                    log.debug("albumstatement: %s", albumstatement)
                                    log.debug("vars: %s", bindvars)
                                    c.execute(albumstatement, bindvars)
                                    albumtype, = c.fetchone()
                                    if albumtype == 10:
                                        bindvars = (genre, artist, field)
                                        log.debug("countstatement: %s", countstatement)
                                        log.debug("vars: %s", bindvars)
                                        c.execute(countstatement, bindvars)
                                    else:
                                        bindvars = (genre, artist, field, albumtype)
                                        log.debug("countstatement2: %s", countstatement2)
                                        log.debug("vars: %s", bindvars)
                                        c.execute(countstatement2, bindvars)
                                totalMatches, = c.fetchone()
                                totalMatches = int(totalMatches)
                                if totalMatches != 0:
                                    # have found the entry we want
                                    found_field = field
                                    break
                            if found_field:
                                found_artist = artist
                                break
                        if found_field:
                            found_genre = genre
                            break

                    if totalMatches != 0:
                        break

            ret  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            count = 0

            # TODO: rationalise tracks so it can use sorts
            if SMAPI == 'Alphatrack':
#                if not show_separator and chunks == 1:
#                    orderby, prefix, suffix, albumtype, table, header = state_pre_suf[0]
#                    if ',' in orderby: orderby = orderby.split(',')[0]
#                    alphastatement = alphastatement % (orderby)
#                    log.debug(alphastatement)
#                    c.execute(alphastatement)
#                    return c.fetchall()
#                else:
#                    return None
                alphastatement = alphastatement % ('title')
                log.debug(alphastatement)
                c.execute(alphastatement)
                return c.fetchall()


            if tracks_type == 'TRACKS':
                log.debug("statement: %s", statement)
                c.execute(statement)
            elif tracks_type == 'FIELD':
                bindvars = (found_field, )
                log.debug("statement: %s", statement)
                log.debug("vars: %s", bindvars)
                c.execute(statement, bindvars)
            elif tracks_type == 'ARTIST':
                if not_album:
                    # genre/artist
                    bindvars = (found_artist, field)
                    log.debug("statement: %s", statement)
                    log.debug("vars: %s", bindvars)
                    c.execute(statement, bindvars)
                else:
                    if albumtype != 10:
                        bindvars = (found_artist, found_field, albumtype)
                        log.debug("statement2: %s", statement2)
                        log.debug("vars: %s", bindvars)
                        c.execute(statement2, bindvars)
                    else:
                        bindvars = (found_artist, found_field)
                        log.debug("statement: %s", statement)

                        log.debug("vars: %s", bindvars)
                        c.execute(statement, bindvars)
            elif tracks_type == 'GENRE':
                if albumtype != 10:
                    bindvars = (found_genre, found_artist, found_field, albumtype)
                    log.debug("statement2: %s", statement2)
                    log.debug("vars: %s", bindvars)
                    c.execute(statement2, bindvars)
                else:
                    bindvars = (found_genre, found_artist, found_field)
                    log.debug("statement: %s", statement)
                    log.debug("vars: %s", bindvars)
                    c.execute(statement, bindvars)

            for row in c:
#                log.debug("row: %s", row)
                if (tracks_type == 'ARTIST' or tracks_type == 'GENRE') and \
                   albumtype != 10 and \
                   not_album == False:
                    id, id2, duplicate, title, artistlistshort, artistlist, albumlist, genre, tracktracknumber, year, albumartistlistshort, albumartistlist, composerlistshort, composerlist, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned, titlesort, albumsort, tracknumber, coverart, coverartid, rowid = row
                    cover, artid = self.choosecover(folderart, trackart, folderartid, trackartid, coverart, coverartid)
                else:
                    id, id2, duplicate, title, artistlistshort, artistlist, albumlist, genre, tracknumber, year, albumartistlistshort, albumartistlist, composerlistshort, composerlist, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned, titlesort, albumsort = row
                    cover, artid = self.choosecover(folderart, trackart, folderartid, trackartid)
                mime = fixMime(mime)

                wsfile = filename
                wspath = os.path.join(path, filename)
#                wspath = path + filename
                path = self.convert_path(path)
                filepath = path + filename
                filepath = encode_path(filepath)
                filepath = escape(filepath, escape_entities)
                protocol = getProtocol(mime)
                contenttype = mime
                filetype = getFileType(filename)

                if SMAPI != '' and source == 'SMAPI':
                    transcode, newtype = checksmapitranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)
                    if transcode:
                        mime = 'audio/mpeg'
                else:
                    transcode, newtype = checktranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)
                if transcode:
                    dummyfile = self.dbname + '.' + id + '.' + newtype
                else:
                    dummyfile = self.dbname + '.' + id + '.' + filetype
                res = self.proxyaddress + '/WMPNSSv3/' + dummyfile
                if transcode:
#                    log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s\ntranscodetype: %s' % (dummyfile, wsfile, wspath, contenttype, newtype))
                    dummystaticfile = webserver.TranscodedFileSonos(dummyfile, wsfile, wspath, newtype, contenttype, cover=cover)
                    self.proxy.wmpcontroller.add_transcoded_file(dummystaticfile)
                else:
#                    log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s' % (dummyfile, wsfile, wspath, contenttype))
                    dummystaticfile = webserver.StaticFileSonos(dummyfile, wsfile, wspath, contenttype, cover=cover)
                    self.proxy.wmpcontroller.add_static_file(dummystaticfile)

                if cover != '' and not cover.startswith('EMBEDDED_'):
                    cvfile = getFile(cover)
                    cvpath = cover
                    coverfiletype = getFileType(cvfile)
                    dummycoverfile = self.dbname + '.' + str(artid) + '.' + coverfiletype
                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                    dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath)    # TODO: pass contenttype
                    self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)

                iduration = int(length)
                duration = maketime(float(length))

                if title == '': title = '[unknown title]'

                # get passed key fields (artist/albumartist/album)
                passed_artist = None
                passed_albumartist = None
                passed_album = None
                if tracks_type == 'TRACKS':
                    # nothing passed
                    pass
                elif tracks_type == 'FIELD':
                    if field_is == 'ARTIST':
                        passed_artist = found_field
                    elif field_is == 'ALBUMARTIST':
                        passed_albumartist = found_field
                elif tracks_type == 'ARTIST':
                    if not_album == False:
                        if artist_is == 'ARTIST':
                            passed_artist = found_artist
                        elif artist_is == 'ALBUMARTIST':
                            passed_albumartist = found_artist
                        passed_album = found_field
                    else:
                        if artist_is == 'ARTIST':
                            passed_artist = found_field
                        elif artist_is == 'ALBUMARTIST':
                            passed_albumartist = found_field
                elif tracks_type == 'GENRE':
                    if artist_is == 'ARTIST':
                        passed_artist = found_artist
                    elif artist_is == 'ALBUMARTIST':
                        passed_albumartist = found_artist
                    passed_album = found_field

                # get which entry to use as default
                artist_selected = False
                album_selected = False
                if self.now_playing_artist == 'selected': artist_selected = True
                if self.now_playing_album == 'selected': album_selected = True

                # get positions for passed fields (they should all be found)
                artist_entry = 0
                albumartist_entry = 0
                album_entry = 0
                if passed_artist:
                    artist_entry = self.get_entry_position(passed_artist, artistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                if passed_albumartist:
                    albumartist_entry = self.get_entry_position(passed_albumartist, albumartistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                if passed_album:
                    album_entry = self.get_entry_position(passed_album, albumlist, self.now_playing_album, self.now_playing_album_combiner)

                # overwrite returned key fields (artist/albumartist/album) with those passed if appropriate
                # - if not passed or selected, get appropriate entries
                artist_entry_id = 0
                albumartist_entry_id = 0
                album_entry_id = 0
                if passed_artist and artist_selected:
                    artist = passed_artist
                    artist_entry_id = str(artist_entry)
                else:
                    if artistlist == '': artist = '[unknown artist]'
                    else:
                        if artist_selected:
                            artist = self.get_entry(artistlist, self.now_playing_artist_selected_default, self.now_playing_artist_combiner)
                        else:
                            artist = self.get_entry(artistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                    artist_entry_id = str(self.get_entry_position(artist, artistlist, self.now_playing_artist, self.now_playing_artist_combiner))

                if passed_albumartist and artist_selected:
                    albumartist = passed_albumartist
                    albumartist_entry_id = str(albumartist_entry)
                else:
                    if albumartistlist == '': albumartist = '[unknown albumartist]'
                    else:
                        if artist_selected:
                            albumartist = self.get_entry(albumartistlist, self.now_playing_artist_selected_default, self.now_playing_artist_combiner)
                        else:
                            albumartist = self.get_entry(albumartistlist, self.now_playing_artist, self.now_playing_artist_combiner)
                    albumartist_entry_id = str(self.get_entry_position(albumartist, albumartistlist, self.now_playing_artist, self.now_playing_artist_combiner))

                if passed_album and album_selected:
                    album = passed_album
                    album_entry_id = str(album_entry)
                else:
                    if albumlist == '': album = '[unknown album]'
                    else:
                        if album_selected:
                            album = self.get_entry(albumlist, self.now_playing_album_selected_default, self.now_playing_album_combiner)
                        else:
                            album = self.get_entry(albumlist, self.now_playing_album, self.now_playing_album_combiner)
                    album_entry_id = str(self.get_entry_position(album, albumlist, self.now_playing_album, self.now_playing_album_combiner))

                orderby, prefix, suffix, spsalbumtype, table, header = state_pre_suf
                p_prefix = self.proxy_makepresuffix(prefix, self.replace_pre, \
                           {'year':year, 'lastplayed':lastplayed, 'playcount':playcount, 'created':created, \
                            'lastmodified':lastmodified, 'inserted':inserted, 'artist':artist, 'albumartist':albumartist, \
                            'composer':composerlist, 'album':album, 'genre':genre, 'tracknumber':tracknumber, 'length':length, \
                            'path':path, 'filename':filename, \
                           })
                if p_prefix: title = '%s%s' % (p_prefix, title)
                p_suffix = self.proxy_makepresuffix(suffix, self.replace_suf,
                           {'year':year, 'lastplayed':lastplayed, 'playcount':playcount, 'created':created,
                            'lastmodified':lastmodified, 'inserted':inserted, 'artist':artist, 'albumartist':albumartist,
                            'composer':composerlist, 'album':album, 'genre':genre, 'tracknumber':tracknumber, 'length':length,
                            'path':path, 'filename':filename, \
                           })
                if p_suffix: title = '%s%s' % (title, p_suffix)

                title = escape(title)
                artist = escape(artist)
                albumartist = escape(albumartist)
                album = escape(album)
                tracknumber = self.convert_tracknumber(tracknumber)
                count += 1

                if SMAPI != '':

                    if cover == '':
                        coverres = ''
                    elif cover.startswith('EMBEDDED_'):
                        coverres = self.proxyaddress + '/WMPNSSv3/' + dummyfile

                    metadatatype = 'track'
#                    metadata = (aristId, artist, composerId, composer, \
#                                albumId, album, albumArtURI, albumArtistId, \
#                                albumArtist, genreId, genre, duration)

                    # fix WMP urls if necessary
                    res = res.replace(self.webserverurl, self.wmpurl)
                    coverres = coverres.replace(self.webserverurl, self.wmpurl)

                    metadata = ('', artist, '', '', \
                                '', album, coverres, '', \
                                albumartist, '', '', iduration)
                    items += [(id, title, mime, res, 'track', metadatatype, metadata)]

                if (tracks_type == 'ARTIST' or tracks_type == 'GENRE') and \
                   albumtype != 10 and \
                   not_album == False:
                    if albumtype >= 21 and albumtype <= 25:
                        if self.virtual_now_playing_album:
                            album_entry_id = '%sv%s' % (album_entry_id, rowid)
                        if self.virtual_now_playing_artist:
                            artist_entry_id = '%sv%s' % (artist_entry_id, rowid)
                            albumartist_entry_id = '%sv%s' % (albumartist_entry_id, rowid)
                    elif albumtype >= 31 and albumtype <= 35:
                        if self.work_now_playing_album:
                            album_entry_id = '%sw%s' % (album_entry_id, rowid)
                        if self.work_now_playing_artist:

                            artist_entry_id = '%sw%s' % (artist_entry_id, rowid)
                            albumartist_entry_id = '%sw%s' % (albumartist_entry_id, rowid)

                full_id = 'T__%s_%s_%s__%s' % (album_entry_id, artist_entry_id, albumartist_entry_id, str(id))

                ret += '<item id="%s" parentID="%s" restricted="true">' % (full_id, self.track_parentid)
                ret += '<dc:title>%s</dc:title>' % (title)
                ret += '<upnp:artist role="AlbumArtist">%s</upnp:artist>' % (albumartist)
                ret += '<upnp:artist role="Performer">%s</upnp:artist>' % (artist)
                ret += '<upnp:album>%s</upnp:album>' % (album)
                if tracknumber != 0:
                    ret += '<upnp:originalTrackNumber>%s</upnp:originalTrackNumber>' % (tracknumber)
                ret += '<upnp:class>%s</upnp:class>' % (self.track_class)
                ret += '<res duration="%s" protocolInfo="%s">%s</res>' % (duration, protocol, res)
####                ret += '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">%s</desc>' % (self.wmpudn)
#                if cover != '' and not cover.startswith('EMBEDDED_'):
#                    ret += '<upnp:albumArtURI>%s</upnp:albumArtURI>' % (coverres)
                ret += '</item>'
            ret += '</DIDL-Lite>'

            res = ret

        elif containerID == '0' and searchCriteria == 'upnp:class = "object.container.playlistContainer" and @refID exists false' or \
             SMAPI == 'Alphaplaylist' or \
             SMAPI == 'playlist' or \
             browse == 'Playlists':

            # Playlist class

            res  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            count = 0
            parentid = '0'

            searchwhere = ''
            if searchcontainer:
                searchstring = escape_sql(searchstring)
                searchwhere = "where playlist like '%s%%'" % searchstring

            c.execute("select count(distinct plfile) from playlists %s" % searchwhere)
            totalMatches, = c.fetchone()

            statement = "select rowid,* from playlists %s group by plfile order by playlist limit %d, %d" % (searchwhere, startingIndex, requestedCount)

            alphastatement = smapialphastatement % ('playlist', 'playlists %s order by %%s' % searchwhere)

            if SMAPI == 'Alphaplaylist':
#                if not show_separator and chunks == 1:
#                    orderby, prefix, suffix, albumtype, table, header = state_pre_suf[0]
#                    if ',' in orderby: orderby = orderby.split(',')[0]
#                    alphastatement = alphastatement % (orderby)
#                    log.debug(alphastatement)
#                    c.execute(alphastatement)
#                    return c.fetchall()
#                else:
#                    return None
                alphastatement = alphastatement % ('playlist')
                log.debug(alphastatement)
                c.execute(alphastatement)
                return c.fetchall()

            c.execute(statement)
            for row in c:
#                log.debug("row: %s", row)
                rowid, playlist, plid, plfile, trackfile, occurs, track, track_id, track_rowid, inserted, created, lastmodified, plfilecreated, plfilelastmodified, trackfilecreated, trackfilelastmodified, scannumber, lastscanned = row
                id = plid
                parentid = '13'
                if playlist == '': playlist = '[unknown playlist]'
                playlist = escape(playlist)

                if SMAPI != '':
                    playlistidval, browsebyid, containerstart = SMAPIkeys['playlist']
                    items += [(rowid + containerstart, playlist)]

                count += 1
                res += '<container id="%s" parentID="%s" restricted="true">' % (id, parentid)
                res += '<dc:title>%s</dc:title>' % (playlist)
                res += '<upnp:class>%s</upnp:class>' % (self.playlist_class)
                res += '</container>'
            res += '</DIDL-Lite>'

        else:
            # unknown search criteria
            print "proxy_search - unknown search criteria, not supported in code"
            res = ''
            count = 0
            totalMatches = 0

        c.close()
        if not self.proxy.db_persist_connection:
            db.close()

        log.debug("SEARCH res: %s", res)

        log.debug("end: %.3f" % time.time())

#        import traceback
#        traceback.print_stack()

        if source == 'SMAPI':
            return items, totalMatches, startingIndex, 'container'

        return res, count, totalMatches






    def dynamicQuery(self, *args, **kwargs):

        # TODO: fix error conditions (return zero)
        log.debug("Mediaserver.dynamicQuery: %s", kwargs)

        log.debug("start: %.3f" % time.time())

        source = kwargs.get('Source', None)

        controllername = kwargs.get('Controller', '')
        controlleraddress = kwargs.get('Address', '')
        log.debug('Controller: %s' % controllername)
        log.debug('Address: %s' % controlleraddress)

        containerID = kwargs['ContainerID']
        searchCriteria = kwargs['SearchCriteria']
        searchCriteria = self.fixcriteria(searchCriteria)
        log.debug('containerID: %s' % str(containerID))
        log.debug('searchCriteria: %s' % searchCriteria)
        #log.debug('searchCriteria: %s' % searchCriteria.encode(enc, 'replace'))

        SMAPIalpha = kwargs.get('SMAPIalpha', None)
        log.debug('SMAPIalpha: %s' % SMAPIalpha)
        SMAPI = kwargs.get('SMAPI', '')
        log.debug('SMAPI: %s' % SMAPI)

        if SMAPIalpha:
            SMAPIhierarchy = SMAPIalpha.split(':')
        else:
            SMAPIhierarchy = SMAPI.split(':')
        log.debug(SMAPIhierarchy)
        SMAPIkeys = kwargs.get('SMAPIkeys', [])
        log.debug(SMAPIkeys)
        SMAPIfull = kwargs.get('SMAPIfull', [])
        log.debug(SMAPIfull)

        startingIndex = int(kwargs['StartingIndex'])
        requestedCount = int(kwargs['RequestedCount'])

        # browse can be called under the following scenarios:
        #
        # 1) For a root container
        #    - SMAPIhierarchy will contain a single entry
        # 2) For a container further down the hierarchy,
        #    which could be a user defined container
        #    - SMAPIhierarchy will contain a set of entries
        # 3) For alpha keys for a root container
        #    - SMAPIalpha populated with container to use
        # 4) For search of a root container
        #    - SMAPIhierarchy will contain a single entry
        #    - searchCriteria contains the search string
        # 5) For search of a user defined container,
        #    which could be single or multiple containers,
        #    or a container further down the hierarchy
        #    - SMAPIhierarchy will contain a single entry of 'usersearch'
        #    - id passed points to usersearch entry with container details
        #    - searchCriteria contains the search string
        #
        # the table to be queried depends on the scenario. Mostly the table
        # is tracks, but playlists and workvirtuals can also be queried.
        # Note that for user defined indexes the table is actually a list
        # in memory (loaded from the ini)

        log.debug("SMAPI_BROWSE: %s", kwargs)

        # set up return list

        items = []

        # get the default table to query if only a single container is
        # requested and it's not a user defined search

        browsetable = self.get_table(SMAPIhierarchy[-1], SMAPIhierarchy[-1])
        log.debug(browsetable)

        # set the basis of any alpha keys call

        smapialphastatement = """
                                 select count(lower(substr(alpha,1,1))) as count,
                                        lower(substr(alpha,1,1)) as character
                                 from (select %s as alpha from %s)
                                 group by character
                                 order by character
                              """

        # check if search requested
        searchcontainer = None
        if searchCriteria != '':
            searchtype = SMAPIhierarchy[-1]
            log.debug(searchtype)
            searchstring = searchCriteria
            log.debug(searchstring)
            searchcontainer = self.convert_field_name(searchtype)
            log.debug(searchcontainer)

        # set up cursor (note we want to refer to fields by name)
        if self.proxy.db_persist_connection:
            db = self.proxy.db
        else:
            db = sqlite3.connect(self.dbspec)
#        log.debug(db)
#        cs = db.execute("PRAGMA cache_size;")
#        log.debug('cache_size now: %s', cs.fetchone()[0])
        db.row_factory = sqlite3.Row
        c = db.cursor()

        # default where clause
        where = ''

        if SMAPIalpha:
            # process alpha request
            entry = SMAPIalpha
            field = self.convert_field_name(entry.split('_')[0])
            browsetable = self.get_table(field, field)
            alphastatement = smapialphastatement % (field, '%s %s group by %s order by %s' % (browsetable, where, field, field))
            log.debug(alphastatement)
            c.execute(alphastatement)
            return c.fetchall()

        # walk through items in hierarchy, getting SQL keys when id passed
        itemidprefix = None
        indexsuffix = ''
        prevtitle = ''
        for entry in SMAPIhierarchy:
        
            idval, browsebyid, containerstart = SMAPIkeys[entry]
            firstbrowsetype, firstbrowsebyid = self.get_index(idval)
            
            if firstbrowsetype == 'usersearch':
                # save id used
                itemidprefix = ':'.join(filter(None,(itemidprefix, str(idval))))
            
            if firstbrowsetype == 'usersearch' and len(SMAPIhierarchy) != 1:
                # don't process entry if it's a user search key
                # and there are further entries
                continue
            
            field = self.convert_field_name(entry.split('_')[0])
            log.debug(field)

            # don't process for usersearch, and only for id's (not for containers)
            if searchcontainer != 'usersearch' and browsebyid:

                if field in self.user_index_entries.keys():
                    # is a user defined index

                    # set the suffix for the next index entry
                    indexsuffix = idval - containerstart
                    title = field

                else:

                    browsetable = self.get_table(entry, field)

                    keystatement = 'select %s from %s where rowid=%s' % (field, browsetable, idval - containerstart)
                    log.debug(keystatement)
                    c.execute(keystatement)
                    title, = c.fetchone()
                    title = escape_sql(title)
                    log.debug(title)
                    # add keys to where clause
                    if where == '': whereword = 'where'
                    else: whereword = 'and'
                    where = "%s%s %s='%s' " % (where, whereword, field, title)

                # save id's used
                itemidprefix = ':'.join(filter(None,(itemidprefix, str(idval))))

                # save the value of the preceding title for display
                prevtitle = title

        # process last item in hierarchy
        
        user_index = False
        searchtype = ''
        searchname = ''
        if entry.lower() != 'track':

            field = self.convert_field_name(entry.split('_')[0])
            log.debug(field)

            if searchcontainer:
            
                # search is always at root level, or a direct call to a lower level,
                # so where clause will only contain search details

                searchlist = []
                searchparentlist = []
                searchconvertlookup = {}
                searchpositionlookup = {}

                if searchcontainer == 'usersearch':
                    # is a user defined search

                    # get search details
                    # searchtype is 'multi' for multiple containers, or 'lower' for lower level search
                    # searchname is the name displayed in the search entry
                    # searchfields is a list of containerid/containername tuples
                    searchtype, searchname, searchroot, searchfields = self.user_search_entries[idval]
                    log.debug(searchtype)
                    log.debug(searchname)
                    log.debug(searchroot)
                    log.debug(searchfields)
                    if searchtype == 'multi' or searchtype == 'lower':
                        pos = 0
                        for searchfieldparent, searchfield in searchfields:
                            convertedsearchfield = self.convert_field_name(searchfield)
                            searchlist.append(convertedsearchfield)
                            searchparentlist.append(searchfieldparent)
                            searchconvertlookup[convertedsearchfield] = searchfield
                            searchpositionlookup[searchfield] = pos
                            pos += 1
                    # set real field for single entry
                    field = searchlist[0]
                else:
                    # is a default search (so only one entry)
                    searchlist = [field]
                    searchparentlist = [containerstart]

                # compile search where clause for user defined searches
                searchlistwhere = []
                for searchitem in searchlist:

                    if searchitem.lower() == 'year':
                        startyear, endyear = self.get_year_ordinal_range(searchstring)
                        whereentry = '%s between %s and %s' % (searchitem, startyear, endyear)
                    elif searchitem.lower() in ['inserted', 'created', 'lastmodified', 'lastscanned', 'lastplayed']:
                        startyear, endyear = self.get_date_epoch_range(searchstring)
                        whereentry = '%s between %s and %s' % (searchitem, startyear, endyear)
                    else:
                        searchstring = self.translate_dynamic_field(searchitem, searchstring, 'in')
                        newsearchstring = escape_sql(searchstring)
                        whereentry = "%s like '%s%%'" % (searchitem, newsearchstring)
                    log.debug(whereentry)

                    searchlistwhere.append('where %s' % whereentry)
                    # set where for single  entry
                    where = 'where %s' % whereentry

                # compile search where clause for default searches
                if searchcontainer != 'usersearch':
                    where = 'where %s' % whereentry

            # process field(s) passed

            if searchcontainer:
                fieldlist = searchlist
                parentlist = searchparentlist
            else:
                fieldlist = [field]
                parentlist = [containerstart]

            metadata = []
            maxfields = 0
            for fieldentry, containerstart in zip(fieldlist, parentlist):

                origfield = self.convert_field_name_back(fieldentry)

                if searchcontainer and len(searchlist) > 1:
                    # multiple search fields
                    sorttype = '%s_%s%s' % (idval, origfield, indexsuffix)
                elif searchcontainer and searchtype == 'multi':
                    sorttype = '%s_%s%s' % (idval, origfield, indexsuffix)
                elif searchcontainer and searchtype == 'lower':
                    sorttype = '%s_%s%s' % (idval, origfield, indexsuffix)
                else:
                    sorttype = '%s_%s%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1], indexsuffix)

                log.debug(sorttype)

                # get sort data
                rangefield, indexrange, sortorder, entryprefix, entrysuffix, albumtype, sectionalbumtypedummy, sectionalbumnamedummy = self.get_smapi_orderby(sorttype, controllername)

                log.debug(rangefield)
                log.debug(indexrange)
                log.debug(sortorder)
                log.debug(entryprefix)
                log.debug(entrysuffix)

                numprefix = 0
                prefixstart = 0
                prefixes = self.split_sql_fields(entryprefix)
                if entryprefix != '':
                    numprefix = len(prefixes)
                    prefixstart = 3
                numsuffix = 0
                suffixstart = 0
                suffixes = self.split_sql_fields(entrysuffix)
                if entrysuffix != '':
                    numsuffix = len(suffixes)
                    suffixstart = 3 + numprefix
                # TODO: albumtype

                if numprefix + numsuffix > maxfields:
                    maxfields = numprefix + numsuffix

                # save data for this field
                metadata.append((rangefield, indexrange, sortorder, entryprefix, entrysuffix, containerstart,
                                 prefixes, numprefix, prefixstart, suffixes, numsuffix, suffixstart))
                log.debug(metadata)

            log.debug(field)

            if field in self.user_index_entries.keys():
            
                # is a user defined index
                
                user_index = True
                index_entries = self.user_index_entries[field]
                totalMatches = len(index_entries)
                rowid = 1
                for title in index_entries:
                    itemid = rowid + containerstart
                    itemid = ':'.join(filter(None,(itemidprefix, str(itemid))))

                    if numprefix:
                        prefix = self.smapi_makepresuffix([prefixes[0]], self.replace_pre, [prevtitle], 'P')
                        if prefix: title = '%s%s' % (prefix, title)
                    if numsuffix:
                        suffix = self.smapi_makepresuffix([suffixes[0]], self.replace_suf, [prevtitle], 'S')
                        if suffix: title = '%s%s' % (title, suffix)

                    items += [(itemid, escape(title))]
                    rowid += 1

            else:

                if not searchcontainer:

                    # if not search, process any range

                    rangestart, rangeend, units = indexrange
                    log.debug('rangestart: %s' % rangestart)
                    log.debug('rangeend: %s' % rangeend)
                    log.debug('units: %s' % units)
                    if rangestart != '' or rangeend != '':

                        # have been passed a range for the index
                        # we need to convert that to a where clause
                        # and add it to the start of any existing where clause

                        if units == '':
                            # have start and end of range
                            pass
                        elif units in ['days', 'weeks', 'months', 'years']:
                            # have a date
                            if rangestart == 'last':
                                rangelength = int(rangeend) * (-1)
                                log.debug(rangelength)
                                rangeenddate = datetime.datetime.now()
                                log.debug(rangeenddate)
                                if units == 'days':
                                    rangestartdate = rangeenddate+datedelta(days=rangelength)
                                    log.debug(rangestartdate)
                                elif units == 'weeks':
                                    rangestartdate = rangeenddate+datedelta(weeks=rangelength)
                                elif units == 'months':
                                    rangestartdate = rangeenddate+datedelta(months=rangelength)
                                elif units == 'years':
                                    rangestartdate = rangeenddate+datedelta(years=rangelength)
                            elif rangestart == 'first':
                                # don't know first date, will have to find it with query - for now use epoch and today
                                rangestartdate = time.gmtime(0)
                                rangeenddate = datetime.datetime.now()
                            else:
                                # must be a range of dates from last (so we need to swap them round
                                # so that they are chronological)
                                rangestart = int(rangestart) * (-1)
                                rangeend = int(rangeend) * (-1)
                                now = datetime.datetime.now()
                                if units == 'days':
                                    rangestartdate = now+datedelta(days=rangeend)
                                    rangeenddate = now+datedelta(days=rangestart)
                                elif units == 'weeks':
                                    rangestartdate = now+datedelta(weeks=rangeend)
                                    rangeenddate = now+datedelta(weeks=rangestart)
                                elif units == 'months':
                                    rangestartdate = now+datedelta(months=rangeend)
                                    rangeenddate = now+datedelta(months=rangestart)
                                elif units == 'years':
                                    rangestartdate = now+datedelta(years=rangeend)
                                    rangeenddate = now+datedelta(years=rangestart)
                            log.debug('rangestartdate: %s' % rangestartdate)
                            log.debug('rangeenddate: %s' % rangeenddate)

                        # now convert the input so the database understands it

                        if rangefield == '': rangefield = field

                        if rangefield.lower() == 'year':
                            rangestartyear, dummy = self.get_year_ordinal_range(rangestart)
                            dummy, rangeendyear = self.get_year_ordinal_range(rangeend)
                            rangewhere = '%s between %s and %s' % (rangefield, rangestartyear, rangeendyear)
                        elif rangefield.lower() in ['inserted', 'created', 'lastmodified', 'lastscanned', 'lastplayed']:
                            rangestartyear = int(time.mktime(rangestartdate.timetuple()))
                            rangeendyear = int(time.mktime(rangeenddate.timetuple()))
                            rangewhere = '%s between %s and %s' % (rangefield, rangestartyear, rangeendyear)
                        else:
                            rangestartstring = self.translate_dynamic_field(field, rangestart, 'in')
                            rangeendstring = self.translate_dynamic_field(field, rangeend, 'in')
                            rangestartstring = escape_sql(rangestartstring)
                            rangeendstring = escape_sql(rangeendstring)
                            rangewhere = "%s between '%s' and '%s'" % (rangefield, rangestartstring, rangeendstring)

                        log.debug('rangewhere: %s' % rangewhere)

                        # and add it to the start of the where clause

                        if where.startswith('where'):
                            where = 'and %s' % where[5:]
                        where = 'where %s %s' % (rangewhere, where)

                        log.debug('where: %s' % where)

                if searchcontainer and len(searchlist) > 1:

                    # multi container search

                    statement = None
                    countstatement = None
                    unioncount = 1
                    for searchitem, searchwhere, searchmetadata in zip(searchlist, searchlistwhere, metadata):

                        field = searchitem
                        where = searchwhere

                        rangefield, indexrange, sortorder, entryprefix, entrysuffix, containerstart, \
                        prefixes, numprefix, prefixstart, suffixes, numsuffix, suffixstart = searchmetadata

                        selectfield = field
                        if numprefix:
                            selectfield += ',' + entryprefix
                        if numsuffix:
                            selectfield += ',' + entrysuffix

                        # pad out to largest number of fields
                        if numprefix + numsuffix < maxfields:
                            paddingfields = maxfields - numprefix - numsuffix
                            for i in range(paddingfields):
                                selectfield += ',%s' % i

                        groupfield = field
                        if groupfield.lower() in ['inserted', 'created', 'lastmodified', 'lastscanned', 'lastplayed']:
                            groupfield = "date(%s, 'unixepoch')" % groupfield

                        orderfield = field
                        if sortorder:
                            orderfield = sortorder

                        browsetable = self.get_table(field, field)

                        if field.lower() == 'title':
                            singlecountstatement = "select count(*) as total from (select %s from %s %s) '%s'" % (field, browsetable, where, unioncount)
                        else:
                            singlecountstatement = "select count(*) as total from (select %s from %s %s group by %s) '%s'" % (field, browsetable, where, groupfield, unioncount)
                        log.debug(singlecountstatement)

                        countstatement = ' union all '.join(filter(None,(countstatement, singlecountstatement)))
                        log.debug(countstatement)

                        log.debug(field.lower())
                        if field.lower() == 'title':
                            singlestatement = "select 'track' as recordtype, rowid, id, title, artist, album, genre, tracknumber, albumartist, composer, codec, length, path, filename, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, folderartid, trackartid, %s from %s %s order by %s" % (selectfield, browsetable, where, orderfield)
                        else:
                            singlestatement = "select '%s' as recordtype, rowid, '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', %s from %s %s group by %s order by %s" % (field, selectfield, browsetable, where, groupfield, orderfield)
                        log.debug(singlestatement)

                        unionblock = "select * from (%s) '%s'" % (singlestatement, unioncount)
                        log.debug(unionblock)

                        statement = ' union all '.join(filter(None,(statement, unionblock)))
                        log.debug(statement)

                        unioncount += 1
                    statement += ' limit ?, ?'
                    countstatement = 'select sum(total) from (%s)' % countstatement

                else:

                    # single container or single search
                    
#                    log.debug(field)
#                    log.debug(searchtype)
#                    log.debug(numprefix)
#                    log.debug(numsuffix)
#                    log.debug(sortorder)
                    
                    selectfield = field
                    if numprefix:
                        selectfield += ',' + entryprefix
                    if numsuffix:
                        selectfield += ',' + entrysuffix

                    groupfield = field
                    if groupfield.lower() in ['inserted', 'created', 'lastmodified', 'lastscanned', 'lastplayed']:
                        groupfield = "date(%s, 'unixepoch')" % groupfield

                    orderfield = field
                    if sortorder:
                        orderfield = sortorder

                    if searchtype == 'multi':
                        # multi search with single entry - root level search
                        browsetable = self.get_table(field, field)
                    elif searchtype == 'lower':
                        # lower level search, find what else is in the hierarchy
                        searchhierarchy = self.hierarchy_lookup[searchroot]
                        log.debug(searchhierarchy)
                        if 'playlist' in searchhierarchy and field.lower() != 'playlist':
                            browsetable = 'playlists'
                        elif 'work' in searchhierarchy and field.lower() != 'work':
                            browsetable = 'workvirtuals'
                        elif 'virtual' in searchhierarchy and field.lower() != 'virtual':
                            browsetable = 'workvirtuals'
                        else:
                            browsetable = self.get_table(field, field)
                    else:
                        browsetable = self.get_table(field, field)

                    log.debug(browsetable)

                    if browsetable == 'tracks':

                        if field.lower() == 'title':
                        
                            if searchtype != '':
                                countstatement = "select count(%s) from %s %s" % (field, browsetable, where)
                                statement = "select 'track' as recordtype, rowid, id, title, artist, album, genre, tracknumber, albumartist, composer, codec, length, path, filename, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, folderartid, trackartid, %s from %s %s order by %s limit ?, ?" % (selectfield, browsetable, where, orderfield)
                            else:
                                countstatement = "select count(%s) from %s %s" % (field, browsetable, where)
                                statement = "select 'track' as recordtype, rowid, %s from %s %s order by %s limit ?, ?" % (selectfield, browsetable, where, orderfield)
                        else:
                            countstatement = "select count(distinct %s) from %s %s" % (groupfield, browsetable, where)
                            statement = "select '%s' as recordtype, rowid, %s from %s %s group by %s order by %s limit ?, ?" % (field, selectfield, browsetable, where, groupfield, orderfield)

                    elif browsetable == 'playlists':

                        if not sortorder:
                            orderfield = 'track,playlist'

                        # playlists can contain stream entries that are not in tracks, so select with outer join

                        countstatement = '''select count(*) from playlists p left outer join tracks t on t.rowid = p.track_rowid
                                            %s
                                         ''' % (where)

                        statement = '''select 'track' as recordtype, t.rowid as rowid, t.id, title, artist, album, genre, tracknumber, albumartist, composer, codec, length, path, filename, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, folderartid, trackartid, playlist, trackfile, track, track_id, %s from playlists p left outer join tracks t on t.rowid = p.track_rowid
                                       %s order by %s limit ?, ?
                                    ''' % (selectfield, where, orderfield)

                log.debug("count statement: %s", countstatement)
                log.debug("statement: %s", statement)

        else:

            # tracks

            sorttype = '%s_%s%s' % (SMAPIhierarchy[0], SMAPIhierarchy[-1], indexsuffix)
            log.debug(sorttype)
            # get sort data
            rangefield, indexrange, sortorder, entryprefix, entrysuffix, albumtype, sectionalbumtypedummy, sectionalbumnamedummy = self.get_smapi_orderby(sorttype, controllername)
            numprefix = 0
            prefixstart = 0
            prefixes = self.split_sql_fields(entryprefix)
            if entryprefix != '':
                numprefix = len(prefixes)
                prefixstart = 3
            numsuffix = 0
            suffixstart = 0
            suffixes = self.split_sql_fields(entrysuffix)
            if entrysuffix != '':
                numsuffix = len(suffixes)
                suffixstart = 3 + numprefix

            countstatement = "select count(title) from %s %s" % (browsetable, where)
            statement = "select 'track' as recordtype, rowid, id, title, artist, album, genre, tracknumber, albumartist, composer, codec, length, path, filename, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, folderartid, trackartid from %s %s order by discnumber, tracknumber, title limit ?, ?" % (browsetable, where)
            log.debug("countstatement: %s", countstatement)
            log.debug("statement: %s", statement)


#        mediafields = ['id', 'title', 'artist', 'album', 'genre', 'tracknumber', 'albumartist',
#                       'composer', 'codec', 'length', 'path', 'filename', 'folderart', 'trackart',
#                       'bitrate', 'samplerate', 'bitspersample', 'channels', 'mime', 'folderartid', 'trackartid']


        if not user_index:

            c.execute(countstatement)
            totalMatches, = c.fetchone()
            log.debug(totalMatches)

            if totalMatches > 0:

                c.execute(statement, (startingIndex, requestedCount))

                for row in c:

#                    log.debug("row: %s", row)

                    recordtype = row['recordtype']
#                    log.debug(recordtype)
                    if recordtype != 'track':

                        rowid = row['rowid']
#                        log.debug(rowid)
                        if searchcontainer and len(searchlist) > 1:
                            title = row[23]          # field may change, position won't
                        else:
                            title = row[2]
#                        log.debug(title)

                        if searchcontainer:
                            searchfieldtype = recordtype
                            
                            if len(searchlist) > 1:
                                field = searchconvertlookup[searchfieldtype]
                                pos = searchpositionlookup[field]
#                                log.debug(searchfieldtype)
#                                log.debug(field)
#                                log.debug(pos)
                            else:
                                pos = 0

                            rangefield, indexrange, sortorder, entryprefix, entrysuffix, containerstart, \
                            prefixes, numprefix, prefixstart, suffixes, numsuffix, suffixstart = metadata[pos]
#                            log.debug(containerstart)

#                        log.debug(field)

                        title = self.translate_dynamic_field(field, title, 'out')
                        if title == '' or title == None: title = '[unknown %s]' % field
                        if not isinstance(title, basestring):
                            title = str(title)
#                        log.debug(title)
#                        log.debug(numprefix)
#                        log.debug(numsuffix)
#                        log.debug(prefixstart)
#                        log.debug(suffixstart)
#                        log.debug(row.keys())
                        if numprefix:
    #                        prefixdata = list(row[prefixstart:prefixstart+numprefix])
                            prefixdata = []
                            for i in range(numprefix):
                                prefixdata.append(row[prefixstart+i])
                            prefix = self.smapi_makepresuffix(prefixes, self.replace_pre, prefixdata, 'P')
                            if prefix: title = '%s%s' % (prefix, title)
                        if numsuffix:
    #                        suffixdata = list(row[suffixstart:suffixstart+numsuffix])
                            suffixdata = []
                            for i in range(numsuffix):
                                suffixdata.append(row[suffixstart+i])
                            suffix = self.smapi_makepresuffix(suffixes, self.replace_suf, suffixdata, 'S')
                            if suffix: title = '%s%s' % (title, suffix)

                        title = escape(title)
#                        log.debug(title)

                        itemid = rowid + containerstart
                        itemid = ':'.join(filter(None,(itemidprefix, str(itemid))))
                        items += [(itemid, title)]

                    else:   # track

#                        log.debug(row.keys())

                        # field names are taken from first select in union, which varies,
                        # so use positions
                        id = row[2]
                        title = row[3]
                        artist = row[4]
                        album = row[5]
                        genre = row[6]
                        tracknumber = row[7]
                        albumartist = row[8]
                        composer = row[9]
                        codec = row[10]
                        length = row[11]
                        path = row[12]
                        filename = row[13]
                        folderart = row[14]
                        trackart = row[15]
                        bitrate = row[16]
                        samplerate = row[17]
                        bitspersample = row[18]
                        channels = row[19]
                        mime = row[20]
                        folderartid = row[21]
                        trackartid = row[22]

                        if not id:

                            playlist = row[23]
                            pl_trackfile = row[24]
                            pl_track = row[25]
                            pl_track_id = row[26]

                            # playlist entry with no matching track - assume stream
                            mime = 'audio/wav'
                            filename = pl_trackfile
                            path = ''
                            length = 0
                            title = pl_trackfile
                            artistlist = 'Stream'
                            albumartistlist = 'Stream'
                            albumlist = 'Stream'
                            id = pl_track_id
                            titlesort = albumsort = None

                        # TODO: other variable fields

#                        log.debug(title)
#                        log.debug(numprefix)
#                        log.debug(numsuffix)
#                        log.debug(prefixstart)
#                        log.debug(suffixstart)
#                        log.debug(row.keys())
                        
#                        if searchtype == 'multi':
                        if prefixstart < 25:
                            prefixstart += 25
                            suffixstart += 25
                        
                        if numprefix:
#                            prefixdata = list(row[prefixstart:prefixstart+numprefix])
                            prefixdata = []
                            for i in range(numprefix):
                                prefixdata.append(row[prefixstart+i])
                            prefix = self.smapi_makepresuffix(prefixes, self.replace_pre, prefixdata, 'P')
                            if prefix: title = '%s%s' % (prefix, title)
                        if numsuffix:
#                            suffixdata = list(row[suffixstart:suffixstart+numsuffix])
                            suffixdata = []
                            for i in range(numsuffix):
                                suffixdata.append(row[suffixstart+i])
                            suffix = self.smapi_makepresuffix(suffixes, self.replace_suf, suffixdata, 'S')
                            if suffix: title = '%s%s' % (title, suffix)





                        cover, artid = self.choosecover(folderart, trackart, folderartid, trackartid)
                        mime = fixMime(mime)

                        wsfile = filename
                        wspath = os.path.join(path, filename)
                        path = self.convert_path(path)
                        filepath = path + filename
                        filepath = encode_path(filepath)
                        filepath = escape(filepath, escape_entities)
                        protocol = getProtocol(mime)
                        contenttype = mime
                        filetype = getFileType(filename)

                        if SMAPI != '' and source == 'SMAPI':
                            transcode, newtype = checksmapitranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)
                            if transcode:
                                mime = 'audio/mpeg'
                        else:
                            transcode, newtype = checktranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)
                        if transcode:
                            dummyfile = self.dbname + '.' + id + '.' + newtype
                        else:
                            dummyfile = self.dbname + '.' + id + '.' + filetype
                        res = self.proxyaddress + '/WMPNSSv3/' + dummyfile
                        if transcode:
                            log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s\ntranscodetype: %s' % (dummyfile, wsfile, wspath, contenttype, newtype))
                            dummystaticfile = webserver.TranscodedFileSonos(dummyfile, wsfile, wspath, newtype, contenttype, cover=cover)
                            self.proxy.wmpcontroller.add_transcoded_file(dummystaticfile)
                        else:
                            log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s' % (dummyfile, wsfile, wspath, contenttype))
                            dummystaticfile = webserver.StaticFileSonos(dummyfile, wsfile, wspath, contenttype, cover=cover)
                            self.proxy.wmpcontroller.add_static_file(dummystaticfile)

                        if cover != '' and not cover.startswith('EMBEDDED_'):
                            cvfile = getFile(cover)
                            cvpath = cover
                            coverfiletype = getFileType(cvfile)
                            dummycoverfile = self.dbname + '.' + str(artid) + '.' + coverfiletype
                            coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                            dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath)    # TODO: pass contenttype
                            self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)

                        iduration = int(length)
                        duration = maketime(float(length))

                        if artist == '': artist = '[unknown artist]'
                        if albumartist == '': albumartist = '[unknown albumartist]'
                        if album == '': album = '[unknown album]'
                        if title == '': title = '[unknown title]'

                        title = escape(title)
                        artist = escape(artist)
                        albumartist = escape(albumartist)
                        album = escape(album)
                        tracknumber = self.convert_tracknumber(tracknumber)

                        if cover == '':
                            coverres = ''
                        elif cover.startswith('EMBEDDED_'):
                            coverres = self.proxyaddress + '/WMPNSSv3/' + dummyfile

                        metadatatype = 'track'
        #                    metadata = (aristId, artist, composerId, composer, \
        #                                albumId, album, albumArtURI, albumArtistId, \
        #                                albumArtist, genreId, genre, duration)

                        # fix WMP urls if necessary
                        res = res.replace(self.webserverurl, self.wmpurl)
                        coverres = coverres.replace(self.webserverurl, self.wmpurl)

                        metadata = ('', artist, '', '', \
                                    '', album, coverres, '', \
                                    albumartist, '', '', iduration)
                        items += [(id, title, mime, res, 'track', metadatatype, metadata)]

                        # TODO: write XML for track return

        c.close()
        db.row_factory = None
        if not self.proxy.db_persist_connection:
            db.close()

        log.debug("end: %.3f" % time.time())

        if source == 'SMAPI':

            if totalMatches == 0:
                itemtype = 'nothing'    # won't be used
            elif len(items[0]) == 2:
                itemtype = 'container'
            else:
                itemtype = 'track'
            return items, totalMatches, startingIndex, itemtype
            
        else:
        
            ret  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'

            for entry in items:
                if len(entry) == 2:
                    id, title = entry
                    ret += '<container id="%s" parentID="%s" restricted="true">' % (id, containerID)
                    ret += '<dc:title>%s</dc:title>' % (title)
                    ret += '<upnp:class>object.container</upnp:class>'
                    ret += '</container>'
                    # TODO: cover?
                else:
                    id, title, mime, res, upnpclass, metadatatype, metadata = entry
                    d1, artist, d2, d3, d4, album, coverres, d5, albumartist, d6, d7, iduration = metadata

                    ret += '<item id="%s" parentID="%s" restricted="true">' % (id, self.track_parentid)
                    ret += '<dc:title>%s</dc:title>' % (title)
                    ret += '<upnp:artist role="AlbumArtist">%s</upnp:artist>' % (albumartist)
                    ret += '<upnp:artist role="Performer">%s</upnp:artist>' % (artist)
                    ret += '<upnp:album>%s</upnp:album>' % (album)
                    # TODO: add tracknumber
#                    if tracknumber != 0:
#                        ret += '<upnp:originalTrackNumber>%s</upnp:originalTrackNumber>' % (tracknumber)
                    ret += '<upnp:class>%s</upnp:class>' % (self.track_class)
                    ret += '<res duration="%s" protocolInfo="%s">%s</res>' % (iduration, getProtocol(mime), res)
    ####                ret += '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">%s</desc>' % (self.wmpudn)
    #                if cover != '' and not cover.startswith('EMBEDDED_'):
    #                    ret += '<upnp:albumArtURI>%s</upnp:albumArtURI>' % (coverres)
                    ret += '</item>'

            ret += '</DIDL-Lite>'
            count = len(items)
            
            if count == 0: ret = ''

            return ret, count, totalMatches



###########################################################################################################################
###########################################################################################################################
###########################################################################################################################



    def chunker(self, startingIndex, requestedCount, count_chunk, show_separator):

        log.debug("chunker: %d %d %s %s" % (startingIndex, requestedCount, str(count_chunk), show_separator))

        # count_chunk is a list of record count / chunk count pairs
        # e.g. (15, 1)
        #      (77, 3)
        totalgroups = 0
        newtotal = 0
        matches = []
        for cc in count_chunk:
            match, chunks = cc
            if show_separator:
                match += 1
            for i in range(chunks):
                totalgroups += 1
                matches.append(match)
                newtotal += match

        log.debug(matches)

        start = startingIndex
        end = start + requestedCount - 1                # this is inclusive, zero based - so 0 means get the first entry

        grouplimits = []
        startgroup = 0
        endgroup = None
        groupstart = 0
        for i in range(totalgroups):
            groupend = groupstart + matches[i] - 1
            grouplimits.append(groupstart)
            grouplimits.append(groupend)
            if start >= groupstart:
                startgroup = i
            if end <= groupend and endgroup == None:
                endgroup = i
            groupstart += matches[i]
        if endgroup == None:
            endgroup = totalgroups - 1

        log.debug(grouplimits)

        groupdata = []

        displayseparator = False
        groupset = startgroup * 2
        thisgroupstart = grouplimits[groupset]
        thisgroupend = grouplimits[groupset+1]
        if start == thisgroupstart:
            thisgroupstartoffset = 0
            if show_separator:
                displayseparator = True
        else:
            thisgroupstartoffset = start - thisgroupstart
            if show_separator:
                thisgroupstartoffset -= 1
        if endgroup != startgroup:
            thisgroupendoffset = thisgroupend - thisgroupstart
        else:
            if end > thisgroupend:
                end = thisgroupend
            thisgroupendoffset = end - thisgroupstart
        if not show_separator:
            thisgroupendoffset += 1
        groupdata.append((startgroup, thisgroupstartoffset, thisgroupendoffset, displayseparator))

        for j in range(startgroup+1,endgroup-1+1):
            groupset = j * 2
            thisgroupstart = grouplimits[groupset]
            thisgroupend = grouplimits[groupset+1]
            thisgroupstartoffset = 0
            if show_separator:
                displayseparator = True
            thisgroupendoffset = thisgroupend - thisgroupstart
            if not show_separator:
                thisgroupendoffset += 1
            groupdata.append((j, thisgroupstartoffset, thisgroupendoffset, displayseparator))

        if endgroup != startgroup:
            groupset = endgroup * 2
            thisgroupstart = grouplimits[groupset]
            thisgroupend = grouplimits[groupset+1]
            thisgroupstartoffset = 0
            if show_separator:
                displayseparator = True
            if end > thisgroupend:
                end = thisgroupend
            thisgroupendoffset = end - thisgroupstart
            if not show_separator:
                thisgroupendoffset += 1
            groupdata.append((endgroup, thisgroupstartoffset, thisgroupendoffset, displayseparator))

        log.debug(groupdata)

        return groupdata, newtotal

    def proxy_makepresuffix(self, fix, replace, fixdict):
        outfix = ''
        if fix and fix != '':
            fix = fix.replace(' ', '')
            fixes = fix.lower().split(',')
            for fix in fixes:
                if fix in fixdict:
                    if fix == 'lastplayed':
                        lastplayed = fixdict['lastplayed']
                        if lastplayed == '':
                            lastplayed = self.chunk_metadata_empty
                        else:
                            try:
                                lastplayed = float(lastplayed)
                                lastplayed = time.strftime(self.chunk_metadata_date_format, time.gmtime(lastplayed))
                            except TypeError:
                                lastplayed = self.chunk_metadata_empty
                        outfix += replace % lastplayed
                    elif fix == 'playcount':
                        playcount = fixdict['playcount']
                        if playcount == '': playcount = '0'
                        outfix += replace % playcount
                    elif fix == 'year':
                        year = fixdict['year']
                        if year == '':
                            year = self.chunk_metadata_empty
                        else:
                            try:
                                year = datetime.date.fromordinal(year).strftime(self.chunk_metadata_date_format)
                            except TypeError:
                                year = self.chunk_metadata_empty
                        outfix += replace % year
                    elif fix == 'inserted':
                        inserted = fixdict['inserted']
                        if inserted == '':
                            inserted = self.chunk_metadata_empty
                        else:
                            try:
                                inserted = float(inserted)
                                inserted = time.strftime(self.chunk_metadata_date_format, time.gmtime(inserted))
#                                inserted = time.asctime(time.gmtime(inserted))
                            except TypeError:
                                inserted = self.chunk_metadata_empty
                        outfix += replace % inserted
                    elif fix == 'created':
                        created = fixdict['created']
                        if created == '':
                            created = self.chunk_metadata_empty
                        else:
                            try:
                                created = float(created)
                                created = time.strftime(self.chunk_metadata_date_format, time.gmtime(created))
                            except TypeError:
                                created = self.chunk_metadata_empty
                        outfix += replace % created
                    elif fix == 'lastmodified':
                        lastmodified = fixdict['lastmodified']
                        if lastmodified == '':
                            lastmodified = self.chunk_metadata_empty
                        else:
                            try:
                                lastmodified = float(lastmodified)
                                lastmodified = time.strftime(self.chunk_metadata_date_format, time.gmtime(lastmodified))
                            except TypeError:
                                lastmodified = self.chunk_metadata_empty
                        outfix += replace % lastmodified
                    else:
                        # other tags just pass through
                        tag = fixdict[fix]
                        if tag == '': tag = self.chunk_metadata_empty
                        outfix += replace % tag
        return outfix

    def removepresuf(self, title, sourcetable, controllername):
        possibleentries = []
        # strip quotes
        fullentry = title[1:-1]



        # experimental
        # check for prefix and suffix separators
        #  - if present just split on those and ignore sorts entry
        ppos = fullentry.rfind(self.prefix_sep)
        if ppos != -1:
            fullentry = fullentry[ppos+1:]
        spos = fullentry.find(self.suffix_sep)
        if spos != -1:
            fullentry = fullentry[:spos]
        return [fullentry]



        orderbylist = self.get_proxy_orderby(sourcetable, controllername)
        log.debug(orderbylist)
        if orderbylist == [(None, None, None, 10, 'dummy', None)]:
            return [fullentry]
        # process all entries returned and return any that could be valid
        for orderbyentry in orderbylist:
            log.debug(orderbyentry)
            orderby, prefix, suffix, albumtype, table, header = orderbyentry
            numprefixes = 0
            numsuffixes = 0
            if prefix and prefix != '':
                prefixes = prefix.split(',')
                numprefixes = len(prefixes)
            if suffix and suffix != '':
                suffixes = suffix.split(',')
                numsuffixes = len(suffixes)
            numfix = numprefixes + numsuffixes
            log.debug("np: %s, ns: %s, nf: %s" % (numprefixes, numsuffixes, numfix))
            entry = fullentry
            if numfix != 0:
                # check whether the correct number of prefixes and suffixes are present
                # only try to find as many as there should be
                numdelimstarts = 0
                if numprefixes:
                    log.debug("mp: %s" % (self.multi_pre % numprefixes))
                    found = re.search(self.multi_pre % numprefixes, entry)
                    if found:
                        pre_found = found.group(0)
                        log.debug("pf: %s" % pre_found)
                        log.debug("sp: %s" % self.searchre_pre)
                        pfound = re.findall(self.searchre_pre, pre_found)
                        log.debug("ppf: %s" % pfound)
                        numdelimstarts = len(pfound)
                        if numdelimstarts == numprefixes:
                            entry = entry.replace(pre_found, '')
                numdelimends = 0
                if numsuffixes:
                    # TODO: decide whether to reverse string and lookup [::-1]
                    log.debug("ms: %s" % (self.multi_suf % numsuffixes))
                    found = re.search(self.multi_suf % numsuffixes, entry)
                    log.debug(found)
                    if found:
                        suf_found = found.group(0)
                        log.debug("sf: %s" % suf_found)
                        log.debug("ss: %s" % self.searchre_suf)
                        pfound = re.findall(self.searchre_suf, suf_found)
                        log.debug("psf: %s" % pfound)
                        numdelimends = len(pfound)
                        log.debug("nde: %s" % numdelimends)
                        if numdelimends == numsuffixes:
                            log.debug(entry)
                            entry = entry.replace(suf_found, '')
                            log.debug(entry)
                numdelim = numdelimstarts + numdelimends
                log.debug("nds: %s, nde: %s, nd: %s" % (numdelimstarts, numdelimends, numdelim))
                if numprefixes != numdelimstarts or numsuffixes != numdelimends:
                    # no match
                    continue
#            # put quotes back
#            entry = '"%s"' % entry
            entry = entry.strip()
            possibleentries.append(entry)
        # TODO: fix using code to work with multiple returns
        log.debug(possibleentries)
        uniqueentries = []
        for entry in possibleentries:
            if not entry in uniqueentries:
                uniqueentries.append(entry)
        log.debug(uniqueentries)
        return uniqueentries

    def get_entry(self, entrylist, entrytype, combiner):
        entrylist = entrylist.split(MULTI_SEPARATOR)
        if entrytype == 'all':
            return combiner.join(entrylist)
        elif entrytype == 'first':
            return entrylist[0]
        elif entrytype == 'last':
            return entrylist[-1]
        else:
            return entrylist[-1]

    def get_entry_position(self, entry, entrylist, entrytype, combiner):
        if entry == '':
            # nothing passed, so return according to ini
            return self.get_entry(entrylist, entrytype, combiner)
        entrylist = entrylist.split(MULTI_SEPARATOR)
        try:
           inx = entrylist.index(entry)
        except ValueError:
            # shouldn't happen, but return first item position just in case
           inx = 0
        return inx

    def get_entry_at_position(self, position, entrylist):
        entrylist = entrylist.split(MULTI_SEPARATOR)
        try:
           return entrylist[position]
        except IndexError:
            # shouldn't happen, but return first item just in case
           return entrylist[0]

    def prime_cache(self):
        log.debug("prime start: %.3f" % time.time())

        if self.proxy.db_persist_connection:
            db = self.proxy.db
        else:
            db = sqlite3.connect(self.dbspec)
#        log.debug(db)
        c = db.cursor()
        try:
            c.execute("""select * from albums""")
            for row in c:
                r = row
            if self.use_albumartist:
                c.execute("""select * from AlbumartistAlbum""")
                for row in c:
                    r = row
            else:
                c.execute("""select * from ArtistAlbum""")
                for row in c:
                    r = row
        except sqlite3.Error, e:
            print "Error priming cache:", e.args[0]
        c.close()
        if not self.proxy.db_persist_connection:
            db.close()
        log.debug("prime end: %.3f" % time.time())

    '''
    def checkkeys(self, proxy, proxykey, controller, controllerkey):

        proxykeys = proxy.lower().split(',')
        proxykeys = [k.strip() for k in proxykeys]
        proxykeys = [k for k in proxykeys if k != '']
        proxyfound = proxykey.lower() in proxykeys or 'all' in proxykeys

        controllerkeys = controller.lower().split(',')
        controllerkeys = [k.strip() for k in controllerkeys]
        controllerkeys = [k for k in controllerkeys if k != '']
        controllerfound = controllerkey.lower() in controllerkeys or 'all' in controllerkeys

        return proxyfound and controllerfound
    '''

    proxy_simple_keys = [
        'proxyname=',
        'controller=',
        'sort_order=',
        'entry_prefix=',
        'entry_suffix=',
        'active=',
        ]

    proxy_advanced_keys = proxy_simple_keys + [
        'section_sequence=',
        'section_albumtype=',
        'section_name=',
        ]

    proxy_simple_key_dict = {
        'proxyname': 'all',
        'controller': 'all',
        'sort_order': '',
        'entry_prefix': '',
        'entry_suffix': '',
        'active': 'y',
        }

    proxy_advanced_key_dict = proxy_simple_key_dict.copy()
    proxy_advanced_key_dict.update({
        'section_sequence': 1,
        'section_albumtype': 'all',
        'section_name': '',
        })

    indexes = [
        'ARTISTS',
        'ARTIST_ALBUMS',
        'CONTRIBUTINGARTISTS',
        'CONTRIBUTINGARTIST_ALBUMS',
        'ALBUMS',
        'COMPOSERS',
        'COMPOSER_ALBUMS',
        'GENRES',
        'GENRE_ARTISTS',
        'GENRE_ARTIST_ALBUMS',
        'TRACKS',
        'PLAYLISTS',
        ]

    def get_proxy_simple_sorts(self):
        simple_sorts = []
        simple_keys = self.proxy_simple_key_dict.copy()
        processing_index = False
        for line in codecs.open('pycpoint.ini','r','utf-8'):
            line == line.strip().lower()
            if line.endswith('\n'): line = line[:-1]
            if line.startswith('['):
#                log.debug(line)
                if processing_index:
                    if simple_keys != self.proxy_simple_key_dict:
                        simple_sorts.append((index[:-1], simple_keys))
                        simple_keys = self.proxy_simple_key_dict.copy()
                processing_index = False
                if line.endswith(' sort index]') and not line.startswith('[SMAPI'):
                    index = line[1:-12].strip()
                    log.debug(index)
                    if index in self.indexes:
                        processing_index = True
                continue
            if processing_index:
                for key in self.proxy_simple_keys:
                    if line.startswith(key):
                        value = line[len(key):].strip()
                        log.debug("%s - %s" % (key, value))
                        simple_keys[key[:-1]] = value
        if processing_index:
            if simple_keys != self.proxy_simple_key_dict:
                simple_sorts.append((index[:-1], simple_keys))
        return simple_sorts

    def get_advanced_sorts(self):
        advanced_sorts = []
        advanced_keys = self.proxy_advanced_key_dict.copy()
        processing_index = False
        for line in codecs.open('pycpoint.ini','r','utf-8'):
            line == line.strip().lower()
            if line.endswith('\n'): line = line[:-1]
            if line.startswith('[') and (line.endswith(' sort index]') or line.endswith(' sort index section]')):
#                log.debug(line)
                if processing_index:
                    if advanced_keys != self.proxy_advanced_key_dict:
                        advanced_sorts.append((index[:-1], advanced_keys, processing_index))
                        advanced_keys = self.proxy_advanced_key_dict.copy()
                index = line[1:].split(' ')[0].strip()
#                log.debug(index)
                if line.endswith(' sort index]'): blocktype = 'index'
                else: blocktype = 'section'
                if index in self.indexes:
                    processing_index = blocktype
                else:
                    processing_index = None
                continue
            if processing_index:
                for key in self.proxy_advanced_keys:
                    if line.startswith(key):
                        value = line[len(key):].strip()
                        # convert any numbers to int
                        if type(advanced_keys[key[:-1]]) == int:
                            try:
                                value = int(value)
                            except:
                                pass
                        # adjust virtual and work to album if specified for sort_order
                        if key == 'sort_order=':
                            if value == 'work' or value == 'virtual':
                                value = 'album'
                        advanced_keys[key[:-1]] = value
        if processing_index:
            if advanced_keys != self.proxy_advanced_key_dict:
                advanced_sorts.append((index[:-1], advanced_keys, processing_index))

        # remove any entries that have section entries as they are overridden
        # (make sure they are for the same controller and proxy

        # get indexes that have sections
        sectionindexes = {}
        for (index, keys, blocktype) in advanced_sorts:
            if blocktype == 'section':
                sectionindexes[index] = keys
        # filter entry list
        filtered_sorts = []
        for (index, keys, blocktype) in advanced_sorts:
            if index in sectionindexes and not blocktype == 'section':
                if keys['proxyname'] == sectionindexes[index]['proxyname'] and keys['controller'] == sectionindexes[index]['controller']:
                    continue
            filtered_sorts.append((index, keys))

        return filtered_sorts

    def get_proxy_orderby(self, sorttype, controller):

        if self.alternative_index_sorting == 'N':

            at = self.get_possible_albumtypes(sorttype)
            return [(None, None, None, at, 'dummy', None)]

        elif self.alternative_index_sorting == 'S':

            changedsorttype = sorttype
            if sorttype == 'ALBUMARTIST': changedsorttype = 'ARTIST'
            elif sorttype == 'ALBUMARTIST_ALBUM': changedsorttype = 'ARTIST_ALBUM'
            elif sorttype == 'GENRE_ALBUMARTIST_ALBUM': changedsorttype = 'GENRE_ARTIST_ALBUM'
            elif sorttype == 'GENRE_ALBUMARTIST': changedsorttype = 'GENRE_ARTIST'
            elif sorttype == 'GENRE_AA': changedsorttype = 'GENRE_A'

            proxyfound = False
            controllerfound = False
            bothfound = False
            foundvalues = None
            for (index, values) in self.simple_sorts:
#                log.debug(index)
#                log.debug(values)
                if changedsorttype == index and values['active'] == 'y':
                    # precedence is proxy-and-controller/proxy/controller/neither
                    if values['proxyname'] == self.proxy.proxyname and controller.startswith(values['controller']) and not bothfound:
                        bothfound = True
                        foundvalues = values
                    elif values['proxyname'] == self.proxy.proxyname and values['controller'] == 'all' and not bothfound and not proxyfound:
                        proxyfound = True
                        foundvalues = values
                    elif values['proxyname'] == 'all' and controller.startswith(values['controller']) and not bothfound and not proxyfound and not controllerfound:
                        controllerfound = True
                        foundvalues = values
                    elif values['proxyname'] == 'all' and values['controller'] == 'all' and \
                         not bothfound and not proxyfound and not controllerfound and not foundvalues:
                        foundvalues = values
            at = self.get_possible_albumtypes(sorttype)
            log.debug(at)
            if not foundvalues:
                return [(None, None, None, at, 'dummy', None)]
            else:
                # convert any artist/albumartist entries
                foundvalues = self.convert_artist(foundvalues)
                return [(foundvalues['sort_order'], foundvalues['entry_prefix'], foundvalues['entry_suffix'], at, 'dummy', None)]

        else:   # must be 'A(dvanced)'

            changedsorttype = sorttype
            if sorttype == 'ALBUMARTIST': changedsorttype = 'ARTIST'
            elif sorttype == 'ALBUMARTIST_ALBUM': changedsorttype = 'ARTIST_ALBUM'
            elif sorttype == 'GENRE_ALBUMARTIST_ALBUM': changedsorttype = 'GENRE_ARTIST_ALBUM'
            elif sorttype == 'GENRE_ALBUMARTIST': changedsorttype = 'GENRE_ARTIST'
            elif sorttype == 'GENRE_AA': changedsorttype = 'GENRE_A'

            bothvalues = []
            proxyvalues = []
            controllervalues = []
            neithervalues = []
            for (index, values) in self.advanced_sorts:
#                log.debug(index)
#                log.debug(values)
                if changedsorttype == index and values['active'] == 'y':
                    # precedence is proxy-and-controller/proxy/controller/neither
                    if values['proxyname'] == self.proxy.proxyname and controller.startswith(values['controller']):
                        bothfound = True
                        bothvalues.append(values)
                    elif values['proxyname'] == self.proxy.proxyname and values['controller'] == 'all':
                        proxyfound = True
                        proxyvalues.append(values)
                    elif values['proxyname'] == 'all' and controller.startswith(values['controller']):
                        controllerfound = True
                        controllervalues.append(values)
                    elif values['proxyname'] == 'all' and values['controller'] == 'all':
                        neithervalues.append(values)
#            log.debug(bothvalues)
#            log.debug(proxyvalues)
#            log.debug(controllervalues)
#            log.debug(neithervalues)
            if bothvalues: return self.get_orderby_values(sorttype, bothvalues)
            elif proxyvalues: return self.get_orderby_values(sorttype, proxyvalues)
            elif controllervalues: return self.get_orderby_values(sorttype, controllervalues)
            elif neithervalues: return self.get_orderby_values(sorttype, neithervalues)
            else:
                at = self.get_possible_albumtypes(sorttype)
                log.debug(at)
                return [(None, None, None, at, 'dummy', None)]

    def convert_artist(self, valuedict):
        newvaluedict = {}
        for key, value in valuedict.iteritems():
            if key.lower() in ['sort_order', 'entry_prefix', 'entry_suffix']:
                entries = value.split(',')
                entries = [s.strip().lower() for s in entries]
                if self.use_albumartist:
                    if 'artist' in entries:
                        newentries = []
                        for e in entries:
                            if e == 'artist': e = 'albumartist'
                            newentries += [e]
                        value = ','.join(newentries)
                else:
                    if 'albumartist' in entries:
                        newentries = []
                        for e in entries:
                            if e == 'albumartist': e = 'artist'
                            newentries += [e]
                        value = ','.join(newentries)
            newvaluedict[key] = value
        return newvaluedict

    def get_orderby_values(self, sorttype, values):
        values.sort(key=operator.itemgetter('section_sequence'))
        orderbyvalues = []
        for valueset in values:
            at = self.get_possible_albumtypes(sorttype, filteralbum=valueset['section_albumtype'])
            log.debug(at)
            log.debug(valueset)
            valueset = self.convert_artist(valueset)
            orderbyvalues.append((valueset['sort_order'], valueset['entry_prefix'], valueset['entry_suffix'], at, valueset['section_albumtype'], valueset['section_name']))
        return orderbyvalues

    def translate_albumtype(self, albumtype, table):
        if not albumtype or albumtype == '':
            return '10', 'album'
        elif albumtype == 'album':
            return '10', albumtype
        elif albumtype == 'virtual':
            if table == 'ALBUM':
                return '21', albumtype
            elif table == 'ARTIST_ALBUM' or table == 'ARTIST' or table == 'GENRE_ARTIST_ALBUM' or table == 'GENRE_ARTIST' or table == 'GENRE_A':
                return '22', albumtype
            elif table == 'ALBUMARTIST_ALBUM' or table == 'ALBUMARTIST' or table == 'GENRE_ALBUMARTIST_ALBUM' or table == 'GENRE_ALBUMARTIST' or table == 'GENRE_AA':
                return '23', albumtype
            elif table == 'CONTRIBUTINGARTIST_ALBUM' or table == 'CONTRIBUTINGARTIST':
                return '24', albumtype
            elif table == 'COMPOSER_ALBUM' or table == 'COMPOSER':
                return '25', albumtype
        elif albumtype == 'work':
            if table == 'ALBUM':
                return '31', albumtype
            elif table == 'ARTIST_ALBUM' or table == 'ARTIST' or table == 'GENRE_ARTIST_ALBUM' or table == 'GENRE_ARTIST' or table == 'GENRE_A':
                return '32', albumtype
            elif table == 'ALBUMARTIST_ALBUM' or table == 'ALBUMARTIST' or table == 'GENRE_ALBUMARTIST_ALBUM' or table == 'GENRE_ALBUMARTIST' or table == 'GENRE_AA':
                return '33', albumtype
            elif table == 'CONTRIBUTINGARTIST_ALBUM' or table == 'CONTRIBUTINGARTIST':
                return '34', albumtype
            elif table == 'COMPOSER_ALBUM' or table == 'COMPOSER':
                return '35', albumtype
        else:
            return '10', 'album'

    def get_possible_albumtypes(self, table, filteralbum=None):
        if not filteralbum:
            album = virtual = work = True
        else:
            if 'all' in filteralbum:
                album = virtual = work = True
            else:
                album = virtual = work = False
                if 'album' in filteralbum: album = True
                if 'virtual' in filteralbum: virtual = True
                if 'work' in filteralbum: work = True
        if album:
            at = [10]
        else:
            at = []
        if table == 'ALBUM':
            if self.display_virtuals_in_album_index and virtual: at.append(21)
            if self.display_works_in_album_index and work: at.append(31)
        elif table == 'ARTIST_ALBUM' or table == 'ARTIST' or table == 'GENRE_ARTIST_ALBUM' or table == 'GENRE_ARTIST' or table == 'GENRE_A':
            if self.display_virtuals_in_artist_index and virtual: at.append(22)
            if self.display_works_in_artist_index and work: at.append(32)
        elif table == 'ALBUMARTIST_ALBUM' or table == 'ALBUMARTIST' or table == 'GENRE_ALBUMARTIST_ALBUM' or table == 'GENRE_ALBUMARTIST' or table == 'GENRE_AA':
            if self.display_virtuals_in_artist_index and virtual: at.append(23)
            if self.display_works_in_artist_index and work: at.append(33)
        elif table == 'CONTRIBUTINGARTIST_ALBUM' or table == 'CONTRIBUTINGARTIST':
            if self.display_virtuals_in_contributingartist_index and virtual: at.append(24)
            if self.display_works_in_contributingartist_index and work: at.append(34)
        elif table == 'COMPOSER_ALBUM' or table == 'COMPOSER':
            if self.display_virtuals_in_composer_index and virtual: at.append(25)
            if self.display_works_in_composer_index and work: at.append(35)
        return at

    def get_albumtype_where(self, albumtypes, table=None):
        if table:
            table = '%s.' % table
        else:
            table = ''
        if len(albumtypes) == 1:
            return '%salbumtype=%s' % (table, albumtypes[0])
        else:
            return '%salbumtype in (%s)' % (table, ','.join(str(t) for t in albumtypes))

    def get_containerupdateid(self):
        # get containerupdateid from db
        if self.proxy.db_persist_connection:
            db = self.proxy.db
        else:
            db = sqlite3.connect(self.dbspec)
#        log.debug(db)
        c = db.cursor()
        statement = "select lastscanid from params where key = '1'"
#        log.debug("statement: %s", statement)
        c.execute(statement)
        new_updateid, = c.fetchone()
        new_updateid = int(new_updateid)
        updated = False
        if new_updateid != self.containerupdateid:
            updated = True
            self.containerupdateid = new_updateid
        c.close()
        if not self.proxy.db_persist_connection:
            db.close()

        return updated, self.containerupdateid

    def set_containerupdateid(self):
        # set containerupdateid
        if self.proxy.db_persist_connection:
            db = self.proxy.db
        else:
            db = sqlite3.connect(self.dbspec)
#        log.debug(db)
        c = db.cursor()

        statement = "update params set lastscanid = lastscanid + 1 where key = '1'"
        log.debug("statement: %s", statement)
        c.execute(statement)
        db.commit()
        statement = "select lastscanid from params where key = '1'"
        log.debug("statement: %s", statement)
        c.execute(statement)
        new_updateid, = c.fetchone()
        new_updateid = int(new_updateid)

        updated = False
        if new_updateid != self.containerupdateid:
            updated = True
            self.containerupdateid = new_updateid
        c.close()
        if not self.proxy.db_persist_connection:
            db.close()

        return updated, self.containerupdateid

    # this method not used at present - NOTE THAT systemupdateid IS A PROXY VARIABLE NOW, NOT HERE
    def inc_playlistupdateid(self):
        # increment and event playlistupdateid, incrementing and eventing systemupdateid too
        self.systemupdateid += 1
        updateid1 = '10,%s' % (self.systemupdateid)
        self._state_variables['ContainerUpdateIDs'].update(updateid1)
        self._state_variables['SystemUpdateID'].update(self.systemupdateid)
        log.debug("ContainerUpdateIDs value: %s" % self._state_variables['ContainerUpdateIDs'].get_value())
        self.systemupdateid += 1
        updateid2 = '11,%s' % (self.systemupdateid)
        self.systemupdateid += 1
        updateid3 = '13,%s' % (self.systemupdateid)
        self.systemupdateid += 1
        updateid4 = 'F,%s' % (self.systemupdateid)
        updateid = '%s,%s,%s' % (updateid2, updateid3, updateid4)
        self.playlistupdateid = self.systemupdateid
        self._state_variables['ContainerUpdateIDs'].update(updateid)
        self._state_variables['SystemUpdateID'].update(self.systemupdateid)
        log.debug("ContainerUpdateIDs value: %s" % self._state_variables['ContainerUpdateIDs'].get_value())

    def fixcriteria(self, criteria):
        criteria = criteria.replace('\\"', '"')
        criteria = criteria.replace('\\\\', '\\')
        return criteria

    def convert_path(self, path):
        filepath = path
        if self.pathreplace != None:
            filepath = filepath.replace(self.pathbefore, self.pathafter)
        if os.sep == '/':
            filepath = filepath.replace('\\', '/')
        else:
            filepath = filepath.replace('/', '\\')
        return filepath

    def convert_tracknumber(self, tracknumber):
        newtracknumber = tracknumber
        if type(newtracknumber) == unicode: newtracknumber = 0
        return newtracknumber

    def process_dummy_album(self, album):
        # note - album has double quotes round it
        dupmatch = re.search(' \(\d+\)"$', album)
        if not dupmatch:
            return album, None
        try:
            dupstring = dupmatch.group(0)
            dup = dupstring.strip()[1:-2]
            newalbum = album[0:-len(dupstring)] + '"'
        except:
            return album, None
        return newalbum, dup

    def choosecover(self, folderart, trackart, folderartid, trackartid, coverart=None, coverartid=0):
#        log.debug(folderart)
#        log.debug(trackart)
#        log.debug(folderartid)
#        log.debug(trackartid)
#        log.debug(coverart)
#        log.debug(coverartid)
        try:
            if coverart and coverart != '' and self.prefer_folderart:
                cover = coverart
                artid = coverartid
            elif folderart and folderart != '' and self.prefer_folderart:
                cover = folderart
                artid = folderartid
            elif trackart and trackart != '':
                cover = trackart
                artid = trackartid
            else:
                cover = ''
                artid = ''
        except Exception, e:
            log.debug(e)
#        log.debug('cover: %s  id: %s' % (cover, artid))
        return cover, artid










# converted after here


    def get_smapi_orderby(self, sorttype, controller, proxy=False):

        if self.smapi_alternative_index_sorting == 'N':

            at = self.get_possible_albumtypes(sorttype)

            if proxy: return [(None, None, None, at, 'dummy', None)]
            else: return ('', ('','',''), '', '', '', at, 'dummy', '')

        else:

            controller = controller.lower()

            proxyfound = False
            controllerfound = False
            bothfound = False
            foundvalues = None

            for (index, values) in self.smapi_simple_sorts:
#                log.debug(index)
#                log.debug(values)
                if sorttype == index and values['active'] == 'y':
                    # precedence is proxy-and-controller/proxy/controller/neither
                    if values['smapiname'] == self.proxy.proxyname and controller.startswith(values['controller']) and not bothfound:
                        bothfound = True
                        foundvalues = values
                    elif values['smapiname'] == self.proxy.proxyname and values['controller'] == 'all' and not bothfound and not proxyfound:
                        proxyfound = True
                        foundvalues = values
                    elif values['smapiname'] == 'all' and controller.startswith(values['controller']) and not bothfound and not proxyfound and not controllerfound:
                        controllerfound = True
                        foundvalues = values
                    elif values['smapiname'] == 'all' and values['controller'] == 'all' and \
                         not bothfound and not proxyfound and not controllerfound and not foundvalues:
                        foundvalues = values
            at = self.get_possible_albumtypes(sorttype)
            if not foundvalues:
                if proxy: return [(None, None, None, at, 'dummy', None)]
                else: return ('', ('','',''), '', '', '', at, 'dummy', '')
            else:
                # convert any artist/albumartist entries
                foundvalues = self.convert_artist(foundvalues)
                if proxy:
                    return [(foundvalues['sort_order'], foundvalues['entry_prefix'], foundvalues['entry_suffix'], at, 'dummy', None)]
                else:
                    return (foundvalues['range_field'], foundvalues['index_range'], foundvalues['sort_order'], foundvalues['entry_prefix'], foundvalues['entry_suffix'], at, 'dummy', '')

    def smapi_makepresuffix(self, fixes, replace, fixdata, ps):
        log.debug(fixes)
        log.debug(replace)
        log.debug(fixdata)
    
        EMPTY = '__EMPTY__'
        outfix = ''
        if fixes and fixes != []:
            fixcount = 0
            for fix in fixes:
                data = fixdata[fixcount]
                if fix in ['lastplayed', 'inserted', 'created', 'lastmodified', 'lastscanned', 'lastplayed']:
                    if data == '' or data == 0:
                        data = EMPTY
                    else:
                        try:
                            data = float(data)
                            data = time.strftime(self.chunk_metadata_date_format, time.gmtime(data))
                        except TypeError:
                            data = EMPTY
                elif fix == 'playcount':
                    if data == '': data = '0'
                elif fix == 'year':
                    if data == '':
                        data = EMPTY
                    else:
                        try:
                            data = datetime.date.fromordinal(data).strftime(self.chunk_metadata_date_format)
                        except TypeError:
                            data = EMPTY
                else:
                    if data == '': data = EMPTY

                if data == EMPTY and ps == 'P' and self.dont_display_separator_for_empty_prefix == False:
                    pass
                elif data == EMPTY and ps == 'S' and self.dont_display_separator_for_empty_suffix == False:
                    pass
                else:
                    if data == EMPTY: data = self.chunk_metadata_empty
                    outfix += replace % data
                fixcount += 1
        return outfix

    def get_index(self, objectIDval):
        parent = self.get_parent(objectIDval)
        browsebyid = False
        if parent != objectIDval: browsebyid = True
        browsetype = self.containername[parent]
        return browsetype, browsebyid

    def get_parent(self, objectid):
        return self.id_length * int(objectid / self.id_length)

    def get_table(self, container, field):
        # work out which table is being queried
        if container == 'usersearch':
            container = field
        if container.lower() == 'playlist':
            browsetable = 'playlists'
        elif container.lower() in ['work', 'virtual']:
            browsetable = 'workvirtuals'
        else:
            browsetable = 'tracks'
        return browsetable

    field_names = {
        'track': 'title'
    }

    def convert_field_name(self, field):
        return self.field_names.get(field, field)

    field_names_back = {
        'title': 'track'
    }

    def convert_field_name_back(self, field):
        return self.field_names_back.get(field, field)

    def split_sql_fields(self, fields):
        count = 0
        out = ''
        for c in fields:
            if c == '(': count += 1
            elif c == ')': count -= 1
            if c == ',' and count == 0:
                out += '_|_'
            else:
                out += c
        return out.split('_|_')

    def translate_dynamic_field(self, field, title, direction):
        if field.lower() == 'year':
            if direction == 'out':
                title = self.convert_year_out(title)
            else:
                title = self.convert_year_in(title)
        elif field.lower() in ['created', 'lastmodified', 'inserted']:
            if direction == 'out':
                title = self.convert_date_out(title)
            else:
                title = self.convert_date_in(title)
        return title

    def convert_year_out(self, ordinal):
        # convert ordinal date to year
        try:
            year = datetime.date.fromordinal(ordinal).year
        except Exception:
            year = ''
        return year

    def convert_year_in(self, year):
        # convert year to ordinal date
        yeardate = datetime.date(int(year), DEFAULTMONTH, DEFAULTDAY)
        ordinal = yeardate.toordinal()
        return ordinal

    def convert_date_out(self, date):
        # convert date to string
#        date = float(date)
        sdate = time.strftime(self.smapi_date_format, time.gmtime(date))
        return sdate

    def convert_date_in(self, sdate):
        # convert string to date
        date = time.strptime(sdate, self.smapi_date_format)
        return date

    zeros = '000'
    nines = '999'

    def get_year_ordinal_range(self, year):
        # assumes year is int
        syear = str(year)
        lenyear = len(syear)
        if lenyear <= 4:
            startyear = syear + self.zeros[:4-lenyear]
            endyear = syear + self.nines[:4-lenyear]
            startyear = self.convert_year_in(int(startyear))
            endyear = self.convert_year_in(int(endyear))
            return startyear, endyear

    D1 = datetime.datetime(1, 1, 1)
    D2 = datetime.datetime(2, 2, 2)
    months = [31,28,31,30,31,30,31,31,30,31,30,31]

    def get_date_epoch_range(self, sdate):
        # assumes sdate is string
        # parse passed date
        try:
            # need to work out which facets were input
            pd1 = parsedate(sdate, default=self.D1)
            pd2 = parsedate(sdate, default=self.D2)
            year = month = day = 0
            if pd1.year == pd2.year:
                year = pd1.year
            if pd1.month == pd2.month:
                month = pd1.month
            if pd1.day == pd2.day:
                day = pd1.day
            if year == 0:
                syear = 1000
                eyear = 2999
            else:
                syear = eyear = year
            if month == 0:
                smonth = 1
                emonth = 12
            else:
                smonth = emonth = month
            if day == 0:
                sday = 1
                eday = self.months[emonth - 1]  # TODO: fix for leap years
            else:
                sday = eday = day
            try:
                sdate = datetime.date(syear, smonth, sday)
                edate = datetime.date(eyear, emonth, eday)
            except Exception:
                sdate = 0
                edate = datetime.datetime.now()
        except Exception:
            # don't really care why parsedate failed
            sdate = 0
            edate = datetime.datetime.now()
        if sdate == 0: startdate = 0
        else: startdate = time.mktime(sdate.timetuple())
        enddate = time.mktime(edate.timetuple()) + 86399

        return int(startdate), int(enddate)

    def get_delim(self, delimname, default, special, when=None, section=None):
        delimsection = 'index entry extras'
        if section: delimsection = section
        delim = default
        try:
            delim = self.proxy.config.get(delimsection, delimname)
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        if delim.startswith("'") and delim.endswith("'"):
            delim = delim[1:-1]
        delim = unicode(delim)
        delim = delim.replace(' ', special)
        if when:
            if when == 'before':
                if delim[0] != special:
                    delim = '%s%s' % (special, delim)
            elif when == 'after':
                if delim[-1] != special:
                    delim = '%s%s' % (delim, special)
        delim2 = re.escape(delim)
        return delim2, delim

    def debugout(self, label, data):
        if isinstance(data, dict):
            log.debug('%s:' % (label))
            for k,v in data.iteritems():
                log.debug('    %s: %s' % (k, v))
        elif isinstance(data, (list, tuple, set, frozenset)):
            log.debug('%s:' % (label))
            for v in data:
                log.debug('    %s' % repr(v))
        else:
            log.debug('%s: %s' % (label, data))


#################
#################
# generic helpers
#################
#################

def encode_path(path):
    filepath = path
    filepath = filepath.replace('&', '__amp__')
    filepath = filepath.replace('=', '__equals__')
    filepath = filepath.replace('-', '__minus__')
    filepath = filepath.replace('+', '__plus__')
    filepath = filepath.replace("'", '__apos__')
    return filepath

def unencode_path(path):
    filepath = path
    filepath = filepath.replace('__amp__', '&')
    filepath = filepath.replace('__equals__', '=')
    filepath = filepath.replace('__minus__', '-')
    filepath = filepath.replace('__plus__', '+')
    filepath = filepath.replace('__apos__', "'")
    return filepath

def fixcolonequals(clist):
    cdict = {}
    for n,v in clist:
        if v.find('=') != -1:
            cat = n + ':' + v
            scat = cat.split('=')
            n = scat[0]
            v = scat[1]
        n = n.replace('__colon__', ':')
        n = n.replace('__equals__', '=')
        v = v.replace('__colon__', ':')
        v = v.replace('__equals__', '=')
        cdict[n] = v
    return cdict

def maketime(seconds):
    if int(seconds) == 0:
        return "00:00:00.000"
    h = int(seconds / 3600)
    seconds -= h * 3600
    m = int(seconds / 60)
    seconds -= m * 60
    s = seconds
    return '%d:%02d:%02d.000' % (h,m,s)

def fixMime(mime):
    if mime == 'audio/x-flac':
        mime = 'audio/flac'
    elif mime == 'audio/vorbis':
        mime = 'application/ogg'
    elif mime == 'audio/mp3':
        mime = 'audio/mpeg'
    return mime

def getProtocol(mime):
    return 'http-get:*:%s:*' % mime
#    return 'http-get:*:%s:%s' % (mime, 'DLNA.ORG_PN=MP3;DLNA.ORG_OP=01;DLNA.ORG_CI=0')

def getFileType(filename):
    return filename.split('.')[-1]

def getFile(path):
    return path.split(os.sep)[-1]

def escape_sql(sql):
    if isinstance(sql, basestring):
        sql = sql.replace("'", "''")
    return sql

escape_entities = {'"' : '&quot;', "'" : '&apos;', " " : '%20'}
escape_entities_quotepos = {'"' : '&quot;', "'" : '&apos;'}
unescape_entities = {'&quot;' : '"', '&apos;' : "'", '%20' : " ", '&amp;' : "&"}
unescape_entities_quotepos = {'&quot;' : '"', '&apos;' : "'"}

