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
import string
from operator import itemgetter

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

DEFAULTINDEX_INI = 'defaultindex.ini'
USERINDEX_INI = 'userindex.ini'
PYCPOINT_INI = 'pycpoint.ini'

class MediaServer(object):

    # constants

    noitemsfound = 'No items found'
    enterkeywords = 'Enter keywords...'
#    keywordsearchdelimiter = '===== %s ====='
    novalidkeywords = 'No valid keywords specified.'

    id_length     = 100000000
    id_range      = 99999999
    half_id_start = 50000000

    user_parentid               = 000000000
    artist_parentid             = 100000000
    albumartist_parentid        = 200000000
    album_parentid              = 300000000
    composer_parentid           = 400000000
    genre_parentid              = 500000000
    genre_albumartist_parentid  = 600000000
    genre_artist_parentid       = 600000000
    track_parentid              = 700000000
    playlist_parentid           = 800000000
    favourite_parentid          = 900000000
    favouritetrack_parentid    = 1000000000
    keywordsearch_parentid     = 1100000000
    dynamic_parentid_start     = 1200000000
    
    # default values, overriden by caller if required

    containerstart = {
                      'album':               album_parentid,
                      'albumartist':         albumartist_parentid,
                      'artist':              artist_parentid,
                      'composer':            composer_parentid,
                      'favourite':           favourite_parentid,
                      'genre':               genre_parentid,
                      'playlist':            playlist_parentid,
                      'track':               track_parentid,
                      'usersearch':          user_parentid,
                     }

    statichierarchy = {
                       'album':               'track',
                       'albumartist':         'album',
                       'artist':              'album',
                       'composer':            'album',
                       'playlist':            'track',
                       'track':               'leaf',
                      }

    tracktypes = [
                  favouritetrack_parentid,  # Favourite track
                  track_parentid,           # Track
                 ]
    
    '''
    flatrootitems = [
                     ('%s' % album_parentid, 'Albums'),
                     ('%s' % albumartist_parentid, 'Artists'),
                     ('%s' % composer_parentid, 'Composers'),
                     ('%s' % artist_parentid, 'Contributing Artists'),
                     ('%s' % genre_parentid, 'Genres'),
                     ('%s' % playlist_parentid, 'Playlists'),
                     ('%s' % track_parentid, 'Tracks'),
                    ]
    '''

    # alpha statement for SMAPI

    smapialphastatement = """
                             select count(lower(substr(alpha,1,1))) as count,
                                    lower(substr(alpha,1,1)) as character
                             from (select %s as alpha from %s)
                             group by character
                             order by character
                          """

    # UPNP classes

    artist_class = 'object.container.person.musicArtist'
    album_class = 'object.container.album.musicAlbum'
    composer_class = 'object.container.person.musicArtist'
    genre_class = 'object.container.genre.musicGenre'
    track_class = 'object.item.audioItem.musicTrack'
    playlist_class = 'object.container.playlistContainer'

    # default key settings for alternative indexes
    
    default_index_key_dict = {
        'proxyname': 'all',
        'servicename': 'all',
        'controller': 'all',
        'sort_order': '',
        'entry_prefix': '',
        'entry_suffix': '',
        'active': 'y',
        }

    range_index_key_dict = {
        'range_field': '',
        'index_range': ('','',''),
        }

    user_index_key_dict = default_index_key_dict.copy()
    user_index_key_dict.update(range_index_key_dict)

    ######
    # init
    ######

    def __init__(self, proxy, dbspec, source, structure, proxyaddress, webserverurl, wmpurl, ininame):

        log.debug('MediaServer.__init__ structure: %s' % structure)
        log.debug('MediaServer.__init__ instance: %s' % self)

        self.proxy = proxy
        self.dbspec = dbspec
        dbpath, self.dbname = os.path.split(dbspec)
        self.source = source
        self.structure = structure
        self.proxyaddress = proxyaddress
        self.webserverurl = webserverurl
        self.wmpurl = wmpurl
        self.ininame = ininame

        self.load_ini()

        log.debug('MediaServer.__init__ structure now: %s' % self.structure)

        self.prime_cache()

        self.containerupdateid = 0
        self.playlistupdateid = 0

    ################
    # ini processing
    ################

    def load_ini(self):

        # the user can set 2 options in the pycpoint ini to affect
        # how indexing operates:
        #
        #    alternative_indexing - allows the user to change
        #                           what is displayed in the 
        #                           default indexes
        #         
        #    user_indexes - allows the user to define
        #                   alternative indexes to the default
        #                   ones, and set what is displayed
        #
        # Currently user_indexes is passed into the Mediaserver
        # via the structure parameter - the Proxy converts
        # user_indexes as follows:
        #
        #    user_indexes = N : structure = HIERARCHY_DEFAULT
        #
        #    user_indexes = Y : structure = HIERARCHY
        #
        # (this is because we may decide in the future to 
        # offer different options for the Proxy and the Service)
        #
        # If alternative_indexing is set but user_indexes is not
        # set, we need to load the settings from the default index
        # ini file. This will contain the default indexes, plus
        # optionally some adjustments to the display of those
        # indexes.
        # If user_indexes is set, we need to load the settings
        # from the users index ini file, which can be a generic
        # name or a name specified on the command line. This ini
        # file will contain a user defined list of indexes, plus
        # optionally some adjustments to the display of those
        # indexes.
        
        # get display properties from ini
        self.load_ini_display()

        # get alternative indexing setting from ini
        self.load_ini_indexing()
        log.debug('alternative_indexing: %s' % self.alternative_indexing)

        # default index settings to empty
        self.index_settings = []

        # get index properties from ini
        if self.structure == 'HIERARCHY_DEFAULT':
        
            # get default indexes
            self.load_indexes('DEFAULT')

        elif self.structure == 'HIERARCHY':
        
            # get user defined indexes
            self.load_indexes('USER')
            
        log.debug(self.index_settings)
        
    ################
    # ini processing
    ################

    def load_ini_indexing(self):

        # get indexing setting
        ini_alternative_indexing = 'N'
        try:
            ini_alternative_indexing = self.proxy.config.get('indexing', 'alternative_indexing')
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        ini_alternative_indexing = ini_alternative_indexing.strip()[:1].upper()
        if ini_alternative_indexing == 'Y':
            self.alternative_indexing = True
        else:
            self.alternative_indexing = False
        log.debug(self.alternative_indexing)

    def load_ini_display(self):

        # get path replacement strings
        try:
            self.pathreplace = self.proxy.config.get('display preferences', 'network_path_translation')
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
            prefer_folderart_option = self.proxy.config.get('display preferences', 'prefer_folderart')
            if prefer_folderart_option.lower() == 'y':
                self.prefer_folderart = True
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        # get albumartist setting
        self.use_albumartist = False
        try:
            ini_albumartist = self.proxy.config.get('display preferences', 'use_albumartist')
            if ini_albumartist.lower() == 'y':
                self.use_albumartist = True
        except ConfigParser.NoSectionError:
            self.use_albumartist = False
        except ConfigParser.NoOptionError:
            self.use_albumartist = False

        # default child of genre
        if self.use_albumartist:
            self.statichierarchy['genre'] = 'albumartist'
        else:
            self.statichierarchy['genre'] = 'artist'

        # get album identification setting
        self.album_distinct_artist = 'album'        # default
        self.album_distinct_albumartist = 'album'   # default
        self.album_groupby_artist = 'album'         # default
        self.album_groupby_albumartist = 'album'    # default
        self.album_group = ['album']                # default
        try:
            ini_album_identification = self.proxy.config.get('display preferences', 'album_identification')
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
            ini_show_separate_albums = self.proxy.config.get('display preferences', 'show_separate_albums')
            if ini_show_separate_albums.lower() == 'y':
                self.show_separate_albums = True
        except ConfigParser.NoSectionError:
            self.show_separate_albums = False
        except ConfigParser.NoOptionError:
            self.show_separate_albums = False

        # make distinct and groupby settings
        self.distinct_albumartist = '%s' % (self.album_distinct_albumartist)
        self.groupby_albumartist = '%s' % (self.album_groupby_albumartist)
        self.distinct_artist = '%s' % (self.album_distinct_artist)
        self.groupby_artist = '%s' % (self.album_groupby_artist)
        self.distinct_composer = '%s' % ('album')
        self.groupby_composer = '%s' % ('album')

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
        self.display_virtuals_in_albumartist_index = True
        try:
            ini_display_virtuals_in_albumartist_index = self.proxy.config.get('virtuals', 'display_virtuals_in_albumartist_index')
            if ini_display_virtuals_in_albumartist_index[:1].lower() == 'n':
                self.display_virtuals_in_albumartist_index = False
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
        self.display_works_in_albumartist_index = True
        try:
            ini_display_works_in_albumartist_index = self.proxy.config.get('works', 'display_works_in_albumartist_index')
            if ini_display_works_in_albumartist_index[:1].lower() == 'n':
                self.display_works_in_albumartist_index = False
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
        self.album_albumtypes = self.get_possible_albumtypes('album_album')
        self.albumartist_album_albumtypes = self.get_possible_albumtypes('albumartist_album')
        self.artist_album_albumtypes = self.get_possible_albumtypes('artist_album')
        self.composer_album_albumtypes = self.get_possible_albumtypes('composer_album')
        self.album_albumtype_where = self.get_albumtype_where(self.album_albumtypes)
        self.albumartist_album_albumtype_where = self.get_albumtype_where(self.albumartist_album_albumtypes)
        self.artist_album_albumtype_where = self.get_albumtype_where(self.artist_album_albumtypes)
        self.composer_album_albumtype_where = self.get_albumtype_where(self.composer_album_albumtypes)

        self.prefix_sep = u'\u00a0'     # non-breaking space
        self.suffix_sep = u'\u007f'     # delete

        # get metadata characters
        prefix_start, self.metadata_delimiter_prefix_start = self.get_delim('entry_prefix_start_separator', '[', self.prefix_sep)
        prefix_end, self.metadata_delimiter_prefix_end = self.get_delim('entry_prefix_end_separator', ']', self.prefix_sep, 'after')

        suffix_start, self.metadata_delimiter_suffix_start = self.get_delim('entry_suffix_start_separator', '[', self.suffix_sep, 'before')
        suffix_end, self.metadata_delimiter_suffix_end = self.get_delim('entry_suffix_end_separator', ']', self.suffix_sep)

        missing, self.metadata_empty = self.get_delim('entry_extras_empty', '_', self.prefix_sep)

        self.dont_display_separator_for_empty_prefix = False
        try:
            ini_dont_display_separator_for_empty_prefix = self.proxy.config.get('index entry extras', 'dont_display_separator_for_empty_prefix')
            if ini_dont_display_separator_for_empty_prefix.lower() == 'y':
                self.dont_display_separator_for_empty_prefix = True
        except ConfigParser.NoSectionError:
            self.dont_display_separator_for_empty_prefix = False
        except ConfigParser.NoOptionError:
            self.dont_display_separator_for_empty_prefix = False

        self.dont_display_separator_for_empty_suffix = False
        try:
            ini_dont_display_separator_for_empty_suffix = self.proxy.config.get('index entry extras', 'dont_display_separator_for_empty_suffix')
            if ini_dont_display_separator_for_empty_suffix.lower() == 'y':
                self.dont_display_separator_for_empty_suffix = True
        except ConfigParser.NoSectionError:
            self.dont_display_separator_for_empty_suffix = False
        except ConfigParser.NoOptionError:
            self.dont_display_separator_for_empty_suffix = False

        dateformat, self.metadata_date_format = self.get_delim('entry_extras_date_format', '%d/%m/%Y', self.prefix_sep)

        self.searchre_pre = '%s[^%s]*%s' % (prefix_start, prefix_end, prefix_end)
        if not suffix_end:
            self.searchre_suf = '%s.*' % (suffix_start)
        else:
            self.searchre_suf = '%s[^%s]*%s' % (suffix_start, suffix_end, suffix_end)

        self.multi_pre = '^(%s){%s}' % (self.searchre_pre, '%s')
        self.multi_suf = '(%s){%s}$' % (self.searchre_suf, '%s')

        self.replace_pre = '%s%s%s' % (self.metadata_delimiter_prefix_start, '%s', self.metadata_delimiter_prefix_end)
        self.replace_suf = '%s%s%s' % (self.metadata_delimiter_suffix_start, '%s', self.metadata_delimiter_suffix_end)

        # get album to display
        self.now_playing_album_selected_default = 'last'
        self.now_playing_album = 'selected'    # default
        try:
            self.now_playing_album = self.proxy.config.get('display preferences', 'now_playing_album')
            self.now_playing_album = self.now_playing_album.lower()
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        if not self.now_playing_album in ['all', 'first', 'last', 'selected']: self.now_playing_album = 'selected'

        self.now_playing_album_combiner = '/'    # default
        try:
            self.now_playing_album_combiner = self.proxy.config.get('display preferences', 'now_playing_album_combiner')
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
            self.now_playing_artist = self.proxy.config.get('display preferences', 'now_playing_artist')
            self.now_playing_artist = self.now_playing_artist.lower()
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        if not self.now_playing_artist in ['all', 'first', 'last', 'selected']: self.now_playing_artist = 'selected'

        self.now_playing_artist_combiner = '/'    # default
        try:
            self.now_playing_artist_combiner = self.proxy.config.get('display preferences', 'now_playing_artist_combiner')
            if self.now_playing_artist_combiner.startswith("'") and self.now_playing_artist_combiner.endswith("'"):
                self.now_playing_artist_combiner = self.now_playing_artist_combiner[1:-1]
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        # get virtual and work album/artist to display
        self.virtual_now_playing_album = False    # default
        try:
            ini_virtual_now_playing_album = self.proxy.config.get('display preferences', 'virtual_now_playing_album')
            if ini_virtual_now_playing_album.lower() == 'y':
                self.virtual_now_playing_album = True
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        self.virtual_now_playing_artist = False    # default
        try:
            ini_virtual_now_playing_artist = self.proxy.config.get('display preferences', 'virtual_now_playing_artist')
            if ini_virtual_now_playing_artist.lower() == 'y':
                self.virtual_now_playing_artist = True
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        self.work_now_playing_album = False    # default
        try:
            ini_work_now_playing_album = self.proxy.config.get('display preferences', 'work_now_playing_album')
            if ini_work_now_playing_album.lower() == 'y':
                self.work_now_playing_album = True
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        self.work_now_playing_artist = False    # default
        try:
            ini_work_now_playing_artist = self.proxy.config.get('display preferences', 'work_now_playing_artist')
            if ini_work_now_playing_artist.lower() == 'y':
                self.work_now_playing_artist = True
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        # get date format setting
        dummy, self.smapi_date_format = self.get_delim('smapi_date_format', '%Y/%m/%d', ' ', section='SMAPI formats')

    def load_indexes(self, index_type):

        # TODO: add validation to ini processing
        self.debugout('index_type', index_type)

        # reset user id count
        self.next_user_id = self.user_parentid + 1

        self.debugout('statichierarchy', self.statichierarchy)

        # load root, hierarchy, path and index settings data
        self.allrootitems, self.displayrootitems, self.hierarchies, self.index_settings, self.path_index_entries = self.load_hierarchy(index_type)

        self.debugout('allrootitems', self.allrootitems)
        self.debugout('displayrootitems', self.displayrootitems)
        self.debugout('hierarchies', self.hierarchies)
        self.debugout('index_settings', self.index_settings)
        self.debugout('path_index_entries', self.path_index_entries)

        # create type, id and dynamic lookups
        dynamic_value = self.dynamic_parentid_start
        self.index_types = {}
        self.index_ids = {}
        self.dynamic_lookup = {}
        for entry, entrystring in self.allrootitems:
            hierarchy = self.hierarchies[entry]
            index_type_list = []
            index_id_list = []
            # for each index pair in hierarchy, check whether static or dynamic
            # and also save parent id (container id)
            for i in range(len(hierarchy) - 1):
                if hierarchy[i] in self.statichierarchy.keys() and hierarchy[i+1] == self.statichierarchy[hierarchy[i]]:
                    index_type_list += ['STATIC']
                    index_id_list += [self.containerstart[hierarchy[i]]]
                else:
                    index_type_list += ['DYNAMIC']
                    index_id_list += [dynamic_value]
                    dynamic_id = dynamic_value + 1
                    dynamic_value += self.id_length
                    
                    # as we have assigned a dynamic range, then we need to create 
                    # lookups between the keys in that range against the P numbers
                    # for the entries in that range
                    
                    # get the path index entry 
                    path_index_key = '%s_%s' % (entry, hierarchy[i])
                    path_index_entry = self.path_index_entries[path_index_key]
                    # process each entry in the list
                    for pid, title in path_index_entry:
                        self.dynamic_lookup[dynamic_id] = pid
                        dynamic_id += 1

            # set leaf data
            index_type_list += ['LEAF']
            index_id_list += [self.containerstart['track']]
            # save into lookups
            self.index_types[entry] = index_type_list
            self.index_ids[entry] = index_id_list

        self.debugout('index_types', self.index_types)
        self.debugout('index_ids', self.index_ids)
        self.debugout('dynamic_lookup', self.dynamic_lookup)

        # now post process dynamic entries - if there is a dynamic
        # above a normal static index, and the range field is the
        # same as the index, then convert it to a range so that
        # we can just use the range in the static call
        # (we could decide to create a list of valid fields, but
        # obviously they are index specific - we'll just go 
        # dynamic if it's not the field we know)
        
        for entry, entrydict in self.index_types.iteritems():
            # check if index starts with dynamic and there are no other dynamic entries
            if entrydict[0] == 'DYNAMIC' and not 'DYNAMIC' in entrydict[1:]:
                rangecheck = True
                # get key for path entry
                pathkey = '%s_%s' % (entry, self.hierarchies[entry][0])
                # get entries for this user defined index
                keydict = self.path_index_entries[pathkey]
                # get child index
                childindex = self.hierarchies[entry][1]
                # check range field for each entry in list
                for indexkey, title in keydict:
                    # get key for path index entry
                    pathindexkey = '%s_%s_%s' % (entry, indexkey, childindex)
                    # get range field for child
                    indexfield = self.index_settings[pathindexkey]['range_field']
                    # check if the range field of the child is the same as the child
                    if indexfield != '' and indexfield != childindex:
                        rangecheck = False
                if rangecheck:
                    self.index_types[entry] = ['RANGE'] + entrydict[1:]

        self.debugout('index_types', self.index_types)



        # TEMP
        self.index_ids['R0'] = [0]
        self.hierarchies['R0'] = [u'usersearch']
        self.debugout('index_ids', self.index_ids)
        self.debugout('hierarchies', self.hierarchies)



        # load user search data
        self.user_search_entries = self.load_searches(index_type)
        self.debugout('user_search_entries', self.user_search_entries)

        # create search entries for user defined search entries
        # TODO: fix the fixed width of the format strings below
        self.searchitems = []
        for searchid, (searchtype, searchname, searchfields) in self.user_search_entries.iteritems():
            if searchtype == 'root':
                rootid, indexentrystart, indexentrytable = searchfields[0]
                self.searchitems += [('%s:%09i' % (rootid, indexentrystart), searchname)]
            else:            
                self.searchitems += [('R0:%09i' % searchid, searchname)]

        if index_type == 'DEFAULT':
            # create search entries for all root entries
            for (rootid, rootname) in self.displayrootitems:
                firstindex = self.hierarchies[rootid][0]
                path_name = '%s_%s' % (rootid, firstindex)
                if path_name not in self.path_index_entries.keys():
                    firstindexstart = self.index_ids[rootid][0]
                    self.searchitems += [('%s:%09i' % (rootid, firstindexstart), rootname)]

        self.debugout('searchitems', self.searchitems)

    def load_hierarchy(self, index_type):

        # allrootitems will contain an ordered list of all root item tuples, of root ID and title
        #    root ID starts with 'R' and is consecutive (and unique) from 1
        #
        # displayrootitems will contain an ordered list of those root items that are to be displayed
        #
        # hierarchy_data will contain a dictionary of root item IDs, with values
        # of a list of the items in the hierarchy for that root
        #
        # hierarchy_entries will contain a dictionary of index data, keyed on:
        #    rootID [path IDs] index
        # with values of a dictionary of the index key/value pairs
        # path ID starts with 'P' and is consecutive (and unique) from 1
        #
        # path_index_entries will contain a dictionary of path data, keyed on:
        #    rootID path_index
        # with values of a list of tuples of the items for that path

        if index_type == 'DEFAULT': inifile = DEFAULTINDEX_INI
        else: 
            if self.ininame == None: inifile = USERINDEX_INI
            else: inifile = self.ininame

        allrootitems = []
        displayrootitems = []
        hierarchy_data = {}
        hierarchy_entries = {}
        path_index_entries = {}
        path_indexes = {}

        processing = stop_processing = False
        tree_count = 0
        path_count = 0
        processing_index = None
        index_key_dict = self.user_index_key_dict.copy()
        
        # read line by line so we can process EOF to tidy up
        f = codecs.open(inifile,'r','utf-8')
        while True:

            line=f.readline()

            # if EOF, pretend we have a new section
            if not line: 
                line = '['
        
            line = self.strip_line(line)
            if not line: continue

            if processing and line.startswith('['):
            
                # force one more time through to tidy up
                line = 'tree=_dummy_'
                stop_processing = True
            
            if line == '[indexes]':
            
                processing = True
                
            elif processing:

                # look for tree entry, format is:
                #    tree = index_entry_level_1_field / ... index_entry_level_n_field

                key, value = self.extract_key_value(line)

                if key == 'tree':

                    if tree_count > 0 and title:
                    
                        # save previous tree data
                        allrootitems += [(tree_id, title)]
                        if display_index:
                            displayrootitems += [(tree_id, title)]
                        hierarchy_data[tree_id] = tree

                        # save prev path entries
                        if path_entry != {}:
                            path_index_entries.update(path_entry)

                        # this block of code is duplicated
                        if index:

                            # get keys of any higher path indexes
                            higher_types = self.get_higher_types(index, tree, path_indexes)
                            if higher_types:
                                index_id = '%s_%s_%s' % (tree_id, higher_types, index)
                            else:
                                index_id = '%s_%s' % (tree_id, index)
                            # save previous index data
                            hierarchy_entries[index_id] = index_key_dict.copy()
                            # reset default index entries                        
                            index_key_dict = self.user_index_key_dict.copy()
                        
                    tree_count += 1
                    tree_id = 'R%s' % tree_count
                    tree = value.split('/')
                    if value != '_dummy_':
                        title = None
                        path_entry = {}
                    path_indexes = {}
                    display_index = True
                    
                elif tree_count > 0:

                    # look for display value
                    if key == 'display':

                        if value.lower() == 'n':
                            display_index = False
                    
                    # look for tree title
                    elif key == 'title':
                    
                        title = value
                        index = None

                    elif title:
                    
                        # look for index key or new tree
                        if key == 'index' or key == 'tree':

                            if index:

                                # get type of higher index
                                higher_types = self.get_higher_types(index, tree, path_indexes)
                                if higher_types:
                                    index_id = '%s_%s_%s' % (tree_id, higher_types, index)
                                else:
                                    index_id = '%s_%s' % (tree_id, index)
                                # save previous index data
                                hierarchy_entries[index_id] = index_key_dict.copy()
                                # reset default index entries                        
                                index_key_dict = self.user_index_key_dict.copy()
                                
                            if value in tree:

                                index = value

                        elif index:
                    
                            if key == 'entry':
                            
                                # is an entry for a user defined path
                                path_count += 1
                                path_id = 'P%s' % path_count
                                path_entry_index = '%s_%s' % (tree_id, index)
                                currentvalue = path_entry.get(path_entry_index, [])
                                path_entry[path_entry_index] = currentvalue + [(path_id, value)]
                                path_indexes[index] = path_id

                            else:
                            
                                if key in index_key_dict.keys():

                                    if key == 'index_range':
                                        value = self.convert_range(value)
                                
                                    # is a key for a user defined index
                                    index_key_dict[key] = value

            if stop_processing: break

        return allrootitems, displayrootitems, hierarchy_data, hierarchy_entries, path_index_entries

    def load_searches(self, index_type):

        if index_type == 'DEFAULT': inifile = DEFAULTINDEX_INI
        else: 
            if self.ininame == None: inifile = USERINDEX_INI
            else: inifile = self.ininame

        user_search_entries = {}

        processing = False

        # read line by line so we can process EOF to tidy up
        f = codecs.open(inifile,'r','utf-8')
        while True:

            line=f.readline()

            # if EOF, pretend we have a new section
            if not line:
                processing = True
                line = '['
        
            line = self.strip_line(line)
            if not line: continue

            if processing and line.startswith('['):
            
                break
            
            if line == '[searches]':

                processing = True

            elif processing:

                # look for search entry, formats are:
                #    search = index_entry_name
                # or
                #    multisearch = index_entry_name_1 , ... index_entry_name_n
                # or
                #    subsearch = root_entry_title / index_entry_field

                key, value = self.extract_key_value(line)

                if key == 'search':

                    user_search_entry = None
                    # is a search index
                    if value != '':
                        # convert entry and get index start
                        convindexentries = []
                        rootkey = self.get_root_entry(value)
                        log.debug('value: %s  rootkey: %s' % (value, rootkey))
                        if rootkey != None:
                            # get index start
                            indexentrystart = self.index_ids[rootkey][0]
                            # get index table
                            indexentrytable = self.hierarchies[rootkey][0]
                            convindexentries += [(rootkey, indexentrystart, indexentrytable)]
                        # save entry
                        if convindexentries != []:
                            user_search_entry = ('root', convindexentries)

                if key == 'multisearch':

                    user_search_entry = None
                    # is a set of search indexes to combine (could be a single one)
                    indexentries = value.split(',')
                    if indexentries != []:
                        # convert entries and get index starts
                        convindexentries = []
                        for rootindex in indexentries:
                            rootkey = self.get_root_entry(rootindex)
                            if rootkey != None:
                                # get index start
                                indexentrystart = self.index_ids[rootkey][0]
                                # get index table
                                indexentrytable = self.hierarchies[rootkey][0]
                                convindexentries += [(rootkey, indexentrystart, indexentrytable)]
                        # save entry
                        if convindexentries != []:
                            user_search_entry = ('multi', convindexentries)

                elif key == 'subsearch':
                
                    user_search_entry = None
                    # is a lower level search type
                    indexentries = value.split('/')
                    if len(indexentries) == 2:
                        lookuproot = indexentries[0]
                        # first entry must be in hierarchies
                        rootkey = self.get_root_entry(lookuproot)
                        if rootkey != None:
                            lookup_indexes = self.hierarchies[rootkey]
                            lookupindex = indexentries[1]
                            # second entry must be in that hierarchy's indexes
                            if lookupindex in lookup_indexes:
                                # get position in ini entry
                                indexentrypos = lookup_indexes.index(lookupindex)
                                # get index start
                                indexentrystart = self.index_ids[rootkey][indexentrypos]
                                # save entry
                                user_search_entry = ('lower', [(rootkey, indexentrystart, lookupindex)])
                    
                elif key == 'title':
                    
                    title = value

                    if user_search_entry != None:

                        # save search data
                        # values are type, title, root, fields
                        user_search_entries[self.next_user_id] = user_search_entry[0], title, user_search_entry[1]
                        self.next_user_id += 1

        # TEMP
        # create keyword entry from album/artist/track root entries
        keywordentry = []
        for sid, (stype, stitle, sindex) in user_search_entries.iteritems():
            if stype == 'root':
                if sindex[0][2] == 'album' or sindex[0][2] == 'albumartist' or sindex[0][2] == 'track':
                    keywordentry += [sindex[0]]
        if keywordentry:        
            user_search_entries[self.next_user_id] = ('keyword', 'Keyword', keywordentry)
            self.next_user_id += 1

        return user_search_entries
    
    '''
    default_indexes = {
        'album': 'album_album',
        'albumartist': 'albumartist_albumartist',
        'albumartist_album': 'albumartist_album',
        'artist': 'artist_artist',
        'artist_album': 'artist_album',
        'composer': 'composer_composer',
        'composer_album': 'composer_album',
        'genre': 'genre_genre',
        'genre_albumartist': 'genre_albumartist',
        'genre_albumartist_album': 'genre_albumartist_album',
        'playlist': 'playlist_playlist',
        'track': 'track_track',
        }
    '''

    #########
    # helpers
    #########

    def get_root_entry(self, title):
        # get root ID given title
        for entry, entrystring in self.allrootitems:
            if entrystring == title:
                return entry
        return None

    def strip_line(self, line):
        # remove whitespace, ignore blank and comment lines
        line = line.strip()
        if line == '': return None
        if line.startswith('#'): return None
        if line.endswith('\n'): line = line[:-1]
        return line

    def extract_key_value(self, line):
        # extract valid key/value pair
        key = value = None
        entries = line.split('=')
        if len(entries) == 2:
            key = entries[0].strip().lower()
            if key == '': key = None
            else:
                value = entries[1].strip()
                if value == '': value = None
        if not key or not value:
            return None, None
        else:
            return key, value

    def get_higher_types(self, index, tree, path_indexes):
        # get concatenated list of all path indexes above passed index
        # get position of index in tree
        pos = tree.index(index)
        # get type of previous entry if there is one
        if pos == 0: return None
        else:
            types = ''
            for i in range(pos):
                entry = tree[i]
                if entry in path_indexes.keys():
                    types = '_'.join(filter(None,(types, path_indexes[entry])))
            return types
        
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

    ##########
    # database
    ##########

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
        
    ###############
    # query service
    ###############

    def query(self, **kwargs):

        log.debug("Mediaserver.query: %s", kwargs)

        # get name of ID field
        if self.source == 'UPNP':
            action = kwargs.get('Action', None)
            if action == 'BROWSE':
                id = 'ObjectID'
            else:
                id = 'ContainerID'
        else:
            id = 'ID'
        queryID = kwargs.get(id, '')
        log.debug("queryID: %s" % queryID)

        # standardise ID field name
        kwargs['QueryID'] = queryID

        return self.hierarchicalQuery(**kwargs)

    def hierarchicalQuery(self, **kwargs):

        log.debug("Mediaserver.hierarchicalQuery: %s", kwargs)

        queryID = kwargs.get('QueryID', '')
        log.debug("QueryID: %s" % queryID)
        index = int(kwargs.get('StartingIndex', 0))
        log.debug("StartingIndex: %s" % index)
        count = int(kwargs.get('RequestedCount', 100))
        log.debug("RequestedCount: %s" % count)
        term = kwargs.get('term', None)
        log.debug("term: %s" % term)

        wassearch = False

        # work out what hierarchy data is asking for
        # it's either
        #     the root entry ('root' if from SMAPI, 0/1 if from UPnP)
        #     the search entry
        #     a track
