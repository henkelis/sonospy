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

from transcode import checktranscode, checksmapitranscode, checkstream, setalsadevice

from xml.etree.ElementTree import _ElementInterface
from xml.etree import cElementTree as ElementTree

from xml.sax.saxutils import escape, unescape

from mediaserver import MediaServer
from mediaserver import getProtocol
from mediaserver import getFileType
from mediaserver import getFile
from mediaserver import fixcolonequals
from mediaserver import fixMime

from brisa.core import log

from brisa.core import webserver, network

from brisa.upnp.device import Device
from brisa.upnp.device.service import Service
from brisa.upnp.device.service import StateVariable
from brisa.upnp.soap import HTTPProxy, HTTPRedirect
from brisa.upnp.soap import build_soap_error
from brisa.core.network import parse_url, get_ip_address, parse_xml
from brisa.utils.looping_call import LoopingCall

from dateutil.parser import parse as parsedate
from dateutil.relativedelta import relativedelta as datedelta

enc = sys.getfilesystemencoding()

class Proxy(object):

    def __init__(self, proxyname, proxytype, proxytrans, udn, config, port,
                 mediaserver=None, controlpoint=None, createwebserver=False,
                 webserverurl=None, wmpurl=None, startwmp=False, dbname=None,
                 wmpudn=None, wmpcontroller=None, wmpcontroller2=None,
                 smapi=False):
        '''
        To proxy an external mediaserver, set:
            port = the port to listen on for proxy control messages
            mediaserver = the mediaserver device being proxied
            controlpoint = the controller device containing a webserver to utilise
            createwebserver = True  # TODO: check why this has changed, do we need to set webserver to controlpoint webserver?
            webserverurl = None
        To serve an internal mediaserver, set:
            port = None
            mediaserver = None
            controlpoint = None
            createwebserver = True
            webserverurl = webserver url
            wmpurl = WMP url to serve from
            wmpcontroller

        '''
        self.root_device = None
        self.upnp_urn = 'urn:schemas-upnp-org:device:MediaServer:1'
        self.proxyname = proxyname
        self.proxytype = proxytype
        self.proxytrans = proxytrans
        self.udn = udn
        self.config = config
        self.port = port
        self.mediaserver = mediaserver
        self.controlpoint = controlpoint
        self.createwebserver = createwebserver
        self.webserverurl = webserverurl
        self.wmpurl = wmpurl
        self.startwmp = startwmp
        if dbname == None:
            self.dbspec = None
            self.dbname = None
        else:
            if not os.path.isabs(dbname):
                dbname = os.path.join(os.getcwd(), dbname)
            self.dbspec = dbname
            self.dbpath, self.dbname = os.path.split(dbname)
            if self.dbname == '':
                self.dbname = 'sonospy.sqlite'
                self.dbspec = os.path.join(os.getcwd(), self.dbname)
        self.wmpudn = wmpudn
        self.wmpwebserver = None
        self.wmpcontroller = wmpcontroller
        self.wmpcontroller2 = wmpcontroller2
        self.smapi = smapi

        self.destmusicaddress = None
        if mediaserver == None:
            self.destaddress = None
        else:
            self.destaddress = mediaserver.address

        # get db cache size
        self.db_cache_size = 2000
        try:
            db_cache_size_option = self.config.get('INI', 'db_cache_size')
            try:
                cache = int(db_cache_size_option)
                if cache > self.db_cache_size:
                    self.db_cache_size = cache
            except ValueError:
                pass
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        # get connection persistence
        self.db_persist_connection = False
        try:
            db_persist_connection_option = self.config.get('INI', 'db_persist_connection')
            if db_persist_connection_option:
                if db_persist_connection_option.lower() == 'y':
                    self.db_persist_connection = True
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        # check database
        error = None
        if self.dbspec != None:
            if not os.access(self.dbspec, os.R_OK):
                error = "Unable to access database file"
            else:
                try:
                    if self.db_persist_connection:
                        db = sqlite3.connect(self.dbspec, check_same_thread = False)
                    else:
                        db = sqlite3.connect(self.dbspec)
                    cs = db.execute("PRAGMA cache_size;")
                    log.debug('cache_size before: %s', cs.fetchone()[0])
                    db.execute("PRAGMA cache_size = %s;" % self.db_cache_size)
                    cs = db.execute("PRAGMA cache_size;")
                    log.debug('cache_size after: %s', cs.fetchone()[0])
                    cs.close()
                    c = db.cursor()
                except sqlite3.Error, e:
                    error = "Unable to open database (%s)" % e.args[0]
                else:
                    try:
                        c.execute("select count(*) from tracks")
                        count, = c.fetchone()
                        if count == 0:
                            error = "Database is empty"
                    except sqlite3.Error, e:
                        error = "Unable to read track table (%s)" % e.args[0]
        if error:
            raise ValueError(error)
        if self.dbspec != None:
            if self.db_persist_connection:
                self.db = db
            else:
                self.db = None
                db.close()
            log.debug(self.db)
        if os.name != 'nt':
            setalsadevice()

    def _add_root_device(self):
        """ Creates the root device object which will represent the device
        description.
        """
        project_page = 'http://brisa.garage.maemo.org'
        if self.controlpoint != None:
            ip, port = self.controlpoint._event_listener.host()
            listen_url = "http://" + ip + ':' + str(self.port)
            udp_listener = self.controlpoint._ssdp_server.udp_listener
        else:
            listen_url = self.webserverurl
            udp_listener = ''
        if self.proxytype == 'WMP':
            model_name='Windows Media Player Sharing'
        else:
            model_name='Rhapsody'

        self.root_device = Device(self.upnp_urn,
                                  self.proxyname,
                                  udn=self.udn,
                                  manufacturer='Henkelis',
                                  manufacturer_url='http://www.microsoft.com/',
                                  model_description='Media Server',
                                  model_name=model_name,
                                  model_number='3.0',
                                  model_url='http://www.microsoft.com/',
                                  serial_number=self.dbname,
                                  udp_listener=udp_listener,
                                  create_webserver=self.createwebserver,
                                  force_listen_url=listen_url)
        self.root_device.webserver.get_render = self.get_render


    def _add_services(self):
        # TODO: investigate why an error in creating the ContentDirectory
        #       causes the controlpoint to receive a duplicate _new_device_event_impl
        #       for the device being proxied
        if self.mediaserver == None:

            if self.smapi:
                self.smapiservice = Smapi(self.root_device.location, self, self.webserverurl, self.wmpurl, self.dbspec, self.wmpudn)
                self.root_device.add_service(self.smapiservice)

            self.cdservice = DummyContentDirectory(self.root_device.location, self, self.webserverurl, self.wmpurl, self.dbspec, self.wmpudn)
            self.root_device.add_service(self.cdservice)
            self.cmservice = DummyConnectionManager()
            self.root_device.add_service(self.cmservice)

        else:
            self.cdservice = ContentDirectory(self.controlpoint, self.mediaserver, self.root_device.location, self)
            self.root_device.add_service(self.cdservice)
            self.cmservice = ConnectionManager(self.controlpoint, self.mediaserver)
            self.root_device.add_service(self.cmservice)
        self.mrservice = X_MS_MediaReceiverRegistrar()
        self.root_device.add_service(self.mrservice)

    def _create_webserver(self, wmpurl):
        p = network.parse_url(wmpurl)
#        self.wmpwebserver = webserver.WebServer(server_name='www.sonospy.com', host=p.hostname, port=p.port)
        self.wmpwebserver = webserver.WebServer(server_name='www.sonospy.com', host='0.0.0.0', port=p.port)
        self.wmplocation = self.wmpwebserver.get_listen_url()
        self.wmpcontroller = ProxyServerController(self, 'WMPNSSv3')
        self.wmpwebserver.add_resource(self.wmpcontroller)
        self.wmpcontroller2 = ProxyServerController(self, 'wmp')
        self.wmpwebserver.add_resource(self.wmpcontroller2)

    def _load(self):
        self._add_root_device()
        self._add_services()
        if self.startwmp == True:
            self._create_webserver(self.wmpurl)

    def start(self):
