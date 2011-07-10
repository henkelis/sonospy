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

from transcode import checktranscode

from xml.etree.ElementTree import _ElementInterface
from xml.etree import cElementTree as ElementTree

from xml.sax.saxutils import escape, unescape

from brisa.core import log

from brisa.core import webserver, network

from brisa.upnp.device import Device
from brisa.upnp.device.service import Service
from brisa.upnp.device.service import StateVariable
from brisa.upnp.soap import HTTPProxy, HTTPRedirect
from brisa.core.network import parse_url, get_ip_address, parse_xml
from brisa.utils.looping_call import LoopingCall

enc = sys.getfilesystemencoding()

MULTI_SEPARATOR = '\n'

class Proxy(object):

    def __init__(self, proxyname, proxytype, proxytrans, udn, config, port, 
                 mediaserver=None, controlpoint=None, createwebserver=False, webserverurl=None, wmpurl=None, startwmp=False, dbname=None, wmpudn=None, wmpcontroller=None, wmpcontroller2=None):
        '''
        To proxy an external mediaserver, set:
            port = the port to listen on for proxy control messages
            mediaserver = the mediaserver device being proxied
            controlpoint = the controller device containing a webserver to utilise
            createwebserver = False
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
        self.dbname = dbname
        self.wmpudn = wmpudn
        self.wmpwebserver = None
        self.wmpcontroller = wmpcontroller
        self.wmpcontroller2 = wmpcontroller2

        self.destmusicaddress = None
        if mediaserver == None:
            self.destaddress = None
        else:
            self.destaddress = mediaserver.address

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
            self.cdservice = DummyContentDirectory(self.root_device.location, self, self.webserverurl, self.wmpurl, self.dbname, self.wmpudn)
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
        self.wmpwebserver = webserver.WebServer(host=p.hostname, port=p.port)
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
        #   db + id + type_extension e.g. mp3tag.sqlite.6000022.flac (also could be mp3tag.sqlite.6000022.jpg)
        # or
        #   db + id + transcode_extension(s) + type extension e.g. mp3tag.sqlite.6000023.mp2.mp3
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
        db = sqlite3.connect(os.path.join(os.getcwd(), dbname))
        c = db.cursor()

        statement = "select * from tracks where id = '%s'" % (objectID)
        log.debug("statement: %s", statement)
        c.execute(statement)

        id, id2, parentID, duplicate, title, artist, album, genre, tracknumber, year, albumartist, composer, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, upnpclass, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned = c.fetchone()
        log.debug("id: %s", id)
        mime = fixMime(mime)
        cover, artid = self.cdservice.choosecover(folderart, trackart, folderartid, trackartid)
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


class ProxyServerController(webserver.SonosResource):

    def __init__(self, proxy, res):
        webserver.SonosResource.__init__(self, res, proxy)


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










class DummyContentDirectory(Service):

    service_name = 'ContentDirectory'
    service_type = 'urn:schemas-upnp-org:service:ContentDirectory:1'
    scpd_xml_path = os.path.join(os.getcwd(), 'content-directory-scpd.xml')

    id_range = 99999999
    artist_parentid = 100000000
    contributingartist_parentid = 200000000   # dummy
    album_parentid = 300000000
    composer_parentid = 400000000
    genre_parentid = 500000000
    track_parentid = 600000000
    playlist_parentid = 700000000


    artist_class = 'object.container.person.musicArtist'
#    contributingartist_class = ''
    album_class = 'object.container.album.musicAlbum'
    composer_class = 'object.container.person.musicArtist'
    genre_class = 'object.container.person.musicArtist'
    track_class = 'object.container.person.musicArtist'
#    playlist_class = ''


    def __init__(self, proxyaddress, proxy , webserverurl, wmpurl, dbname, wmpudn):
        self.proxyaddress = proxyaddress
        self.proxy = proxy
        self.webserverurl = webserverurl
        self.wmpurl = wmpurl
        self.dbname = dbname
        self.wmpudn = wmpudn
        if self.dbname == '':
            self.dbname = 'sonospy.sqlite'

#        self.prime_cache()
        
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
            self.album_distinct_duplicate = ' || duplicate'
            self.album_groupby_duplicate = ', duplicate'
            self.album_where_duplicate = ''
            self.album_and_duplicate = ''
        else:
            self.album_distinct_duplicate = ''
            self.album_groupby_duplicate = ''
            self.album_where_duplicate = ' where duplicate = 0'
            self.album_and_duplicate = ' and duplicate = 0'

        # get sorts setting
        self.use_sorts = False
        try:        
            ini_use_sorts = self.proxy.config.get('INI', 'use_sorts')
            if ini_use_sorts.lower() == 'y':
                self.use_sorts = True
        except ConfigParser.NoSectionError:
            self.use_sorts = False
        except ConfigParser.NoOptionError:
            self.use_sorts = False

        # get separator settings
        self.show_chunk_separator = False
        try:        
            ini_show_chunk_header = self.proxy.config.get('INI', 'show_chunk_header')
            if ini_show_chunk_header.lower() == 'y':
                self.show_chunk_separator = True
        except ConfigParser.NoSectionError:
            self.show_chunk_separator = False
        except ConfigParser.NoOptionError:
            self.show_chunk_separator = False

        self.show_chunk_separator_single = False
        try:        
            ini_show_chunk_header_single = self.proxy.config.get('INI', 'show_chunk_header_on_single')
            if ini_show_chunk_header_single.lower() == 'y':
                self.show_chunk_separator_single = True
        except ConfigParser.NoSectionError:
            self.show_chunk_separator_single = False
        except ConfigParser.NoOptionError:
            self.show_chunk_separator_single = False

        self.show_chunk_header_empty = False
        try:        
            ini_show_chunk_header_empty = self.proxy.config.get('INI', 'show_chunk_header_when_empty')
            if ini_show_chunk_header_empty.lower() == 'y':
                self.show_chunk_header_empty = True
        except ConfigParser.NoSectionError:
            self.show_chunk_header_empty = False
        except ConfigParser.NoOptionError:
            self.show_chunk_header_empty = False

        # override headers if sorts is off
        if not self.use_sorts:
            self.show_chunk_separator = False
            self.show_chunk_separator_single = False
            self.show_chunk_header_empty = False

        self.chunk_separator_delimiter = '-----'
        try:        
            self.chunk_separator_delimiter = self.proxy.config.get('INI', 'chunk_header_delimiter')
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        self.prefix_sep = u'\u00a0'
        self.suffix_sep = u'\u007f'

        # get chunk metadata characters
        prefix_start, self.chunk_metadata_delimiter_prefix_start = self.get_delim('chunk_metadata_delimiter_prefix_start', '[', self.prefix_sep)

#        prefix_end, self.chunk_metadata_delimiter_prefix_end = self.get_delim('chunk_metadata_delimiter_prefix_end', ']')
        prefix_end, self.chunk_metadata_delimiter_prefix_end = self.get_delim('chunk_metadata_delimiter_prefix_end', ']', self.prefix_sep, 'after')

#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('chunk_metadata_delimiter_suffix_start', '[', 'before', u'\u0092')
#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('chunk_metadata_delimiter_suffix_start', '[', 'before', u'\u200B\u034F\u0082\u0083\u0091\u0092\u2007\u2060\uFEFF\uFE00')
#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('chunk_metadata_delimiter_suffix_start', '[', 'before', u'\u2029\u2028\u202f\u2061\u2062\u2063\uE000\uE001')
#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('chunk_metadata_delimiter_suffix_start', '[', 'before', u'1 \uF7002 \uF7013 \uF85D4 \uF85C5 \uF8D76 \u000a7 \u000d')
#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('chunk_metadata_delimiter_suffix_start', '[', 'before', u'1 \u000d')
#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('chunk_metadata_delimiter_suffix_start', '[', 'before', u'\u007f')
#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('chunk_metadata_delimiter_suffix_start', '[', 'before', u'\u0f0c')
#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('chunk_metadata_delimiter_suffix_start', '[', 'before', u'\u007f \u232b \u0080 \u000a \u000d \u001b \u009f')

#        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('chunk_metadata_delimiter_suffix_start', '[')
        suffix_start, self.chunk_metadata_delimiter_suffix_start = self.get_delim('chunk_metadata_delimiter_suffix_start', '[', self.suffix_sep, 'before')

        suffix_end, self.chunk_metadata_delimiter_suffix_end = self.get_delim('chunk_metadata_delimiter_suffix_end', ']', self.suffix_sep)

        missing, self.chunk_metadata_empty = self.get_delim('chunk_metadata_empty', '_', self.prefix_sep)
        dateformat, self.chunk_metadata_date_format = self.get_delim('chunk_metadata_date_format', '%d/%m/%Y', self.prefix_sep)

        self.searchre_pre = '%s[^%s]*%s' % (prefix_start, prefix_end, prefix_end)
        if not suffix_end:
            self.searchre_suf = '%s.*' % (suffix_start)
        else:
            self.searchre_suf = '%s[^%s]*%s' % (suffix_start, suffix_end, suffix_end)

        self.multi_pre = '^(%s){%s}' % (self.searchre_pre, '%s')
        self.multi_suf = '(%s){%s}$' % (self.searchre_suf, '%s')

        self.replace_pre = '%s%s%s' % (self.chunk_metadata_delimiter_prefix_start, '%s', self.chunk_metadata_delimiter_prefix_end)
        self.replace_suf = '%s%s%s' % (self.chunk_metadata_delimiter_suffix_start, '%s', self.chunk_metadata_delimiter_suffix_end)

        # get artist to display
        self.now_playing_artist = 'all'    # default
        try:        
            self.now_playing_artist = self.proxy.config.get('INI', 'now_playing_artist')
            self.now_playing_artist = self.now_playing_artist.lower()
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        if not self.now_playing_artist in ['all', 'first', 'last']: self.now_playing_artist = 'all'

        self.now_playing_artist_combiner = '/'    # default
        try:        
            self.now_playing_artist_combiner = self.proxy.config.get('INI', 'now_playing_artist_combiner')
            if self.now_playing_artist_combiner.startswith("'") and self.now_playing_artist_combiner.endswith("'"):
                self.now_playing_artist_combiner = self.now_playing_artist_combiner[1:-1]
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        self.mouseover_artist = 'all'    # default
        try:        
            self.mouseover_artist = self.proxy.config.get('INI', 'mouseover_artist')
            self.mouseover_artist = self.mouseover_artist.lower()
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
        if not self.mouseover_artist in ['all', 'first', 'last']: self.mouseover_artist = 'all'

        self.mouseover_artist_combiner = '/'    # default
        try:        
            self.mouseover_artist_combiner = self.proxy.config.get('INI', 'mouseover_artist_combiner')
            if self.mouseover_artist_combiner.startswith("'") and self.mouseover_artist_combiner.endswith("'"):
                self.mouseover_artist_combiner = self.mouseover_artist_combiner[1:-1]
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

        Service.__init__(self, self.service_name, self.service_type, url_base='', scpd_xml_filepath=self.scpd_xml_path)

        self.updateid = ''
        self.update_loop = LoopingCall(self.get_updateid)
        self.update_loop.start(60.0, now=True)

    def get_delim(self, delimname, default, special, when=None):
        delim = default
        try:        
            delim = self.proxy.config.get('INI', delimname)
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

    def soap_Browse(self, *args, **kwargs):
#        for key in kwargs:
#            print "another keyword arg: %s: %s" % (key, kwargs[key])

        log.debug("PROXY_BROWSE: %s", kwargs)

        controllername = kwargs.get('Controller', '')
        controlleraddress = kwargs.get('Address', '')
        log.debug('Controller: %s' % controllername)
        log.debug('Address: %s' % controlleraddress)

        '''
{'ObjectID': '3000476',
 'BrowseFlag': 'BrowseDirectChildren',
 'Filter': 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber',
 'RequestedCount': '500',
 'StartingIndex': '0',
 'SortCriteria': '+upnp:originalTrackNumber'}
 