#        #     a playlist
        #     a list of IDs
        
        items = None
        track = False
        playlist = False
        if queryID == 'root' or queryID == '0' or queryID == '1':
            # TODO: process count/index (i.e. take note of how many entries are requested)
            items = self.displayrootitems
        elif queryID == 'search':
            # TODO: process count/index (i.e. take note of how many entries are requested)
            items = self.searchitems
            '''            
        elif len(queryID) == 32 and not ':' in queryID:
            # track id is 32 hex chars
            # TODO: check this is hex
            track = True
        elif len(queryID) == 8 and not ':' in queryID:
            # playlist id is 8 hex chars, everything else will be 9 or more
            # TODO: check this is hex
            playlist = True
            '''            
        elif '__' in queryID:
            # must be track (the only time we pass a faceted ID this way)
            track = True
        else:
            # must be a list of IDs separated by :
            
            # remove any search flag and store it
            if queryID.startswith('S'):
                wassearch = True
                queryID = queryID[1:]
                
            ids = queryID.split(':')

        log.debug("items: %s" % items)
        if items != None:

            # TODO: process count/index (i.e. take note of how many entries are requested)

            if self.source == 'SMAPI':

                total = len(items)

                return items, total, index, 'container'

            else:

                ret  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'

                for (id, title) in items:

                    ret += '<container id="%s" parentID="%s" restricted="true">' % (id, queryID)
                    ret += '<dc:title>%s</dc:title>' % (title)
                    ret += '<upnp:class>object.container</upnp:class>'
                    ret += '</container>'

                ret += '</DIDL-Lite>'
                count = len(items)
                totalMatches = len(items)

                return ret, count, totalMatches

        # TODO: remember we need to only reject this for SMAPI getMetadata (not getMediametadata)

        elif track:
        
            if self.source == 'SMAPI':

                # not allowed to call getMetadata for track for SMAPI
                # - gets called wrongly from WDCR with double click on Linux
                return build_soap_error(600, 'Invalid to call getMetadata for track')

            else:

                return self.staticQuery(**kwargs)

        elif playlist:
        
            if self.source == 'SMAPI':

                # not allowed to call getMetadata for playlist for SMAPI
                return build_soap_error(600, 'Invalid to call getMetadata for playlist')

            else:

                return self.staticQuery(**kwargs)

        else:

            controllername = kwargs.get('Controller', '')
            log.debug('Controller: %s' % controllername)
            controlleraddress = kwargs.get('Address', '')
            log.debug('Address: %s' % controlleraddress)

            # have a list of queryIDs - are a hierarchy of containers
            log.debug('ids: %s' % ids)

            # convert keys to integers (except rootname)
            ids = [i if i.startswith('R') else int(i) for i in ids]

            # ID is always passed prepended with root name
            rootname, indexkeys = self.get_index_parts(ids)

            log.debug('rootname: %s' % rootname)
            log.debug('indexkeys: %s' % indexkeys)

            # get position of last index in list in hierarchy 
            indexentryposition = len(indexkeys) - 1

            # get this entry key
            indexentrykey = indexkeys[indexentryposition]

            # get index entry id
            indexentryid = self.index_ids[rootname][indexentryposition]

            # get index entry name
            indexentryname = self.hierarchies[rootname][indexentryposition]

            # check if entry is id rather than container
            isid = False if indexentrykey == indexentryid else True

            # check if current entry is a key that isn't a leaf, if so
            # we need to append the next entry in the index
            if indexentryname == 'usersearch':
#                pass
                # check if we have been passed the keyword search entry
                if rootname == 'R0' and queryID in [searchitem[0] for searchitem in self.searchitems]:
                    searchtype, searchtitle, searchfields = self.user_search_entries[indexkeys[0]]
                    if searchtype == 'keyword':
                        if not '=' in term or term[-1] == '=':
                            items = []
                            return items, -1, -1, 'container'
                        else:
#                            items = [('R0:1', u'Success 1', None, 'artist'), ('R0:1', u'Success 2', None, 'album')]
#                            return items, 2, 2, 'container'
                            StartingIndex = str(index)
                            RequestedCount = str(count)
                            hierarchy = queryID
                            idkeys = {}
                            return self.keywordQuery(Controller=controllername,
                                                      Address=controlleraddress,
                                                      QueryID=queryID,
                                                      StartingIndex=StartingIndex,
                                                      RequestedCount=RequestedCount,
                                                      SMAPI=hierarchy,
                                                      idkeys=idkeys,
                                                      Action='BROWSE',
                                                      term=term,
                                                      searchfields=searchfields)

            elif isid and not indexentryid in self.tracktypes:
            
                # current entry is a container, but a key has been passed,
                # append next container to key list
                next_container = self.index_ids[rootname][indexentryposition + 1]
                ids += [next_container]
                indexkeys += [next_container]
                indexentryposition += 1

            log.debug('ids: %s' % ids)
            log.debug('indexkeys: %s' % indexkeys)

            # get type of last item in hierarchy
            if self.index_ids[rootname][indexentryposition] in self.tracktypes:
                itemtype = 'track'
            else:
                itemtype = 'container'
                
            log.debug('itemtype: %s' % itemtype)

            # check whether this call is supported by static or dynamic
            static = False
            firstindexentryname = self.hierarchies[rootname][0]
            
            if wassearch:
            
                # TEMP - if its a search, assume dynamic
                static = 'DYNAMIC'

            elif firstindexentryname != 'usersearch' and indexentryname != 'usersearch':

#                static = self.index_types[rootname][indexentryposition - 1]
                static = self.index_types[rootname][indexentryposition]

                if static == 'STATIC' or static == 'LEAF':
                    # though the index is marked as static, it may have a range
                    # if it is after a dynamic index, and hence needs to be
                    # treated as dynamic. To work that out, work out what its
                    # index setting key is (rootname + pathnames + indexname)
                    # and check whether there is a range set for that index setting
                    # - but only do this if there is a dynamic index in this hierarchy
                    #   before this index entry
                    if 'DYNAMIC' in self.index_types[rootname][:indexentryposition]:
#                    #   immediately before this index entry
#                    if self.index_types[rootname][indexentryposition] == 'DYNAMIC':
                    
                        # TEMP - if there is a dynamic above it, assume it is dynamic
                        static = 'DYNAMIC'
                
#                        index_key = self.get_index_key(ids)
#                        log.debug("index_key: %s" % index_key)
#                        if index_key in self.index_settings.keys():
#                            index_setting = self.index_settings[index_key]
#                            log.debug("index_setting: %s" % index_setting)
#                            index_range = index_setting['index_range']
#                            log.debug("index_range: %s" % (index_range,))
#                            if index_range != ('', '', ''):
#                                static = 'DYNAMIC'

            log.debug('static: %s' % static)
            
            # if recursive requested, replace last item in hierarchy
            # with track
            # (assumes all hierarchies end in track, or at least
            # that recursive will only be requested for hierarchies
            # that end in tracks)
            recursive = kwargs.get('recursive', False)
            log.debug("recursive: %s" % recursive)
            if recursive:
                # if last entry has a user defined path index as a parent,
                # append rather than replace as we need to take account
                # of any range in the user defined index
                append = False
                if len(ids) > 2:
                    indexname = self.hierarchies[rootname][len(ids) - 3]
                    path_name = '%s_%s' % (rootname, indexname)
                    log.debug('path_name: %s' % path_name)
                    if path_name in self.path_index_entries.keys():
                        append = True
                if append:
                    ids += [self.track_parentid]
                    indexkeys += [self.track_parentid]
                else:
                    ids[-1] = self.track_parentid
                    indexkeys[-1] = self.track_parentid
                log.debug('ids: %s' % ids)
                log.debug('indexkeys: %s' % indexkeys)
            
            # process ids
            idkeys = {}
            hierarchy = ''
            for i in range(len(indexkeys)):

                # get this entry key
                indexentrykey = indexkeys[i]

                # get index entry id and index entry name
                if not recursive or i < len(indexkeys) - 1:
                    indexentryid = self.index_ids[rootname][i]
                    indexentryname = self.hierarchies[rootname][i]
                else:
                    # if recursive, last entry must be last entry in index
                    # (and must be tracks)
                    indexentryid = self.index_ids[rootname][-1]
                    indexentryname = self.hierarchies[rootname][-1]

                # check if entry is id rather than container
                isid = False if indexentrykey == indexentryid else True
                
                # build up hierarchy
                hierarchy = ':'.join(filter(None, (hierarchy, indexentryname)))

                # create key entry
                id = int(indexentrykey)
                idkeys[indexentryname] = (id, isid, indexentryid)

            log.debug('hierarchy: %s' % hierarchy)
            log.debug('idkeys: %s' % idkeys)
            
            # if we get this far we have a list of IDs and we need to query the database
            
            if indexentryname == 'usersearch' or static == 'DYNAMIC' or static == 'RANGE':

                # dynamic
                # create call data to dynamicQuery and call it
#                queryID = '-1'
                if term: SearchCriteria = term
                else: SearchCriteria = ''
                StartingIndex = str(index)
                RequestedCount = str(count)

                return self.dynamicQuery(Controller=controllername,
                                           Address=controlleraddress,
                                           QueryID=queryID,
                                           SearchCriteria=SearchCriteria,
                                           StartingIndex=StartingIndex,
                                           RequestedCount=RequestedCount,
                                           SMAPI=hierarchy,
                                           idkeys=idkeys,
                                           wassearch=wassearch)

            else:

                # static
                # create call data to staticQuery and call it