#        self.stop()
        self._load()
        self.root_device.start()
        if self.startwmp == True:
            self.wmpwebserver.start()

    def stop(self):
        if self.root_device:
            self.root_device.stop()
            self.root_device = None
        if self.startwmp == True:
            self.wmpwebserver.stop()

    def get_render(self, uri, params):
        return self

    def render(self, env, start_response):
        if self.destmusicaddress is not None:
            address = self.destmusicaddress
        else:
            address = self.destaddress
#        respbody = HTTPProxy().call(address, env, start_response)
        respbody = HTTPRedirect().call(address, env, start_response)
        return respbody

    def get_Track(self, objectname):
        # get track details from passed objectname
        # and create a staticfile for the track and albumart (if that exists)
        log.debug("proxy.get_Track objectname: %s" % objectname)
        # object name is either:
        #   db + id + type_extension e.g. database.sqlite.6000022.flac (also could be database.sqlite.6000022.jpg)
        # or
        #   db + id + transcode_extension(s) + type extension e.g. database.sqlite.6000023.mp2.mp3
        # the id is a 32 char hex MD5, assume that the extensions are not
        # note that db can be any number of facets (e.g. name, name.ext, name1.name2.ext etc)
        # assume this is only called for a valid id
        objectfacets = objectname.split('.')
        lenfacets = len(objectfacets)
        # find id
        for i in range(lenfacets-1,-1,-1):
            if len(objectfacets[i]) == 32:
                try:
                    val = int(objectfacets[i], 16)
                    # assume we have found the id
                    idpos = i
                    break
                except ValueError:
                    pass
        objectID = objectfacets[idpos]
#        # check whether we have a transcode
#        transcode = False
#        if lenfacets - idpos > 2:
#            transcode = True
        # get dbname
        dbfacets = objectname.split('.' + objectID + '.')
        dbname = dbfacets[0]
        log.debug("proxy.get_Track objectID: %s" % objectID)
        log.debug("proxy.get_Track dbname: %s" % dbname)
        # try and open the database in the same folder as the proxy database
        # if it is the proxy database, that will work
        # if it isn't, then it will only work if the database specified is where the proxy database is
        # TODO: work out whether we want to store the database path somewhere
        try:
            if self.db_persist_connection:
                db = self.db
            else:
                db = sqlite3.connect(os.path.join(self.dbpath, dbname))
            log.debug(self.db)
            c = db.cursor()
        except sqlite3.Error, e:
            log.debug("error opening database: %s %s %s", self.dbpath, dbname, e.args[0])
            return

        statement = "select * from tracks where id = '%s'" % (objectID)
        log.debug("statement: %s", statement)
        c.execute(statement)

        id, id2, duplicate, title, artistshort, artist, album, genre, tracknumber, year, albumartistshort, albumartist, composershort, composer, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned, titlesort, albumsort = c.fetchone()
        log.debug("id: %s", id)
        mime = fixMime(mime)
        cover, artid = self.cdservice.mediaServer.choosecover(folderart, trackart, folderartid, trackartid)
        log.debug("cover: %s, artid: %s" % (cover, artid))

        wsfile = filename
        wspath = os.path.join(path, filename)

        protocol = getProtocol(mime)
        contenttype = mime
        filetype = getFileType(filename)

        log.debug("filetype: %s", filetype)

        transcode, newtype = checktranscode(filetype, bitrate, samplerate, bitspersample, channels, codec)

        log.debug("transcode: %s", transcode)
        log.debug("newtype: %s", newtype)

        if transcode:
            log.debug('\nobjectname: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s\ntranscodetype: %s' % (objectname, wsfile, wspath, contenttype, newtype))
            dummystaticfile = webserver.TranscodedFileSonos(objectname, wsfile, wspath, newtype, contenttype, cover=cover)
            self.wmpcontroller.add_transcoded_file(dummystaticfile)
        else:
            log.debug('\nobjectname: %s\nwsfile: %s\nwspath: %s\ncontenttype: %s' % (objectname, wsfile, wspath, contenttype))
            dummystaticfile = webserver.StaticFileSonos(objectname, wsfile, wspath, contenttype, cover=cover)
            self.wmpcontroller.add_static_file(dummystaticfile)

        if cover.startswith('EMBEDDED_'):
            # art is embedded for this file
            coverparts = cover.split('_')
            coveroffsets = coverparts[1]
            # spec may contain '_'
            specstart = len('EMBEDDED_') + len(coveroffsets) + 1
            coverspec = cover[specstart:]
            cvfile = getFile(coverspec)
            cvpath = coverspec
            dummycoverfile = dbname + '.' + str(artid) + '.coverart'
#            coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
            dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath, cover=cover)
            self.wmpcontroller2.add_static_file(dummycoverstaticfile)
        elif cover != '':
            cvfile = getFile(cover)
            cvpath = cover
            coverfiletype = getFileType(cvfile)
            dummycoverfile = dbname + '.' + str(artid) + '.' + coverfiletype
            dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath)    # TODO: pass contenttype
            self.wmpcontroller2.add_static_file(dummycoverstaticfile)

        c.close()
        if not self.db_persist_connection:
            db.close()

class ProxyServerController(webserver.SonosResource):

    def __init__(self, proxy, res):
        webserver.SonosResource.__init__(self, res, proxy)

##########################
##########################
# ContentDirectory service
##########################
##########################

class ContentDirectory(Service):

    service_name = 'ContentDirectory'
    service_type = 'urn:schemas-upnp-org:service:ContentDirectory:1'
    scpd_xml_path = os.path.join(os.getcwd(), 'content-directory-scpd.xml')

    searchArtists = {}
    searchContributing = {}
    searchAlbums = {}
    searchComposers = {}
    searchGenres = {}
    searchTracks = {}
    searchPlaylists = {}

    dictmapping = {'Artist'                 : searchArtists,
                   'Contributing Artists'   : searchContributing,
                   'Album'                  : searchAlbums,
                   'Composer'               : searchComposers,
                   'Genre'                  : searchGenres,
                   'Tracks'                 : searchTracks,
                   'Playlists'              : searchPlaylists }

    decaches = {'microsoft:artistAlbumArtist'   : searchArtists,
# should not be needed as replace is performed later                'upnp:artist'     : searchArtists,  # TODO: create this automatically from mapping
                'microsoft:artistPerformer'     : searchContributing,
                'upnp:album'                    : searchAlbums,
                'microsoft:authorComposer'      : searchComposers,
# should not be needed as replace is performed later                'upnp:author'      : searchComposers,  # TODO: create this automatically from mapping
                'upnp:genre'                    : searchGenres,
                'NOT_NEEDED'                    : searchTracks,
                'ug'                            : searchPlaylists }

    # TODO: fix playlists

    defaultcaches = {'107' + ' - ' + 'upnp:class = "object.container.person.musicArtist"' : searchArtists,
                     '100' + ' - ' + 'upnp:class = "object.container.person.musicArtist"' : searchContributing,
                     '0'   + ' - ' + 'upnp:class = "object.container.album.musicAlbum"'   : searchAlbums,
                     '108' + ' - ' + 'upnp:class = "object.container.person.musicArtist"' : searchComposers,
                     '0'   + ' - ' + 'upnp:class = "object.container.genre.musicGenre"'   : searchGenres,
                     '0'   + ' - ' + 'upnp:class derivedfrom "object.item.audioItem"'     : searchTracks,
                     '0'   + ' - ' + 'upnp:class = "object.container.playlistContainer"'  : searchPlaylists }
    defaultop = '='

    def __init__(self, controlpoint, mediaserver, proxyaddress, proxy):
        self.controlpoint = controlpoint
        self.mediaserver = mediaserver
        self.destscheme = mediaserver.scheme
        self.destip = mediaserver.ip
        self.proxyaddress = proxyaddress
        self.destmusicaddress = None
        self.proxy = proxy
        self.translate = 0
        self.subtranslate = ''
        self.caches = {}
        self.sonos_containers = {}
        self.sonos_decache = {}
        self.proxy_decache = {}
        self.containers = {}
        self.container_mappings = {}
        self.attribute_mappings = {}
        self.operators = [self.defaultop]

        Service.__init__(self, self.service_name, self.service_type, url_base='', scpd_xml_filepath=self.scpd_xml_path)

        # TODO: add error processing for ini file entries

        if self.proxy.proxytrans == '':
            self.translate = 'Through'
        else:
            try:
                self.translate = self.proxy.config.get('WMP Translators', self.proxy.proxytrans)
                if ',' in self.translate:
                    valuestring = self.translate.split(',')
                    self.translate = valuestring[0]
                    self.subtranslate = valuestring[1]
            except ConfigParser.NoSectionError:
                self.translate = '0'
            except ConfigParser.NoOptionError:
                self.translate = '0'

            if self.translate != '0':
                # set defaults
                self.caches = self.defaultcaches.copy()
                # load Sonos container mapping
                try:
                    self.conts = self.proxy.config.items('Sonos Containers')
                    self.sonos_containers = fixcolonequals(self.conts)
                    for k, v in self.sonos_containers.iteritems():
                        if v == '': continue    # ignore empty keys
                        valuestring = v.split(',')
                        if len(valuestring) == 1:
                            cachestring = valuestring[0]
                        elif len(valuestring) == 2:
                            cachestring = valuestring[0] + ' - ' + 'upnp:class = "' + valuestring[1] + '"'
                        else:
                            cachestring = valuestring[0] + ' - ' + 'upnp:class ' + valuestring[2] + ' "' + valuestring[1] + '"'
                            if valuestring[2] not in self.operators:
                                    self.operators.append(valuestring[2])
                        self.caches[cachestring] = self.dictmapping[k]