{'ObjectID': '6006179',
 'BrowseFlag': 'BrowseMetadata',
 'Filter': 'dc:title,res,res@duration,upnp:artist,upnp:artist@role,upnp:album,upnp:originalTrackNumber',
 'RequestedCount': '1',
 'StartingIndex': '0',
 'SortCriteria': ''}
        '''

        objectID = kwargs['ObjectID']
        browseFlag = kwargs['BrowseFlag']
        log.debug("objectID: %s" % objectID)

        db = sqlite3.connect(os.path.join(os.getcwd(), self.dbname))
        c = db.cursor()

        startingIndex = int(kwargs['StartingIndex'])
        requestedCount = int(kwargs['RequestedCount'])

        # TODO: work out whether we need support for anything other than album and track
        if '__' in objectID:
            objectfacets = objectID.split('__')
            objectTable = objectfacets[0]
            objectID = objectfacets[1]
        try:
            objectIDval = int(objectID)
        except ValueError:
            objectIDval = -1
            
        browsetype = ''
        
        if objectIDval == 0:
            browsetype = 'Root'
        elif objectIDval >= self.album_parentid and objectIDval <= (self.album_parentid + self.id_range):
            browsetype = 'Album'
        elif objectIDval == -1:
            browsetype = 'Track'
        elif objectIDval >= self.artist_parentid and objectIDval <= (self.artist_parentid + self.id_range):
            print "proxy_browse - asked for artist, not supported in code"
        elif objectIDval >= self.contributingartist_parentid and objectIDval <= (self.contributingartist_parentid + self.id_range):
            print "proxy_browse - asked for contributing artist, not supported in code"
        elif objectIDval >= self.composer_parentid and objectIDval <= (self.composer_parentid + self.id_range):
            print "proxy_browse - asked for composer, not supported in code"
        elif objectIDval >= self.genre_parentid and objectIDval <= (self.genre_parentid + self.id_range):
            print "proxy_browse - asked for genre, not supported in code"
        elif objectIDval >= self.playlist_parentid and objectIDval <= (self.playlist_parentid + self.id_range):
            print "proxy_browse - asked for playlist, not supported in code yet"

        if browsetype == 'Album':

            ret  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            count = 0

            # note that there is no way to select discrete tracks from an album 
            # that relate to an artist, composer etc with this search
            statement = "select album, artist, albumartist, duplicate, albumtype from albums where id = '%s'" % (objectID)
            log.debug("statement: %s", statement)
            c.execute(statement)
            album_title, album_artist, album_albumartist, album_duplicate, album_type = c.fetchone()

            album_title = album_title.replace("'", "''")
            album_artist = album_artist.replace("'", "''")
            album_albumartist = album_albumartist.replace("'", "''")

            if album_type != 10:
                where = "dummyalbum='%s'" % album_title
            else:
                where = "album='%s'" % album_title
            if 'artist' in self.album_group:
                where += " and artist='%s'" % album_artist
            if 'albumartist' in self.album_group:
                where += " and albumartist='%s'" % album_albumartist
            if self.show_duplicates:
                where += " and duplicate=%s" % album_duplicate
            else:
                where += " and duplicate=0"
            if album_type != 10:
                where += " and albumtype=%s" % album_type

            if album_type != 10:
                # is a work or a virtual album
#                statement = '''select * from tracks t, tracknumbers n where id in
#                               (select track_id from TrackNumbers where %s)
#                               and t.id = n.track_id and t.genre=n.genre and t.artist=n.artist and t.albumartist=n.albumartist and t.album=n.album and t.composer=n.composer and t.duplicate=n.duplicate and n.albumtype=%s and n.dummyalbum="%s"
#                               order by t.discnumber, n.tracknumber, t.title''' % (where, album_type, album_title)

                statement = '''
                                select * from tracks t join tracknumbers n on t.id = n.track_id where id in
                               (select track_id from TrackNumbers where %s)
                                and n.albumtype=%s and n.dummyalbum="%s"
                                order by n.tracknumber, t.title
                            ''' % (where, album_type, album_title)

                log.debug("statement: %s", statement)
                c.execute(statement)
            else:
                # is a normal album            
                statement = "select * from tracks where %s order by discnumber, tracknumber, title" % (where)
                log.debug("statement: %s", statement)
                c.execute(statement)
            for row in c:
#                log.debug("row: %s", row)
                if album_type != 10:
                    id, id2, parentID, duplicate, title, artist, album, genre, tracknumber, year, albumartist, composer, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, upnpclass, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned, d1, d2, d3, d4, d5, d6, d7, d8, d9, d10 = row
                else:
                    id, id2, parentID, duplicate, title, artist, album, genre, tracknumber, year, albumartist, composer, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, upnpclass, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned = row
                mime = fixMime(mime)
                cover, artid = self.choosecover(folderart, trackart, folderartid, trackartid)

                # TODO: automate mount
                wsfile = filename
                wspath = os.path.join(path, filename)
                path = self.convert_path(path)
                filepath = path + filename
                filepath = encode_path(filepath)
                filepath = escape(filepath, escape_entities)
                protocol = getProtocol(mime)
                contenttype = mime
                filetype = getFileType(filename)

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
                
                duration = maketime(float(length))

                if title == '': title = '[unknown title]'
                if artist == '': artist = '[unknown artist]'
                else: artist = self.get_artist(artist, self.mouseover_artist, self.mouseover_artist_combiner)
                if albumartist == '': albumartist = '[unknown albumartist]'
                else: albumartist = self.get_artist(albumartist, self.now_playing_artist, self.now_playing_artist_combiner)
                if album == '': album = '[unknown album]'
#                title = escape(title, escape_entities_quotepos)
#                artist = escape(artist, escape_entities_quotepos)
#                albumartist = escape(albumartist, escape_entities_quotepos)
#                album = escape(album, escape_entities_quotepos)
                title = escape(title)
                artist = escape(artist)
                albumartist = escape(albumartist)
                album = escape(album)
                tracknumber = self.convert_tracknumber(tracknumber)

                count += 1
                ret += '<item id="%s" parentID="%s" restricted="true">' % (id, parentID)
                ret += '<dc:title>%s</dc:title>' % (title)
                ret += '<upnp:artist role="AlbumArtist">%s</upnp:artist>' % (albumartist)
                ret += '<upnp:artist role="Performer">%s</upnp:artist>' % (artist)
                ret += '<upnp:album>%s</upnp:album>' % (album)
                if tracknumber != 0:
                    ret += '<upnp:originalTrackNumber>%s</upnp:originalTrackNumber>' % (tracknumber)
                ret += '<upnp:class>%s</upnp:class>' % (upnpclass)
                ret += '<res duration="%s" protocolInfo="%s">%s</res>' % (duration, protocol, res)
#                if cover != '' and not cover.startswith('EMBEDDED_'):
#                    ret += '<upnp:albumArtURI>%s</upnp:albumArtURI>' % (coverres)
                ret += '</item>'
            ret += '</DIDL-Lite>'

        elif browsetype == 'Track':

            ret  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            count = 0

            statement = "select * from tracks where id = '%s'" % (objectID)
            log.debug("statement: %s", statement)
            c.execute(statement)
            for row in c:   # will only be one row
#                log.debug("row: %s", row)
                id, id2, parentID, duplicate, title, artist, album, genre, tracknumber, year, albumartist, composer, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, upnpclass, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned = row
                mime = fixMime(mime)
                cover, artid = self.choosecover(folderart, trackart, folderartid, trackartid)

                # TODO: automate mount
                wsfile = filename
                wspath = os.path.join(path, filename)
                path = self.convert_path(path)
                filepath = path + filename
                filepath = encode_path(filepath)
                filepath = escape(filepath, escape_entities)
                protocol = getProtocol(mime)
                contenttype = mime
                filetype = getFileType(filename)
                
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
                
                duration = maketime(float(length))

                if title == '': title = '[unknown title]'
                if artist == '': artist = '[unknown artist]'
                else: artist = self.get_artist(artist, self.now_playing_artist, self.now_playing_artist_combiner)
                if albumartist == '': albumartist = '[unknown albumartist]'
                else: albumartist = self.get_artist(albumartist, self.now_playing_artist, self.now_playing_artist_combiner)
                if album == '': album = '[unknown album]'