#                queryID = '-1'
                BrowseFlag = 'BrowseDirectChildren'
                if term: SearchCriteria = 'SEARCH::%s::%s' % (hierarchy, term)
                else: SearchCriteria = ''
                StartingIndex = str(index)
                RequestedCount = str(count)

                return self.staticQuery(Controller=controllername,
                                          Address=controlleraddress,
                                          QueryID=queryID,
                                          BrowseFlag=BrowseFlag,
                                          SearchCriteria=SearchCriteria,
                                          StartingIndex=StartingIndex,
                                          RequestedCount=RequestedCount,
                                          SMAPI=hierarchy,
                                          idkeys=idkeys,
                                          Action='BROWSE')

    def staticQuery(self, *args, **kwargs):

        log.debug("Mediaserver.staticQuery: %s", kwargs)

        '''
        Write up options that can be passed (in staticbrowsetypes.py)
        '''

        action = kwargs.get('Action', None)
        log.debug("action: %s" % action)

        queryID = kwargs.get('QueryID', '')
        log.debug("queryID: %s" % queryID)

# TODO
# TODO: remember to decide what to do with titlesort and how to allow the user to select it (or other tags)
# TODO

        SMAPI = kwargs.get('SMAPI', '')
        log.debug('SMAPI: %s' % SMAPI)
        idhierarchy = SMAPI.split(':')
        log.debug(idhierarchy)
        idkeys = kwargs.get('idkeys', '')
        log.debug(idkeys)

        searchCriteria = kwargs.get('SearchCriteria', '')
        searchCriteria = self.fixcriteria(searchCriteria)
        log.debug('searchCriteria: %s' % searchCriteria.encode(enc, 'replace'))

        items = []
        browsetype = SMAPI

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

        # create call data for metadata/mediametadata and call it
        return self.querymetadata(Controller=controllername,
                                   Address=controlleraddress,
                                   QueryID='%s' % queryID,
                                   SearchCriteria=searchCriteria,
                                   StartingIndex=startingIndex,
                                   RequestedCount=requestedCount,
                                   SMAPI=SMAPI,
                                   idkeys=idkeys,
                                   browsetype=browsetype)

    ###############################
    # static queries for containers
    ###############################

    def getQuerySingletrack(self, roottype, controllername, tracktype):

        artisttype = 'singletrack'
        sorttype = '%s_%s' % (roottype, 'track')
        # TODO: orderby is not applicable for this call (others probably aren't too)
        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='track')

        if tracktype == 'T':
            querystatement = "select * from tracks where id = ?"
        else:
            querystatement = "select * from playlists where track_id = ?"

        return querystatement, prefix, suffix, artisttype
            
    def getQueryAlbumartist(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='albumartist')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        artisttype = 'albumartist'

        searchwhere = ''
        if searchcontainer:
            searchstring = escape_sql(searchstring)
            searchwhere = "albumartist like '%s%%'" % searchstring

        albumwhere = '%s' % self.albumartist_album_albumtype_where

        where = ' and '.join(filter(None,(rangewhere, searchwhere, albumwhere)))
        if where != '':
            where = 'where %s' % where

        countstatement = "select count(distinct albumartist) from AlbumartistAlbum %s" % where
        orderstatement = "select rowid, albumartist, lastplayed, playcount from AlbumartistAlbum %s group by albumartist order by %s limit ?, ?" % (where, orderby)
        alphastatement = self.smapialphastatement % ('albumartist', 'AlbumartistAlbum %s group by albumartist order by %%s' % where)

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange
            
    def getQueryArtist(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='artist')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        artisttype = 'artist'

        searchwhere = ''
        if searchcontainer:
            searchstring = escape_sql(searchstring)
            searchwhere = "artist like '%s%%'" % searchstring

        albumwhere = '%s' % self.artist_album_albumtype_where

        where = ' and '.join(filter(None,(rangewhere, searchwhere, albumwhere)))
        if where != '':
            where = 'where %s' % where

        countstatement = "select count(distinct artist) from ArtistAlbum %s" % where
        orderstatement = "select rowid, artist, lastplayed, playcount from ArtistAlbum %s group by artist order by %s limit ?, ?" % (where, orderby)
        alphastatement = self.smapialphastatement % ('artist', 'ArtistAlbum %s group by artist order by %%s' % where)

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryGenreAlbumartist(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='albumartist')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        artisttype = 'albumartist'
        albumwhere = 'and %s' % self.albumartist_album_albumtype_where
        
        countstatement = "select count(distinct albumartist) from GenreAlbumartistAlbum where genre=? %s" % albumwhere
        orderstatement = "select rowid, albumartist, lastplayed, playcount from GenreAlbumartistAlbum where genre=? %s group by albumartist order by %s limit ?, ?" % (albumwhere, orderby)
        alphastatement = ''
        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryGenreArtist(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='artist')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        artisttype = 'artist'
        albumwhere = 'and %s' % self.artist_album_albumtype_where
        countstatement = "select count(distinct artist) from GenreArtistAlbum where genre=? %s" % albumwhere
        orderstatement = "select rowid, artist, lastplayed, playcount from GenreArtistAlbum where genre=? %s group by artist order by %s limit ?, ?" % (albumwhere, orderby)
        alphastatement = ''
        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryGenre(self, searchcontainer, searchstring, sorttype, controllername):

        searchwhere = ''
        if searchcontainer:
            searchstring = escape_sql(searchstring)
            searchwhere = "genre like '%s%%'" % searchstring
            
        if self.use_albumartist:
        
            orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='genre')
            rangetype, rangewhere = self.format_range(rangefield, indexrange)

            artisttype = 'albumartist'
            albumwhere = '%s' % self.albumartist_album_albumtype_where

            where = ' and '.join(filter(None,(rangewhere, searchwhere, albumwhere)))
            if where != '':
                where = 'where %s' % where


            countstatement = "select count(distinct genre) from GenreAlbumartistAlbum %s" % where
            orderstatement = """select rowid, genre, lastplayed, playcount from Genre where genre in
                               (select distinct genre from GenreAlbumartistAlbum %s)
                               order by %s limit ?, ?""" % (where, orderby)
            alphastatement = self.smapialphastatement % ('genre', 'GenreAlbumartistAlbum %s group by genre order by %%s' % where)

        else:

            orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='genre')
            rangetype, rangewhere = self.format_range(rangefield, indexrange)

            artisttype = 'artist'
            albumwhere = '%s' % self.artist_album_albumtype_where

            where = ' and '.join(filter(None,(rangewhere, searchwhere, albumwhere)))
            if where != '':
                where = 'where %s' % where

            countstatement = "select count(distinct genre) from GenreArtistAlbum %s" % where
            orderstatement = """select rowid, genre, lastplayed, playcount from Genre where genre in
                               (select distinct genre from GenreArtistAlbum %s)
                               order by %s limit ?, ?"""  % (where, orderby)
            alphastatement = self.smapialphastatement % ('genre', 'GenreArtistAlbum %s group by genre order by %%s' % where)

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryComposer(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='composer')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        artisttype = 'composer'

        searchwhere = ''
        if searchcontainer:
            searchstring = escape_sql(searchstring)
            searchwhere = "composer like '%s%%'" % searchstring

        albumwhere = '%s' % self.composer_album_albumtype_where

        where = ' and '.join(filter(None,(rangewhere, searchwhere, albumwhere)))
        if where != '':
            where = 'where %s' % where

        countstatement = "select count(distinct composer) from ComposerAlbum %s" % (where)
        orderstatement = "select rowid, composer, lastplayed, playcount from ComposerAlbum %s group by composer order by %s limit ?, ?" % (where, orderby)
        alphastatement = self.smapialphastatement % ('composer', 'ComposerAlbum %s group by composer order by %%s' % where)

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryAlbum(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='album')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        searchwhere = ''
        if searchcontainer:
            searchstring = escape_sql(searchstring)
            searchwhere = "album like '%s%%'" % searchstring

        at = self.get_albumtype_where(albumtype, table='aa')
        albumwhere = '%s' % at

        where = ' and '.join(filter(None,(rangewhere, searchwhere, albumwhere)))
        if where != '':
            where = 'where %s' % where

        if self.use_albumartist:

            artisttype = 'albumartist'
            album_distinct = self.distinct_albumartist
            album_groupby = self.groupby_albumartist
            orderby = self.album_groupby_albumartist
            if 'albumartist' in self.album_group:
                countstatement = "select count(distinct %s) from AlbumartistAlbum aa %s" % (album_distinct, where)
                orderstatement = """
                                   select album_id, album, '', albumartist, '', a.*, 0 from AlbumartistAlbum aa join albums a on
                                   aa.album_id = a.id
                                   %s group by %s
                                   order by %s limit ?, ?
                                 """ % (where, album_groupby, orderby)
                alphastatement = self.smapialphastatement % ('album', 'AlbumartistAlbum aa %s group by %s order by %%s' % (where, album_groupby))
            else:
                separate_albums = '||albumartist' if self.show_separate_albums else ''
                countstatement = "select count(distinct %s%s) from AlbumartistAlbumsonly aa %s" % (album_distinct, separate_albums, where)
                separate_albums = ',albumartist' if self.show_separate_albums else ''
                orderstatement = """
                                   select album_id, aa.album, '', aa.albumartist, '', a.* from AlbumartistAlbumsonly aa join albumsonly a on
                                   aa.album_id = a.id
                                   %s group by %s%s
                                   order by %s limit ?, ?
                                 """ % (where, album_groupby, separate_albums, orderby)
                alphastatement = self.smapialphastatement % ('album', 'AlbumartistAlbumsonly aa %s group by %s%s order by %%s' % (where, album_groupby, separate_albums))

        else:
        
            artisttype = 'artist'
            album_distinct = self.distinct_artist
            album_groupby = self.groupby_artist
            orderby = self.album_groupby_artist
            if 'artist' in self.album_group:
                countstatement = "select count(distinct %s) from ArtistAlbum aa %s" % (album_distinct, where)
                orderstatement = """
                                   select album_id, album, artist, '', '', a.*, 0 from ArtistAlbum aa join albums a on
                                   aa.album_id = a.id
                                   %s group by %s
                                   order by %s limit ?, ?
                                 """ % (where, album_groupby, orderby)
                alphastatement = self.smapialphastatement % ('album', 'ArtistAlbum aa %s group by %s order by %%s' % (where, album_groupby))
            else:
                separate_albums = '||artist' if self.show_separate_albums else ''
                countstatement = "select count(distinct %s%s) from ArtistAlbumsonly aa %s" % (album_distinct, separate_albums, where)
                separate_albums = ',artist' if self.show_separate_albums else ''
                orderstatement = """
                                   select album_id, aa.album, aa.artist, '', '', a.* from ArtistAlbumsonly aa join albumsonly a on
                                   aa.album_id = a.id
                                   %s group by %s%s
                                   order by %s limit ?, ?
                                 """ % (where, album_groupby, separate_albums, orderby)
                alphastatement = self.smapialphastatement % ('album', 'ArtistAlbumsonly aa %s group by %s%s order by %%s' % (where, album_groupby, separate_albums))

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryPlaylist(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='playlist')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        if self.use_albumartist:
            artisttype = 'albumartist'
        else:
            artisttype = 'artist'
        searchwhere = ''
        if searchcontainer:
            searchstring = escape_sql(searchstring)
            searchwhere = "playlist like '%s%%'" % searchstring

        albumwhere = ''
        where = ' and '.join(filter(None,(rangewhere, searchwhere, albumwhere)))
        if where != '':
            where = 'where %s' % where

        countstatement = "select count(distinct plfile) from playlists %s" % (where)
        orderstatement = "select rowid,* from playlists %s group by plfile order by playlist limit ?, ?" % (where)
        alphastatement = self.smapialphastatement % ('playlist', 'playlists %s order by %%s' % where)

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryTrack(self, searchcontainer, searchstring, sorttype, controllername):

        log.debug('searchcontainer: %s' % searchcontainer)
        log.debug('searchstring: %s' % searchstring)
        log.debug('sorttype: %s' % sorttype)
        log.debug('controllername: %s' % controllername)

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='title')
#        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='titleorder')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        log.debug('orderby: %s' % orderby)
        log.debug('prefix: %s' % prefix)
        log.debug('suffix: %s' % suffix)
        log.debug('albumtype: %s' % albumtype)

        searchwhere = ''
        #TODO: check artisttype
        artisttype = 'track'
        if searchcontainer:
            searchstring = escape_sql(searchstring)
            searchwhere = "title like '%s%%'" % searchstring

        albumwhere = ''
        where = ' and '.join(filter(None,(rangewhere, searchwhere, albumwhere)))
        if where != '':
            where = 'where %s' % where

        countstatement = "select count(1) from tracks %s" % where
        orderstatement = "select * from tracks %s order by %s limit ?, ?" % (where, orderby)
#        orderstatement = "select * from tracks %s where titleorder >= ? and titleorder < ? order by %s" % (where, orderby)
        alphastatement = self.smapialphastatement % ('title', 'tracks %s order by %%s' % where)

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryAlbumTrack(self, searchcontainer, searchstring, sorttype, controllername, albumtype, separated):

        if albumtype != 10:
            orderby = 'n.tracknumber, t.title'
        else:
            orderby = 'discnumber, tracknumber, title'

        # TODO: fix albumtypedummy - can't differentiate between albumtypes in same index any more anyway....
        orderby, prefix, suffix, albumtypedummy, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby=orderby)
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        #TODO: check artisttype
        artisttype = 'track'

        # work out what params are needed
        params = []
        if albumtype == 10:
            where = "n.album=?"
        else:
            where = "n.dummyalbum=?"
        if 'artist' in self.album_group:
            where += " and n.artist=?"
            params += ['artist']
        if 'albumartist' in self.album_group:
            where += " and n.albumartist=?"
            params += ['albumartist']
        if not 'artist' in self.album_group and not 'albumartist' in self.album_group:
            if self.show_separate_albums and separated:
                if self.use_albumartist:
                    where += " and n.albumartist=?"
                    params += ['albumartist']
                else:
                    where += " and n.artist=?"
                    params += ['artist']
        if albumtype != 10:
            where += " and n.albumtype=?"

        if albumtype != 10:
            # is a work or a virtual album
            countstatement = '''
                                select count(*) from (select track_id from tracknumbers n where %s group by tracknumber)
                             ''' % (where, )
            orderstatement = '''
                                select t.*, n.tracknumber, n.coverart, n.coverartid, n.rowid from tracknumbers n join tracks t
                                on n.track_id = t.rowid
                                where %s
                                group by n.tracknumber
                                order by %s
                                limit ?, ?
                             ''' % (where, orderby)
        else:
            # is a normal album
            countstatement = "select count(*) from tracks n where %s" % (where)
            orderstatement = "select * from tracks n where %s order by %s limit ?, ?" % (where, orderby)

        alphastatement = ''

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange, params

    def getQueryPlaylistTrack(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='p.track')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        #TODO: check artisttype
        artisttype = 'track'

        # playlists can contain stream entries that are not in tracks, so select with outer join
        countstatement = '''select count(*) from playlists p left outer join tracks t on t.rowid = p.track_rowid
                            where p.id = ?
                         '''
        orderstatement = '''select t.*, p.* from playlists p left outer join tracks t on t.rowid = p.track_rowid
                            where p.id = ? order by %s limit ?, ?
                         ''' % (orderby)
        #TODO: add alphastatement
        alphastatement = ''

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryComposerAlbum(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='album')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        albumtypewhere = self.get_albumtype_where(albumtype, table='aa')

        artisttype = 'composer'
        countstatement = "select count(distinct %s) from ComposerAlbum aa where composer=? and %s" % (self.distinct_composer, albumtypewhere)
        orderstatement = """
                           select album_id, album, '', '', composer, a.*, 0 from ComposerAlbum aa join albums a on
                           aa.album_id = a.id
                           where composer=? and %s
                           group by %s
                           order by %s limit ?, ?
                        """ % (albumtypewhere, self.groupby_composer, orderby)

        alphastatement = ''
        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryAlbumartistAlbum(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='album')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        albumtypewhere = self.get_albumtype_where(albumtype, table='aa')

        artisttype = 'albumartist'
        countstatement = "select count(distinct %s) from AlbumartistAlbum aa where albumartist=? and %s" % (self.distinct_albumartist, albumtypewhere)
        orderstatement = """
                           select album_id, album, '', albumartist, '', a.*, 0 from AlbumartistAlbum aa join albums a on
                           aa.album_id = a.id
                           where albumartist=? and %s
                           group by %s
                           order by %s limit ?, ?
                         """ % (albumtypewhere, self.groupby_albumartist, orderby)
        alphastatement = ''
        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryArtistAlbum(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='album')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        albumtypewhere = self.get_albumtype_where(albumtype, table='aa')

        artisttype = 'artist'
        countstatement = "select count(distinct %s) from ArtistAlbum aa where artist=? and %s" % (self.distinct_artist, albumtypewhere)
        orderstatement = """
                           select album_id, album, artist, '', '', a.*, 0 from ArtistAlbum aa join albums a on
                           aa.album_id = a.id
                           where artist=? and %s
                           group by %s
                           order by %s limit ?, ?
                         """ % (albumtypewhere, self.groupby_artist, orderby)

        alphastatement = ''
        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryGenreAlbumartistAlbum(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='album')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        albumtypewhere = self.get_albumtype_where(albumtype, table='aa')

        artisttype = 'albumartist'
        countstatement = "select count(distinct %s) from GenreAlbumartistAlbum aa where genre=? and albumartist=? and %s" % (self.distinct_albumartist, albumtypewhere)
        orderstatement = """
                           select album_id, album, '', albumartist, '', a.*, 0 from GenreAlbumartistAlbum aa join albums a on
                           aa.album_id = a.id
                           where genre=? and albumartist=? and %s
                           group by %s
                           order by %s limit ?, ?
                         """ % (albumtypewhere, self.groupby_albumartist, orderby)
        alphastatement = ''
        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryGenreArtistAlbum(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='album')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)
        
        albumtypewhere = self.get_albumtype_where(albumtype, table='aa')

        artisttype = 'artist'
        countstatement = "select count(distinct %s) from GenreArtistAlbum aa where genre=? and artist=? and %s" % (self.distinct_artist, albumtypewhere)
        orderstatement = """
                           select album_id, album, artist, '', '', a.*, 0 from GenreArtistAlbum aa join albums a on
                           aa.album_id = a.id
                           where genre=? and artist=? and %s
                           group by %s
                           order by %s limit ?, ?
                         """ % (albumtypewhere, self.groupby_artist, orderby)

        alphastatement = ''
        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryAlbumartistTrack(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='title')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        artisttype = 'albumartist'
        countstatement = "select count(*) from AlbumartistAlbumTrack aa where aa.albumartist=?"
        orderstatement = "select * from tracks where rowid in (select track_id from AlbumartistAlbumTrack aa where aa.albumartist=?) order by album, discnumber, tracknumber, title limit ?, ?"
        alphastatement = ''

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryArtistTrack(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='title')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        artisttype = 'artist'
        countstatement = "select count(*) from ArtistAlbumTrack aa where aa.artist=?"
        orderstatement = "select * from tracks where rowid in (select track_id from ArtistAlbumTrack aa where aa.artist=?) order by album, discnumber, tracknumber, title limit ?, ?"
        alphastatement = ''

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryComposerTrack(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='title')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        artisttype = 'composer'
        countstatement = "select count(*) from ComposerAlbumTrack aa where aa.composer=?"
        orderstatement = "select * from tracks where rowid in (select track_id from ComposerAlbumTrack aa where aa.composer=?) order by album, discnumber, tracknumber, title limit ?, ?"
        alphastatement = ''

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryGenreTrack(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='title')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        if self.use_albumartist:
            artisttype = 'albumartist'
            countstatement = "select count(*) from GenreAlbumartistAlbumTrack aa where aa.genre=?"
            orderstatement = "select * from tracks where rowid in (select track_id from GenreAlbumartistAlbumTrack aa where aa.genre=?) order by albumartist, album, discnumber, tracknumber, title limit ?, ?"
        else:
            artisttype = 'artist'
            countstatement = "select count(*) from GenreArtistAlbumTrack aa where aa.genre=?"
            orderstatement = "select * from tracks where rowid in (select track_id from GenreArtistAlbumTrack aa where aa.genre=?) order by artist, album, discnumber, tracknumber, title limit ?, ?"
        alphastatement = ''

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryGenreAlbumartistTrack(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='title')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        artisttype = 'albumartist'
        countstatement = "select count(*) from GenreAlbumartistAlbumTrack where genre=? and albumartist=?"
        orderstatement = "select * from tracks where rowid in (select track_id from GenreAlbumartistAlbumTrack where genre=? and albumartist=?) order by discnumber, tracknumber, title limit ?, ?"
        alphastatement = ''

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryGenreArtistTrack(self, searchcontainer, searchstring, sorttype, controllername):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='title')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        artisttype = 'artist'
        countstatement = "select count(*) from GenreArtistAlbumTrack where genre=? and artist=?"
        orderstatement = "select * from tracks where rowid in (select track_id from GenreArtistAlbumTrack where genre=? and artist=?) order by discnumber, tracknumber, title limit ?, ?" % (startingIndex, requestedCount)
        alphastatement = ''

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryAlbumartistAlbumTrack(self, searchcontainer, searchstring, sorttype, controllername, queryalbumtype):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='tracknumber')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        artisttype = 'albumartist'
        if queryalbumtype == 10:
            countstatement = "select count(*) from AlbumartistAlbumTrack where albumartist=? and album=?"
            orderstatement = "select * from tracks where rowid in (select track_id from AlbumartistAlbumTrack where albumartist=? and album=?) order by discnumber, tracknumber, title limit ?, ?"
        else:
            countstatement = "select count(*) from (select track_id from tracknumbers where albumartist=? and dummyalbum=? and albumtype=? group by tracknumber)"
            orderstatement = '''
                                select t.*, n.tracknumber, n.coverart, n.coverartid, n.rowid from tracknumbers n join tracks t
                                on n.track_id = t.rowid
                                where n.albumartist=? and n.dummyalbum=? and n.albumtype=?
                                group by n.tracknumber
                                order by n.tracknumber, t.title
                                limit ?, ?
                             '''
        alphastatement = ''

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryArtistAlbumTrack(self, searchcontainer, searchstring, sorttype, controllername, queryalbumtype):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='tracknumber')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        artisttype = 'artist'
        if queryalbumtype == 10:
            countstatement = "select count(*) from ArtistAlbumTrack where artist=? and album=?"
            orderstatement = "select * from tracks where rowid in (select track_id from ArtistAlbumTrack where artist=? and album=?) order by discnumber, tracknumber, title limit ?, ?"
        else:
            countstatement = "select count(*) from (select track_id from tracknumbers where artist=? and dummyalbum=? and albumtype=? group by tracknumber)"
            orderstatement = '''
                                select t.*, n.tracknumber, n.coverart, n.coverartid, n.rowid from tracknumbers n join tracks t
                                on n.track_id = t.rowid
                                where n.artist=? and n.dummyalbum=? and n.albumtype=?
                                group by n.tracknumber
                                order by n.tracknumber, t.title
                                limit ?, ?
                             '''
        alphastatement = ''

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryComposerAlbumTrack(self, searchcontainer, searchstring, sorttype, controllername, queryalbumtype):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='tracknumber')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        artisttype = 'composer'
        if queryalbumtype == 10:
            countstatement = "select count(*) from ComposerAlbumTrack where composer=? and album=?"
            orderstatement = "select * from tracks where rowid in (select track_id from ComposerAlbumTrack where composer=? and album=?) order by discnumber, tracknumber, title limit ?, ?"
        else:
            countstatement = "select count(*) from (select track_id from tracknumbers where composer=? and dummyalbum=? and albumtype=? group by tracknumber)"
            orderstatement = '''
                                select t.*, n.tracknumber, n.coverart, n.coverartid, n.rowid from tracknumbers n join tracks t
                                on n.track_id = t.rowid
                                where n.composer=? and n.dummyalbum=? and n.albumtype=?
                                group by n.tracknumber
                                order by n.tracknumber, t.title
                                limit ?, ?
                             '''
        alphastatement = ''

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryGenreAlbumartistAlbumTrack(self, searchcontainer, searchstring, sorttype, controllername, queryalbumtype):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='tracknumber')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        artisttype = 'albumartist'
        if queryalbumtype == 10:
            countstatement = "select count(*) from GenreAlbumartistAlbumTrack where genre=? and albumartist=? and album=?"
            orderstatement = "select * from tracks where rowid in (select track_id from GenreAlbumartistAlbumTrack where genre=? and albumartist=? and album=?) order by discnumber, tracknumber, title limit ?, ?"
        else:
            countstatement = "select count(*) from (select track_id from tracknumbers where genre=? and albumartist=? and dummyalbum=? and albumtype=? group by tracknumber)"
            orderstatement = '''
                                select t.*, n.tracknumber, n.coverart, n.coverartid, n.rowid from tracknumbers n join tracks t
                                on n.track_id = t.rowid
                                where n.genre=? and n.albumartist=? and n.dummyalbum=? and n.albumtype=?
                                group by n.tracknumber
                                order by n.tracknumber, t.title
                                limit ?, ?
                             '''
        alphastatement = ''
                             
        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    def getQueryGenreArtistAlbumTrack(self, searchcontainer, searchstring, sorttype, controllername, queryalbumtype):

        orderby, prefix, suffix, albumtype, rangefield, indexrange = self.get_orderby(sorttype, controllername, dynamic=False, orderby='tracknumber')
        rangetype, rangewhere = self.format_range(rangefield, indexrange)

        artisttype = 'artist'
        if queryalbumtype == 10:
            countstatement = "select count(*) from GenreArtistAlbumTrack where genre=? and artist=? and album=?"
            orderstatement = "select * from tracks where rowid in (select track_id from GenreArtistAlbumTrack where genre=? and artist=? and album=? and duplicate = %s) order by discnumber, tracknumber, title limit %d, %d" % (duplicate_number, startingIndex, requestedCount)
        else:
            countstatement = "select count(*) from (select track_id from tracknumbers where genre=? and artist=? and dummyalbum=? and albumtype=? group by tracknumber)"
            orderstatement = '''
                                select t.*, n.tracknumber, n.coverart, n.coverartid, n.rowid from tracknumbers n join tracks t
                                on n.track_id = t.rowid
                                where n.genre=? and n.artist=? and n.dummyalbum=? and n.albumtype=?
                                group by n.tracknumber
                                order by n.tracknumber, t.title
                                limit ?, ?
                             '''
        alphastatement = ''

        return countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange

    #############################################
    # static query post processors for containers
    #############################################

    def processQueryArtist(self, c, artisttype, prefix, suffix, idkeys, queryIDprefix):

        items = []
        res = ''
        count = 0
        for row in c:
#            log.debug("row: %s", row)
            count += 1
            rowid, artist, lastplayed, playcount = row
            playcount = str(playcount)
            if artist == '': artist = '[unknown %s]' % artisttype
            artist = escape(artist)

            fixdict = {'lastplayed':lastplayed, 'playcount':playcount}
            if prefix:
                a_prefix = self.static_makepresuffix(prefix, self.replace_pre, fixdict, 'P')
                if a_prefix: artist = '%s%s' % (a_prefix, artist)
            if suffix:
                a_suffix = self.static_makepresuffix(suffix, self.replace_suf, fixdict, 'S')
                if a_suffix: artist = '%s%s' % (artist, a_suffix)

            artistidval, browsebyid, containerstart = idkeys[artisttype]
            itemid = rowid + containerstart

            itemid = ':'.join(filter(None,(queryIDprefix, str(itemid))))
            if self.source == 'SMAPI':
                items += [(itemid, artist)]
            else:
#                itemid = ':'.join(filter(None,(queryIDprefix, str(itemid))))
                res += self.artist_didl(itemid, containerstart, artist)

        return res, items, count

    def processQueryComposer(self, c, artisttype, prefix, suffix, idkeys, queryIDprefix):

        items = []
        res = ''
        count = 0
        for row in c:
#            log.debug("row: %s", row)
            count += 1
            rowid, composer, lastplayed, playcount = row
            if composer == '': composer = '[unknown composer]'
            composer = escape(composer)

            fixdict = {'lastplayed':lastplayed, 'playcount':playcount}
            if prefix:
                a_prefix = self.static_makepresuffix(prefix, self.replace_pre, fixdict, 'P')
                if a_prefix: composer = '%s%s' % (a_prefix, composer)
            if suffix:
                a_suffix = self.static_makepresuffix(suffix, self.replace_suf, fixdict, 'S')
                if a_suffix: composer = '%s%s' % (composer, a_suffix)

            composeridval, browsebyid, containerstart = idkeys['composer']
            itemid = rowid + containerstart

            itemid = ':'.join(filter(None,(queryIDprefix, str(itemid))))
            if self.source == 'SMAPI':
                items += [(itemid, composer)]
            else:
#                itemid = ':'.join(filter(None,(queryIDprefix, str(itemid))))
                res += self.composer_didl(itemid, containerstart, composer)

        return res, items, count

    def processQueryGenre(self, c, artisttype, prefix, suffix, idkeys, queryIDprefix):
                
        items = []
        res = ''
        count = 0
        for row in c:
#            log.debug("row: %s", row)
            count += 1
            rowid, genre, lastplayed, playcount = row
            playcount = str(playcount)
            if genre == '': genre = '[unknown genre]'
            genre = escape(genre)

            fixdict = {'lastplayed':lastplayed, 'playcount':playcount}
            if prefix:
                a_prefix = self.static_makepresuffix(prefix, self.replace_pre, fixdict, 'P')
                if a_prefix: genre = '%s%s' % (a_prefix, genre)
            if suffix:
                a_suffix = self.static_makepresuffix(suffix, self.replace_suf, fixdict, 'S')
                if a_suffix: genre = '%s%s' % (genre, a_suffix)

            genreidval, browsebyid, containerstart = idkeys['genre']
            itemid = rowid      # genre rowid already includes containerstart

            itemid = ':'.join(filter(None,(queryIDprefix, str(itemid))))
            if self.source == 'SMAPI':
                items += [(itemid, genre)]
            else:
#                itemid = ':'.join(filter(None,(queryIDprefix, str(itemid))))
                res += self.genre_didl(itemid, containerstart, genre)

        return res, items, count

    def processQueryPlaylist(self, c, artisttype, prefix, suffix, idkeys, queryIDprefix):
                
        items = []
        res = ''
        count = 0
        for row in c:
#            log.debug("row: %s", row)
            count += 1
            rowid, playlist, plid, plfile, trackfile, occurs, track, track_id, track_rowid, inserted, created, lastmodified, plfilecreated, plfilelastmodified, trackfilecreated, trackfilelastmodified, scannumber, lastscanned = row
            id = plid
            if playlist == '': playlist = '[unknown playlist]'
            playlist = escape(playlist)

            '''
            fixdict = {'lastplayed':lastplayed, 'playcount':playcount}
            if prefix:
                a_prefix = self.static_makepresuffix(prefix, self.replace_pre, fixdict, 'P')
                if a_prefix: genre = '%s%s' % (a_prefix, genre)
            if suffix:
                a_suffix = self.static_makepresuffix(suffix, self.replace_suf, fixdict, 'S')
                if a_suffix: genre = '%s%s' % (genre, a_suffix)
            '''

            playlistidval, browsebyid, containerstart = idkeys['playlist']
            itemid = rowid + containerstart
            itemid = ':'.join(filter(None,(queryIDprefix, str(itemid))))
            if self.source == 'SMAPI':
                items += [(itemid, playlist)]
            else:
#                itemid = ':'.join(filter(None,(queryIDprefix, str(itemid))))
                res += self.playlist_didl(itemid, containerstart, playlist)

        return res, items, count

    def processQueryAlbum(self, c, artisttype, prefix, suffix, idkeys, queryIDprefix):

        items = []
        res = ''
        count = 0
        for row in c:
            log.debug("row: %s", row)
            count += 1
            album_id, album, artist, albumartist, composer, id, albumlist, artistlist, year, albumartistlist, duplicate, cover, artid, inserted, composerlist, tracknumbers, created, lastmodified, albumtype, lastplayed, playcount, albumsort, separated = row
            id = str(id)
            playcount = str(playcount)

#            log.debug("id: %s", id)
#            log.debug("artisttype: %s", artisttype)
#            log.debug("self.now_playing_artist: %s", self.now_playing_artist)

            # get entries/entry positions
            if artisttype == 'albumartist':
            
                if not 'albumartist' in self.album_group:
                    if albumartist == '': albumartist = '[unknown albumartist]'
                    if self.now_playing_artist == 'selected':
                        albumartist = self.get_entry(albumartist, self.now_playing_artist_selected_default, self.now_playing_artist_combiner)
                    else:
                        albumartist = self.get_entry(albumartist, self.now_playing_artist, self.now_playing_artist_combiner)
#                log.debug("albumartist: %s", albumartist)
                albumartist_entry = self.get_entry_position(albumartist, albumartistlist, self.now_playing_artist, self.now_playing_artist_combiner)
#                log.debug("albumartist_entry: %s", albumartist_entry)
                if self.now_playing_artist == 'selected':
                    artist_entry = albumartist_entry
                    artist = self.get_entry_at_position(artist_entry, artistlist)
                else:
                    artist = self.get_entry(artistlist, self.now_playing_artist, self.now_playing_artist_combiner)
#                    log.debug("artist: %s", artist)
                    artist_entry = self.get_entry_position(artist, artistlist, self.now_playing_artist, self.now_playing_artist_combiner)
#                    log.debug("artist_entry: %s", artist_entry)
                    
            elif artisttype == 'artist':
            
                if not 'artist' in self.album_group:
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
#            log.debug("album: %s", album)
            if self.now_playing_album == 'selected':
                album_entry = self.get_entry_position(album, albumlist, self.now_playing_album_selected_default, self.now_playing_album_combiner)
            else:
                album_entry = self.get_entry_position(album, albumlist, self.now_playing_album, self.now_playing_album_combiner)
#            log.debug("album_entry: %s", album_entry)

            album = escape(album)
            artist = escape(artist)
            albumartist = escape(albumartist)

#            log.debug("album: %s", album)
#            log.debug("artist: %s", artist)
#            log.debug("albumartist: %s", albumartist)

            fixdict = {'year':year, 'lastplayed':lastplayed, 'playcount':playcount, 'created':created, 'lastmodified':lastmodified, 'inserted':inserted, 'artist':artist, 'albumartist':albumartist, 'composer':composer}
            log.debug('fixdict: %s' % fixdict)
            if prefix:
                a_prefix = self.static_makepresuffix(prefix, self.replace_pre, fixdict, 'P')
                if a_prefix: album = '%s%s' % (a_prefix, album)
            if suffix:
                a_suffix = self.static_makepresuffix(suffix, self.replace_suf, fixdict, 'S')
                if a_suffix: album = '%s%s' % (album, a_suffix)
                log.debug('a_suffix: %s' % a_suffix)

            coverres = ''
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
#                log.debug("dummycoverfile: %s", dummycoverfile)
#                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                coverres = self.proxyaddress + '/wmp/' + dummycoverfile
#                log.debug("coverres: %s", coverres)
                dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath, cover=cover)
#                log.debug("dummycoverstaticfile: %s", dummycoverstaticfile)
                self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)
#                log.debug("after add_static_file")
            elif cover != '':
                cvfile = getFile(cover)
                cvpath = cover
                coverfiletype = getFileType(cvfile)
                dummycoverfile = self.dbname + '.' + str(artid) + '.' + coverfiletype
#                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                coverres = self.proxyaddress + '/wmp/' + dummycoverfile
                dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath)    # TODO: pass contenttype
                self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)

            albumidval, browsebyid, containerstart = idkeys['album']
#            itemid = album_id - containerstart
            itemid = album_id

            # TODO: check this
            if self.structure.startswith('HIERARCHY'):
                pass
            else:
                itemid ='A__%s_%s_%s__%s' % (album_entry, artist_entry, albumartist_entry, id)
#            log.debug("itemid: %s", itemid)

            itemid = ':'.join(filter(None,(queryIDprefix, str(itemid))))
            if self.source == 'SMAPI':
                items += [(itemid, album, coverres)]
            else:
#                itemid = ':'.join(filter(None,(queryIDprefix, str(itemid))))
                res += self.album_didl(itemid, containerstart, albumartist, artist, album, coverres)

        return res, items, count

    def processQueryTrack(self, c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype, \
                          passed_albumartist=None, passed_artist=None, passed_album=None, \
                          special_albumartist=None, special_artist=None, special_album=None, \
                          albumtype=None, container=None, tracktype=None):

        items = []
        ret = ''
        count = 0
        roottype = browsetype.split(':')[0]
        
        if tracktype == None: tracktype = 'T'
        call_tracktype = tracktype
        
        for row in c:
            log.debug("row: %s", row)
            count += 1

            if call_tracktype == 'S':
            
                # is a call for mediametadata for a playlist stream entry
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
                year = lastplayed = playcount = created = None
                lastmodified = inserted = None
                composerlist = genre = None
                size = discnumber = None
                codec = bitrate = samplerate = bitspersample = channels = None

            elif container == 'playlist':

                # is a call for mediametadata for tracks from a playlist            
                id, id2, duplicate, title, artistlistshort, artistlist, albumlist, genre, tracktracknumber, year, albumartistlistshort, albumartistlist, composerlistshort, composerlist, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned, titlesort, albumsort, playlist, pl_id, pl_plfile, pl_trackfile, pl_occurs, tracknumber, pl_track_id, pl_track_rowid, pl_inserted, pl_created, pl_lastmodified, pl_plfilecreated, pl_plfilelastmodified, pl_trackfilecreated, pl_trackfilelastmodified, pl_scannumber, pl_lastscanned = row

                if not id:
                    # playlist entry with no matching track - assume stream
                    # TODO: what mime to use?
                    tracktype = 'S'
                    mime = 'audio/mpeg'
                    filename = pl_trackfile
                    path = ''
                    length = 0
                    title = pl_trackfile
                    artistlist = 'Stream'
                    albumartistlist = 'Stream'
                    albumlist = 'Stream'
                    id = pl_track_id
                    titlesort = albumsort = None
            
            else:

                # is a call for mediametadata for a single track of the tracks from an album/virtual/work
                if albumtype and albumtype != 10:
                    id, id2, duplicate, title, artistlistshort, artistlist, albumlist, genre, tracktracknumber, year, albumartistlistshort, albumartistlist, composerlistshort, composerlist, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned, titlesort, albumsort, tracknumber, coverart, coverartid, rowid = row
                else:
                    id, id2, duplicate, title, artistlistshort, artistlist, albumlist, genre, tracknumber, year, albumartistlistshort, albumartistlist, composerlistshort, composerlist, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned, titlesort, albumsort = row
#                    id, id2, duplicate, title, artistlistshort, artistlist, albumlist, genre, tracknumber, year, albumartistlistshort, albumartistlist, composerlistshort, composerlist, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned, titlesort, albumsort, titleorder, alpha, alphaorder = row

            mime = fixMime(mime)
            if albumtype and albumtype != 10:
                cover, artid = self.choosecover(folderart, trackart, folderartid, trackartid, coverart, coverartid)
            else:
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
                if self.source == 'SMAPI':
                    transcode, newtype, ext = checksmapitranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)
                    if transcode:
                        mime = getMime(ext)
                else:
                    transcode, newtype = checktranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)
                
            if transcode:
                dummyfile = self.dbname + '.' + id + '.' + newtype
            elif stream:
                dummyfile = self.dbname + '.' + id + '.' + newtype
            else:
                dummyfile = self.dbname + '.' + id + '.' + filetype
            res = self.proxyaddress + '/WMPNSSv3/' + dummyfile
            if transcode:
#                log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s\ntranscodetype: %s' % (dummyfile, wsfile, wspath, contenttype, newtype))
                dummystaticfile = webserver.TranscodedFileSonos(dummyfile, wsfile, wspath, newtype, contenttype, cover=cover)
                self.proxy.wmpcontroller.add_transcoded_file(dummystaticfile)
            elif stream:
                log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s\ntranscodetype: %s' % (dummyfile, wsfile, wsfile, contenttype, newtype))
                dummystaticfile = webserver.TranscodedFileSonos(dummyfile, wsfile, wsfile, newtype, contenttype, cover=cover, stream=True)
                self.proxy.wmpcontroller.add_transcoded_file(dummystaticfile)
            else:
#                log.debug('\ndummyfile: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s' % (dummyfile, wsfile, wspath, contenttype))
                dummystaticfile = webserver.StaticFileSonos(dummyfile, wsfile, wspath, contenttype, cover=cover)
                self.proxy.wmpcontroller.add_static_file(dummystaticfile)

            if self.source == 'SMAPI':

                coverres = ''
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
    #                log.debug("dummycoverfile: %s", dummycoverfile)
    #                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                    coverres = self.proxyaddress + '/wmp/' + dummycoverfile
    #                log.debug("coverres: %s", coverres)
                    dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath, cover=cover)
    #                log.debug("dummycoverstaticfile: %s", dummycoverstaticfile)
                    self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)
    #                log.debug("after add_static_file")
                elif cover != '':
                    cvfile = getFile(cover)
                    cvpath = cover
                    coverfiletype = getFileType(cvfile)
                    dummycoverfile = self.dbname + '.' + str(artid) + '.' + coverfiletype
    #                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                    coverres = self.proxyaddress + '/wmp/' + dummycoverfile
                    dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath)    # TODO: pass contenttype
                    self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)

            else:
            
                if cover == '':
                    coverres = ''
                elif cover != '' and not cover.startswith('EMBEDDED_'):
                    cvfile = getFile(cover)
                    cvpath = cover
                    coverfiletype = getFileType(cvfile)
                    dummycoverfile = self.dbname + '.' + str(artid) + '.' + coverfiletype
                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                    dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath)    # TODO: pass contenttype
                    self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)
                elif cover.startswith('EMBEDDED_'):
                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummyfile


            iduration = int(length)
            duration = maketime(float(length))

            if title == '': title = '[unknown title]'

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

            # TODO: check this is in the correct place            
            if special_artist or special_albumartist or special_album:
                # virtual/work details have been passed in - replace artist/album with those details
                if special_artist:
                    artist = special_artist
                if special_albumartist:
                    albumartist = special_albumartist
                if specialalbumtype:
                    album = special_album

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

            fixdict = {'year':year, 'lastplayed':lastplayed, 'playcount':playcount, 'created':created,
                        'lastmodified':lastmodified, 'inserted':inserted, 'artist':artist, 'albumartist':albumartist,
                        'composer':composerlist, 'album':album, 'genre':genre, 'tracknumber':tracknumber, 'length':length,
                        'path':path, 'filename':filename, 'size':size,
                        'titlesort':titlesort, 'discnumber':discnumber,
                        'codec':codec, 'bitrate':bitrate, 'samplerate':samplerate, 'bitspersample':bitspersample, 'channels':channels,
                      }
                      
            if container == 'playlist':
                fixdict['playlist'] = playlist

            if prefix:
                p_prefix = self.static_makepresuffix(prefix, self.replace_pre, fixdict, 'P')
                if p_prefix: title = '%s%s' % (p_prefix, title)
            if suffix:
                p_suffix = self.static_makepresuffix(suffix, self.replace_suf, fixdict, 'S')
                if p_suffix: title = '%s%s' % (title, p_suffix)

            title = escape(title)
            artist = escape(artist)
            albumartist = escape(albumartist)
            album = escape(album)
            tracknumber = self.convert_tracknumber(tracknumber)

            # fix WMP urls if necessary
            res = res.replace(self.webserverurl, self.wmpurl)
            coverres = coverres.replace(self.webserverurl, self.wmpurl)

            if albumtype and albumtype != 10:
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

            full_id = '%s%s__%s_%s_%s__%s' % (tracktype, roottype, album_entry_id, artist_entry_id, albumartist_entry_id, str(id))

            if self.source == 'SMAPI':

                metadatatype = 'track'
                # metadata = (aristId, artist, composerId, composer, \
                #             albumId, album, albumArtURI, albumArtistId, \
                #             albumArtist, genreId, genre, duration)

                metadata = ('', artist, '', '', \
                            '', album, coverres, '', \
                            albumartist, '', '', iduration)
                items += [(full_id, title, mime, res, 'track', metadatatype, metadata)]

            else:


#                itemid = ':'.join(filter(None,(queryIDprefix, str(itemid))))
                ret += self.track_didl(full_id, self.track_parentid, title, albumartist, artist, album, tracknumber, duration, protocol, res)

        return ret, items, count

    #############################################
    # static query alpha processor for containers
    #############################################

    def processAlphaQuery(self, c, orderby, alphastatement):

        if ',' in orderby: orderby = orderby.split(',')[0]
        alphastatement = alphastatement % (orderby)
        log.debug(alphastatement)
        c.execute(alphastatement)
        ret = c.fetchall()
        c.close()
        if not self.proxy.db_persist_connection:
            db.close()
        return ret 

    #############################
    # static query lookup queries
    #############################

    def runQuerySpecial(self, c, rowid):
        specialstatement = "select artist, albumartist, dummyalbum from tracknumbers where rowid = '%s'" % (rowid)
        log.debug("specialstatement: %s", specialstatement)
        c.execute(specialstatement)
        row = c.fetchone()
#        log.debug("row: %s", row)
        s_artist, s_albumartist, s_album = row
        return s_artist, s_albumartist, s_album

    def runQueryAlbumartist(self, c, idkeys):

        albumartistidval, browsebyid, containerstart = idkeys['albumartist']
        rowid = albumartistidval - containerstart
        statement = """select albumartist from AlbumartistAlbum where rowid=%s""" % rowid
        log.debug(statement)
        c.execute(statement)
        albumartist, = c.fetchone()
        if albumartist == '[unknown albumartist]': albumartist = ''
        return albumartist

    def runQueryArtist(self, c, idkeys):

        artistidval, browsebyid, containerstart = idkeys['artist']
        rowid = artistidval - containerstart
        statement = """select artist from ArtistAlbum where rowid=%s""" % rowid
        log.debug(statement)
        c.execute(statement)
        artist, = c.fetchone()
        if artist == '[unknown artist]': artist = ''
        return artist

    def runQueryGenre(self, c, idkeys):
        
        genreidval, browsebyid, containerstart = idkeys['genre']
        rowid = genreidval
        statement = """select genre from genre where rowid=%s""" % rowid
        log.debug(statement)
        c.execute(statement)
        genre, = c.fetchone()
        if genre == '[unknown genre]': genre = ''
        return genre

    def runQueryAlbum(self, c, idkeys):

        albumidval, browsebyid, containerstart = idkeys['album']
        rowid = albumidval

        # album ID can be in one of two ranges, showing whether it is in the albums or albumsonly table
        if albumidval >= self.album_parentid + self.half_id_start:
            albumstatement = "select albumlist, artistlist, albumartistlist, albumtype, separated from albumsonly where rowid = %s" % (rowid)
        else:
#            albumstatement = "select albumlist, artistlist, albumartistlist, albumtype, 0 from albums where rowid = %s" % (rowid)
            albumstatement = "select albumlist, artistlist, albumartistlist, albumtype, 1 from albums where rowid = %s" % (rowid)
        log.debug("albumstatement: %s", albumstatement)
        c.execute(albumstatement)
        albumlist, artistlist, albumartistlist, albumtype, separated = c.fetchone()

        log.debug("albumlist: %s", albumlist)
        log.debug("artistlist: %s", artistlist)
        log.debug("albumartistlist: %s", albumartistlist)
        log.debug("albumtype: %s", albumtype)
        log.debug("separated: %s", separated)

#        albumlist = escape_sql(albumlist)
#        artistlist = escape_sql(artistlist)
#        albumartistlist = escape_sql(albumartistlist)

        # TODO - work out what works/virtuals needed to use one entry from list only
        '''
        albumposition = 0
        artistposition = 0
        albumartistposition = 0
        albumentry = self.get_entry_at_position(albumposition, albumlist)
        artistentry = self.get_entry_at_position(artistposition, artistlist)
        albumartistentry = self.get_entry_at_position(albumartistposition, albumartistlist)
        '''

        if albumlist == '[unknown album]': albumlist = ''
        if artistlist == '[unknown artist]': artistlist = ''
        if albumartistlist == '[unknown albumartist]': albumartistlist = ''

        return albumartistlist, artistlist, albumlist, albumtype, separated

    def runQueryPlaylist(self, c, idkeys):

        playlistidval, browsebyid, containerstart = idkeys['playlist']
        rowid = playlistidval - containerstart
        
        playliststatement = """select id from playlists where rowid=%s""" % rowid
        log.debug("playliststatement: %s", playliststatement)
        c.execute(playliststatement)
        playlistid, = c.fetchone()

        log.debug("playlistid: %s", playlistid)

        return playlistid

    def runQueryComposer(self, c, idkeys):

        composeridval, browsebyid, containerstart = idkeys['composer']
        rowid = composeridval - containerstart
        statement = """select composer from ComposerAlbum where rowid=%s""" % rowid
        log.debug(statement)
        c.execute(statement)
        composer, = c.fetchone()
        if composer == '[unknown composer]': composer = ''
        return composer

    def runQueryGenreAlbumartist(self, c, idkeys):

        albumartistidval, browsebyid, containerstart = idkeys['albumartist']
        rowid = albumartistidval - containerstart
        statement = """select genre, albumartist from GenreAlbumartistAlbum where rowid=%s""" % rowid
        log.debug(statement)
        c.execute(statement)
        genre, albumartist = c.fetchone()
        if genre == '[unknown genre]': genre = ''
        if albumartist == '[unknown albumartist]': albumartist = ''
        return genre, albumartist

    def runQueryGenreArtist(self, c, idkeys):

        artistidval, browsebyid, containerstart = idkeys['artist']
        rowid = artistidval - containerstart
        statement = """select genre, artist from GenreArtistAlbum where rowid=%s""" % rowid
        log.debug(statement)
        c.execute(statement)
        genre, artist, = c.fetchone()
        if genre == '[unknown genre]': genre = ''
        if artist == '[unknown artist]': artist = ''
        return genre, artist

    def runQueryAlbumartistAlbum(self, c, idkeys):

        albumidval, browsebyid, containerstart = idkeys['album']
        statement = """select albumartist, album, albumtype from AlbumartistAlbum where album_id=%s""" % albumidval
        log.debug(statement)
        c.execute(statement)
        albumartist, album, albumtype = c.fetchone()
        if albumartist == '[unknown albumartist]': albumartist = ''
        if album == '[unknown album]': album = ''
        return albumartist, album, albumtype

    def runQueryArtistAlbum(self, c, idkeys):

        albumidval, browsebyid, containerstart = idkeys['album']
        statement = """select artist, album, albumtype from ArtistAlbum where album_id=%s""" % albumidval
        log.debug(statement)
        c.execute(statement)
        artist, album, albumtype = c.fetchone()
        if artist == '[unknown artist]': artist = ''
        if album == '[unknown album]': album = ''
        return artist, album, albumtype

    def runQueryComposerAlbum(self, c, idkeys):

        albumidval, browsebyid, containerstart = idkeys['album']
        statement = """select composer, album, albumtype from ComposerAlbum where album_id=%s""" % albumidval
        log.debug(statement)
        c.execute(statement)
        composer, album, albumtype = c.fetchone()
        if composer == '[unknown composer]': composer = ''
        if album == '[unknown album]': album = ''
        return composer, album, albumtype

    def runQueryGenreAlbumartistAlbum(self, c, idkeys):

        albumidval, browsebyid, containerstart = idkeys['album']
        statement = """select genre, albumartist, album, albumtype from GenreAlbumartistAlbum where album_id=%s""" % albumidval
        log.debug(statement)
        c.execute(statement)
        genre, albumartist, album, albumtype = c.fetchone()
        if genre == '[unknown genre]': genre = ''
        if albumartist == '[unknown albumartist]': albumartist = ''
        if album == '[unknown album]': album = ''
        return genre, albumartist, album, albumtype

    def runQueryGenreArtistAlbum(self, c, idkeys):

        albumidval, browsebyid, containerstart = idkeys['album']
        statement = """select genre, artist, album, albumtype from GenreArtistAlbum where album_id=%s""" % albumidval
        log.debug(statement)
        c.execute(statement)
        genre, artist, album, albumtype = c.fetchone()
        if genre == '[unknown genre]': genre = ''
        if artist == '[unknown artist]': artist = ''
        if album == '[unknown album]': album = ''
        return genre, artist, album, albumtype

    #############################
    # static query xml processors
    #############################

    def artist_didl(self, id, parentid, artist):
        res  = '<container id="%s" parentID="%s" restricted="true">' % (id, parentid)
        res += '<dc:title>%s</dc:title>' % (artist)
        res += '<upnp:class>%s</upnp:class>' % (self.artist_class)
        res += '</container>'
        return res

    def genre_didl(self, id, parentid, genre):
        res  = '<container id="%s" parentID="%s" restricted="true">' % (id, parentid)
        res += '<dc:title>%s</dc:title>' % (genre)
        res += '<upnp:class>%s</upnp:class>' % (self.genre_class)
        res += '</container>'
        return res

    def composer_didl(self, id, parentid, composer):
        res  = '<container id="%s" parentID="%s" restricted="true">' % (id, parentid)
        res += '<dc:title>%s</dc:title>' % (composer)
## test this!                res += '<upnp:artist role="AuthorComposer">%s</upnp:artist>' % (composer)
        res += '<upnp:class>%s</upnp:class>' % (self.composer_class)
        res += '</container>'
        return res

    def playlist_didl(self, id, parentid, playlist):
        res  = '<container id="%s" parentID="%s" restricted="true">' % (id, parentid)
        res += '<dc:title>%s</dc:title>' % (playlist)
        res += '<upnp:class>%s</upnp:class>' % (self.playlist_class)
        res += '</container>'
        return res

    def album_didl(self, id, parentid, albumartist, artist, album, coverres):
        res  = '<container id="%s" parentID="%s" restricted="true">' % (id, parentid)
        res += '<dc:title>%s</dc:title>' % (album)
        res += '<upnp:artist role="AlbumArtist">%s</upnp:artist>' % (albumartist)
        res += '<upnp:artist role="Performer">%s</upnp:artist>' % (artist)
        res += '<upnp:class>%s</upnp:class>' % (self.album_class)
        res += '<upnp:album>%s</upnp:album>' % (album)
        if coverres != '':
            res += '<upnp:albumArtURI>%s</upnp:albumArtURI>' % (coverres)
        res += '</container>'
        return res
        
    def track_didl(self, id, parentid, title, albumartist, artist, album, tracknumber, duration, protocol, res):
        ret  = '<item id="%s" parentID="%s" restricted="true">' % (id, parentid)
        ret += '<dc:title>%s</dc:title>' % (title)
        ret += '<upnp:artist role="AlbumArtist">%s</upnp:artist>' % (albumartist)
        ret += '<upnp:artist role="Performer">%s</upnp:artist>' % (artist)
        ret += '<upnp:album>%s</upnp:album>' % (album)
        if tracknumber != 0:
            ret += '<upnp:originalTrackNumber>%s</upnp:originalTrackNumber>' % (tracknumber)
        ret += '<upnp:class>%s</upnp:class>' % (self.track_class)
        ret += '<res duration="%s" protocolInfo="%s">%s</res>' % (duration, protocol, res)