#                        self.sonos_decache[valuestring[0] + ',' + valuestring[1]] = k
                        self.sonos_decache[v] = k
                except ConfigParser.NoSectionError:
                    pass

                # load mappings for selected proxy
                try:
                    self.conts = self.proxy.config.items(self.proxy.proxytrans + ' Containers')
                    self.containers = fixcolonequals(self.conts)
#                    print self.containers

                    '''
                    for k, v in self.containers.iteritems():

# Composer=1$16,object.container.person.author

                        if v == '': continue    # ignore empty keys
                        valuestring = v.split(',')
                        if len(valuestring) == 1:
                            cachestring = valuestring[0]
                        elif len(valuestring) == 2:
                            cachestring = valuestring[0] + ' - ' + 'upnp:class = "' + valuestring[1] + '"'
                        else:
                            cachestring = valuestring[0] + ' - ' + 'upnp:class ' + valuestring[2] + ' "' + valuestring[1] + '"'
                            if valuestring[2] not in self.operators:
                                    self.operators.append(valuestring[2])
                        self.caches[cachestring] = self.dictmapping[k]
                        self.proxy_decache[v] = k
                    '''
                except ConfigParser.NoSectionError:
                    pass

                try:
                    self.cont_maps = self.proxy.config.items(self.proxy.proxytrans + ' Container Mapping')
                    self.container_mappings = fixcolonequals(self.cont_maps)
                except ConfigParser.NoSectionError:
                    pass

                try:
                    self.attr_maps = self.proxy.config.items(self.proxy.proxytrans + ' Attribute Mapping')
                    self.attribute_mappings = fixcolonequals(self.attr_maps)
#                    print self.attribute_mappings
                except ConfigParser.NoSectionError:
                    pass

#            print "##############################"
#            print self.proxy.proxytrans
#            print self.translate
#            print self.caches
#            print self.sonos_containers
#            print self.sonos_decache
#            print self.containers
#            print self.container_mappings
#            print self.attribute_mappings
#            print "##############################"


    def soap_Browse(self, *args, **kwargs):
#        for key in kwargs:
#            print "another keyword arg: %s: %s" % (key, kwargs[key])

        log.debug("PROXY_BROWSE: %s", kwargs)

        result = self.controlpoint.proxyBrowse(kwargs['ObjectID'], kwargs['BrowseFlag'], kwargs['Filter'], kwargs['StartingIndex'], kwargs['RequestedCount'], kwargs['SortCriteria'], self.mediaserver)
        if 'Result' in result:

            # if we are browsing the root, filter out 2 (video) and 3 (pictures)
            res = result['Result']

            c = 0
            cont1 = re.search('<container id="1" parentID="0".*?/container>', res)
            if cont1 != None:
                # root entry
                cont2 = re.search('<container id="2" parentID="0".*?/container>', res)
                if cont2 != None:
                    c -= 1
                    res = re.sub('<container id="2" parentID="0".*?/container>', '', res)
                cont3 = re.search('<container id="3" parentID="0".*?/container>', res)
                if cont3 != None:
                    c -= 1
                    res = re.sub('<container id="3" parentID="0".*?/container>', '', res)
            # correct the counts
            if 'NumberReturned' in result:
                nr = int(result['NumberReturned'])
                nr += c
                result['NumberReturned'] = str(nr)
            if 'TotalMatches' in result:
                tm = int(result['TotalMatches'])
                tm += c
                result['TotalMatches'] = str(tm)

            log.debug("BROWSE res: %s", res)

            # if result contains destination addresses in XML, need to transform them to proxy addresses
            # (otherwise the Sonos kicks up a fuss)
            # for WMP at least, the port of the dest track address may not be the port of the dest webserver
            #    so we need to save the dest track address
            address = re.search(self.destip + ':[0-9]*', res)
            if address != None:
                self.destmusicaddress = self.destscheme + '://' + address.group()
                # save this address so proxy can use it
                self.proxy.destmusicaddress = self.destmusicaddress
                res = re.sub(self.destmusicaddress, self.proxyaddress, res)

#            print "@@@@@@@@@ res after: " + str(res)

            result['Result'] = res
        return result

    def soap_Search(self, *args, **kwargs):

        containerID = kwargs['ContainerID']
        mscontainerID = containerID
        searchCriteria = kwargs['SearchCriteria']

        log.debug('containerID: %s' % str(containerID))
        log.debug('searchCriteria: %s' % str(searchCriteria))
#        print 'translate: ' + str(self.translate)

        if self.translate == 'Through':

            result = self.controlpoint.proxySearch(containerID, searchCriteria, kwargs['Filter'], kwargs['StartingIndex'], kwargs['RequestedCount'], kwargs['SortCriteria'], self.mediaserver)
#            print result['Result']

        elif self.translate == 'Translate':

            # perform any container and attribute mappings
            if containerID in self.container_mappings:
                containerID = self.container_mappings[containerID]
            for k, v in self.attribute_mappings.iteritems():
                searchCriteria = re.sub(k, v, searchCriteria)

            if containerID == '':
                # server does not support search type
                result = {'NumberReturned': '0', 'UpdateID': '1', 'Result': '', 'TotalMatches': '0'}
                return result
            else:
                result = self.controlpoint.proxySearch(containerID, searchCriteria, kwargs['Filter'], kwargs['StartingIndex'], kwargs['RequestedCount'], kwargs['SortCriteria'], self.mediaserver)

        elif self.translate == 'Cache':

#            if kwargs['Filter'] == 'dc:title,res':
#                kwargs['Filter'] = 'dc:title,res,upnp:albumArtURI'
#            print "%%%%%%%%%%%%%%%%%%%%%%%%"
#            print kwargs['Filter']
#            print "%%%%%%%%%%%%%%%%%%%%%%%%"


            # TODO: look into sort criteria