#                title = escape(title, escape_entities_quotepos)
#                artist = escape(artist, escape_entities_quotepos)
#                albumartist = escape(albumartist, escape_entities_quotepos)
#                album = escape(album, escape_entities_quotepos)
                title = escape(title)
                artist = escape(artist)
                albumartist = escape(albumartist)
                album = escape(album)
                tracknumber = self.convert_tracknumber(tracknumber)

                count += 1
                ret += '<item id="%s" parentID="%s" restricted="true">' % (id, parentID)
                ret += '<dc:title>%s</dc:title>' % (title)
                ret += '<upnp:artist role="AlbumArtist">%s</upnp:artist>' % (albumartist)
                ret += '<upnp:artist role="Performer">%s</upnp:artist>' % (artist)
                ret += '<upnp:album>%s</upnp:album>' % (album)
                if tracknumber != 0:
                    ret += '<upnp:originalTrackNumber>%s</upnp:originalTrackNumber>' % (tracknumber)
                ret += '<upnp:class>%s</upnp:class>' % (upnpclass)
                ret += '<res duration="%s" protocolInfo="%s">%s</res>' % (duration, protocol, res)
#####                ret += '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">%s</desc>' % (self.wmpudn)
#                if cover != '' and not cover.startswith('EMBEDDED_'):
#                    ret += '<upnp:albumArtURI>%s</upnp:albumArtURI>' % (coverres)
                ret += '</item>'
            ret += '</DIDL-Lite>'

        elif browsetype == 'Root':

            ret  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'

            rootitems = [
                         ('7', 'Albums'),
                         ('6', 'Artists'),
                         ('108', 'Composers'),
                         ('100', 'Contributing Artists'),
                         ('5', 'Genres'),
                         ('F', 'Playlists'),
                         ('99', 'Tracks'),
                        ]

            for (id, title) in rootitems:

                ret += '<container id="%s" parentID="0" restricted="true">' % (id)
                ret += '<dc:title>%s</dc:title>' % (title)
                ret += '<upnp:class>object.container</upnp:class>'
                ret += '</container>'

            ret += '</DIDL-Lite>'
            count = 7

        elif browsetype == '':

            ret  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            ret += '</DIDL-Lite>'
            count = 0

        c.close()

        # fix WMP urls if necessary
        ret = ret.replace(self.webserverurl, self.wmpurl)

        log.debug("BROWSE ret: %s", ret)
        result = {'NumberReturned': str(count), 'UpdateID': self.updateid, 'Result': ret, 'TotalMatches': count}

        return result


    def soap_Search(self, *args, **kwargs):

        # TODO: fix error conditions (return zero)

        controllername = kwargs.get('Controller', '')
        controlleraddress = kwargs.get('Address', '')
        log.debug('Controller: %s' % controllername)
        log.debug('Address: %s' % controlleraddress)
        
        log.debug("start: %.3f" % time.time())

        containerID = kwargs['ContainerID']
        searchCriteria = kwargs['SearchCriteria']
        
        searchCriteria = self.fixcriteria(searchCriteria)

        log.debug('containerID: %s' % str(containerID))
        log.debug('searchCriteria: %s' % searchCriteria.encode(enc, 'replace'))
        log.debug("PROXY_SEARCH: %s", kwargs)

        # check if search requested