#        ret += '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">%s</desc>' % (self.wmpudn)
#        if cover != '' and not cover.startswith('EMBEDDED_'):
#            ret += '<upnp:albumArtURI>%s</upnp:albumArtURI>' % (coverres)
        ret += '</item>'
        return ret
        
    #############################
    # track id metadata processor
    #############################

    def checkspecial(self, passed):

        if passed == None: return None, None, None
        specialtype = None
        specialpassed = None
        specialrowid = None
        if 'v' in passed:
            specialtype = 'VIRTUAL'
            p = passed.split('v')
            specialpassed = p[0]
            specialrowid = p[1]
        elif 'w' in passed:
            specialtype = 'WORK'
            p = passed.split('w')
            specialpassed = p[0]
            specialrowid = p[1]
            
        return specialtype, specialpassed, specialrowid

    ###########################################
    # metadata query processor for static calls
    ###########################################

    def querymetadata(self, *args, **kwargs):

        log.debug("Mediaserver.search: %s", kwargs)

        # TODO: fix error conditions (return zero)

        controllername = kwargs.get('Controller', '')
        controlleraddress = kwargs.get('Address', '')
        log.debug('Controller: %s' % controllername)
        log.debug('Address: %s' % controlleraddress)

        log.debug("start: %.3f" % time.time())

        queryID = kwargs['QueryID']
        log.debug('QueryID: %s' % str(queryID))

        ids = queryID.split(':')
        log.debug('ids: %s' % ids)

        searchCriteria = kwargs.get('SearchCriteria', '')
        searchCriteria = self.fixcriteria(searchCriteria)
        log.debug('searchCriteria: %s' % searchCriteria.encode(enc, 'replace'))

        browsetype = kwargs.get('browsetype', '')
        log.debug('browsetype: %s' % browsetype)

        idhierarchy = browsetype.split(':')
        log.debug('idhierarchy: %s' % idhierarchy)
        idkeys = kwargs.get('idkeys', '')
        log.debug('idkeys: %s' % idkeys)

        # check if search requested
        searchcontainer = None
        searchstring = None
        if searchCriteria.startswith('SEARCH::'):
            searchtype = searchCriteria[8:].split('::')[0]
            searchstring = searchCriteria[10+len(searchtype):]
            searchcontainer = searchtype
            # TODO: check this

        if self.proxy.db_persist_connection:
            db = self.proxy.db
        else:
            db = sqlite3.connect(self.dbspec)
        c = db.cursor()

        startingIndex = int(kwargs['StartingIndex'])
        requestedCount = int(kwargs['RequestedCount'])

        items = []
        count = 0
        xml = ''

        if browsetype == '':
        
            # must have been passed a track ID plus metadata
            browsetype = 'singletrack'
            queryIDprefix = ''
            
            if len(queryID) == 32 and not ':' in queryID and not '_' in queryID:
                # track id is 32 hex chars
                # TODO: check valid hex
                passed_album = passed_artist = passed_albumartist = None                        
            elif '__' in queryID:
                    idfacets = queryID.split('__')
                    tracktype = idfacets[0][0]
                    roottype = idfacets[0][1:]
                    # TODO: check if this can occur (no album etc details)
                    if len(idfacets) == 2:
                        passed_album = passed_artist = passed_albumartist = None                        
                        queryID = idfacets[1]
                    else:
                        passedfielddata = idfacets[1].split('_')
                        passed_album = passedfielddata[0]                        
                        passed_artist = passedfielddata[1]
                        passed_albumartist = passedfielddata[2]
                        queryID = idfacets[2]

            else:
                # will cause this to fall through
                browsetype = 'invalid'

            if browsetype == 'singletrack':                        
                # split out virtual/work details if passed
                # (they contain rowids too)
                specialalbumtype, specialpassed_album, specialalbumrowid = self.checkspecial(passed_album)
                specialartisttype, specialpassed_artist, specialartistrowid = self.checkspecial(passed_artist)
                specialalbumartisttype, specialpassed_albumartist, specialalbumartistrowid = self.checkspecial(passed_albumartist)

        else:

            # have a list of entries
            rootname, indexkeys = self.get_index_parts(ids)
            log.debug('rootname: %s' % rootname)
            log.debug('indexkeys: %s' % indexkeys)

            # get sorttype
            
            # if there is only one index key and it's a dynamic one, it means we are running
            # a static query with an associated range. If there is more than one index key
            # and the first key is a dynamic one, we need to filter out the dynamic key (as
            # we have already taken account of the range in a previous query).
            # Either way we will need to insert the dynamic key into the sort type to get
            # the range, plus remove the dynamic facet of the browsetype
            
            if int(indexkeys[0]) in self.dynamic_lookup.keys():
                # get sorttype containing dynamic facet

                # if recursive is set, then there could be more than one non-key indexkey entry
                # - we need to find the first of those to put in the sorttype
                #   e.g. if we are asked for all entries for a path entry, the index keys
                #   will contain both the entry below the path and a tracks entry
                for entry in idhierarchy:
                    key, iskey, parent = idkeys[entry]
                    if iskey == False:
                        break
                sorttype = '%s_%s_%s' % (rootname, self.dynamic_lookup[int(indexkeys[0])], entry)
                # remove dynamic facet of browsetype
                browsetype = ':'.join(idhierarchy[1:])
                log.debug("browsetype: %s" % browsetype)
                
            else:
                sorttype = self.get_index_key(ids, idhierarchy)

            log.debug("sorttype: %s" % sorttype)

            # remove the last entry from the query ID if it's a container id
            # so that we can subsequently append the key selected from that container
            # - we have already pre-processed the query ID into rootname and indexkeys
            indexentryposition = len(indexkeys) - 1
            # get index entry id
            indexentryid = self.index_ids[rootname][indexentryposition]
            # check if entry is id rather than container
            isid = False if int(indexkeys[indexentryposition]) == indexentryid else True
            if not isid:            
                queryIDprefix = ':'.join(filter(None,[rootname] + indexkeys[:-1]))
            else:
                queryIDprefix = queryID

            log.debug('queryIDprefix: %s' % queryIDprefix)

        # note - there is a small amount of duplicated code per browsetype
        #        so that they are self-contained and easier to understand
        #        (may decide to genericise so users can add entries via hooks)

        ###########################
        # track mediametadata query
        ###########################

        if browsetype == 'singletrack':

            log.debug('singletrack')

            special = False
            special_artist = special_albumartist = special_album = None
            if specialalbumtype or specialartisttype or specialalbumartisttype:
                special = True
                if specialalbumtype: rowid = specialalbumrowid
                elif specialartisttype: rowid = specialartistrowid
                elif specialalbumartisttype: rowid = specialalbumartistrowid
                special_artist, special_albumartist, special_album = self.runQuerySpecial(c, rowid)

            # can be either a track (T) or a playlist stream (S)
            querystatement, prefix, suffix, artisttype = self.getQuerySingletrack(roottype, controllername, tracktype)

            totalMatches = 1
            
            log.debug("querystatement: %s", querystatement)

            c.execute(querystatement, (queryID, ))

            xml, items, count = self.processQueryTrack(c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype, \
                                                       passed_albumartist=passed_albumartist, passed_artist=passed_artist, passed_album=passed_album, \
                                                       special_albumartist=special_albumartist, special_artist=special_artist, special_album=special_album, \
                                                       tracktype=tracktype)

        ##############
        # root queries
        ##############

        elif browsetype == '!ALPHAalbum' or \
             browsetype == 'album':

            log.debug('albums')
            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryAlbum(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)
            log.debug("orderby: %s", orderby)
            log.debug("prefix: %s", prefix)
            log.debug("suffix: %s", suffix)

            c.execute(countstatement)
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                if browsetype == '!ALPHAalbum':
                    return self.processAlphaQuery(c, orderby, alphastatement)

                c.execute(orderstatement, (startingIndex, requestedCount))

                xml, items, count = self.processQueryAlbum(c, artisttype, prefix, suffix, idkeys, queryIDprefix)

        elif browsetype == '!ALPHAalbumartist' or \
             browsetype == 'albumartist':

            log.debug('albumartist')
            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryAlbumartist(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement)
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                if browsetype == '!ALPHAalbumartist':
                    return self.processAlphaQuery(c, orderby, alphastatement)

                c.execute(orderstatement, (startingIndex, requestedCount))

                xml, items, count = self.processQueryArtist(c, artisttype, prefix, suffix, idkeys, queryIDprefix)

        elif browsetype == '!ALPHAartist' or \
             browsetype == 'artist':

            log.debug('albumartist')
            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryArtist(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement)
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                if browsetype == '!ALPHAartist':
                    return self.processAlphaQuery(c, orderby, alphastatement)

                c.execute(orderstatement, (startingIndex, requestedCount))

                xml, items, count = self.processQueryArtist(c, artisttype, prefix, suffix, idkeys, queryIDprefix)

        elif browsetype == '!ALPHAcomposer' or \
             browsetype == 'composer':

            log.debug('composer')

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryComposer(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement)
            totalMatches, = c.fetchone()
            totalMatches = int(totalMatches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                if browsetype == '!ALPHAcomposer':
                    return self.processAlphaQuery(c, orderby, alphastatement)

                c.execute(orderstatement, (startingIndex, requestedCount))

                xml, items, count = self.processQueryComposer(c, artisttype, prefix, suffix, idkeys, queryIDprefix)

        elif browsetype == '!ALPHAgenre' or \
             browsetype == 'genre':

            log.debug('genre')

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryGenre(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement)
            totalMatches, = c.fetchone()
            totalMatches = int(totalMatches)
            
            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                if browsetype == '!ALPHAgenre':
                    return self.processAlphaQuery(c, orderby, alphastatement)

                c.execute(orderstatement, (startingIndex, requestedCount))
                
                xml, items, count = self.processQueryGenre(c, artisttype, prefix, suffix, idkeys, queryIDprefix)

        elif browsetype == '!ALPHAplaylist' or \
             browsetype == 'playlist':

            log.debug('playlist')

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryPlaylist(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement)
            totalMatches, = c.fetchone()
            totalMatches = int(totalMatches)
            
            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                if browsetype == '!ALPHAplaylist':
                    return self.processAlphaQuery(c, orderby, alphastatement)

                c.execute(orderstatement, (startingIndex, requestedCount))
                
                xml, items, count = self.processQueryPlaylist(c, artisttype, prefix, suffix, idkeys, queryIDprefix)

        elif browsetype == '!ALPHAtrack' or \
             browsetype == 'track':

            log.debug('track')

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryTrack(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement)
            totalMatches, = c.fetchone()
            totalMatches = int(totalMatches)
            
            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                if browsetype == '!ALPHAtrack':
                    return self.processAlphaQuery(c, orderby, alphastatement)

#                c.execute(orderstatement, (startingIndex, requestedCount))
                c.execute(orderstatement, (startingIndex, startingIndex + requestedCount))
                
                xml, items, count = self.processQueryTrack(c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype)

        #################
        # level 2 queries
        #################

        elif browsetype == 'album:track':

            log.debug('tracks for album')

            albumartistlist, artistlist, albumlist, albumtype, separated = self.runQueryAlbum(c, idkeys)
            log.debug('    albumartistlist: %s', albumartistlist)
            log.debug('    artistlist: %s', artistlist)
            log.debug('    albumlist: %s', albumlist)
            log.debug('    albumtype: %s', albumtype)
            log.debug('    separated: %s', separated)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange, params = self.getQueryAlbumTrack(searchcontainer, searchstring, sorttype, controllername, albumtype, separated)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            log.debug("params: %s", params)

            # create parameter list based on what was returned when getting statement
            paramtuple = (albumlist, )
            for param in params:
                if param == 'artist': paramtuple += (artistlist, )
                if param == 'albumartist': paramtuple += (albumartistlist, )
            if albumtype != 10:
                paramtuple += (albumtype, )

            log.debug("paramtuple: %s", paramtuple)

            c.execute(countstatement, paramtuple)
            matches, = c.fetchone()
            totalMatches = int(matches)

            log.debug("totalMatches: %s", totalMatches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                paramtuple += (startingIndex, requestedCount)

                log.debug("paramtuple: %s", paramtuple)
                
                c.execute(orderstatement, paramtuple)

                xml, items, count = self.processQueryTrack(c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype, albumtype=albumtype)

        elif browsetype == 'playlist:track':

            log.debug('tracks for playlist')

            playlistid = self.runQueryPlaylist(c, idkeys)
            log.debug('    playlistid: %s', playlistid)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryPlaylistTrack(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement, (playlistid, ))
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                c.execute(orderstatement, (playlistid, startingIndex, requestedCount))

                xml, items, count = self.processQueryTrack(c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype, container='playlist')

        elif browsetype == 'albumartist:album':

            log.debug('albums for albumartist')

            albumartist = self.runQueryAlbumartist(c, idkeys)
            log.debug('    albumartist: %s', albumartist)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryAlbumartistAlbum(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement, (albumartist, ))
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                c.execute(orderstatement, (albumartist, startingIndex, requestedCount))

                xml, items, count = self.processQueryAlbum(c, artisttype, prefix, suffix, idkeys, queryIDprefix)

        elif browsetype == 'artist:album':
             
            log.debug('albums for artist')

            artist = self.runQueryArtist(c, idkeys)
            log.debug('    artist: %s', artist)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryArtistAlbum(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement, (artist, ))
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                c.execute(orderstatement, (artist, startingIndex, requestedCount))

                xml, items, count = self.processQueryAlbum(c, artisttype, prefix, suffix, idkeys, queryIDprefix)

        elif browsetype == 'composer:album':

            log.debug('albums for composer')

            composer = self.runQueryComposer(c, idkeys)
            log.debug('    composer: %s', composer)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryComposerAlbum(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement, (composer, ))
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                c.execute(orderstatement, (composer, startingIndex, requestedCount))

                xml, items, count = self.processQueryAlbum(c, artisttype, prefix, suffix, idkeys, queryIDprefix)

        elif browsetype == 'genre:albumartist':

            # Artists for genre
            log.debug('albumartists for genre')

            genre = self.runQueryGenre(c, idkeys)
            log.debug('    genre: %s', genre)
            
            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryGenreAlbumartist(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement, (genre, ))
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                c.execute(orderstatement, (genre, startingIndex, requestedCount))

                xml, items, count = self.processQueryArtist(c, artisttype, prefix, suffix, idkeys, queryIDprefix)

        elif browsetype == 'genre:artist':

            # Artists for genre
            log.debug('artists for genre')

            genre = self.runQueryGenre(c, idkeys)
            log.debug('    genre: %s', genre)
            
            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryGenreArtist(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement, (genre, ))
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                c.execute(orderstatement, (genre, startingIndex, requestedCount))

                xml, items, count = self.processQueryArtist(c, artisttype, prefix, suffix, idkeys, queryIDprefix)

        #################
        # level 3 queries
        #################

        elif browsetype == 'genre:albumartist:album':

            log.debug('albums for genre and albumartist')

            genre, albumartist = self.runQueryGenreAlbumartist(c, idkeys)
            log.debug('    genre: %s', genre)
            log.debug('    albumartist: %s', albumartist)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryGenreAlbumartistAlbum(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement, (genre, albumartist))
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                c.execute(orderstatement, (genre, albumartist, startingIndex, requestedCount))

                xml, items, count = self.processQueryAlbum(c, artisttype, prefix, suffix, idkeys, queryIDprefix)

        elif browsetype == 'genre:artist:album':

            log.debug('albums for genre and artist')

            genre, artist = self.runQueryGenreArtist(c, idkeys)
            log.debug('    genre: %s', genre)
            log.debug('    artist: %s', artist)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryGenreArtistAlbum(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement, (genre, artist))
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                c.execute(orderstatement, (genre, artist, startingIndex, requestedCount))

                xml, items, count = self.processQueryAlbum(c, artisttype, prefix, suffix, idkeys, queryIDprefix)

        #################################
        # all tracks non track containers
        #################################

        elif browsetype == 'albumartist:track':

            log.debug('tracks for albumartist')

            albumartist = self.runQueryAlbumartist(c, idkeys)
            log.debug('    albumartist: %s', albumartist)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryAlbumartistTrack(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement, (albumartist, ))
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                c.execute(orderstatement, (albumartist, startingIndex, requestedCount))

                xml, items, count = self.processQueryTrack(c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype)

        elif browsetype == 'artist:track':

            log.debug('tracks for artist')

            artist = self.runQueryArtist(c, idkeys)
            log.debug('    artist: %s', artist)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryArtistTrack(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement, (artist, ))
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                c.execute(orderstatement, (artist, startingIndex, requestedCount))

                xml, items, count = self.processQueryTrack(c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype)

        elif browsetype == 'composer:track':

            log.debug('tracks for composer')

            composer = self.runQueryComposer(c, idkeys)
            log.debug('    composer: %s', composer)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryComposerTrack(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement, (artist, ))
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                c.execute(orderstatement, (composer, startingIndex, requestedCount))

                xml, items, count = self.processQueryTrack(c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype)

        elif browsetype == 'genre:track':

            log.debug('tracks for genre')

            genre = self.runQueryGenre(c, idkeys)
            log.debug('    genre: %s', genre)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryGenreTrack(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement, (genre, ))
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                c.execute(orderstatement, (genre, startingIndex, requestedCount))

                xml, items, count = self.processQueryTrack(c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype)

        elif browsetype == 'genre:albumartist:track':

            log.debug('tracks for genre/albumartist')

            genre, albumartist = self.runQueryGenreAlbumartist(c, idkeys)
            log.debug('    genre: %s', genre)
            log.debug('    albumartist: %s', albumartist)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryGenreAlbumartistTrack(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement, (genre, albumartist))
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                c.execute(orderstatement, (genre, albumartist, startingIndex, requestedCount))

                xml, items, count = self.processQueryTrack(c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype)

        elif browsetype == 'genre:artist:track':

            log.debug('tracks for genre/artist')

            genre, artist = self.runQueryGenreArtist(c, idkeys)
            log.debug('    genre: %s', genre)
            log.debug('    artist: %s', artist)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryGenreArtistTrack(searchcontainer, searchstring, sorttype, controllername)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            c.execute(countstatement, (genre, artist))
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                c.execute(orderstatement, (genre, artist, startingIndex, requestedCount))

                xml, items, count = self.processQueryTrack(c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype)

        ##############################
        # tracks from track containers
        ##############################

        elif browsetype == 'albumartist:album:track':

            log.debug('tracks for albumartist/album')

            albumartist, album, albumtype = self.runQueryAlbumartistAlbum(c, idkeys)
            log.debug('    albumartist: %s', albumartist)
            log.debug('    album: %s', album)
            log.debug('    albumtype: %s', albumtype)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryAlbumartistAlbumTrack(searchcontainer, searchstring, sorttype, controllername, albumtype)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            paramtuple = (albumartist, album)
            if albumtype != 10:
                paramtuple += (albumtype, )
                
            c.execute(countstatement, paramtuple)
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                paramtuple += (startingIndex, requestedCount)
                c.execute(orderstatement, paramtuple)

                xml, items, count = self.processQueryTrack(c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype, passed_albumartist=albumartist, passed_album=album, albumtype=albumtype)

        elif browsetype == 'artist:album:track':

            log.debug('tracks for artist/album')

            artist, album, albumtype = self.runQueryArtistAlbum(c, idkeys)
            log.debug('    artist: %s', artist)
            log.debug('    album: %s', album)
            log.debug('    albumtype: %s', albumtype)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryArtistAlbumTrack(searchcontainer, searchstring, sorttype, controllername, albumtype)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            paramtuple = (artist, album)
            if albumtype != 10:
                paramtuple += (albumtype, )
                
            c.execute(countstatement, paramtuple)
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                paramtuple += (startingIndex, requestedCount)
                c.execute(orderstatement, paramtuple)

                xml, items, count = self.processQueryTrack(c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype, passed_artist=artist, passed_album=album, albumtype=albumtype)

        elif browsetype == 'composer:album:track':

            log.debug('tracks for composer/album')

            composer, album, albumtype = self.runQueryComposerAlbum(c, idkeys)
            log.debug('    composer: %s', composer)
            log.debug('    album: %s', album)
            log.debug('    albumtype: %s', albumtype)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryComposerAlbumTrack(searchcontainer, searchstring, sorttype, controllername, albumtype)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            paramtuple = (composer, album)
            if albumtype != 10:
                paramtuple += (albumtype, )
                
            c.execute(countstatement, paramtuple)
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                paramtuple += (startingIndex, requestedCount)
                c.execute(orderstatement, paramtuple)

                xml, items, count = self.processQueryTrack(c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype, passed_album=album, albumtype=albumtype)

        elif browsetype == 'genre:albumartist:album:track':

            log.debug('tracks for genre/albumartist/album')

            genre, albumartist, album, albumtype = self.runQueryGenreAlbumartistAlbum(c, idkeys)
            log.debug('    genre: %s', genre)
            log.debug('    albumartist: %s', albumartist)
            log.debug('    album: %s', album)
            log.debug('    albumtype: %s', albumtype)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryGenreAlbumartistAlbumTrack(searchcontainer, searchstring, sorttype, controllername, albumtype)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            paramtuple = (genre, albumartist, album)
            if albumtype != 10:
                paramtuple += (albumtype, )
                
            c.execute(countstatement, paramtuple)
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                paramtuple += (startingIndex, requestedCount)
                c.execute(orderstatement, paramtuple)

                xml, items, count = self.processQueryTrack(c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype, passed_albumartist=albumartist, passed_album=album, albumtype=albumtype)

        elif browsetype == 'genre:artist:album:track':

            log.debug('tracks for genre/artist/album')

            genre, artist, album, albumtype = self.runQueryGenreArtistAlbum(c, idkeys)
            log.debug('    genre: %s', genre)
            log.debug('    artist: %s', artist)
            log.debug('    album: %s', album)
            log.debug('    albumtype: %s', albumtype)

            countstatement, orderstatement, alphastatement, orderby, prefix, suffix, artisttype, rangetype, indexrange = self.getQueryGenreArtistAlbumTrack(searchcontainer, searchstring, sorttype, controllername, albumtype)

            log.debug("countstatement: %s", countstatement)
            log.debug("orderstatement: %s", orderstatement)
            log.debug("alphastatement: %s", alphastatement)

            paramtuple = (genre, artist, album)
            if albumtype != 10:
                paramtuple += (albumtype, )
                
            c.execute(countstatement, paramtuple)
            matches, = c.fetchone()
            totalMatches = int(matches)

            if rangetype == 'count':
                totalMatches, orderstatement, alphastatement = self.adjust_for_range(indexrange, totalMatches, orderstatement, alphastatement)
                
            if totalMatches != 0:

                paramtuple += (startingIndex, requestedCount)
                c.execute(orderstatement, paramtuple)

                xml, items, count = self.processQueryTrack(c, artisttype, prefix, suffix, idkeys, queryIDprefix, browsetype, passed_artist=artist, passed_album=album, albumalbumtype=albumtype)

        c.close()
        if not self.proxy.db_persist_connection:
            db.close()

        log.debug("end: %.3f" % time.time())

        if self.source == 'SMAPI':
            return items, totalMatches, startingIndex, 'container'
        elif self.source == 'UPNP':
            res  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            res += xml        
            res += '</DIDL-Lite>'
            log.debug("SEARCH res: %s", res)
            return res, count, totalMatches

    #########################
    # dynamic query processor
    #########################

    def dynamicQuery(self, *args, **kwargs):

        # TODO: fix error conditions (return zero)
        log.debug("Mediaserver.dynamicQuery: %s", kwargs)

        log.debug("start: %.3f" % time.time())

        # process params
        ################

        controllername = kwargs.get('Controller', '')
        controlleraddress = kwargs.get('Address', '')
        log.debug('Controller: %s' % controllername)
        log.debug('Address: %s' % controlleraddress)

        queryID = kwargs.get('QueryID','')
        log.debug('queryID: %s' % str(queryID))
        
        ids = queryID.split(':')
        log.debug('ids: %s' % ids)
        
        searchCriteria = kwargs['SearchCriteria']
        searchCriteria = self.fixcriteria(searchCriteria)
        log.debug('searchCriteria: %s' % searchCriteria)
        #log.debug('searchCriteria: %s' % searchCriteria.encode(enc, 'replace'))

        SMAPI = kwargs.get('SMAPI', '')
        log.debug('SMAPI: %s' % SMAPI)
        if SMAPI.startswith('!ALPHA'):
            idhierarchy = [SMAPI[6:]]
        else:
            idhierarchy = SMAPI.split(':')
        log.debug('idhierarchy: %s' % idhierarchy)
        idkeys = kwargs.get('idkeys', [])
        log.debug('idkeys: %s' % idkeys)

        startingIndex = int(kwargs['StartingIndex'])
        requestedCount = int(kwargs['RequestedCount'])

        wassearch = kwargs.get('wassearch', False)

        # browse can be called under the following scenarios:
        #
        # 1) For a root container
        #    - idhierarchy will contain a single entry
        # 2) For a container further down the hierarchy,
        #    which could be a user defined container
        #    - idhierarchy will contain a set of entries
        # 3) For alpha keys for a root container
        #    - idhierarchy will contain a single entry
        #      that starts with '!ALPHA'
        # 4) For search of a root container
        #    - idhierarchy will contain a single entry
        #    - searchCriteria contains the search string
        # 5) For search of a user defined container,
        #    which could be single or multiple containers,
        #    or a container further down the hierarchy
        #    - idhierarchy will contain a single entry of 'usersearch'
        #    - id passed points to usersearch entry with container details
        #    - searchCriteria contains the search string
        # 6) For a container further down the hierarchy
        #    that is the result of a search
        #    - wassearch is set to True
        #
        # the table to be queried depends on the scenario. Mostly the table
        # is tracks, but playlists and workvirtuals can also be queried.
        # Note that for user defined indexes the table is actually a list
        # in memory (loaded from the ini)

        # set up return list
        items = []

        # get the default table to query if only a single container is
        # requested and it's not a user defined search
        browsetable = self.get_table(idhierarchy[-1], idhierarchy[-1])
        log.debug(browsetable)

        # check if search requested
        searchcontainer = None
        if searchCriteria != '':
            searchtype = idhierarchy[-1]
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
        db.row_factory = sqlite3.Row
        c = db.cursor()

        # default where clause
        where = ''

        # process any ALPHA request and exit
        ####################################

        if SMAPI.startswith('!ALPHA'):
            # process alpha request
            
            field = self.convert_field_name(idhierarchy[0])
            browsetable = self.get_table(field, field)
            alphastatement = self.smapialphastatement % (field, '%s %s group by %s order by %s' % (browsetable, where, field, field))
            log.debug(alphastatement)
            c.execute(alphastatement)
            ret = c.fetchall()
            c.close()
            db.row_factory = None
            if not self.proxy.db_persist_connection:
                db.close()
            return ret

        # process hierarchy
        ###################

        # convert keys to integers (except rootname)
        ids = [i if i.startswith('R') else int(i) for i in ids]

        # ID is always passed prepended with root name
        rootname, indexkeys = self.get_index_parts(ids)
        
        log.debug('rootname: %s' % rootname)
        log.debug('indexkeys: %s' % indexkeys)

        # walk through items in hierarchy, getting SQL keys when id passed
        itemidprefix = rootname
        indexsuffix = ''
        prevtitle = ''

        for entry in idhierarchy:

            idval, browsebyid, containerstart = idkeys[entry]

#            # get index entry name
#            indexentryname = self.hierarchies[rootname][idhierarchy.index(entry)]

#            firstbrowsetype, firstbrowsebyid = self.get_index(idval, 'SINGLE', root=root)

            if entry == 'usersearch':
                # save id used
                itemidprefix = ':'.join(filter(None,(itemidprefix, str(idval))))
            
            if entry == 'usersearch' and len(idhierarchy) != 1:
                # don't process entry if it's a user search key
                # and there are further entries
                continue
            
            field = self.convert_field_name(entry)
            log.debug('field: %s' % field)

            path_name = '%s_%s' % (rootname, field)
            log.debug('path_name: %s' % path_name)

            # process for id's only (not containers and usersearch)
            if searchcontainer != 'usersearch' and browsebyid:

                if path_name in self.path_index_entries.keys():
                    # is a user defined path index

                    # set the suffix for the next index entry
# CHECK THIS                    indexsuffix = idval - containerstart
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
        ################################
        
        user_index = False
        searchtype = ''
        searchname = ''
        rangetype = None
        if entry.lower() != 'track':

            field = self.convert_field_name(entry)
            log.debug(field)
            path_name = '%s_%s' % (rootname, field)
            log.debug('path_name: %s' % path_name)

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
                    searchtype, searchname, searchfields = self.user_search_entries[idval]
                    log.debug(searchtype)
                    log.debug(searchname)
                    log.debug(searchfields)
                    if searchtype == 'multi' or searchtype == 'lower':
                        pos = 0
                        itemidprefixes = {}
                        for searchroot, searchfieldparent, searchfield in searchfields:
                            convertedsearchfield = self.convert_field_name(searchfield)
                            searchlist.append(convertedsearchfield)
                            searchparentlist.append(searchfieldparent)
                            searchconvertlookup[convertedsearchfield] = searchfield
                            searchpositionlookup[searchfield] = pos
                            pos += 1

                            itemidprefixes[searchfield] = searchroot

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

                    # TODO: explain this code and work out what indexsuffix was intended for
                    
                    ids += [self.index_ids[rootname][len(idhierarchy) - 1]]

                    log.debug("ids: %s" % ids)

#                    sorttype = '%s_%s%s' % (idhierarchy[0], idhierarchy[-1], indexsuffix)
                    sorttype = self.get_index_key(ids, idhierarchy)
                    log.debug("sorttype: %s" % sorttype)

                log.debug(sorttype)

                # get sort data
                rangefield, indexrange, sortorder, entryprefix, entrysuffix, albumtype = self.get_orderby(sorttype, controllername, dynamic=True)

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
            log.debug(self.path_index_entries)

            if path_name in self.path_index_entries.keys():
            
                # is a user defined path index
                
                user_index = True
                recordtype = 'userindex'
                index_entries = self.path_index_entries[path_name]
                totalMatches = len(index_entries)
                rowid = 1
                for path, title in index_entries:
                    itemid = rowid + containerstart
                    itemid = ':'.join(filter(None,(itemidprefix, str(itemid))))

                    if numprefix:
                        prefix = self.dynamic_makepresuffix([prefixes[0]], self.replace_pre, [prevtitle], 'P')
                        if prefix: title = '%s%s' % (prefix, title)
                    if numsuffix:
                        suffix = self.dynamic_makepresuffix([suffixes[0]], self.replace_suf, [prevtitle], 'S')
                        if suffix: title = '%s%s' % (title, suffix)

                    items += [(itemid, escape(title))]
                    rowid += 1

                log.debug("items: %s" % items)

            else:

                if not searchcontainer:

                    # if not search, process any range

                    if indexrange:

                        if rangefield == '': rangefield = field

                        rangetype, rangewhere = self.format_range(rangefield, indexrange)
                        
                        if rangetype == 'where':

                            # add it to the start of the where clause
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
                        elif browsetable == 'tracks':
                            singlestatement = "select '%s' as recordtype, rowid, '', '', '', '', '', '', '', '', '', '', '', '', folderart, trackart, '', '', '', '', '', folderartid, trackartid, %s from %s %s group by %s order by %s" % (field, selectfield, browsetable, where, groupfield, orderfield)
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
                        searchhierarchy = self.hierarchies[searchroot]
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
                    log.debug(field)

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

                log.debug("countstatement: %s", countstatement)
                log.debug("statement: %s", statement)

        else:

            # tracks

            sorttype = '%s_%s%s' % (idhierarchy[0], idhierarchy[-1], indexsuffix)
            log.debug(sorttype)
            # get sort data
            rangefield, indexrange, sortorder, entryprefix, entrysuffix, albumtype = self.get_orderby(sorttype, controllername, dynamic=True)
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
            log.debug('totalMatches: %s' % totalMatches)

            # check if we need to apply a count to the query
            if rangetype == 'count':

                rangeset, rangecount, units = indexrange
                # rangeset can be either 'first' or 'last'
                # rangecount is a number of records to retrieve
                rangecount = int(rangecount)
                # units will be 'records'

                # adjust the SQL to limit what we get back
                # we need to limit the initial (full) result, which may be further 
                # limited by the requested count
                
                # for the count, we'll just limit what was returned
                originalMatches = totalMatches
                if totalMatches > rangecount:
                    totalMatches = rangecount
                    log.debug('range adjusted count: %s' % totalMatches)

                # for the select, we need to add a bounding limit to the initial
                # query before applying the existing requested count/startindex
                
                # work out bounding limit clause
                if rangeset == 'first':
                    limitclause = ' limit %s)' % rangecount
                elif rangeset == 'last':
                    limitclause = ' limit %s, %s)' % (originalMatches - rangecount, rangecount)
                
                # add outer select
                statement = 'SELECT * from (%s' % statement
                
                # insert outer select limit before call limit
                statement = statement.replace(' limit ', ' %s limit ' % limitclause)

                log.debug('range adjusted statement: %s' % statement)
                
            if totalMatches > 0:

                c.execute(statement, (startingIndex, requestedCount))

                for row in c:

#                    log.debug("row: %s", row)
                    log.debug("keys: %s", row.keys())

                    recordtype = row['recordtype']
#                    log.debug(recordtype)
                    if recordtype != 'track':

                        rowid = row['rowid']

                        if searchcontainer and len(searchlist) > 1:
                            title = row[23]          # field may change, position won't
                        else:
                            title = row[2]

                        log.debug("recordtype, rowid, title: %s, %s, %s" % (recordtype, rowid, title))

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
                            prefix = self.dynamic_makepresuffix(prefixes, self.replace_pre, prefixdata, 'P')
                            if prefix: title = '%s%s' % (prefix, title)
                        if numsuffix:
    #                        suffixdata = list(row[suffixstart:suffixstart+numsuffix])
                            suffixdata = []
                            for i in range(numsuffix):
                                suffixdata.append(row[suffixstart+i])
                            suffix = self.dynamic_makepresuffix(suffixes, self.replace_suf, suffixdata, 'S')
                            if suffix: title = '%s%s' % (title, suffix)

                        title = escape(title)
#                        log.debug(title)


                        coverres = ''

                        folderart = None if not 'folderart' in row.keys() else row['folderart']
                        trackart = None if not 'trackart' in row.keys() else row['trackart']
                        folderartid = None if not 'folderartid' in row.keys() else row['folderartid']
                        trackartid = None if not 'trackartid' in row.keys() else row['trackartid']
                        
                        log.debug('%s, %s, %s, %s' % (folderart, trackart, folderartid, trackartid))
                        
                        if folderart or trackart:
                            cover, artid = self.choosecover(folderart, trackart, folderartid, trackartid)


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
                #                log.debug("dummycoverfile: %s", dummycoverfile)
                #                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                                coverres = self.proxyaddress + '/wmp/' + dummycoverfile
                #                log.debug("coverres: %s", coverres)
                                dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath, cover=cover)
                #                log.debug("dummycoverstaticfile: %s", dummycoverstaticfile)
                                self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)
                #                log.debug("after add_static_file")
                            elif cover != '':
                                cvfile = getFile(cover)
                                cvpath = cover
                                coverfiletype = getFileType(cvfile)
                                dummycoverfile = self.dbname + '.' + str(artid) + '.' + coverfiletype
                #                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                                coverres = self.proxyaddress + '/wmp/' + dummycoverfile
                                dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath)    # TODO: pass contenttype
                                self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)

                        log.debug(coverres)





                        if searchtype == 'lower':

                            log.debug('itemidprefixes: %s' % itemidprefixes)

                        elif searchtype == 'multi':