#<SortCriteria>+dc:title,+microsoft:artistAlbumArtist</SortCriteria>

#            print "map: " + str(self.attribute_mappings)

            # split search string into components
            # TODO: check if there is ever an 'or'
            searchelements = searchCriteria.split(' and ')

            # TODO: add error processing if dict items not found

#            print "len: " + str(len(searchelements))

            if len(searchelements) == 2:
                # first time through, just class and refID
                # get search type from containerID and class combination
                for op in self.operators:
                    if op in searchelements[0]:
                        thisop = op
                        break
                upnpclass = searchelements[0].split(' ' + thisop + ' ')[1][1:-1]

#                print "Class: " + str(upnpclass)

                searchkey = containerID + ',' + upnpclass
                if thisop != self.defaultop:
                    searchkey += ',' + thisop

#                print "searchkey: " + str(searchkey)

                searchtype = self.sonos_decache[searchkey]

#                print "searchtype: " + str(searchtype)

                # get containerID from map
                containerID = self.containers[searchtype]

                # check for translation
                criteriatrans = False
                if ',' in containerID:
                    valuestring = containerID.split(',')
                    containerID = valuestring[0]
                    newclass = valuestring[1]
                    if newclass != '':
                        criteriatrans = True

#                print "containerID: " + str(containerID)

                # just use container for search
                if self.subtranslate == 'Discrete':
                    searchCriteria = ''
                else:
                    searchCriteria = searchelements[0]

                # apply translation
                if criteriatrans == True:
                    searchCriteria = re.sub(upnpclass, newclass, searchCriteria)

#                print "searchCriteria: " + str(searchCriteria)

                if containerID == '':
                    # server does not support search type
                    result = {'NumberReturned': '0', 'UpdateID': '1', 'Result': '', 'TotalMatches': '0'}
                    return result
                else:
                    result = self.controlpoint.proxySearch(containerID, searchCriteria, kwargs['Filter'], kwargs['StartingIndex'], kwargs['RequestedCount'], kwargs['SortCriteria'], self.mediaserver)
                # cache results

                if 'Result' in result:
                    # at this level there should be at least one container in the result (Asset returns items for playlists if not registered),
                    # unless we are searching tracks

#                    print result['Result']

                    if not '<container id' in result['Result'] and searchtype != 'Tracks':
                        result = {'NumberReturned': '0', 'UpdateID': '1', 'Result': '', 'TotalMatches': '0'}
                        return result

                    if searchtype != 'Tracks':
                        # get cache to hold results in
                        cache = self.caches[mscontainerID + ' - ' + searchelements[0]]
                        # save results in cache
                        self.update_cache(result['Result'], cache)

            elif len(searchelements) >= 3:
                # not first time through, use cache to get container id

                check_for_containers = False
                if searchelements[0] == 'upnp:class derivedfrom "object.item.audioItem"':
                    # In this search Sonos is expecting items rather than containers, need to check
                    # what we get in the result and may need to make another search
                    check_for_containers = True

                # get cache
                classstring = searchelements[2].split(' = ')
                upnpclass = classstring[0]
                dctitle = classstring[1][1:-1]
                cache = self.decaches[upnpclass]

                # add on any subelements to cache item name
                numelements = len(searchelements)
                if numelements > 3:
                    for i in range(3, numelements):
                        substring = searchelements[i].split(' = ')
                        subtype = substring[0]
                        subtitle = substring[1][1:-1]
                        dctitle += ' - ' + subtitle

                containerID = cache[dctitle]

#                print "containerID: " + str(containerID)

                if self.subtranslate == 'Discrete':
                    searchCriteria = ''
                else:
                    searchCriteria = searchelements[0]
                    if numelements >= 3:
                        for i in range(2, numelements):
                            additionalCriteria = searchelements[i]
                            # perform any attribute translations
                            for k, v in self.attribute_mappings.iteritems():
                                additionalCriteria = re.sub(k, v, additionalCriteria)
#                            print "@@@@ add: " + str(additionalCriteria)
                            # 3 hacks for Twonky follow TODO: add to ini
                            if not 'upnp:genre' in additionalCriteria:
                                searchCriteria += ' and ' + additionalCriteria
                            if 'upnp:genre' in additionalCriteria and check_for_containers == True:
                                searchCriteria += ' and ' + additionalCriteria
                        if 'upnp:author' in searchCriteria:
                            searchCriteria = '*'
                        if 'upnp:albumArtist' in searchCriteria:
                            searchCriteria = '*'

#                print "searchCriteria: " + str(searchCriteria)

                result = self.controlpoint.proxySearch(containerID, searchCriteria, kwargs['Filter'], kwargs['StartingIndex'], kwargs['RequestedCount'], kwargs['SortCriteria'], self.mediaserver)

#                print result['Result']

                if 'Result' in result:

                    # save in cache with prefix of search class
                    container_found, item_found, container_list = self.update_cache(result['Result'], cache, dctitle)

                    if check_for_containers == True and container_found == True and self.subtranslate == 'Discrete':
                        # In this search Sonos is expecting items rather than containers, but we found containers
                        # We need to search the containers too
#                        print container_list
                        new_result = {}
                        numberReturned = totalMatches = 0
                        items = ''
                        if 'UpdateID' in result:
                            new_result['UpdateID'] = result['UpdateID']

                        for childID in container_list:
                            child_result = self.controlpoint.proxySearch(childID, searchCriteria, kwargs['Filter'], kwargs['StartingIndex'], kwargs['RequestedCount'], kwargs['SortCriteria'], self.mediaserver)
                            if 'Result' in child_result:
                                numberReturned += int(child_result['NumberReturned'])
                                totalMatches += int(child_result['TotalMatches'])

                                # split out items and containers
                                item, containers = self.process_result(child_result['Result'])
                                # for containers, append to list we are processing
                                if containers != []:
                                    container_list += containers
                                # for items, add to found items
                                if item != '':
                                    items += item
                        result_xml  = '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:dlna="urn:schemas-dlna-org:metadata-1-0/">'
                        result_xml += items
                        result_xml += '</DIDL-Lite>'

                        new_result['NumberReturned'] = str(numberReturned)
                        new_result['TotalMatches'] = str(totalMatches)
                        new_result['Result'] = result_xml
#                        print 'new_result: ' + str(new_result)

                        # save our result
                        result = new_result

                    if check_for_containers == False and item_found == True and self.subtranslate != 'Discrete':
                        # In this search Sonos is expecting containers rather than items, but we found items too
                        # We need to remove the items (assume they may not be consecutive)
                        new_result = result['Result']
                        numberReturned = int(result['NumberReturned'])
                        totalMatches = int(result['TotalMatches'])
                        num_items = new_result.count('</item>')
                        numberReturned -= num_items
                        totalMatches -= num_items
                        while '<item ' in new_result:
                            new_result = re.sub('<item.*?</item>' , '', new_result)
                        result['Result'] = new_result
                        result['NumberReturned'] = str(numberReturned)
                        result['TotalMatches'] = str(totalMatches)