#        result = {'SearchCaps': 'Artist,Contributing Artist,Composer,Album,Track,ALL'}
        searchcontainer = None
        if searchCriteria.startswith('SEARCH::'):
            searchtype = searchCriteria[8:].split('::')[0]
            searchstring = searchCriteria[10+len(searchtype):]
            searchcontainer = searchtype
            if searchcontainer == 'Contributing Artist': searchcontainer = 'Artist'

        db = sqlite3.connect(os.path.join(os.getcwd(), self.dbname))
        c = db.cursor()

        startingIndex = int(kwargs['StartingIndex'])
        requestedCount = int(kwargs['RequestedCount'])

        if ((containerID == '107' or containerID == '100') and searchCriteria.startswith('upnp:class = "object.container.person.musicArtist" and @refID exists false')) or \
           searchcontainer == 'Artist':

            # Artist/Contributing Artist containers

            genres = []
            state_pre_suf = []

            if searchCriteria == 'upnp:class = "object.container.person.musicArtist" and @refID exists false' or \
               searchcontainer == 'Artist':
                # Artists
                log.debug('artists')
                genres.append('dummy')
                searchtype = 'ARTIST'
                searchwhere = ''
                if containerID == '107':
                    if self.use_albumartist:
                        artisttype = 'albumartist'
                        if searchcontainer:
                            searchwhere = 'where albumartist like "%%%s%%"' % searchstring
                        countstatement = "select count(distinct albumartist) from AlbumartistAlbum %s" % searchwhere
                        statement = "select albumartist, lastplayed, playcount from AlbumartistAlbum %s group by albumartist order by orderby limit ?, ?" % searchwhere
                        orderbylist = self.get_orderby('ALBUMARTIST', controllername)
                        for orderbyentry in orderbylist:
                            orderby, prefix, suffix, albumtype, table, header = orderbyentry
                            if not orderby or orderby == '':
                                orderby = 'albumartist'
                            state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                        id_pre = 'ALBUMARTIST__'
                    else:                
                        artisttype = 'artist'
                        if searchcontainer:
                            searchwhere = 'where artist like "%%%s%%"' % searchstring
                        countstatement = "select count(distinct artist) from ArtistAlbum %s" % searchwhere
                        statement = "select artist, lastplayed, playcount from ArtistAlbum %s group by artist order by orderby limit ?, ?" % searchwhere
                        orderbylist = self.get_orderby('ARTIST', controllername)
                        for orderbyentry in orderbylist:                                        
                            orderby, prefix, suffix, albumtype, table, header = orderbyentry
                            if not orderby or orderby == '':
                                orderby = 'artist'
                            state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                        id_pre = 'ARTIST__'
                else:
                    artisttype = 'contributingartist'
                    if searchcontainer:
                        searchwhere = 'where artist like "%%%s%%"' % searchstring
                    countstatement = "select count(distinct artist) from ArtistAlbum %s" % searchwhere
                    statement = "select artist, lastplayed, playcount from ArtistAlbum %s group by artist order by orderby limit ?, ?" % searchwhere
                    orderbylist = self.get_orderby('CONTRIBUTINGARTIST', controllername)
                    for orderbyentry in orderbylist:                                        
                        orderby, prefix, suffix, albumtype, table, header = orderbyentry
                        if not orderby or orderby == '':
                            orderby = 'artist'
                        state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                    id_pre = 'CONTRIBUTINGARTIST__'
            else:
                criteria = searchCriteria.split('=')
                if criteria[1].endswith('upnp:genre '):
                    # Artists for genre
                    log.debug('artists for genre')
                    searchtype = 'GENRE_ARTIST'
                    genre = criteria[2][1:]
                    genre_options = self.removepresuf(genre, 'GENRE', controllername)
                    for genre in genre_options:
                        if genre == '[unknown genre]': genre = ''
                        log.debug('    genre: %s', genre)
                        genres.append(genre)
                        if self.use_albumartist:
                            artisttype = 'albumartist'
                            countstatement = "select count(distinct albumartist) from GenreAlbumartistAlbum where genre=?"
                            statement = "select albumartist, lastplayed, playcount from GenreAlbumartistAlbum where genre=? group by albumartist order by orderby limit ?, ?"
                            orderbylist = self.get_orderby('GENRE_ALBUMARTIST', controllername)
                            for orderbyentry in orderbylist:                                        
                                orderby, prefix, suffix, albumtype, table, header = orderbyentry
                                if not orderby or orderby == '':
                                    orderby = 'albumartist'
                                state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                            id_pre = 'GENRE_ALBUMARTIST__'
                        else:                
                            artisttype = 'artist'
                            countstatement = "select count(distinct artist) from GenreArtistAlbum where genre=?"
                            statement = "select artist, lastplayed, playcount from GenreArtistAlbum where genre=? group by artist order by orderby limit ?, ?"
                            orderbylist = self.get_orderby('GENRE_ARTIST', controllername)
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
                            log.debug('before')
                            c.execute(countstatement, (genre, ))
                            log.debug('after')
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

                for chunk in chunkdata:
                
                    group, start, end, sep = chunk
                    length = end - start
                    
                    orderby, prefix, suffix, albumtype, table, header = chunk_data[group]

                    if show_separator and sep:
                        count += 1
                        if not header or header == '':
                            header = "%s %s" % ('ordered by', orderby)
                        separator = '%s %s %s' % (self.chunk_separator_delimiter, header, self.chunk_separator_delimiter)
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
    #                    log.debug("row: %s", row)

                        artist, lastplayed, playcount = row
                        playcount = str(playcount)
                        if artist == '': artist = '[unknown %s]' % artisttype
                        artist = escape(artist)

                        a_prefix = self.makepresuffix(prefix, self.replace_pre, {'lastplayed':lastplayed, 'playcount':playcount})
                        if a_prefix: artist = '%s%s' % (a_prefix, artist)
                        a_suffix = self.makepresuffix(suffix, self.replace_suf, {'lastplayed':lastplayed, 'playcount':playcount})
                        if a_suffix: artist = '%s%s' % (artist, a_suffix)

                        count += 1
                        id = id_pre + str(startingIndex + count + self.artist_parentid)  # dummy, sequential
                        
                        res += '<container id="%s" parentID="%s" restricted="true">' % (id, self.artist_parentid)
                        res += '<dc:title>%s</dc:title>' % (artist)
                        res += '<upnp:class>%s</upnp:class>' % (self.artist_class)
                        res += '</container>'

            res += '</DIDL-Lite>'

        elif (containerID == '0' and searchCriteria.startswith('upnp:class = "object.container.album.musicAlbum" and @refID exists false')) or \
             searchcontainer == 'Album':

            # Albums class

            # TODO: brought this here in case duplicate clause was not always needed - check that and move to start of method if this is the only case
            distinct_albumartist = '%s%s' % (self.album_distinct_albumartist, self.album_distinct_duplicate)
            groupby_albumartist = '%s%s' % (self.album_groupby_albumartist, self.album_groupby_duplicate)
            distinct_artist = '%s%s' % (self.album_distinct_artist, self.album_distinct_duplicate)
            groupby_artist = '%s%s' % (self.album_groupby_artist, self.album_groupby_duplicate)
            distinct_composer = '%s%s' % ('album', self.album_distinct_duplicate)
            groupby_composer = '%s%s' % ('album', self.album_groupby_duplicate)

            genres = []
            fields = []
            state_pre_suf = []
        
            if searchCriteria == 'upnp:class = "object.container.album.musicAlbum" and @refID exists false' or \
               searchcontainer == 'Album':
                # Albums
                log.debug('albums')
                searchtype = 'ALBUM'

                albumwhere = self.album_where_duplicate
                if searchcontainer:
                    if albumwhere == '':
                        albumwhere = 'where album like "%%%s%%"' % searchstring
                    else:
                        albumwhere += ' and album like "%%%s%%"' % searchstring

                # default albumtype to albums only
                at = 'albumtype=10'

                genres.append('dummy')     # dummy for albums
                fields.append('dummy')     # dummy for albums

                if self.use_albumartist:
                    album_distinct = distinct_albumartist
                    album_groupby = groupby_albumartist
                else:
                    album_distinct = distinct_artist
                    album_groupby = groupby_artist

                # get the sort sequence for this database and query
                orderbylist = self.get_orderby('ALBUM', controllername)
                
                log.debug(orderbylist)

                # FIXME: this code will use the albumtype from the last entry in the orderbylist
                
                for orderbyentry in orderbylist:
                    orderby, prefix, suffix, albumtype, table, header = orderbyentry
                    if not orderby or orderby == '':
                        orderby = 'album, albumartist'
                    if table != 'dummy':
                        # albumtype will be a list of albumtypes
                        if len(albumtype) == 1:
                            at = 'albumtype = %s' % albumtype[0]
                        else:
                            at = 'albumtype in (%s)' % ','.join(['%s' % n for n in albumtype])
                    if albumwhere == '':
                        albumwhere = 'where %s' % at
                    else:
                        albumwhere += ' and %s' % at

                    countstatement = "select count(distinct %s) from albums %s" % (album_distinct, albumwhere)
                    if controllername == 'PCDCR':
                        statement = "select a.* from ( select album, min(tracknumbers) as mintrack, albumtype, duplicate from albums %s group by %s ) as m inner join albums as a on a.album = m.album and a.tracknumbers = m.mintrack and a.albumtype = m.albumtype and a.duplicate = m.duplicate order by orderby limit ?, ?" % (albumwhere, album_groupby)
                    else:
                        statement = "select * from albums %s group by %s order by orderby limit ?, ?" % (albumwhere, album_groupby)

                    state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))

                id_pre = 'ALBUM__'
                
            else:
            
                criteria = searchCriteria.split('=')
                numcrit = len(criteria)
                if numcrit == 3:
                    # searchCriteria: upnp:class = "object.container.album.musicAlbum" and @refID exists false and microsoft:authorComposer = "7 Aurelius"                
                    searchtype = 'FIELD_ALBUM'
                    genres.append('dummy')     # dummy for composer/artist/contributingartist
                    if criteria[1].endswith('microsoft:authorComposer '):
                        # Albums for Composer
                        log.debug('albums for composer')
                        composer = criteria[2][1:]
                        countstatement = "select count(distinct %s) from ComposerAlbum where composer=? and albumtype=? %s" % (distinct_composer, self.album_and_duplicate)
                        statement = "select * from albums where id in (select album_id from ComposerAlbum where composer=? and albumtype=? %s) group by %s order by orderby limit ?, ?" % (self.album_and_duplicate, groupby_composer)
                        composer_options = self.removepresuf(composer, 'COMPOSER', controllername)
                        for composer in composer_options:
                            if composer == '[unknown composer]': composer = ''
                            log.debug('    composer: %s', composer)
                            fields.append(composer)
                            orderbylist = self.get_orderby('COMPOSER_ALBUM', controllername)
                            for orderbyentry in orderbylist:
                                orderby, prefix, suffix, albumtype, table, header = orderbyentry
                                if not orderby or orderby == '':
                                    orderby = 'album'
                                state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                            id_pre = 'COMPOSER_ALBUM__'

                    elif criteria[1].endswith('microsoft:artistAlbumArtist '):
                        # Albums for albumartist
                        log.debug('albums for artist (microsoft:artistAlbumArtist)')
                        artist = criteria[2][1:]
                        if self.use_albumartist:
                            countstatement = "select count(distinct %s) from AlbumartistAlbum where albumartist=? and albumtype=? %s" % (distinct_albumartist, self.album_and_duplicate)
                            statement = "select * from albums where id in (select album_id from AlbumartistAlbum where albumartist=? and albumtype=? %s) group by %s order by orderby limit ?, ?" % (self.album_and_duplicate, groupby_albumartist)
                            artist_options = self.removepresuf(artist, 'ALBUMARTIST', controllername)
                        else:
                            countstatement = "select count(distinct %s) from ArtistAlbum where artist=? and albumtype=? %s" % (distinct_artist, self.album_and_duplicate)
                            statement = "select * from albums where id in (select album_id from ArtistAlbum where artist=? and albumtype=? %s) group by %s order by orderby limit ?, ?" % (self.album_and_duplicate, groupby_artist)
                            artist_options = self.removepresuf(artist, 'ARTIST', controllername)
                        for artist in artist_options:
                            if artist == '[unknown artist]': artist = ''
                            log.debug('    artist: %s', artist)
                            fields.append(artist)
                            if self.use_albumartist:
                                orderbylist = self.get_orderby('ALBUMARTIST_ALBUM', controllername)
                                for orderbyentry in orderbylist:
                                    orderby, prefix, suffix, albumtype, table, header = orderbyentry
                                    if not orderby or orderby == '':
                                        orderby = 'album'
                                    state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                                id_pre = 'ALBUMARTIST_ALBUM__'
                            else:
                                orderbylist = self.get_orderby('ARTIST_ALBUM', controllername)
                                for orderbyentry in orderbylist:
                                    orderby, prefix, suffix, albumtype, table, header = orderbyentry
                                    if not orderby or orderby == '':
                                        orderby = 'album'
                                    state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                                id_pre = 'ARTIST_ALBUM__'

                    elif criteria[1].endswith('microsoft:artistPerformer '):
                        # searchCriteria: upnp:class = "object.container.album.musicAlbum" and @refID exists false and microsoft:artistPerformer = "1 Giant Leap"
                        # Albums for contributing artist
                        log.debug('albums for artist (microsoft:artistPerformer)')
                        artist = criteria[2][1:]
                        countstatement = "select count(distinct %s) from ArtistAlbum where artist=? and albumtype=? %s" % (distinct_artist, self.album_and_duplicate)
                        statement = "select * from albums where id in (select album_id from ArtistAlbum where artist=? and albumtype=? %s) group by %s order by orderby limit ?, ?" % (self.album_and_duplicate, groupby_artist)
                        artist_options = self.removepresuf(artist, 'CONTRIBUTINGARTIST', controllername)
                        for artist in artist_options:
                            if artist == '[unknown artist]': artist = ''
                            log.debug('    artist: %s', artist)
                            fields.append(artist)
                            orderbylist = self.get_orderby('CONTRIBUTINGARTIST_ALBUM', controllername)
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
                    if criteria[1].endswith('upnp:genre ') and criteria[2].endswith('microsoft:artistAlbumArtist '):
                        searchtype = 'GENRE_FIELD_ALBUM'
                        # Albums for genre and artist
                        log.debug('albums for genre and artist')
                        genre = criteria[2][1:-33]
                        if self.use_albumartist:
                            countstatement = "select count(distinct %s) from GenreAlbumartistAlbum where genre=? and albumartist=? and albumtype=? %s" % (distinct_albumartist, self.album_and_duplicate)
                            statement = "select * from albums where id in (select album_id from GenreAlbumartistAlbum where genre=? and albumartist=? and albumtype=? %s) group by %s order by orderby limit ?, ?" % (self.album_and_duplicate, groupby_albumartist)
                        else:
                            countstatement = "select count(distinct %s) from GenreArtistAlbum where genre=? and artist=? and albumtype=? %s" % (distinct_artist, self.album_and_duplicate)
                            statement = "select * from albums where id in (select album_id from GenreArtistAlbum where genre=? and artist=? and albumtype=? %s) group by %s order by orderby limit ?, ?" % (self.album_and_duplicate, groupby_artist)
                        genre_options = self.removepresuf(genre, 'GENRE', controllername)
                        for genre in genre_options:
                            if genre == '[unknown genre]': genre = ''
                            log.debug('    genre: %s', genre)
                            genres.append(genre)
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
                                    orderbylist = self.get_orderby('ALBUMARTIST_ALBUM', controllername)
                                    for orderbyentry in orderbylist:
                                        orderby, prefix, suffix, albumtype, table, header = orderbyentry
                                        if not orderby or orderby == '':
                                            orderby = 'album'
                                        state_pre_suf.append((orderby, prefix, suffix, albumtype, table, header))
                                    id_pre = 'GENRE_ALBUMARTIST_ALBUM__'
                                else:
                                    orderbylist = self.get_orderby('ARTIST_ALBUM', controllername)
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
                                log.debug(countstatement)
                                log.debug(field)
                                log.debug(albumtype)

                                c.execute(countstatement, (field, albumtype))
                            elif searchtype == 'GENRE_FIELD_ALBUM':
                                c.execute(countstatement, (genre, field, albumtype))
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

                for chunk in chunkdata:
                
                    group, start, end, sep = chunk
                    length = end - start
                    
                    orderby, prefix, suffix, albumtype, table, header = chunk_data[group]

                    if show_separator and sep:
                        count += 1
                        if not header or header == '':
                            header = "%s %s" % ('ordered by', orderby)
                        separator = '%s %s %s' % (self.chunk_separator_delimiter, header, self.chunk_separator_delimiter)
                        res += '<container id="%s" parentID="%s" restricted="true">' % (id_pre, parentid)
                        res += '<dc:title>%s</dc:title>' % (separator)
                        res += '<upnp:class>%s</upnp:class>' % (self.album_class)
                        res += '</container>'

                    orderstatement = statement.replace('order by orderby', 'order by ' + orderby)
                    log.debug(orderstatement)

                    if searchtype == 'ALBUM':
                        c.execute(orderstatement, (start, length))
                    elif searchtype == 'FIELD_ALBUM':
                        c.execute(orderstatement, (found_field, albumtype, start, length))
                    elif searchtype == 'GENRE_FIELD_ALBUM':
                        c.execute(orderstatement, (found_genre, found_field, albumtype, start, length))

                    for row in c:
#                        log.debug("row: %s", row)

                        id, parentID, album, artist, year, albumartist, duplicate, cover, artid, inserted, composer, tracknumbers, created, lastmodified, albumtype, lastplayed, playcount, upnpclass = row
                        id = str(id)
                        playcount = str(playcount)

                        # NOTE: in this case IDs are real IDs, but because of the group by's they are not necessarily the right ones

                        if artist == '': artist = '[unknown artist]'
                        else: artist = self.get_artist(artist, self.mouseover_artist, self.mouseover_artist_combiner)
                        if albumartist == '': albumartist = '[unknown albumartist]'
                        else: albumartist = self.get_artist(albumartist, self.mouseover_artist, self.mouseover_artist_combiner)
                        if album == '': album = '[unknown album]'
                        album = escape(album)
                        artist = escape(artist)
                        albumartist = escape(albumartist)

                        if duplicate != 0:
                            album += ' (' + str(duplicate) + ')'

                        a_prefix = self.makepresuffix(prefix, self.replace_pre, {'year':year, 'lastplayed':lastplayed, 'playcount':playcount, 'created':created, 'lastmodified':lastmodified, 'inserted':inserted, 'artist':artist, 'albumartist':albumartist, 'composer':composer})
                        if a_prefix: album = '%s%s' % (a_prefix, album)
                        a_suffix = self.makepresuffix(suffix, self.replace_suf, {'year':year, 'lastplayed':lastplayed, 'playcount':playcount, 'created':created, 'lastmodified':lastmodified, 'inserted':inserted, 'artist':artist, 'albumartist':albumartist, 'composer':composer})
                        if a_suffix: album = '%s%s' % (album, a_suffix)

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
        #                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                            coverres = self.proxyaddress + '/wmp/' + dummycoverfile
                            dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath, cover=cover)
                            self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)
                        elif cover != '':
                            cvfile = getFile(cover)
                            cvpath = cover
                            coverfiletype = getFileType(cvfile)
                            dummycoverfile = self.dbname + '.' + str(artid) + '.' + coverfiletype
        #                    coverres = self.proxyaddress + '/WMPNSSv3/' + dummycoverfile
                            coverres = self.proxyaddress + '/wmp/' + dummycoverfile
                            dummycoverstaticfile = webserver.StaticFileSonos(dummycoverfile, cvfile, cvpath)    # TODO: pass contenttype
                            self.proxy.wmpcontroller2.add_static_file(dummycoverstaticfile)

                        id = id_pre + str(id)

                        count += 1
                        res += '<container id="%s" parentID="%s" restricted="true">' % (id, parentid)
                        res += '<dc:title>%s</dc:title>' % (album)
                        res += '<upnp:artist role="AlbumArtist">%s</upnp:artist>' % (albumartist)
                        res += '<upnp:artist role="Performer">%s</upnp:artist>' % (artist)
                        res += '<upnp:class>%s</upnp:class>' % (upnpclass)
                        res += '<upnp:album>%s</upnp:album>' % (album)
                        if cover != '':
                            res += '<upnp:albumArtURI>%s</upnp:albumArtURI>' % (coverres)
                        res += '</container>'
                    
            res += '</DIDL-Lite>'

        elif (containerID == '108' and searchCriteria == 'upnp:class = "object.container.person.musicArtist" and @refID exists false') or \
             searchcontainer == 'Composer':

            # Composer container

            state_pre_suf = []

            searchwhere = ''
            if searchcontainer:
                searchwhere = 'where composer like "%%%s%%"' % searchstring

            countstatement = "select count(distinct composer) from ComposerAlbum %s" % searchwhere
            statement = "select composer, lastplayed, playcount from ComposerAlbum %s group by composer order by orderby limit ?, ?" % searchwhere

            orderbylist = self.get_orderby('COMPOSER', controllername)
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

                for chunk in chunkdata:
                
                    group, start, end, sep = chunk
                    length = end - start
                    
                    orderby, prefix, suffix, albumtype, table, header = state_pre_suf[group]

                    if show_separator and sep:
                        count += 1
                        if not header or header == '':
                            header = "%s %s" % ('ordered by', orderby)
                        separator = '%s %s %s' % (self.chunk_separator_delimiter, header, self.chunk_separator_delimiter)
                        res += '<container id="%s" parentID="%s" restricted="true">' % (id_pre, parentid)
                        res += '<dc:title>%s</dc:title>' % (separator)
                        res += '<upnp:class>%s</upnp:class>' % (self.composer_class)
                        res += '</container>'

                    orderstatement = statement.replace('order by orderby', 'order by ' + orderby)
                    log.debug(orderstatement)

                    c.execute(orderstatement, (start, length))
                    for row in c:
#                        log.debug("row: %s", row)
                        composer, lastplayed, playcount = row
                        if composer == '': composer = '[unknown composer]'
                        composer = escape(composer)
                        
                        a_prefix = self.makepresuffix(prefix, self.replace_pre, {'lastplayed':lastplayed, 'playcount':playcount})
                        if a_prefix: composer = '%s%s' % (a_prefix, composer)
                        a_suffix = self.makepresuffix(suffix, self.replace_suf, {'lastplayed':lastplayed, 'playcount':playcount})
                        if a_suffix: composer = '%s%s' % (composer, a_suffix)
                        
                        count += 1
                        id = id_pre + str(startingIndex + count + self.composer_parentid)  # dummy, sequential
                        
                        res += '<container id="%s" parentID="%s" restricted="true">' % (id, parentid)
                        res += '<dc:title>%s</dc:title>' % (composer)
        ## test this!                res += '<upnp:artist role="AuthorComposer">%s</upnp:artist>' % (composer)
                        res += '<upnp:class>%s</upnp:class>' % (self.composer_class)
                        res += '</container>'

            res += '</DIDL-Lite>'

        elif containerID == '0' and searchCriteria == 'upnp:class = "object.container.genre.musicGenre" and @refID exists false':

            # Genre class
            
            res  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            count = 0
            parentid = '5'

            state_pre_suf = []

            countstatement = "select count(distinct genre) from GenreArtist"
            statement = "select genre, lastplayed, playcount from GenreArtist group by genre order by orderby limit ?, ?"

            orderbylist = self.get_orderby('GENRE', controllername)
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

                for chunk in chunkdata:
                
                    group, start, end, sep = chunk
                    length = end - start
                    
                    orderby, prefix, suffix, albumtype, table, header = state_pre_suf[group]

                    if show_separator and sep:
                        count += 1
                        if not header or header == '':
                            header = "%s %s" % ('ordered by', orderby)
                        separator = '%s %s %s' % (self.chunk_separator_delimiter, header, self.chunk_separator_delimiter)
                        res += '<container id="%s" parentID="%s" restricted="true">' % (id_pre, parentid)
                        res += '<dc:title>%s</dc:title>' % (separator)
                        res += '<upnp:class>%s</upnp:class>' % (self.genre_class)
                        res += '</container>'

                    orderstatement = statement.replace('order by orderby', 'order by ' + orderby)
                    log.debug(orderstatement)

                    c.execute(orderstatement, (start, length))
                    for row in c:
#                        log.debug("row: %s", row)
                        genre, lastplayed, playcount = row
                        playcount = str(playcount)

                        if genre == '': genre = '[unknown genre]'
                        genre = escape(genre)
                        
                        a_prefix = self.makepresuffix(prefix, self.replace_pre, {'lastplayed':lastplayed, 'playcount':playcount})
                        if a_prefix: genre = '%s%s' % (a_prefix, genre)
                        a_suffix = self.makepresuffix(suffix, self.replace_suf, {'lastplayed':lastplayed, 'playcount':playcount})
                        if a_suffix: genre = '%s%s' % (genre, a_suffix)
                        
                        count += 1
                        id = id_pre + str(startingIndex + count + self.genre_parentid)  # dummy, sequential
                        
                        res += '<container id="%s" parentID="%s" restricted="true">' % (id, parentid)
                        res += '<dc:title>%s</dc:title>' % (genre)
                        res += '<upnp:class>%s</upnp:class>' % (self.genre_class)
                        res += '</container>'

            res += '</DIDL-Lite>'

        elif (containerID == '0' and searchCriteria.startswith('upnp:class derivedfrom "object.item.audioItem" and @refID exists false')) or \
             searchcontainer == 'Track':

            # Track class

            genres = []
            artists = []
            fields = []
            tracks_type = None
            
            if searchCriteria == 'upnp:class derivedfrom "object.item.audioItem" and @refID exists false' or \
               searchcontainer == 'Track':
                # Tracks
                tracks_type = 'TRACKS'
                if self.show_duplicates:
                    where = ""
                else:
                    where = "where duplicate = 0"

                searchwhere = where
                if searchcontainer:
                    if searchwhere == '':
                        searchwhere = 'where title like "%%%s%%"' % searchstring
                    else:
                        searchwhere += ' and title like "%%%s%%"' % searchstring

                countstatement = "select count(*) from tracks %s" % searchwhere
                statement = "select * from tracks %s order by title limit %d, %d" % (searchwhere, startingIndex, requestedCount)

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

                    # Tracks for class/album or class
                    duplicate_number = '0'
                    criteria = searchCriteria.split('=')
                    
                    if len(criteria) == 2:

                        tracks_type = 'FIELD'
                        genres.append('dummy')
                        artists.append('dummy')

                        if criteria[0].endswith('microsoft:authorComposer '):

                            # tracks for composer
                            # searchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:authorComposer = "A New Found Glory"
                            log.debug('tracks for composer')
                            composer = criteria[1][1:]
                            countstatement = "select count(*) from ComposerAlbumTrack where composer=? %s" % (self.album_and_duplicate)
                            statement = "select * from tracks where id in (select track_id from ComposerAlbumTrack where composer=? %s) order by album, discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)
                            composer_options = self.removepresuf(composer, 'COMPOSER', controllername)
                            for composer in composer_options:
                                if composer == '[unknown composer]': composer = ''
                                fields.append(composer)
                                if album_loop == 1:
                                    # shouldn't get here
                                    break
                                log.debug('    composer: %s', composer)

                        elif criteria[0].endswith('microsoft:artistAlbumArtist '):

                            # tracks for artist
                            # SearchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:artistAlbumArtist = "30 Seconds to Mars"
                            log.debug('tracks for artist')
                            artist = criteria[1][1:]
                            if self.use_albumartist:
                                countstatement = "select count(*) from AlbumartistAlbumTrack where albumartist=? %s" % (self.album_and_duplicate)
                                statement = "select * from tracks where id in (select track_id from AlbumartistAlbumTrack where albumartist=? %s) order by album, discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)
                                artist_options = self.removepresuf(artist, 'ALBUMARTIST', controllername)
                            else:
                                countstatement = "select count(*) from ArtistAlbumTrack where artist=? %s" % (self.album_and_duplicate)
                                statement = "select * from tracks where id in (select track_id from ArtistAlbumTrack where artist=? %s) order by album, discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)
                                artist_options = self.removepresuf(artist, 'ARTIST', controllername)
                            for artist in artist_options:
                                if artist == '[unknown artist]': artist = ''
                                if artist == '[unknown albumartist]': artist = ''
                                fields.append(artist)
                                if album_loop == 1:
                                    # shouldn't get here
                                    break
                                log.debug('    artist: %s', artist)

                        elif criteria[0].endswith('microsoft:artistPerformer '):

                            # tracks for contributing artist
                            # searchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:artistPerformer = "1 Giant Leap"
                            log.debug('tracks for contributing artist')
                            artist = criteria[1][1:]
                            countstatement = "select count(*) from ArtistAlbumTrack where artist=? %s" % (self.album_and_duplicate)
                            statement = "select * from tracks where id in (select track_id from ArtistAlbumTrack where artist=? %s) order by album, discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)
                            artist_options = self.removepresuf(artist, 'CONTRIBUTINGARTIST', controllername)
                            for artist in artist_options:
                                if artist == '[unknown artist]': artist = ''
                                fields.append(artist)
                                if album_loop == 1:
                                    # shouldn't get here
                                    break
                                log.debug('    artist: %s', artist)

                        elif criteria[0].endswith('upnp:genre '):

                            # tracks for genre
                            # searchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and upnp:genre = "Alt. Pop"
                            log.debug('tracks for genre')
                            genre = criteria[1][1:]
                            if self.use_albumartist:
                                countstatement = "select count(*) from GenreAlbumartistAlbumTrack where genre=? %s" % (self.album_and_duplicate)
                                statement = "select * from tracks where id in (select track_id from GenreAlbumartistAlbumTrack where genre=? %s) order by albumartist, album, discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)
                            else:                
                                countstatement = "select count(*) from GenreArtistAlbumTrack where genre=? %s" % (self.album_and_duplicate)
                                statement = "select * from tracks where id in (select track_id from GenreArtistAlbumTrack where genre=? %s) order by artist, album, discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)
                            genre_options = self.removepresuf(genre, 'GENRE', controllername)
                            for genre in genre_options:
                                if genre == '[unknown genre]': genre = ''
                                fields.append(genre)
                                if album_loop == 1:
                                    # shouldn't get here
                                    break
                                log.debug('    genre: %s', genre)
                    
                    elif len(criteria) == 3:

                        tracks_type = 'ARTIST'
                        genres.append('dummy')
                        not_album = False

                        if criteria[0].endswith('microsoft:authorComposer '):
                            # tracks for composer/album
                            # SearchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:authorComposer = "A Lee" and upnp:album = "Fallen"
                            log.debug('tracks for composer/album')
                            composer = criteria[1][1:-16]
                            composer_options = self.removepresuf(composer, 'COMPOSER', controllername)
                            for composer in composer_options:
                                if composer == '[unknown composer]': composer = ''
                                artists.append(composer)
                                log.debug('    composer: %s', composer)
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

                            possible_albumtypes = self.get_possible_albumtypes('COMPOSER_ALBUM')
                                    
                            countstatement = "select count(*) from ComposerAlbumTrack where composer=? and album=? and duplicate=%s" % (duplicate_number)
                            countstatement2 = "select count(*) from ComposerAlbumTrack where composer=? and album=? and duplicate=%s and albumtype=?" % (duplicate_number)
                            statement = "select * from tracks where id in (select track_id from ComposerAlbumTrack where composer=? and album=? and duplicate=%s) order by discnumber, tracknumber, title limit %d, %d" % (duplicate_number, startingIndex, requestedCount)
                            statement2 = "select distinct(albumtype) from ComposerAlbumTrack where composer=? and album=? and duplicate=%s order by albumtype" % (duplicate_number)