#                        if searchcontainer and len(searchlist) > 1:
                            # if we are processing multiple containers, we need
                            # to set the prefix appropriately
                            rowitemidprefix = itemidprefixes[recordtype]
                        else:
                            rowitemidprefix = itemidprefix

                        # if we are searching, need to capture that for subsequent calls (so they are dynamic too)
                        if searchcontainer or wassearch:
                            rowitemidprefix = '%s%s' % ('S', rowitemidprefix)

                        itemid = rowid + containerstart
                        itemid = ':'.join(filter(None,(rowitemidprefix, str(itemid))))
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

                        tracktype = 'T'

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

                            tracktype = 'S'

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
                            prefix = self.dynamic_makepresuffix(prefixes, self.replace_pre, prefixdata, 'P')
                            if prefix: title = '%s%s' % (prefix, title)
                        if numsuffix:
#                            suffixdata = list(row[suffixstart:suffixstart+numsuffix])
                            suffixdata = []
                            for i in range(numsuffix):
                                suffixdata.append(row[suffixstart+i])
                            suffix = self.dynamic_makepresuffix(suffixes, self.replace_suf, suffixdata, 'S')
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

                        if SMAPI != '' and self.source == 'SMAPI':
                            transcode, newtype, ext = checksmapitranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)
                            if transcode:
                                mime = getMime(ext)
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

                        if self.source == 'SMAPI':

                            coverres = ''
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
                #                log.debug("dummycoverfile: %s", dummycoverfile)
                #                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                                coverres = self.proxyaddress + '/wmp/' + dummycoverfile
                #                log.debug("coverres: %s", coverres)
                                dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath, cover=cover)
                #                log.debug("dummycoverstaticfile: %s", dummycoverstaticfile)
                                self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)
                #                log.debug("after add_static_file")
                            elif cover != '':
                                cvfile = getFile(cover)
                                cvpath = cover
                                coverfiletype = getFileType(cvfile)
                                dummycoverfile = self.dbname + '.' + str(artid) + '.' + coverfiletype
                #                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                                coverres = self.proxyaddress + '/wmp/' + dummycoverfile
                                dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath)    # TODO: pass contenttype
                                self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)

                        else:

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

                        # TODO: fix entry IDs
#                        full_id = '%s%s__%s_%s_%s__%s' % (tracktype, idhierarchy[0], album_entry_id, artist_entry_id, albumartist_entry_id, str(id))
                        full_id = '%s%s__%s_%s_%s__%s' % (tracktype, idhierarchy[0], 0, 0, 0, str(id))

                        metadata = ('', artist, '', '', \
                                    '', album, coverres, '', \
                                    albumartist, '', '', iduration)
                        items += [(full_id, title, mime, res, 'track', metadatatype, metadata)]

        c.close()
        db.row_factory = None
        if not self.proxy.db_persist_connection:
            db.close()

        log.debug("end: %.3f" % time.time())

        if self.source == 'SMAPI':

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
                    ret += '<container id="%s" parentID="%s" restricted="true">' % (id, queryID)
                    ret += '<dc:title>%s</dc:title>' % (title)
                    
                    # recordtype will contain type of last entry - assume all entries are the same type
                    if recordtype == 'artist':
                        classtype = 'object.container.person.musicArtist'
                    elif recordtype == 'albumartist':
                        classtype = 'object.container.person.musicArtist'
                    elif recordtype == 'album':
                        classtype = 'object.container.album.musicAlbum'
                    elif recordtype == 'composer':
                        classtype = 'object.container.person.musicArtist'
                    elif recordtype == 'genre':
                        classtype = 'object.container.genre.musicGenre'
                    elif recordtype == 'playlist':
                        classtype = 'object.container.playlistContainer'
                    else:
                        classtype = 'object.container'

                    ret += '<upnp:class>%s</upnp:class>' % (classtype)
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












    def keywordQuery(self, *args, **kwargs):

        # TODO: fix error conditions (return zero)
        log.debug("Mediaserver.keywordQuery: %s", kwargs)

        log.debug("start: %.3f" % time.time())

        # process params
        ################

        controllername = kwargs.get('Controller', '')
        controlleraddress = kwargs.get('Address', '')
        log.debug('Controller: %s' % controllername)
        log.debug('Address: %s' % controlleraddress)

        queryID = kwargs.get('QueryID','')
        log.debug('queryID: %s' % str(queryID))
        
        ids = queryID.split(':')
        log.debug('ids: %s' % ids)
        
        term = kwargs.get('term', None)
        log.debug("term: %s" % term)

        searchfields = kwargs.get('searchfields', None)
        log.debug("searchfields: %s" % searchfields)

        SMAPI = kwargs.get('SMAPI', '')
        log.debug('SMAPI: %s' % SMAPI)
        if SMAPI.startswith('!ALPHA'):
            idhierarchy = [SMAPI[6:]]
        else:
            idhierarchy = SMAPI.split(':')
        log.debug('idhierarchy: %s' % idhierarchy)
        idkeys = kwargs.get('idkeys', [])
        log.debug('idkeys: %s' % idkeys)

        startingIndex = int(kwargs['StartingIndex'])
        requestedCount = int(kwargs['RequestedCount'])

        wassearch = kwargs.get('wassearch', False)

        # keyword search can be called under the following scenarios:
        #    TODO:

        # set up return list
        items = []
        extras = []

        # set up cursor (note we want to refer to fields by name)
        if self.proxy.db_persist_connection:
            db = self.proxy.db
        else:
            db = sqlite3.connect(self.dbspec)
        db.row_factory = sqlite3.Row
        c = db.cursor()

        # process hierarchy
        ###################

        # convert keys to integers (except rootname)
        ids = [i if i.startswith('R') else int(i) for i in ids]

        # ID is always passed prepended with root name
        rootname, indexkeys = self.get_index_parts(ids)
        
        log.debug('rootname: %s' % rootname)
        log.debug('indexkeys: %s' % indexkeys)

        itemidprefix = rootname

        # process term
        albumartist = album = track = None
        termitems = term.split(' ')
        orderby = ''
        for subterm in termitems:
            subterm = subterm.lower()
            if subterm.startswith('artist='):
                albumartist = subterm[7:]
                orderby = ','.join(filter(None,(orderby, 'albumartist')))
            elif subterm.startswith('albumartist='):
                albumartist = subterm[12:]
                orderby = ','.join(filter(None,(orderby, 'albumartist')))
            if subterm.startswith('album='):
                album = subterm[6:]
                orderby = ','.join(filter(None,(orderby, 'album')))
            if subterm.startswith('track='):
                track = subterm[6:]
                orderby = ','.join(filter(None,(orderby, 'title')))
        log.debug('orderby: %s' % orderby)

        if not albumartist and not album and not track:
            return items, -2, -2, 'container'
            
        log.debug('albumartist=%s, album=%s, track=%s' % (albumartist, album, track))
        albumartistwhere = '' if not albumartist else "albumartist like '%%%s%%'" % (albumartist)
        albumwhere = '' if not album else "album like '%%%s%%'" % (album)
        trackwhere = '' if not track else "title like '%%%s%%'" % (track)
        where = ' and '.join(filter(None,(albumartistwhere, albumwhere, trackwhere)))
        log.debug('where: %s' % where)

#        countstatement = "select count(title) from tracks where %s" % (where)
#        statement = "select 'track' as recordtype, rowid, id, title, artist, album, genre, tracknumber, albumartist, composer, codec, length, path, filename, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, folderartid, trackartid from tracks where %s order by %s limit ?, ?" % (where, orderby)

        countstatement  = "select sum(total) from ("
        countstatement += "select count(*) as total from (select title from tracks where %s) '1'" % where
        countstatement += " union all "
        countstatement += "select count(*) as total from (select album from tracks where %s group by album) '2'" % where
        countstatement += " union all "
        countstatement += "select count(*) as total from (select albumartist from tracks where %s group by albumartist) '3'" % where
        countstatement += ")"
        
        statement  = "select * from (select 'track' as recordtype, rowid, id, title, artist, album, genre, tracknumber, albumartist, composer, codec, length, path, filename, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, folderartid, trackartid from tracks where %s order by %s) '1'" % (where, orderby)
        statement += " union all "
        statement += "select * from (select 'album' as recordtype, rowid, '', '', '', album, '', '', '', '', '', '', '', '', folderart, trackart, '', '', '', '', '', folderartid, trackartid from tracks where %s group by album order by %s) '2'" % (where, orderby)
        statement += " union all "
        statement += "select * from (select 'albumartist' as recordtype, rowid, '', '', '', '', '', '', albumartist, '', '', '', '', '', folderart, trackart, '', '', '', '', '', folderartid, trackartid from tracks where %s group by albumartist order by %s) '3'" % (where, orderby)
        statement += " limit ?, ?"

        log.debug("countstatement: %s", countstatement)
        log.debug("statement: %s", statement)

        c.execute(countstatement)
        totalMatches, = c.fetchone()
        log.debug('totalMatches: %s' % totalMatches)

#        foundalbumartists = []
#        foundalbumartistalbums = []            

        extraskeydata = {}
        for searchroot, searchfieldparent, searchfield in searchfields:        
            extraskeydata['%s:root' % searchfield] = searchroot
            extraskeydata['%s:parent' % searchfield] = searchfieldparent
        
        if totalMatches > 0:

            c.execute(statement, (startingIndex, requestedCount))

            for row in c:

                log.debug("row: %s", row)
                log.debug("keys: %s", row.keys())

                recordtype = row['recordtype']
                rowid = row['rowid']

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

                tracktype = 'T'

                cover, artid = self.choosecover(folderart, trackart, folderartid, trackartid)
                
                if recordtype == 'track':

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

                    if SMAPI != '' and self.source == 'SMAPI':
                        transcode, newtype, ext = checksmapitranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)
                        if transcode:
                            mime = getMime(ext)
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

                if self.source == 'SMAPI':

                    coverres = ''
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
        #                log.debug("dummycoverfile: %s", dummycoverfile)
        #                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                        coverres = self.proxyaddress + '/wmp/' + dummycoverfile
        #                log.debug("coverres: %s", coverres)
                        dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath, cover=cover)
        #                log.debug("dummycoverstaticfile: %s", dummycoverstaticfile)
                        self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)
        #                log.debug("after add_static_file")
                    elif cover != '':
                        cvfile = getFile(cover)
                        cvpath = cover
                        coverfiletype = getFileType(cvfile)
                        dummycoverfile = self.dbname + '.' + str(artid) + '.' + coverfiletype
        #                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                        coverres = self.proxyaddress + '/wmp/' + dummycoverfile
                        dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath)    # TODO: pass contenttype
                        self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)

                else:

                    if cover != '' and not cover.startswith('EMBEDDED_'):
                        cvfile = getFile(cover)
                        cvpath = cover
                        coverfiletype = getFileType(cvfile)
                        dummycoverfile = self.dbname + '.' + str(artid) + '.' + coverfiletype
                        coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                        dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath)    # TODO: pass contenttype
                        self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)

                if recordtype == 'track':
                    iduration = int(length)
                    duration = maketime(float(length))
                    tracknumber = self.convert_tracknumber(tracknumber)

                if artist == '': artist = '[unknown artist]'
                if albumartist == '': albumartist = '[unknown albumartist]'
                if album == '': album = '[unknown album]'
                if title == '': title = '[unknown title]'

                title = escape(title)
                artist = escape(artist)
                albumartist = escape(albumartist)
                album = escape(album)