#                    print result['Result']

                    '''
                    test of album art

                    if '<upnp:albumArtURI dlna:profileID="JPEG_TN">http://192.168.0.10:26125/albumart/Art--1859633031.jpg/cover.jpg</upnp:albumArtURI>' in result['Result']:

                        print "------------------------------------------------------"
                        print "UDN: " + str(self.proxy.udn)
                        udn = self.proxy.udn.replace('uuid:', '')
                        print ">>>>>>>>>>>"

#                        aart  = '<upnp:albumArtURI>/getaa?m=1&u=http://'
                        aart  = '<upnp:albumArtURI>/getaa?u=http://'
                        aart += udn
                        aart += '.x-udn/'
#                        aart += '192.168.0.2:10243/
                        aart += 'albumart/Art--1859633031.jpg/cover.jpg'
#                        aart += 'content/c2/b16/f44100/7782.mp3'
#                        aart += '?albumArt=true</upnp:albumArtURI>'
                        aart += '</upnp:albumArtURI>'

#                        aart = '<upnp:albumArtURI>http://192.168.0.2:10243/albumart/Art--1859633031.jpg/cover.jpg</upnp:albumArtURI>'
#                        aart = '<upnp:albumArtURI>/getaa?m=1&u=http://192.168.0.2:10243/content/c2/b16/f44100/7782.mp3?albumArt=true</upnp:albumArtURI>'

#http://192.168.0.2:10243/albumart/Art--1859633031.jpg/cover.jpg

                        result['Result'] = result['Result'].replace('<upnp:albumArtURI dlna:profileID="JPEG_TN">http://192.168.0.10:26125/albumart/Art--1859633031.jpg/cover.jpg</upnp:albumArtURI>', aart)

                        print result['Result']

                        print "------------------------------------------------------"

#<upnp:albumArtURI dlna:profileID="JPEG_TN">http://192.168.0.10:26125/albumart/Art--1859633031.jpg/cover.jpg</upnp:albumArtURI>

#/getaa?m=1&u=http://02286246-a968-4b5b-9a9a-defd5e9237e0.x-udn/WMPNSSv3/4206383637/1_e0JBNDM5NENDLUJENjgtNDQ0Ny05NTdFLTMxNTQ5QTAxRDI2Qn0uMC40.mp3?albumArt=true

#/getaa?m=1&u=http://b68dd228-957b-4cfe-abcd-123456789abc.x-udn/content/c2/b16/f44100/7782.mp3?albumArt=true

                    '''

        elif self.translate == 'Browse':
            pass

#            if containerID in self.container_mappings:
#                containerID = self.container_mappings[containerID]

#            result = self.soap_Browse(ObjectID=containerID, BrowseFlag='BrowseDirectChildren', Filter='*', StartingIndex=kwargs['StartingIndex'], RequestedCount=kwargs['RequestedCount'], SortCriteria='')
#            REMEMBER TO ADJUST THE XML SURROUNDING THE RESULT SO IT LOOKS LIKE A SEARCH RESPONSE!
#            result = self.controlpoint.proxySearch(containerID, searchCriteria, kwargs['Filter'], kwargs['StartingIndex'], kwargs['RequestedCount'], kwargs['SortCriteria'], self.mediaserver)
#            print result['Result']

        else:
            print 'Unsupported Translation type "' + self.translate + '" in pycpoint.ini file'
            result = {'NumberReturned': '0', 'UpdateID': '1', 'Result': '', 'TotalMatches': '0'}
            return result

        # post process result
        if 'Result' in result:
            # if result contains destination addresses in XML, need to transform them to proxy addresses
            # (otherwise the Sonos kicks up a fuss)
            # for WMP at least, the port of the dest track address may not be the port of the dest webserver
            #    so we need to save the dest track address
            res = result['Result']
            address = re.search(self.destip + ':[0-9]*', res)
            if address != None:
                self.destmusicaddress = self.destscheme + '://' + address.group()
                # save this address so proxy can use it
                self.proxy.destmusicaddress = self.destmusicaddress
                res = re.sub(self.destmusicaddress, self.proxyaddress, res)

#            # remove all but first res - assumes res are consecutive
#            firstres = re.search('<res[^<]*</res>', res)
#            if firstres != None:
#                res = re.sub('<res.*</res>' , firstres.group(), res)

            # if proxied server returns flac, spoof it as something else that is supported
            # on WMP, otherwise Sonos will not offer to play it as an individual track
            res = res.replace(':audio/x-flac:', ':audio/x-ms-wma:')

            result['Result'] = res
#            print "@@@@@@@@@ res after: " + str(res)

        return result

    def update_cache(self, result, cache, prefix=''):
        # get containers returned
        container_found = False
        item_found = False
        container_list = []
        elt = parse_xml(result)
        elt = elt.getroot()
        for item in elt.getchildren():
            # only save containers, not individual items
            if item.tag == '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}container':
                containerid = item.attrib.get('id')
                dctitle = item.find('{%s}%s' % ('http://purl.org/dc/elements/1.1/', 'title')).text
#                upnpclass = item.find('{%s}%s' % ('urn:schemas-upnp-org:metadata-1-0/upnp/', 'class'))
                if prefix != '':
                    dctitle = prefix + ' - ' + dctitle
                cache[dctitle] = containerid
                container_list.append(containerid)
                container_found = True
            elif item.tag == '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item':
                item_found = True
        return container_found, item_found, container_list
#        print "~~~~~~~~~~~~~~~~~~~~~~~"
#        print cache
#        print "~~~~~~~~~~~~~~~~~~~~~~~"

    def process_result(self, result):
        container_list = []
        items = ''
        elt = parse_xml(result)
        elt = elt.getroot()
        for item in elt.getchildren():
            if item.tag == '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}container':
                containerid = item.attrib.get('id')
                container_list.append(containerid)
            elif item.tag == '{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}item':
                items += ElementTree.tostring(item)
        return items, container_list

    def soap_GetSearchCapabilities(self, *args, **kwargs):
        result = self.controlpoint.proxyGetSearchCapabilities(self.mediaserver)
        return result
    def soap_GetSortCapabilities(self, *args, **kwargs):
        result = self.controlpoint.proxyGetSortCapabilities(self.mediaserver)
        return result
    def soap_GetSystemUpdateID(self, *args, **kwargs):
        result = self.controlpoint.proxyGetSystemUpdateID(self.mediaserver)
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

###############
###############
# SMAPI service
###############
###############

class Smapi(Service):

    service_name = 'smapi'
    service_type = 'http://www.sonos.com/Services/1.1'
#    service_type = 'urn:schemas-upnp-org:service:smapi:1'
    scpd_xml_path = os.path.join(os.getcwd(), 'smapi-scpd.xml')

    def __init__(self, proxyaddress, proxy , webserverurl, wmpurl, dbspec, wmpudn):

        self.proxyaddress = proxyaddress
        self.proxy = proxy
        self.webserverurl = webserverurl
        self.wmpurl = wmpurl
        self.dbspec = dbspec
        dbpath, self.dbname = os.path.split(dbspec)
        self.wmpudn = wmpudn

        # create MediaServer with SMAPI structure
        self.mediaServer = MediaServer(self.proxy, self.dbspec, 'HIERARCHY', self.proxyaddress, self.webserverurl, self.wmpurl)

#        self.prime_cache()

        Service.__init__(self, self.service_name, self.service_type, url_base='', scpd_xml_filepath=self.scpd_xml_path)

# TODO: replace scpd with ws:
#       namespace is currently hardcoded
#       result is manually created from children

    #####################
    # SMAPI soap services
    #####################

    def soap_getSessionId(self, *args, **kwargs):
        # shouldn't be used, set to anonymous
        log.debug("SMAPI_GETSESSIONID: %s", kwargs)
        sessionid = 'sessionid'
        res  = '<ns0:sessionId>%s</ns0:sessionId>' % (sessionid)
        result = {'{http://www.sonos.com/Services/1.1}getSessionIdResult': '%s' % (res)}
        log.debug("GETSESSIONID ret: %s", result)
        return result

    def soap_getLastUpdate(self, *args, **kwargs):
#        log.debug("SMAPI_GETLASTUPDATE: %s", kwargs)

#        db1 = sqlite3.connect('lastupdate.sqlite')
#        cs1 = db1.cursor()
#        cs1.execute('select catalog from lastupdate')
#        catalog, = cs1.fetchone()
#        db1.close()

        updated, containerupdateid = self.mediaServer.get_containerupdateid()

        res  = '<ns0:catalog>%s</ns0:catalog>' % (containerupdateid)
        res += '<ns0:favorites>%s</ns0:favorites>' % ('1')
        result = {'{http://www.sonos.com/Services/1.1}getLastUpdateResult': '%s' % (res)}