#                            statement3 = '''select * from tracks t, tracknumbers n where id in 
#                                           (select track_id from ComposerAlbumTrack where composer=? and album=? and duplicate=%s)
#                                           and t.id = n.track_id and t.genre=n.genre and t.artist=n.artist and t.albumartist=n.albumartist and t.album=n.album and t.composer=n.composer and t.duplicate=n.duplicate and n.albumtype=?
#                                           order by t.discnumber, n.tracknumber, t.title limit %d, %d''' % (duplicate_number, startingIndex, requestedCount)

                            statement3 = '''
                                            select * from tracks t join tracknumbers n on t.id = n.track_id where id in
                                            (select track_id from tracknumbers where track_id in 
                                                (select track_id from ComposerAlbumTrack where composer=? and album=? and duplicate=%s and albumtype=?)
                                            and albumtype=?)
                                            and albumtype=? 
                                            order by n.tracknumber, t.title
                                            limit %d, %d
                                         ''' % (duplicate_number, startingIndex, requestedCount)

                        elif criteria[0].endswith('microsoft:artistAlbumArtist '):
                            # tracks for artist/album
                            # searchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:artistAlbumArtist = "1 Giant Leap" and upnp:album = "1 Giant Leap"
                            log.debug('tracks for artist/album')
                            artist = criteria[1][1:-16]
                            if self.use_albumartist:
                                artist_options = self.removepresuf(artist, 'ALBUMARTIST', controllername)
                            else:
                                artist_options = self.removepresuf(artist, 'ARTIST', controllername)
                            for artist in artist_options:
                                log.debug(artist)
                                if artist == '[unknown artist]': artist = ''
                                artists.append(artist)
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

                                possible_albumtypes = self.get_possible_albumtypes('ALBUMARTIST_ALBUM')
                                    
                                countstatement = "select count(*) from AlbumartistAlbumTrack where albumartist=? and album=? and duplicate=%s" % (duplicate_number)
                                countstatement2 = "select count(*) from AlbumartistAlbumTrack where albumartist=? and album=? and duplicate=%s and albumtype=?" % (duplicate_number)
                                statement = "select * from tracks where id in (select track_id from AlbumartistAlbumTrack where albumartist=? and album=? and duplicate=%s) order by discnumber, tracknumber, title limit %d, %d" % (duplicate_number, startingIndex, requestedCount)
                                statement2 = "select distinct(albumtype) from AlbumartistAlbumTrack where albumartist=? and album=? and duplicate=%s order by albumtype" % (duplicate_number)
#                                statement3 = '''select * from tracks t, tracknumbers n where id in 
#                                               (select track_id from AlbumartistAlbumTrack where albumartist=? and album=? and duplicate=%s)
#                                               and t.id = n.track_id and t.genre=n.genre and t.artist=n.artist and t.albumartist=n.albumartist and t.album=n.album and t.composer=n.composer and t.duplicate=n.duplicate and n.albumtype=?
#                                               order by t.discnumber, n.tracknumber, t.title limit %d, %d''' % (duplicate_number, startingIndex, requestedCount)

                                statement3 = '''
                                                select * from tracks t join tracknumbers n on t.id = n.track_id where id in
                                                (select track_id from tracknumbers where track_id in 
                                                    (select track_id from AlbumartistAlbumTrack where albumartist=? and album=? and duplicate=%s and albumtype=?)
                                                and albumtype=?)
                                                and albumtype=? 
                                                order by n.tracknumber, t.title
                                                limit %d, %d
                                             ''' % (duplicate_number, startingIndex, requestedCount)

                            else:                
                            
                                possible_albumtypes = self.get_possible_albumtypes('ARTIST_ALBUM')
                                    
                                countstatement = "select count(*) from ArtistAlbumTrack where artist=? and album=? and duplicate=%s" % (duplicate_number)
                                countstatement2 = "select count(*) from ArtistAlbumTrack where artist=? and album=? and duplicate=%s and albumtype=?" % (duplicate_number)
                                statement = "select * from tracks where id in (select track_id from ArtistAlbumTrack where artist=? and album=? and duplicate=%s) order by discnumber, tracknumber, title limit %d, %d" % (duplicate_number, startingIndex, requestedCount)
                                statement2 = "select distinct(albumtype) from ArtistAlbumTrack where albumartist=? and album=? and duplicate=%s order by albumtype" % (duplicate_number)
#                                statement3 = '''select * from tracks t, tracknumbers n where id in 
#                                               (select track_id from ArtistAlbumTrack where albumartist=? and album=? and duplicate=%s)
#                                               and t.id = n.track_id and t.genre=n.genre and t.artist=n.artist and t.albumartist=n.albumartist and t.album=n.album and t.composer=n.composer and t.duplicate=n.duplicate and n.albumtype=?
#                                               order by t.discnumber, n.tracknumber, t.title limit %d, %d''' % (duplicate_number, startingIndex, requestedCount)

                                statement3 = '''
                                                select * from tracks t join tracknumbers n on t.id = n.track_id where id in
                                                (select track_id from tracknumbers where track_id in 
                                                    (select track_id from ArtistAlbumTrack where albumartist=? and album=? and duplicate=%s and albumtype=?)
                                                and albumtype=?)
                                                and albumtype=? 
                                                order by n.tracknumber, t.title
                                                limit %d, %d
                                             ''' % (duplicate_number, startingIndex, requestedCount)

                        elif criteria[0].endswith('microsoft:artistPerformer '):
                            # tracks for contributing artist/album
                            # searchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and microsoft:artistPerformer = "1 Giant Leap" and upnp:album = "1 Giant Leap"
                            log.debug('tracks for contributing artist/album')
                            artist = criteria[1][1:-16]
                            artist_options = self.removepresuf(artist, 'CONTRIBUTINGARTIST', controllername)
                            for artist in artist_options:
                                if artist == '[unknown artist]': artist = ''
                                artists.append(artist)
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

                            possible_albumtypes = self.get_possible_albumtypes('CONTRIBUTINGARTIST_ALBUM')
                                    
                            countstatement = "select count(*) from ArtistAlbumTrack where artist=? and album=? and duplicate=%s" % (duplicate_number)
                            countstatement2 = "select count(*) from ArtistAlbumTrack where artist=? and album=? and duplicate=%s and albumtype=?" % (duplicate_number)
                            statement = "select * from tracks where id in (select track_id from ArtistAlbumTrack where artist=? and album=? and duplicate=%s) order by discnumber, tracknumber, title limit %d, %d" % (duplicate_number, startingIndex, requestedCount)
                            statement2 = "select distinct(albumtype) from ArtistAlbumTrack where artist=? and album=? and duplicate=%s order by albumtype" % (duplicate_number)