#                # save artists/albums encountered
#                if not albumartist in foundalbumartists:
#                    foundalbumartists += [albumartist]
#                    extras += [(rowid, albumartist, 'albumartist')]
#                if not (albumartist, album) in foundalbumartistalbums:
#                    foundalbumartistalbums += [(albumartist, album)]
#                    extras += [(rowid, album, 'album')]

                if cover == '':
                    coverres = ''
                elif cover.startswith('EMBEDDED_'):
                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummyfile

                # fix WMP urls if necessary
                res = res.replace(self.webserverurl, self.wmpurl)
                coverres = coverres.replace(self.webserverurl, self.wmpurl)

                # TODO: fix entry IDs
#                        full_id = '%s%s__%s_%s_%s__%s' % (tracktype, idhierarchy[0], album_entry_id, artist_entry_id, albumartist_entry_id, str(id))

                if recordtype == 'track':

                    metadatatype = 'track'
    #                    metadata = (aristId, artist, composerId, composer, \
    #                                albumId, album, albumArtURI, albumArtistId, \
    #                                albumArtist, genreId, genre, duration)


                    full_id = '%s%s__%s_%s_%s__%s' % (tracktype, idhierarchy[0], 0, 0, 0, str(id))

                    metadata = ('', artist, '', '', \
                                '', album, coverres, '', \
                                albumartist, '', '', iduration)
                    items += [(full_id, title, mime, res, 'track', metadatatype, metadata)]

                else:

                    ekey = 'S%s:%s' % (extraskeydata['%s:root' % recordtype], extraskeydata['%s:parent' % recordtype] + rowid)
                    if recordtype == 'album':
                        items += [(ekey, 'AL: %s' % album, None, recordtype)]
                    else:
                        items += [(ekey, 'AR: %s' % albumartist, None, recordtype)]

        # sort extras on type then title
#        extras = sorted(extras, key=itemgetter(2,1))
#        self.debugout('extras', extras)
#        # get extras key data
#        extraskeydata = {}
#        for searchroot, searchfieldparent, searchfield in searchfields:        
#            extraskeydata['%s:root' % searchfield] = searchroot
#            extraskeydata['%s:parent' % searchfield] = searchfieldparent
#        # post process extras        
#        for eid, etitle, etype in extras:
#            ekey = 'S%s:%s' % (extraskeydata['%s:root' % etype], extraskeydata['%s:parent' % etype] + eid)
#            items += [(ekey, etitle, None, etype)]
#        totalMatches += len(extras)

        c.close()
        db.row_factory = None
        if not self.proxy.db_persist_connection:
            db.close()

        log.debug("end: %.3f" % time.time())

        if self.source == 'SMAPI':

            if totalMatches == 0:
                itemtype = 'nothing'    # won't be used
#            elif len(items[0]) == 2:
            itemtype = 'container'
#            else:
#                itemtype = 'track'
            return items, totalMatches, startingIndex, itemtype
            











    ###############
    # query helpers
    ###############

    def format_range(self, rangefield, indexrange):

        rangestart, rangeend, units = indexrange
        log.debug('rangestart: %s' % rangestart)
        log.debug('rangeend: %s' % rangeend)
        log.debug('units: %s' % units)

        # ignore empty range
        if rangestart == '' and rangeend == '':

            # range is empty        
            return None, None
            
        # check if it is a count of records
        if units == 'records':
        
            return 'count', None
        
        
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

        if rangefield.lower() == 'year':
            rangestartyear, dummy = self.get_year_ordinal_range(rangestart)
            dummy, rangeendyear = self.get_year_ordinal_range(rangeend)
            rangewhere = '%s between %s and %s' % (rangefield, rangestartyear, rangeendyear)
        elif rangefield.lower() in ['inserted', 'created', 'lastmodified', 'lastscanned', 'lastplayed']:
            rangestartyear = int(time.mktime(rangestartdate.timetuple()))
            rangeendyear = int(time.mktime(rangeenddate.timetuple()))
            rangewhere = '%s between %s and %s' % (rangefield, rangestartyear, rangeendyear)
        else:
            rangestartstring = self.translate_dynamic_field(rangefield, rangestart, 'in')
            rangeendstring = self.translate_dynamic_field(rangefield, rangeend, 'in')
            rangestartstring = escape_sql(rangestartstring)
            rangeendstring = escape_sql(rangeendstring)
            rangewhere = "%s between '%s' and '%s'" % (rangefield, rangestartstring, rangeendstring)

        log.debug('rangewhere: %s' % rangewhere)

        return 'where', rangewhere

    def adjust_for_range(self, rangedetails, totalMatches, orderstatement, alphastatement):

        # rangedetails contains the type and count
        rangeset, rangecount, units = rangedetails
        
        # rangeset can be either 'first' or 'last'
        # rangecount is a number of records to retrieve
        # units will be 'records'
        rangecount = int(rangecount)

        # adjust the SQL to limit what we get back
        # we need to limit the initial (full) result, which may be further 
        # limited by the requested count
        
        # for the count, we'll just limit what was returned
        originalMatches = totalMatches
        if totalMatches > rangecount:
            totalMatches = rangecount
            log.debug('range adjusted count: %s' % totalMatches)

        # for the statements we need to add additional limits
        # work out bounding limit clause
        if rangeset == 'first':
            limitclause = ' limit %s)' % rangecount
        elif rangeset == 'last':
            limitclause = ' limit %s, %s)' % (originalMatches - rangecount, rangecount)

        # orderstatement
        if orderstatement != '':
            # we need to add a bounding limit to the initial query
            # before applying the existing requested count/startindex
            # add outer select
            orderstatement = 'SELECT * from (%s' % orderstatement
            # insert outer select limit before call limit
            orderstatement = orderstatement.replace(' limit ', ' %s limit ' % limitclause)
            log.debug('range adjusted orderstatement: %s' % orderstatement)

        # alphastatement
        if alphastatement != '':
            # we need to add a bounding limit to the inner query
            alphastatement = alphastatement.replace('order by %%s)', 'order by %%s limit %s)' % limitclause)
            log.debug('range adjusted alphastatement: %s' % alphastatement)
        
        return totalMatches, orderstatement, alphastatement

    #################    
    # display helpers
    #################    

    def removepresuf(self, title, sourcetable, controllername):

        # not currently used
        
        possibleentries = []
        # strip quotes
        fullentry = title[1:-1]

        # check for prefix and suffix separators
        #  - if present just split on those and ignore sorts entry
        ppos = fullentry.rfind(self.prefix_sep)
        if ppos != -1:
            fullentry = fullentry[ppos+1:]
        spos = fullentry.find(self.suffix_sep)
        if spos != -1:
            fullentry = fullentry[:spos]
        return [fullentry]

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
    
    '''
    def get_proxy_simple_sorts(self):
        simple_sorts = []
        simple_keys = self.proxy_simple_key_dict.copy()
        processing_index = False
        for line in codecs.open(PYCPOINT_INI,'r','utf-8'):
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
    '''
    
    '''
    def get_proxy_orderby(self, sorttype, controller):

        if self.alternative_indexing == 'N':

            at = self.get_possible_albumtypes(sorttype)
            return [(None, None, None, at, 'dummy', None)]

        else:

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

    '''

    '''
    def convert_artist(self, valuedict):
        newvaluedict = {}
        for key, value in valuedict.iteritems():
            if key.lower() in ['sort_order', 'entry_prefix', 'entry_suffix']:
                entries = value.split(',')
                entries = [s.strip() for s in entries]
                entrieslower = map(string.lower, entries)
                if self.use_albumartist:
                    if 'artist' in entrieslower:
                        newentries = []
                        for e in entries:
                            if e.lower() == 'artist': e = 'albumartist'
                            newentries += [e]
                        value = ','.join(newentries)
                else:
                    if 'albumartist' in entrieslower:
                        newentries = []
                        for e in entries:
                            if e.lower() == 'albumartist': e = 'artist'
                            newentries += [e]
                        value = ','.join(newentries)
            newvaluedict[key] = value
        return newvaluedict
    '''
    '''
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
    '''
    '''
    def translate_albumtype(self, albumtype, table):
        if not albumtype or albumtype == '':
            return '10', 'album'
        elif albumtype == 'album':
            return '10', albumtype
        elif albumtype == 'virtual':
            if table == 'ALBUM':
                return '21', albumtype
            elif table == 'ALBUMARTIST_ALBUM' or table == 'ALBUMARTIST' or table == 'GENRE_ALBUMARTIST_ALBUM' or table == 'GENRE_ALBUMARTIST' or table == 'GENRE_AA':
                return '22', albumtype
            elif table == 'ARTIST_ALBUM' or table == 'ARTIST' or table == 'GENRE_ARTIST_ALBUM' or table == 'GENRE_ARTIST' or table == 'GENRE_A':
                return '23', albumtype
            elif table == 'COMPOSER_ALBUM' or table == 'COMPOSER':
                return '24', albumtype
        elif albumtype == 'work':
            if table == 'ALBUM':
                return '31', albumtype
            elif table == 'ALBUMARTIST_ALBUM' or table == 'ALBUMARTIST' or table == 'GENRE_ALBUMARTIST_ALBUM' or table == 'GENRE_ALBUMARTIST' or table == 'GENRE_AA':
                return '32', albumtype
            elif table == 'ARTIST_ALBUM' or table == 'ARTIST' or table == 'GENRE_ARTIST_ALBUM' or table == 'GENRE_ARTIST' or table == 'GENRE_A':
                return '33', albumtype
            elif table == 'COMPOSER_ALBUM' or table == 'COMPOSER':
                return '34', albumtype
        else:
            return '10', 'album'
    '''
    def get_possible_albumtypes(self, sorttype, filteralbum=None):
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
        if sorttype == 'album_album':
            if self.display_virtuals_in_album_index and virtual: at.append(21)
            if self.display_works_in_album_index and work: at.append(31)
        elif sorttype == 'albumartist_album' or sorttype == 'albumartist' or sorttype == 'genre_albumartist_album' or sorttype == 'genre_albumartist':
            if self.display_virtuals_in_artist_index and virtual: at.append(22)
            if self.display_works_in_artist_index and work: at.append(32)
        elif sorttype == 'artist_album' or sorttype == 'artist' or sorttype == 'genre_artist_album' or sorttype == 'genre_artist':
            if self.display_virtuals_in_artist_index and virtual: at.append(23)
            if self.display_works_in_artist_index and work: at.append(33)
        elif sorttype == 'composer_album' or sorttype == 'composer':
            if self.display_virtuals_in_composer_index and virtual: at.append(24)
            if self.display_works_in_composer_index and work: at.append(34)
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

    #####################
    # updateid processors
    #####################
    
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

    
    #########
    # helpers
    #########
    
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

    def get_orderby(self, sorttype, controller, dynamic=True, orderby=None):

        log.debug('get_orderby sorttype: %s' % sorttype)
        log.debug('get_orderby orderby: %s' % orderby)
        albumtypes = self.get_possible_albumtypes(sorttype)
        
        # static = sort_order, entry_prefix, entry_suffix, albumtypes
        default_static_orderby = (orderby, None, None, albumtypes, '', ('','',''))

        # dynamic = range_field, index_range, sort_order, entry_prefix, entry_suffix, albumtypes
        default_dynamic_orderby = ('', ('','',''), '', '', '', albumtypes)

        if self.alternative_indexing == 'N':

            if dynamic: 
                return default_dynamic_orderby
            else: 
                return default_static_orderby

        else:

            controller = controller.lower()
            proxyfound = False
            controllerfound = False
            bothfound = False
            foundvalues = None

            if self.source == 'SMAPI':
                namekey = 'servicename'
            else:
                namekey = 'proxyname'

#            log.debug(self.index_settings)
            for (index, values) in self.index_settings.iteritems():
#                log.debug(index)
#                log.debug(values)
                if sorttype == index and values['active'] == 'y':
                    # precedence is proxy-and-controller/proxy/controller/neither
                    if values[namekey] == self.proxy.proxyname and controller.startswith(values['controller']) and not bothfound:
                        bothfound = True
                        foundvalues = values
                    elif values[namekey] == self.proxy.proxyname and values['controller'].lower() == 'all' and not bothfound and not proxyfound:
                        proxyfound = True
                        foundvalues = values
                    elif values[namekey].lower() == 'all' and controller.startswith(values['controller']) and not bothfound and not proxyfound and not controllerfound:
                        controllerfound = True
                        foundvalues = values
                    elif values[namekey].lower() == 'all' and values['controller'].lower() == 'all' and \
                         not bothfound and not proxyfound and not controllerfound and not foundvalues:
                        foundvalues = values
            log.debug('foundvalues: %s' % foundvalues)
            if not foundvalues:
                if dynamic: 
                    return default_dynamic_orderby
                else: 
                    return default_static_orderby
            else:
                sort_order = foundvalues['sort_order']
                if sort_order == None or sort_order == '': sort_order = orderby
                if dynamic:
                    return (foundvalues['range_field'], foundvalues['index_range'], sort_order, foundvalues['entry_prefix'], foundvalues['entry_suffix'], albumtypes)
                else:
                    range_field = foundvalues['range_field']
                    if range_field == None or range_field == '': range_field = orderby
                    return (sort_order, foundvalues['entry_prefix'], foundvalues['entry_suffix'], albumtypes, range_field, foundvalues['index_range'])

    def static_makepresuffix(self, fix, replace, fixdict, ps):
        EMPTY = '__EMPTY__'
        outfix = ''
        if fix and fix != '':
            fix = fix.replace(' ', '')
            fixes = fix.lower().split(',')
            for fix in fixes:
                if fix in fixdict:
                    data = fixdict[fix]
                    if fix in ['lastplayed', 'inserted', 'created', 'lastmodified', 'lastscanned']:
                        if data == '':
                            data = EMPTY
                        else:
                            try:
                                data = float(data)
                                data = time.strftime(self.metadata_date_format, time.gmtime(data))
                            except TypeError:
                                data = EMPTY
                    elif fix == 'playcount':
                        if data == '': data = '0'
                    elif fix == 'year':
                        if data == '':
                            data = EMPTY
                        else:
                            try:
                                data = datetime.date.fromordinal(data).strftime(self.metadata_date_format)
                            except TypeError:
                                data = EMPTY
                    else:
                        # other tags just pass through
                        if data == '': data = EMPTY
                        
                    if data == EMPTY and ps == 'P' and self.dont_display_separator_for_empty_prefix == False:
                        pass
                    elif data == EMPTY and ps == 'S' and self.dont_display_separator_for_empty_suffix == False:
                        pass
                    else:
                        if data == EMPTY: data = self.metadata_empty
                        outfix += replace % data
        return outfix

    def dynamic_makepresuffix(self, fixes, replace, fixdata, ps):
#        log.debug(fixes)
#        log.debug(replace)
#        log.debug(fixdata)
    
        EMPTY = '__EMPTY__'
        outfix = ''
        if fixes and fixes != []:
            fixcount = 0
            for fix in fixes:
                data = fixdata[fixcount]
                if fix in ['lastplayed', 'inserted', 'created', 'lastmodified', 'lastscanned']:
                    if data == '' or data == 0:
                        data = EMPTY
                    else:
                        try:
                            data = float(data)
                            data = time.strftime(self.metadata_date_format, time.gmtime(data))
                        except TypeError:
                            data = EMPTY
                elif fix == 'playcount':
                    if data == '': data = '0'
                elif fix == 'year':
                    if data == '':
                        data = EMPTY
                    else:
                        try:
                            data = datetime.date.fromordinal(data).strftime(self.metadata_date_format)
                        except TypeError:
                            data = EMPTY
                else:
                    # other tags just pass through
                    if data == '': data = EMPTY

                if data == EMPTY and ps == 'P' and self.dont_display_separator_for_empty_prefix == False:
                    pass
                elif data == EMPTY and ps == 'S' and self.dont_display_separator_for_empty_suffix == False:
                    pass
                else:
                    if data == EMPTY: data = self.metadata_empty
                    outfix += replace % data
                fixcount += 1
        return outfix

    def get_index_parts(self, idkeys):
        # split root name from keys and return both separately
        rootname = idkeys[0]
        if len(idkeys) == 1:
            # first time through the keys will just contain the root name
            # so we need to look up the first container id and add it
            indexkeys = [self.index_ids[rootname][0]]
        else:
            # otherwise just remove first entry (which is rootname)
            indexkeys = idkeys[1:]
        return rootname, indexkeys

    def get_index_key(self, ids, idhierarchy):

        # first facet of ids is rootname
        rootname = ids[0]
        keylist = [rootname]
        # add another facet for each path index in the list
        for i in range(len(ids) - 1):
            if ids[i] in self.dynamic_lookup.keys():
                keylist += [self.dynamic_lookup[ids[i]]]
        # last facet of idhierarchy is index name and position
        keylist += [idhierarchy[-1]]
#        # last facet is index name, if there is one
#        if len(ids) > 2:
#            keylist += [self.hierarchies[rootname][len(ids) - 2]]
#        else:
#            # if not, get first item in list
#            keylist += [self.hierarchies[rootname][0]]
        return '_'.join(keylist)

    '''
    def get_index(self, idkeys, position, root=None):
        log.debug('idkeys: %s', idkeys)
        log.debug('position: %s', position)
        log.debug('root: %s', root)
        browsebyid = False
        if root: 
            firstkey = root
        else: 
            firstkey = idkeys[0]
        if position == 'FIRST' or len(idkeys) == 1 or idkeys == root:
            parent = self.containerstart[firstkey]
        elif position == 'LAST':        
            lastkey = idkeys[-1]
            parent = self.get_parent(lastkey)
            if parent != int(lastkey): browsebyid = True
        elif position == 'SINGLE':
            thiskey = idkeys
            parent = self.get_parent(thiskey)
            if parent != int(thiskey): browsebyid = True
        parent = '%s_%s' % (firstkey, parent)
        browsetype = self.containername[parent] # FIXME: this is not a valid dict anymore
        return browsetype, browsebyid

    def get_parent(self, objectid):
        return self.id_length * int(int(objectid) / self.id_length)
    '''

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

    #############
    # conversions
    #############

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
            if delim == '': delim = special
            else:
                if when == 'before':
                    if delim[0] != special:
                        delim = '%s%s' % (special, delim)
                elif when == 'after':
                    if delim[-1] != special:
                        delim = '%s%s' % (delim, special)
        delim2 = re.escape(delim)
        return delim2, delim

    def debugout(self, label, data):
    
        # note that when logging with debugout, the callers details will be
        # logger rather than debugout's details (hacked in brisa/log.py)
    
        if isinstance(data, dict):
            dbo = ''
            for k,v in data.iteritems():
                dbo += '\n\t\t\t\t\t\t\t\t\t\t\t\t%s: %s' % (k, v)
            log.debug('%s:%s' % (label, dbo))
        elif isinstance(data, (list, tuple, set, frozenset)):
            dbo = ''
            for v in data:
                dbo += '\n\t\t\t\t\t\t\t\t\t\t\t\t%s' % (repr(v))
            log.debug('%s:%s' % (label, dbo))
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
    elif mime == 'audio/x-ms-wma':
        mime = 'audio/wma'
    return mime

def getMime(ext):
    if ext == 'flac':
        mime = 'audio/flac'
    elif ext == 'wav':
        mime = 'audio/wav'
    elif ext == 'mp3':
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