#        log.debug("GETLASTUPDATE ret: %s", result)
        return result

    def soap_reloadIni(self, *args, **kwargs):

        log.debug("SMAPI_RELOADINI: %s", kwargs)

        import ConfigParser
        import StringIO
        import codecs
        config = ConfigParser.ConfigParser()
        config.optionxform = str
        ini = ''
        f = codecs.open('pycpoint.ini', encoding=enc)
        for line in f:
            ini += line
        config.readfp(StringIO.StringIO(ini))
        self.proxy.config = config

        self.load_ini()

        ret = '<ns0:result>1</ns0:result>'

        result = {'reloadIniResult': ret}
        log.debug("SMAPI_RELOADINI ret: %s\n", result)
        return result

    def soap_invalidateCD(self, *args, **kwargs):

        log.debug("SMAPI_INVALIDATECD: %s", kwargs)

        self.mediaServer.set_containerupdateid()

        ret = '<ns0:result>1</ns0:result>'

        result = {'invalidateCDResult': ret}
        log.debug("SMAPI_INVALIDATECD ret: %s\n", result)
        return result

    def soap_getScrollIndices(self, *args, **kwargs):

        '''
Are we implementing this for search?
What about genre-artist?
Which indices are large - should we just perform it for all container queries that return a large count (or over a certain number)?
What do we do if a result is not in alpha order?
        '''

        log.debug("\nSMAPI_GETSCROLLINDICES: %s", kwargs)

        controllername = kwargs.get('Controller', '')
        controlleraddress = kwargs.get('Address', '')
        log.debug('Controller: %s' % controllername)
        log.debug('Address: %s' % controlleraddress)

        collectionID = kwargs['{http://www.sonos.com/Services/1.1}id']
        log.debug("id: %s" % collectionID)

        collectionIDval = None
        try:
            collectionIDval = int(collectionID)
        except ValueError:
            pass

        result = ''
        res = ''
        if collectionIDval:

            browsetype, browsebyid = self.mediaServer.get_index(collectionIDval)
            log.debug(browsetype)
            log.debug(browsebyid)

            # get type of hierarchy
            static = self.hierarchytype[browsetype]
            log.debug(static)

            if not static:

                # dynamic
                ContainerID = '999'     # dummy
                SearchCriteria = ''
                StartingIndex = 0
                RequestedCount = 1
                scrollresult = self.mediaServer.dynamicQuery(Controller=controllername,
                                                                Address=controlleraddress,
                                                                ContainerID=ContainerID,
                                                                SearchCriteria=SearchCriteria,
                                                                StartingIndex=StartingIndex,
                                                                RequestedCount=RequestedCount,
                                                                SMAPIalpha=browsetype,
                                                                SMAPI=None,
                                                                SMAPIkeys=[],
                                                                SMAPIfull=[],
                                                                Source='SMAPI')

            elif not browsebyid:

                scrolltype = 'Alpha%s' % browsetype
                # create call data for CD Search and call it
                ContainerID = '999'     # dummy
                SearchCriteria = ''
                StartingIndex = 0
                RequestedCount = 1
                scrollresult = self.mediaServer.staticQuery(Controller=controllername,
                                                              Address=controlleraddress,
                                                              QueryID=ContainerID,
                                                              SearchCriteria=SearchCriteria,
                                                              StartingIndex=StartingIndex,
                                                              RequestedCount=RequestedCount,
                                                              SMAPI=scrolltype,
                                                              SMAPIkeys='',
                                                              smapiservice=self,
                                                              Source='SMAPI')

            log.debug(scrollresult)

            if scrollresult:
                alphabet = u'abcdefghijklmnopqrstuvwxyz'
                index = 0
                alpha = {}
                for row in scrollresult:
                    log.debug("row: %s", row)
                    count, char = row
                    if char != '' and char in alphabet:
                        alpha[char] = str(index)
                        currindex = index
                    index += count
                log.debug(alpha)
                if index > 0:
                    for letter in alphabet[::-1]:
                        if letter in alpha.keys():
                            currindex = alpha[letter]
                        else:
                            alpha[letter] = currindex
                        res = ','.join(filter(None,(letter, str(currindex), res)))
                log.debug(alpha)
                res = res.upper()

        result = {'{http://www.sonos.com/Services/1.1}getScrollIndicesResult': '%s' % (res)}
        log.debug("SMAPI_GETSCROLLINDICES ret: %s\n", result)
        return result

    def soap_getMediaURI(self, *args, **kwargs):

        log.debug("\nSMAPI_GETMEDIAURI: %s", kwargs)
        res = self.processMediaMetadata('uri', kwargs)
        result = {'{http://www.sonos.com/Services/1.1}getMediaURIResult': '%s' % (res)}
        log.debug("SMAPI_GETMEDIAURI ret: %s\n", result)
        return result

    def soap_search(self, *args, **kwargs):

        log.debug("SMAPI_SEARCH: %s", kwargs)
        res = self.processMetadata(kwargs)
        result = {'{http://www.sonos.com/Services/1.1}searchResult': '%s' % res}
        log.debug("SMAPI_SEARCH ret: %s\n", result)
        return result

    def soap_getMetadata(self, *args, **kwargs):

        log.debug("SMAPI_GETMETADATA: %s", kwargs)
        res = self.processMetadata(kwargs)
        result = {'{http://www.sonos.com/Services/1.1}getMetadataResult': '%s' % res}
        log.debug("SMAPI_GETMETADATA ret: %s\n", result)
        return result

    def soap_getMediaMetadata(self, *args, **kwargs):

        log.debug("SMAPI_GETMEDIAMETADATA: %s", kwargs)
        res = self.processMediaMetadata('metadata', kwargs)
        result = {'{http://www.sonos.com/Services/1.1}getMediaMetadataResult': '%s' % res}
        log.debug("SMAPI_GETMEDIAMETADATA ret: %s\n", result)
        return result

    ####################
    # SMAPI soap helpers
    ####################

    def processMetadata(self, kwargs):

        # extract args and convert to MediaServer ones
        controllername = kwargs.get('Controller', '')
        controlleraddress = kwargs.get('Address', '')
        log.debug('Controller: %s' % controllername)
        log.debug('Address: %s' % controlleraddress)

        id = kwargs['{http://www.sonos.com/Services/1.1}id']
        log.debug("id: %s" % id)
        index = int(kwargs['{http://www.sonos.com/Services/1.1}index'])
        log.debug("index: %s" % index)
        count = int(kwargs['{http://www.sonos.com/Services/1.1}count'])
        log.debug("count: %s" % count)
        recursive = kwargs.get('{http://www.sonos.com/Services/1.1}recursive', False)
        if recursive == 'true' or recursive == '1': recursive = True
        log.debug("recursive: %s" % recursive)
        term = kwargs.get('{http://www.sonos.com/Services/1.1}term', None)
        log.debug("term: %s" % term)

        try:
            # we don't know query type, call wrapper
            items, total, index, itemtype = self.mediaServer.query(Controller=controllername,
                                                                    Address=controlleraddress,
                                                                    ID=id,
                                                                    StartingIndex=index,
                                                                    RequestedCount=count,
                                                                    recursive=recursive,
                                                                    term=term,
                                                                    Source='SMAPI')

        except: # catch *all* exceptions
            e = sys.exc_info()[0]
            log.debug(e)
            import traceback
            tb = traceback.format_exc()
            log.debug(tb)

        # create result XML
        if itemtype == 'container':
            result = self.make_collectionresult(items, total, index, canscroll=False)
        elif itemtype == 'track':
            result = self.make_metadataresult(items, total, index, nototal=False)
        else:   # root or search
            result = self.make_collectionresult(items, total, index, canscroll=True)

        log.debug("METADATA ret: %s", result)

        return result

    def processMediaMetadata(self, metadatatype, kwargs):

        # extract args and convert to MediaServer ones
        controllername = kwargs.get('Controller', '')
        controlleraddress = kwargs.get('Address', '')
        log.debug('Controller: %s' % controllername)
        log.debug('Address: %s' % controlleraddress)

        objectID = kwargs['{http://www.sonos.com/Services/1.1}id']
        log.debug("id: %s" % objectID)

        BrowseFlag = 'BrowseDirectChildren'            ## IS THIS CORRECT (probably ignored)
        index = 0
        count = 1

        # we know query type, call it direct
        items, total, index, itemtype = self.mediaServer.staticQuery(Controller=controllername,
                                                                        Address=controlleraddress,
                                                                        ObjectID=objectID,
                                                                        BrowseFlag=BrowseFlag,
                                                                        StartingIndex=index,
                                                                        RequestedCount=count,
                                                                        SMAPI='Track',
                                                                        smapiservice=self,
                                                                        Source='SMAPI',
                                                                        Action='BROWSE')
        log.debug(total)
        log.debug(items)

        # create result XML
        if metadatatype == 'metadata':
            result = self.make_metadataresult(items, total, index, nototal=True)
        else:   # 'uri'
            result = self.make_uriresult(items)

        log.debug("MEDIAMETADATA ret: %s", result)

        return result

    def make_collectionresult(self, items, total, index, canscroll=True):

        log.debug(items)
        log.debug(total)

        ret = ''
        count = 0

        canenumerate = True
        canplay = True
        
        if total == 0:
#                itemid = containerstart + self.id_range
#                title = self.noitemsfound
#                itemid = ':'.join(filter(None,(itemidprefix, str(itemid))))
#                items += [(itemid, title)]
#                totalMatches = 1

            items = [('NIF', self.mediaServer.noitemsfound)]
        
#        if total == 1 and items[0][1] == self.mediaServer.noitemsfound:
            # empty index
            canenumerate = False
            canplay = False
            total = 1

        for item in items:
            id = item[0]
            title = item[1]
            count += 1
            if len(item) == 2:
                # is a container
                ret += '<ns0:mediaCollection>'
                ret += '<ns0:id>%s</ns0:id>' % (id)
                ret += '<ns0:title>%s</ns0:title>' % (title)
                ret += '<ns0:itemType>container</ns0:itemType>'
                ret += '<ns0:canPlay>%i</ns0:canPlay>' % (canplay)
                ret += '<ns0:canScroll>%i</ns0:canScroll>' % (canscroll)
                ret += '<ns0:canEnumerate>%i</ns0:canEnumerate>' % (canenumerate)
                ret += '</ns0:mediaCollection>'
            else:
                # is a track
                ret += self.make_metadataresult([item], total, index, nototal=True)

        log.debug(ret)

        pre  = '<ns0:index>%s</ns0:index>' % (index)
        pre += '<ns0:count>%s</ns0:count>' % (count)
        pre += '<ns0:total>%s</ns0:total>' % (total)

        res = '%s%s' % (pre, ret)

        return res

    def make_metadataresult(self, items, total, index, nototal=False):

        ret = ''
        count = 0
        for (id, title, mimetype, uri, itemtype, metadatatype, metadata) in items:

            if metadatatype == 'track':
                meta = self.make_trackmetadataresult(metadata)
            elif metadatatype == 'stream':
                meta = self.make_streammetadataresult(metadata)

            count += 1
            ret += '<ns0:mediaMetadata>'
            ret += '<ns0:id>%s</ns0:id>' % (id)
            ret += '<ns0:title>%s</ns0:title>' % (title)
            ret += '<ns0:mimeType>%s</ns0:mimeType>' % (mimetype)
            ret += '<ns0:itemType>%s</ns0:itemType>' % (itemtype)
            ret += meta
            ret += '</ns0:mediaMetadata>'

        if nototal:
            pre = ''
        else:
            pre  = '<ns0:index>%s</ns0:index>' % (index)
            pre += '<ns0:count>%s</ns0:count>' % (count)
            pre += '<ns0:total>%s</ns0:total>' % (total)

        res = '%s%s' % (pre, ret)

        return res

    def make_trackmetadataresult(self, metadata):

        ret = ''

        aristId, artist, composerId, composer, \
        albumId, album, albumArtURI, albumArtistId, \
        albumArtist, genreId, genre, duration = metadata

        ret += '<ns0:trackMetadata>'
        ret += '<ns0:aristId>%s</ns0:aristId>' % (aristId)
        ret += '<ns0:artist>%s</ns0:artist>' % (artist)
        ret += '<ns0:composerId>%s</ns0:composerId>' % (composerId)
        ret += '<ns0:composer>%s</ns0:composer>' % (composer)
        ret += '<ns0:albumId>%s</ns0:albumId>' % (albumId)
        ret += '<ns0:album>%s</ns0:album>' % (album)
        ret += '<ns0:albumArtURI>%s</ns0:albumArtURI>' % (albumArtURI)
        ret += '<ns0:albumArtistId>%s</ns0:albumArtistId>' % (albumArtistId)
        ret += '<ns0:albumArtist>%s</ns0:albumArtist>' % (albumArtist)
        ret += '<ns0:genreId>%s</ns0:genreId>' % (genreId)
        ret += '<ns0:genre>%s</ns0:genre>' % (genre)
        ret += '<ns0:duration>%s</ns0:duration>' % (duration)
        ret += '</ns0:trackMetadata>'

        return ret

    def make_streammetadataresult(self, metadata):

        ret = ''

        # TODO

        return ret

    def make_uriresult(self, items):

        id, title, mimetype, uri, itemtype, metadatatype, metadata = items[0]

        return uri

###############################
###############################
# DummyContentDirectory service
###############################
###############################

class DummyContentDirectory(Service):

    service_name = 'ContentDirectory'
    service_type = 'urn:schemas-upnp-org:service:ContentDirectory:1'
    scpd_xml_path = os.path.join(os.getcwd(), 'content-directory-scpd.xml')

    def __init__(self, proxyaddress, proxy , webserverurl, wmpurl, dbspec, wmpudn):
        self.proxyaddress = proxyaddress
        self.proxy = proxy
        self.webserverurl = webserverurl
        self.wmpurl = wmpurl
        self.dbspec = dbspec
        dbpath, self.dbname = os.path.split(dbspec)
        self.wmpudn = wmpudn

        # check what structure we should use
        self.load_ini()

        if self.use_browse_for_WMP and not self.use_SMAPI_indexes_for_WMP:

            # create MediaServer with default SMAPI structure
            self.mediaServer = MediaServer(self.proxy, self.dbspec, 'HIERARCHY_DEFAULT', self.proxyaddress, self.webserverurl, self.wmpurl)

        elif self.use_SMAPI_indexes_for_WMP:

            # create MediaServer with user defined SMAPI structure
            self.mediaServer = MediaServer(self.proxy, self.dbspec, 'HIERARCHY', self.proxyaddress, self.webserverurl, self.wmpurl)

        else:

            # create MediaServer with Proxy structure
            self.mediaServer = MediaServer(self.proxy, self.dbspec, 'FLAT', self.proxyaddress, self.webserverurl, self.wmpurl)

        Service.__init__(self, self.service_name, self.service_type, url_base='', scpd_xml_filepath=self.scpd_xml_path)

        self.systemupdateid = 0
        self.update_loop = LoopingCall(self.get_containerupdateid)
        self.update_loop.start(60.0, now=True)