#                            statement3 = '''select * from tracks t, tracknumbers n where id in 
#                                           (select track_id from ArtistAlbumTrack where artist=? and album=? and duplicate=%s)
#                                           and t.id = n.track_id and t.genre=n.genre and t.artist=n.artist and t.albumartist=n.albumartist and t.album=n.album and t.composer=n.composer and t.duplicate=n.duplicate and n.albumtype=?
#                                           order by t.discnumber, n.tracknumber, t.title limit %d, %d''' % (duplicate_number, startingIndex, requestedCount)

                            statement3 = '''
                                            select * from tracks t join tracknumbers n on t.id = n.track_id where id in
                                            (select track_id from tracknumbers where track_id in 
                                                (select track_id from ArtistAlbumTrack where artist=? and album=? and duplicate=%s and albumtype=?)
                                            and albumtype=?)
                                            and albumtype=? 
                                            order by n.tracknumber, t.title
                                            limit %d, %d
                                         ''' % (duplicate_number, startingIndex, requestedCount)

                        elif criteria[0].endswith('upnp:genre '):
                            # tracks for genre/artist
                            # searchCriteria: upnp:class derivedfrom "object.item.audioItem" and @refID exists false and upnp:genre = "Alt. Rock" and microsoft:artistAlbumArtist = "Elvis Costello"
                            not_album = True
                            log.debug('tracks for genre/artist')
                            genre = criteria[1][1:-33]
                            genre_options = self.removepresuf(genre, 'GENRE', controllername)
                            for genre in genre_options:
                                if genre == '[unknown genre]': genre = ''
                                artists.append(genre)
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
                                statement = "select * from tracks where id in (select track_id from GenreAlbumartistAlbumTrack where genre=? and albumartist=? %s) order by discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)
                            else:                
                                countstatement = "select count(*) from GenreArtistAlbumTrack where genre=? and artist=? %s" % (self.album_and_duplicate)
                                statement = "select * from tracks where id in (select track_id from GenreArtistAlbumTrack where genre=? and artist=? %s) order by discnumber, tracknumber, title limit %d, %d" % (self.album_and_duplicate, startingIndex, requestedCount)
                    else:
                        # len = 4
                        # tracks for genre/artist/album
                        log.debug('tracks for genre/artist/album')
                        tracks_type = 'GENRE'
                        genre = criteria[1][1:-33]
                        genre_options = self.removepresuf(genre, 'GENRE', controllername)
                        for genre in genre_options:
                            if genre == '[unknown genre]': genre = ''
                            genres.append(genre)
                            artist = criteria[2][1:-16]
                            if self.use_albumartist:
                                artist_options = self.removepresuf(artist, 'GENRE_ALBUMARTIST', controllername)
                            else:
                                artist_options = self.removepresuf(artist, 'GENRE_ARTIST', controllername)
                            for artist in artist_options:
                            
                                log.debug("artist: %s", artist)
                            
                                if artist == '[unknown artist]': artist = ''
                                artists.append(artist)
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
                        
                            possible_albumtypes = self.get_possible_albumtypes('ALBUMARTIST_ALBUM')
                        
                            countstatement = "select count(*) from GenreAlbumartistAlbumTrack where genre=? and albumartist=? and album=? and duplicate = %s" % (duplicate_number)
                            countstatement2 = "select count(*) from GenreAlbumartistAlbumTrack where genre=? and albumartist=? and album=? and duplicate = %s and albumtype=?" % (duplicate_number)
                            statement = "select * from tracks where id in (select track_id from GenreAlbumartistAlbumTrack where genre=? and albumartist=? and album=? and duplicate = %s) order by discnumber, tracknumber, title limit %d, %d" % (duplicate_number, startingIndex, requestedCount)
                            statement2 = "select distinct(albumtype) from GenreAlbumartistAlbumTrack where genre=? and albumartist=? and album=? and duplicate=%s order by albumtype" % (duplicate_number)
#                            statement3 = '''select * from tracks t, tracknumbers n where id in 
#                                           (select track_id from GenreAlbumartistAlbumTrack where genre=? and albumartist=? and album=? and duplicate=%s)
#                                           and t.id = n.track_id and t.genre=n.genre and t.artist=n.artist and t.albumartist=n.albumartist and t.album=n.album and t.composer=n.composer and t.duplicate=n.duplicate and n.albumtype=?
#                                           order by t.discnumber, n.tracknumber, t.title limit %d, %d''' % (duplicate_number, startingIndex, requestedCount)

                            statement3 = '''
                                            select * from tracks t join tracknumbers n on t.id = n.track_id where id in
                                            (select track_id from tracknumbers where track_id in 
                                                (select track_id from GenreAlbumartistAlbumTrack where genre=? and albumartist=? and album=? and duplicate=%s and albumtype=?)
                                            and albumtype=?)
                                            and albumtype=? 
                                            order by n.tracknumber, t.title
                                            limit %d, %d
                                         ''' % (duplicate_number, startingIndex, requestedCount)

                        else:                

                            possible_albumtypes = self.get_possible_albumtypes('ARTIST_ALBUM')
                        
                            countstatement = "select count(*) from GenreArtistAlbumTrack where genre=? and artist=? and album=? and duplicate = %s" % (duplicate_number)
                            countstatement2 = "select count(*) from GenreArtistAlbumTrack where genre=? and artist=? and album=? and duplicate = %s and albumtype=?" % (duplicate_number)
                            statement = "select * from tracks where id in (select track_id from GenreArtistAlbumTrack where genre=? and artist=? and album=? and duplicate = %s) order by discnumber, tracknumber, title limit %d, %d" % (duplicate_number, startingIndex, requestedCount)
                            statement2 = "select distinct(albumtype) from GenreArtistAlbumTrack where genre=? and albumartist=? and album=? and duplicate=%s order by albumtype" % (duplicate_number)
#                            statement3 = '''select * from tracks t, tracknumbers n where id in 
#                                           (select track_id from GenreArtistAlbumTrack where genre=? and albumartist=? and album=? and duplicate=%s)
#                                           and t.id = n.track_id and t.genre=n.genre and t.artist=n.artist and t.albumartist=n.albumartist and t.album=n.album and t.composer=n.composer and t.duplicate=n.duplicate and n.albumtype=?
#                                           order by t.discnumber, n.tracknumber, t.title limit %d, %d''' % (duplicate_number, startingIndex, requestedCount)

                            statement3 = '''
                                            select * from tracks t join tracknumbers n on t.id = n.track_id where id in
                                            (select track_id from tracknumbers where track_id in 
                                                (select track_id from GenreArtistAlbumTrack where genre=? and albumartist=? and album=? and duplicate=%s and albumtype=?)
                                            and albumtype=?)
                                            and albumtype=? 
                                            order by n.tracknumber, t.title
                                            limit %d, %d
                                         ''' % (duplicate_number, startingIndex, requestedCount)

                    log.debug("count statement: %s", countstatement)
                    log.debug("statement: %s", statement)

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
                                    c.execute(countstatement, (field, ))
                                elif tracks_type == 'ARTIST':
                                    if not_album:
                                        c.execute(countstatement, (artist, field))
                                    else:
                                        albumtype = 10
                                        c.execute(statement2, (artist, field))
                                        for row in c:
                                            albumtype, = row
                                            if albumtype == 10: break
                                            elif albumtype in possible_albumtypes: break
                                        if albumtype == 10:
                                            c.execute(countstatement, (artist, field))
                                        else:            
                                            c.execute(countstatement2, (artist, field, albumtype))
                                elif tracks_type == 'GENRE':
                                    albumtype = 10
                                    c.execute(statement2, (genre, artist, field))
                                    for row in c:
                                        albumtype, = row
                                        if albumtype == 10: break
                                        elif albumtype in possible_albumtypes: break
                                    if albumtype == 10:
                                        c.execute(countstatement, (genre, artist, field))
                                    else:            
                                        c.execute(countstatement2, (genre, artist, field, albumtype))
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

            albumtype = 10
            if tracks_type == 'TRACKS':
                c.execute(statement)
            elif tracks_type == 'FIELD':
                c.execute(statement, (field, ))
            elif tracks_type == 'ARTIST':
                if not_album:
                    # genre/artist
                    c.execute(statement, (artist, field))
                else:
                
                    log.debug(statement2)
                    log.debug(artist)
                    log.debug(field)
                    log.debug(statement3)
                
                    c.execute(statement2, (artist, field))
                    albumtype, = c.fetchone()
                    if albumtype != 10:
                        c.execute(statement3, (artist, field, albumtype, albumtype, albumtype))
                    else:            
                        c.execute(statement, (artist, field))
            elif tracks_type == 'GENRE':
                c.execute(statement2, (genre, artist, field))
                albumtype, = c.fetchone()
                if albumtype != 10:
                    c.execute(statement3, (genre, artist, field, albumtype, albumtype, albumtype))
                else:            
                    c.execute(statement, (genre, artist, field))

            for row in c:
                log.debug("row: %s", row)
                if albumtype != 10:
                    id, id2, parentID, duplicate, title, artist, album, genre, tracknumber, year, albumartist, composer, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, upnpclass, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned, d1, d2, d3, d4, d5, d6, d7, d8, d9, d10 = row
                else:
                    id, id2, parentID, duplicate, title, artist, album, genre, tracknumber, year, albumartist, composer, codec, length, size, created, path, filename, discnumber, comment, folderart, trackart, bitrate, samplerate, bitspersample, channels, mime, lastmodified, upnpclass, folderartid, trackartid, inserted, lastplayed, playcount, lastscanned = row
                mime = fixMime(mime)
                cover, artid = self.choosecover(folderart, trackart, folderartid, trackartid)

                # TODO: automate mount
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

                duration = maketime(float(length))

                if title == '': title = '[unknown title]'
                if artist == '': artist = '[unknown artist]'
                else: artist = self.get_artist(artist, self.now_playing_artist, self.now_playing_artist_combiner)
                if albumartist == '': albumartist = '[unknown albumartist]'
                else: albumartist = self.get_artist(albumartist, self.now_playing_artist, self.now_playing_artist_combiner)
                if album == '': album = '[unknown album]'
                title = escape(title)
                artist = escape(artist)
                albumartist = escape(albumartist)
                album = escape(album)
                tracknumber = self.convert_tracknumber(tracknumber)
                count += 1
                
                ret += '<item id="%s" parentID="%s" restricted="true">' % (id, parentID)
                ret += '<dc:title>%s</dc:title>' % (title)
                ret += '<upnp:artist role="AlbumArtist">%s</upnp:artist>' % (albumartist)
                ret += '<upnp:artist role="Performer">%s</upnp:artist>' % (artist)
                ret += '<upnp:album>%s</upnp:album>' % (album)
                if tracknumber != 0:
                    ret += '<upnp:originalTrackNumber>%s</upnp:originalTrackNumber>' % (tracknumber)
                ret += '<upnp:class>%s</upnp:class>' % (upnpclass)
                ret += '<res duration="%s" protocolInfo="%s">%s</res>' % (duration, protocol, res)
####                ret += '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">%s</desc>' % (self.wmpudn)
#                if cover != '' and not cover.startswith('EMBEDDED_'):
#                    ret += '<upnp:albumArtURI>%s</upnp:albumArtURI>' % (coverres)
                ret += '</item>'
            ret += '</DIDL-Lite>'

            res = ret
            
        elif containerID == '0' and searchCriteria == 'upnp:class = "object.container.playlistContainer" and @refID exists false':
            # Playlist class

            res  = '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
            count = 0
            parentid = '0'

            c.execute("select count(*) from playlists")
            totalMatches, = c.fetchone()
            
            statement = "select * from playlists order by playlist limit %d, %d" % (startingIndex, requestedCount)
            c.execute(statement)
            for row in c:
#                log.debug("row: %s", row)
                id, parentID, playlist, path, upnpclass = row
                id = str(id)
                if playlist == '': playlist = '[unknown playlist]'
                playlist = escape(playlist)
                count += 1
                res += '<container id="%s" parentID="%s" restricted="true">' % (id, parentid)
                res += '<dc:title>%s</dc:title>' % (playlist)
                res += '<upnp:class>%s</upnp:class>' % (upnpclass)
                res += '</container>'
            res += '</DIDL-Lite>'
            
        else:
            # unknown search criteria
            print "proxy_search - unknown search criteria, not supported in code"
            res = ''
            count = 0
            totalMatches = 0
            
        c.close()

        # fix WMP urls if necessary
        res = res.replace(self.webserverurl, self.wmpurl)

        log.debug("SEARCH res: %s", res)
        result = {'NumberReturned': str(count), 'UpdateID': self.updateid, 'Result': res, 'TotalMatches': totalMatches}
        log.debug("SEARCH result: %s", result)

        log.debug("end: %.3f" % time.time())

#        import traceback        
#        traceback.print_stack()

        return result

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

    def makepresuffix(self, fix, replace, fixdict):
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
                    elif fix == 'artist':
                        artist = fixdict['artist']
                        if artist == '': artist = self.chunk_metadata_empty
                        outfix += replace % artist
                    elif fix == 'albumartist':
                        albumartist = fixdict['albumartist']
                        if albumartist == '': albumartist = self.chunk_metadata_empty
                        outfix += replace % albumartist
                    elif fix == 'composer':
                        composer = fixdict['composer']
                        if composer == '': composer = self.chunk_metadata_empty
                        outfix += replace % composer
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


        
        orderbylist = self.get_orderby(sourcetable, controllername)
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

    def get_artist(self, artist, entrytype, combiner):
        artistlist = artist.split(MULTI_SEPARATOR)
        if entrytype == 'all':
            return combiner.join(artistlist)
        elif entrytype == 'first':
            return artistlist[0]        
        elif entrytype == 'last':
            return artistlist[-1]        

    def prime_cache(self):
        db = sqlite3.connect(os.path.join(os.getcwd(), self.dbname))
        c = db.cursor()
        try:
            c.execute("""select * from albums""")
        except sqlite3.Error, e:
            print "Error priming cache:", e.args[0]
        c.close()

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

    def get_orderby(self, sorttype, controller):
        # TODO: only load this on start and updateid change
        if not self.use_sorts:
            return [(None, None, None, 10, 'dummy', None)]
        order_out = []
        db = sqlite3.connect(os.path.join(os.getcwd(), self.dbname))
        db.create_function("checkkeys", 4, self.checkkeys)
        c = db.cursor()
        try:
            dummysorttype = sorttype
            if sorttype == 'ALBUMARTIST_ALBUM':
                dummysorttype = 'ARTIST_ALBUM'
            elif sorttype == 'ALBUMARTIST':
                dummysorttype = 'ARTIST'
            elif sorttype == 'GENRE_ALBUMARTIST':
                dummysorttype = 'GENRE_ARTIST'
            statement = """select sort_order, sort_prefix, sort_suffix, album_type, header_name from sorts where checkkeys(proxyname, "%s", controller, "%s") and sort_type="%s" and active is not null and active!="" order by sort_seq""" % (self.proxy.proxyname, controller, dummysorttype)
            log.debug(statement)
            c.execute(statement)
            for row in c:
                log.debug(row)
                so, sp, ss, albumtypestring, hn = row
                if self.use_albumartist:
                    if so: so = re.sub('(?<!album)artist', 'albumartist', so)
                    if sp: sp = re.sub('(?<!album)artist', 'albumartist', sp)
                    if ss: ss = re.sub('(?<!album)artist', 'albumartist', ss)
                else:
                    if so: so = so.replace('albumartist', 'artist')
                    if sp: sp = sp.replace('albumartist', 'artist')
                    if ss: ss = ss.replace('albumartist', 'artist')
                # special case for album
                if sorttype == 'ALBUM':
                    if not albumtypestring:
                        albumtypestrings = ['album']
                    else:
                        if self.use_albumartist:
                            albumtypestring = re.sub('(?<!album)artist_virtual', 'albumartist_virtual', albumtypestring)
                        else:
                            albumtypestring = albumtypestring.replace('albumartist_virtual', 'artist_virtual')
                        albumtypestrings = albumtypestring.split(',')
                        albumtypestrings = [k.strip() for k in albumtypestrings]
                        albumtypestrings = [k for k in albumtypestrings if k != '']
                        if not 'album' in albumtypestrings:
                            albumtypestrings.insert(0, 'album')
                        log.debug(albumtypestrings)
                    ats = []
                    for at in albumtypestrings:
                        albumtypenum, table = self.translate_albumtype(at, sorttype)
                        ats.append(albumtypenum)
                    albumtypenum = ats
                else:
                    albumtypenum, table = self.translate_albumtype(albumtypestring, sorttype)
                order_out.append((so, sp, ss, albumtypenum, table, hn))
        except sqlite3.Error, e:
            print "Error getting sort info:", e.args[0]
        c.close()
        if order_out == []:
            return [(None, None, None, 10, 'dummy', None)]
        log.debug(order_out)
        return order_out

    def translate_albumtype(self, albumtype, table):
        if not albumtype or albumtype == '':
            return '10', 'album'
        elif albumtype == 'album':
            return '10', albumtype
        elif albumtype == 'virtual':
            if table == 'COMPOSER_ALBUM':
                return '25', albumtype
            elif table == 'ARTIST_ALBUM':
                return '26', albumtype
            elif table == 'ALBUMARTIST_ALBUM':
                return '27', albumtype
            elif table == 'CONTRIBUTINGARTIST_ALBUM':
                return '28', albumtype
        elif albumtype == 'work':
            if table == 'COMPOSER_ALBUM':
                return '31', albumtype
            elif table == 'ARTIST_ALBUM':
                return '32', albumtype
            elif table == 'ALBUMARTIST_ALBUM':
                return '33', albumtype
            elif table == 'CONTRIBUTINGARTIST_ALBUM':
                return '34', albumtype

        elif albumtype == 'composer_virtual':
            return '25', albumtype
        elif albumtype == 'artist_virtual':
            return '26', albumtype
        elif albumtype == 'albumartist_virtual':
            return '27', albumtype
        elif albumtype == 'contributingartist_virtual':
            return '28', albumtype

        elif albumtype == 'composer_work':
            return '31', albumtype
        elif albumtype == 'artist_work':
            return '32', albumtype
        elif albumtype == 'albumartist_work':
            return '33', albumtype
        elif albumtype == 'contributingartist_work':
            return '34', albumtype

        else:
            return '10', 'album'

    def get_possible_albumtypes(self, table):
        if table == 'COMPOSER_ALBUM':
            return [25, 31]
        elif table == 'ARTIST_ALBUM':
            return [26, 32]
        elif table == 'ALBUMARTIST_ALBUM':
            return [27, 33]
        elif table == 'CONTRIBUTINGARTIST_ALBUM':
            return [28, 34]

    def get_updateid(self):
        db = sqlite3.connect(os.path.join(os.getcwd(), self.dbname))
        c = db.cursor()
        statement = "select lastscanid from params where key = '1'"
        log.debug("statement: %s", statement)
        c.execute(statement)
        new_updateid, = c.fetchone()
        if new_updateid != self.updateid:
            self.updateid = new_updateid
            self._state_variables['SystemUpdateID'].update(self.updateid)
            log.debug("SystemUpdateID value: %s" % self._state_variables['SystemUpdateID'].get_value())

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

    def choosecover(self, folderart, trackart, folderartid, trackartid):
#        log.debug(folderart)
#        log.debug(trackart)
#        log.debug(folderartid)
#        log.debug(trackartid)
        try:
            if trackart and trackart != '' and not (folderart and folderart!= '' and self.prefer_folderart):
                cover = trackart
                artid = trackartid
            elif folderart and folderart != '':
                cover = folderart
                artid = folderartid
            else:
                cover = ''
                artid = ''
        except Exception, e:
            log.debug(e)
#        log.debug('cover: %s  id: %s' % (cover, artid))
        return cover, artid

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
        result = {'Id': self.updateid}
        return result

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
#    return 'http-get:*:%s:*' % mime    
    return 'http-get:*:%s:%s' % (mime, 'DLNA.ORG_PN=MP3;DLNA.ORG_OP=01;DLNA.ORG_CI=0')



def getFileType(filename):
    return filename.split('.')[-1]

def getFile(path):
    return path.split(os.sep)[-1]

escape_entities = {'"' : '&quot;', "'" : '&apos;', " " : '%20'}
escape_entities_quotepos = {'"' : '&quot;', "'" : '&apos;'}
unescape_entities = {'&quot;' : '"', '&apos;' : "'", '%20' : " ", '&amp;' : "&"}
unescape_entities_quotepos = {'&quot;' : '"', '&apos;' : "'"}