#        self.inc_playlistupdateid()
#        from brisa.core.threaded_call import run_async_function
#        run_async_function(self.inc_playlistupdateid, (), 10)

    def get_containerupdateid(self):
        
        updated, containerupdateid = self.mediaServer.get_containerupdateid()
        if updated == True:
            self.systemupdateid += 1
            self._state_variables['SystemUpdateID'].update(self.systemupdateid)
            log.debug("SystemUpdateID value: %s" % self._state_variables['SystemUpdateID'].get_value())

    def set_containerupdateid(self):

        updated, containerupdateid = self.mediaServer.set_containerupdateid()

        if updated == True:
            self.systemupdateid += 1
            self._state_variables['SystemUpdateID'].update(systemupdateid)
            log.debug("SystemUpdateID value: %s" % self._state_variables['SystemUpdateID'].get_value())

    def load_ini(self):

        # get browse setting
        self.use_browse_for_WMP = False
        try:
            ini_use_browse_for_WMP = self.proxy.config.get('INI', 'use_browse_for_WMP')
            if ini_use_browse_for_WMP.lower() == 'y':
                self.use_browse_for_WMP = True
        except ConfigParser.NoSectionError:
            self.use_browse_for_WMP = False
        except ConfigParser.NoOptionError:
            self.use_browse_for_WMP = False
            
        # get SMAPI setting
        self.use_SMAPI_indexes_for_WMP = False
        try:
            ini_use_SMAPI_indexes_for_WMP = self.proxy.config.get('SMAPI WMP', 'use_SMAPI_indexes_for_WMP')
            if ini_use_SMAPI_indexes_for_WMP.lower() == 'y':
                self.use_SMAPI_indexes_for_WMP = True
        except ConfigParser.NoSectionError:
            self.use_SMAPI_indexes_for_WMP = False
        except ConfigParser.NoOptionError:
            self.use_SMAPI_indexes_for_WMP = False
            
    ###################
    # DCD soap services
    ###################

    def soap_ReloadIni(self, *args, **kwargs):
#        for key in kwargs:
#            print "another keyword arg: %s: %s" % (key, kwargs[key])

        log.debug("PROXY_RELOADINI: %s", kwargs)

        invalidate = kwargs.get('Invalidate', '')
        log.debug('Invalidate: %s' % invalidate)

        import ConfigParser
        import StringIO
        import codecs
        config = ConfigParser.ConfigParser()
        config.optionxform = str
        ini = ''
        f = codecs.open('pycpoint.ini', encoding=enc)
        for line in f:
            ini += line
        config.readfp(StringIO.StringIO(ini))
        self.proxy.config = config

        self.load_ini()

        ret  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
        ret += '1'
        ret += '</DIDL-Lite>'

        result = {'Result': ret}

        if int(invalidate) != 0:
            self.mediaServer.set_containerupdateid()

        return result

    def soap_InvalidateCD(self, *args, **kwargs):

        log.debug("PROXY_INVALIDATECD: %s", kwargs)

        invalidate = kwargs.get('Invalidate', '')
        log.debug('Invalidate: %s' % invalidate)

        self.mediaServer.set_containerupdateid()

        ret  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
        ret += '1'
        ret += '</DIDL-Lite>'

        result = {'Result': ret}

        return result

    def soap_Browse(self, *args, **kwargs):
#        for key in kwargs:
#            print "another keyword arg: %s: %s" % (key, kwargs[key])

        log.debug("PROXY_BROWSE: %s", kwargs)

        log.debug("self.use_browse_for_WMP: %s", self.use_browse_for_WMP)
        log.debug("self.use_SMAPI_indexes_for_WMP: %s", self.use_SMAPI_indexes_for_WMP)

        if (self.use_SMAPI_indexes_for_WMP or self.use_browse_for_WMP):
            structure = 'HIERARCHY'
        else:
            structure = 'FLAT'
        log.debug("structure: %s", structure)

        try:
            # call wrapper
            xml, count, total = self.mediaServer.query(Structure=structure,
                                                        Source='UPNP',
                                                        Action='BROWSE',
                                                        **kwargs)
        except: # catch *all* exceptions
            e = sys.exc_info()[0]
            log.debug(e)
            import traceback
            tb = traceback.format_exc()
            log.debug(tb)

        # fix WMP urls if necessary
        ret = xml.replace(self.webserverurl, self.wmpurl)

        log.debug("BROWSE ret: %s", ret)
        result = {'NumberReturned': str(count), 'UpdateID': self.systemupdateid, 'Result': ret, 'TotalMatches': str(total)}

        return result

    def soap_Search(self, *args, **kwargs):

        log.debug("PROXY_SEARCH: %s", kwargs)

        # hierarchy is not supported for search
        structure = 'FLAT'

        try:
            # call wrapper
            xml, count, total = self.mediaServer.query(Structure=structure,
                                                        Source='UPNP',
                                                        Action='SEARCH',
                                                        **kwargs)
        except: # catch *all* exceptions
            e = sys.exc_info()[0]
            log.debug(e)
            import traceback
            tb = traceback.format_exc()
            log.debug(tb)

        # fix WMP urls if necessary
        ret = xml.replace(self.webserverurl, self.wmpurl)

        log.debug("SEARCH ret: %s", ret)
        result = {'NumberReturned': str(count), 'UpdateID': self.systemupdateid, 'Result': ret, 'TotalMatches': str(total)}

        return result

    def soap_GetSearchCapabilities(self, *args, **kwargs):
        log.debug("PROXY_GetSearchCapabilities: %s", kwargs)
        result = {'SearchCaps': 'Artist,Contributing Artist,Composer,Album,Track,ALL'}
        return result
    def soap_GetSortCapabilities(self, *args, **kwargs):
        log.debug("PROXY_GetSortCapabilities: %s", kwargs)
        result = {'SortCaps': ''}
        return result
    def soap_GetSystemUpdateID(self, *args, **kwargs):
        log.debug("PROXY_GetSystemUpdateID: %s", kwargs)
        result = {'Id': self.systemupdateid}
        return result

################################
################################
# DummyConnectionManager service
################################
################################

class DummyConnectionManager(Service):

    service_name = 'ConnectionManager'
    service_type = 'urn:schemas-upnp-org:service:ConnectionManager:1'
    scpd_xml_path = os.path.join(os.getcwd(), 'connection-manager-scpd.xml')

    def __init__(self):
        Service.__init__(self, self.service_name, self.service_type, url_base='', scpd_xml_filepath=self.scpd_xml_path)
    def soap_GetCurrentConnectionInfo(self, *args, **kwargs):
        log.debug("PROXY_GetCurrentConnectionInfo: %s", kwargs)
        result = {'RcsID': '-1',
                  'AVTransportID': '-1',
                  'ProtocolInfo': '',
                  'PeerConnectionManager': '',
                  'PeerConnectionID': '-1',
                  'Direction': 'Output',
                  'Status': 'OK',
                 }
        return result
    def soap_GetProtocolInfo(self, *args, **kwargs):
        log.debug("PROXY_GetProtocolInfo: %s", kwargs)
        result = {'Source': 'http-get:*:*:*',
                  'Sink': '',
                 }
        return result
    def soap_GetCurrentConnectionIDs(self, *args, **kwargs):
        log.debug("PROXY_GetCurrentConnectionIDs: %s", kwargs)
        result = {'ConnectionIDs': '0'}
        return result

#####################################
#####################################
# X_MS_MediaReceiverRegistrar service
#####################################
#####################################

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
#        ret = {'RegistrationRespMsg': '1'}
        resp = '''AgIAvzAwMEU1ODIzQTg4QTAxNDAp1ehXMUNEcFMtyN5so8RGABZJUDQ6MTkyLjE2OC4wLjEwOjEwMjgwAQCAYKJjzWiIzMQgENT1usjHt48MqNb4j5GFPAndo54eQEH57uzmZgeiqFXMf9WqB/denTRWXV2XIm75hg5/TmgTA6h0OwDqBLxdB2EZxfy1mtMndH79CwmVxXHmdsuAAgMy9I3g/mu3lE9M60Mzzkuu0obNpisuRWeGXwB2qGgmQTIBABDqzqB4aML/dcQfOobboXDh'''
        ret = {'RegistrationRespMsg': resp}
        return ret


