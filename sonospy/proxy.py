#
# proxy
#
# Copyright (c) 2009-2013 Mark Henkelis
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

################################
# Proxy for internal mediaserver
################################

class Proxy(object):

    def __init__(self, proxyname, proxytype, proxytrans, udn, config, port,
                 mediaserver=None, controlpoint=None, createwebserver=False,
                 webserverurl=None, wmpurl=None, startwmp=False, dbname=None, ininame=None,
                 wmpudn=None, wmpcontroller=None, wmpcontroller2=None,
                 wmptype=None):
        '''
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
        self.presentation_map_file = '%s.xml' % self.udn[5:]
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
        if ininame == None:
            self.ininame = None
        else:
            self.ininame = ininame
        self.wmpudn = wmpudn
        self.wmpwebserver = None
        self.wmpcontroller = wmpcontroller
        self.wmpcontroller2 = wmpcontroller2
        self.wmptype = wmptype

        self.destmusicaddress = None
        if mediaserver == None:
            self.destaddress = None
        else:
            self.destaddress = mediaserver.address

        # get db cache size
        self.db_cache_size = 2000
        try:
            db_cache_size_option = self.config.get('database', 'db_cache_size')
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
            db_persist_connection_option = self.config.get('database', 'db_persist_connection')
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
        try:
            if self.wmptype == 'Service':
                self.smapiservice = Smapi(self.root_device.location, self, self.webserverurl, self.wmpurl, self.dbspec, self.wmpudn, self.ininame)
                self.root_device.add_service(self.smapiservice)
            elif self.wmptype == 'Proxy':
                self.cdservice = ContentDirectory(self.root_device.location, self, self.webserverurl, self.wmpurl, self.dbspec, self.wmpudn, self.ininame)
                self.root_device.add_service(self.cdservice)
                self.cmservice = ConnectionManager()
                self.root_device.add_service(self.cmservice)
                self.mrservice = X_MS_MediaReceiverRegistrar()
                self.root_device.add_service(self.mrservice)
        except: # catch *all* exceptions
            e = sys.exc_info()[0]
            log.debug(e)
            import traceback
            tb = traceback.format_exc()
            log.debug(tb)

    def _create_webserver(self, wmpurl):
        p = network.parse_url(wmpurl)
#        self.wmpwebserver = webserver.WebServer(server_name='www.sonospy.com', host=p.hostname, port=p.port)
        self.wmpwebserver = webserver.WebServer(server_name='www.sonospy.com', host='0.0.0.0', port=p.port)
        self.wmplocation = self.wmpwebserver.get_listen_url()
        self.wmpcontroller = ProxyServerController(self, 'WMPNSSv3')
        self.wmpwebserver.add_resource(self.wmpcontroller)
        self.wmpcontroller2 = ProxyServerController(self, 'wmp')
        self.wmpwebserver.add_resource(self.wmpcontroller2)

    def _serve_pm_file(self):
        # serve presentation map XML from Proxy
        pm_xml_path = os.path.join(os.getcwd(), self.presentation_map_file)
        log.debug("pm file: %s" % pm_xml_path)
        pmstaticfile = webserver.StaticFile(self.presentation_map_file, pm_xml_path)
        self.root_device.webserver.add_static_file(pmstaticfile)

    def _load(self):
        self._add_root_device()
        self._add_services()
        if self.startwmp == True:
            self._create_webserver(self.wmpurl)
            if self.wmptype == 'Service':
                self._serve_pm_file()

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

    def __init__(self, proxyaddress, proxy , webserverurl, wmpurl, dbspec, wmpudn, ininame):

        self.proxyaddress = proxyaddress
        self.proxy = proxy
        self.webserverurl = webserverurl
        self.wmpurl = wmpurl
        self.dbspec = dbspec
        dbpath, self.dbname = os.path.split(dbspec)
        self.wmpudn = wmpudn
        self.ininame = ininame

        # check whether user indexes are enabled
        self.load_user_index_flag()

        if not self.user_indexes:

            # create MediaServer with default hierarchical ID
            self.mediaServer = MediaServer(self.proxy, self.dbspec, 'SMAPI', 'HIERARCHY_DEFAULT', self.proxyaddress, self.webserverurl, self.wmpurl, self.ininame)

        else:

            # create MediaServer with user defined hierarchical ID
            self.mediaServer = MediaServer(self.proxy, self.dbspec, 'SMAPI', 'HIERARCHY', self.proxyaddress, self.webserverurl, self.wmpurl, self.ininame)

        Service.__init__(self, self.service_name, self.service_type, url_base='', scpd_xml_filepath=self.scpd_xml_path)

# TODO: replace scpd with ws:
#       namespace is currently hardcoded
#       result is manually created from children

    def load_user_index_flag(self):

        # get user index setting
        self.user_indexes = False
        try:
            ini_user_indexes = self.proxy.config.get('indexing', 'user_indexes')
            if ini_user_indexes.lower() == 'y':
                self.user_indexes = True
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass

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

        self.mediaServer.load_ini()

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
What do we do if a result is not in alpha order? - spec says it has to be
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

                scrolltype = '!Alpha%s' % browsetype
                # dynamic
                queryID = '-1'
                SearchCriteria = ''
                StartingIndex = 0
                RequestedCount = 1
                scrollresult = self.mediaServer.dynamicQuery(Controller=controllername,
                                                                Address=controlleraddress,
                                                                QueryID=queryID,
                                                                SearchCriteria=SearchCriteria,
                                                                StartingIndex=StartingIndex,
                                                                RequestedCount=RequestedCount,
                                                                SMAPI=scrolltype)

            elif not browsebyid:

                scrolltype = '!Alpha%s' % browsetype
                # create call data for CD Search and call it
                queryID = '-1'
                SearchCriteria = ''
                StartingIndex = 0
                RequestedCount = 1
                scrollresult = self.mediaServer.staticQuery(Controller=controllername,
                                                              Address=controlleraddress,
                                                              QueryID=queryID,
                                                              SearchCriteria=SearchCriteria,
                                                              StartingIndex=StartingIndex,
                                                              RequestedCount=RequestedCount,
                                                              SMAPI=scrolltype)

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

    def soap_getExtendedMetadata(self, *args, **kwargs):

        log.debug("SMAPI_GETEXTENDEDMETADATA: %s", kwargs)
#        res = self.processExtendedMetadata(kwargs)
#        res = '''<ns0:mediaMetadata><ns0:id>Talbumartist__0_0_0__7da3dd8d08cc9d3ac60206449cae886e</ns0:id><ns0:title>Eat for Two</ns0:title><ns0:mimeType>audio/mpeg</ns0:mimeType><ns0:itemType>track</ns0:itemType><ns0:trackMetadata><ns0:aristId></ns0:aristId><ns0:artist>10,000 Maniacs</ns0:artist><ns0:composerId></ns0:composerId><ns0:composer></ns0:composer><ns0:albumId></ns0:albumId><ns0:album>Blind Man's Zoo</ns0:album><ns0:albumArtURI>http://192.168.1.71:10243/wmp/chow.29.jpg</ns0:albumArtURI><ns0:albumArtistId></ns0:albumArtistId><ns0:albumArtist>10,000 Maniacs</ns0:albumArtist><ns0:genreId></ns0:genreId><ns0:genre></ns0:genre><ns0:duration>212</ns0:duration></ns0:trackMetadata></ns0:mediaMetadata><ns0:relatedText><ns0:id>Talbumartist__0_0_0__7da3dd8d08cc9d3ac60206449cae886e</ns0:id><ns0:type>ALBUM_NOTES</ns0:type></ns0:relatedText>'''

        id = kwargs['{http://www.sonos.com/Services/1.1}id']
        log.debug("id: %s" % id)
        if not id.startswith('T'):
            ret = u''
            ret += '<ns0:mediaCollection>'
            ret += '<ns0:id>%s</ns0:id>' % (id)
            ret += '<ns0:title>title</ns0:title>'
            ret += '<ns0:itemType>artist</ns0:itemType>'
            ret += '<ns0:canPlay>%i</ns0:canPlay>' % (False)
            ret += '<ns0:canScroll>%i</ns0:canScroll>' % (False)
            ret += '<ns0:canEnumerate>%i</ns0:canEnumerate>' % (False)
            ret += '</ns0:mediaCollection>'
            ret += '<ns0:relatedBrowse>'
            ret += '<ns0:id>ABCDE</ns0:id>'
            ret += '<ns0:type>RELATED_ARTISTS</ns0:type>'
            ret += '</ns0:relatedBrowse>'
            ret += '<ns0:relatedText>'
            ret += '<ns0:id>%s</ns0:id>' % (id)
            ret += '<ns0:type>ARTIST_BIO</ns0:type>'
            ret += '</ns0:relatedText>'
            ret += '<ns0:relatedText>'
            ret += '<ns0:id>%s</ns0:id>' % (id)
            ret += '<ns0:type>ALBUM_NOTES</ns0:type>'
            ret += '</ns0:relatedText>'
            res = ret
        else:

            res = self.processMediaMetadata('metadata', kwargs)
            log.debug(res)
            res = '''<ns0:mediaMetadata><ns0:id>Talbumartist__0_0_0__67346f5465fa836fc3e6acf9e8e46115</ns0:id><ns0:itemType>track</ns0:itemType><ns0:title>Babylon</ns0:title><ns0:mimeType>audio/mpeg</ns0:mimeType><ns0:trackMetadata><ns0:aristId>R8:200000043</ns0:aristId><ns0:artist>David Gray</ns0:artist><ns0:albumId>R8:200000043:300000038</ns0:albumId><ns0:album>Greatest Hits</ns0:album><ns0:albumArtistId>R8:200000043</ns0:albumArtistId><ns0:albumArtist>David Gray</ns0:albumArtist><ns0:duration>217</ns0:duration><ns0:canPlay>true</ns0:canPlay><ns0:canSkip>true</ns0:canSkip><ns0:canAddToFavorites>true</ns0:canAddToFavorites></ns0:trackMetadata></ns0:mediaMetadata><ns0:relatedBrowse><ns0:id>ABCDE</ns0:id><ns0:type>RELATED_ARTISTS</ns0:type></ns0:relatedBrowse><ns0:relatedText><ns0:id>R8:200000043</ns0:id><ns0:type>ARTIST_BIO</ns0:type></ns0:relatedText><ns0:relatedText><ns0:id>R8:200000043:300000038</ns0:id><ns0:type>ALBUM_NOTES</ns0:type></ns0:relatedText>'''
            res = unicode(res)



#<ns0:relatedBrowse><ns0:id>ABCDE</ns0:id><ns0:type>RELATED_ARTISTS</ns0:type></ns0:relatedBrowse>
#<ns0:relatedText><ns0:id>R8:200000043</ns0:id><ns0:type>ARTIST_BIO</ns0:type></ns0:relatedText>
#<ns0:relatedText><ns0:id>R8:200000043:300000038</ns0:id><ns0:type>ALBUM_NOTES</ns0:type></ns0:relatedText>

        '''
            ret = u''
            ret += '<ns0:mediaMetadata>'
            ret += '<ns0:id>%s</ns0:id>' % (id)
            ret += '<ns0:title>Eat for Two</ns0:title>'
            ret += '<ns0:mimeType>audio/mpeg</ns0:mimeType>'
            ret += '<ns0:itemType>track</ns0:itemType>'
            ret += '<ns0:trackMetadata>'
            ret += '<ns0:aristId></ns0:aristId>'
            ret += '<ns0:artist>artist</ns0:artist>'
            ret += '<ns0:composerId></ns0:composerId>'
            ret += '<ns0:composer>composer</ns0:composer>'
            ret += '<ns0:albumId></ns0:albumId>'
            ret += '<ns0:album>album</ns0:album>'
            ret += '<ns0:albumArtURI></ns0:albumArtURI>'
            ret += '<ns0:albumArtistId></ns0:albumArtistId>'
            ret += '<ns0:albumArtist>albumartist</ns0:albumArtist>'
            ret += '<ns0:genreId></ns0:genreId>'
            ret += '<ns0:genre>genre</ns0:genre>'
            ret += '<ns0:duration>100</ns0:duration>'
            ret += '</ns0:trackMetadata>'
            ret += '</ns0:mediaMetadata>'
#            ret += '<ns0:relatedBrowse>'
#            ret += '<ns0:id>ABCDE</ns0:id>'
#            ret += '<ns0:type>RELATED_ARTISTS</ns0:type>'
#            ret += '</ns0:relatedBrowse>'
#            ret += '<ns0:relatedText>'
#            ret += '<ns0:id>%s</ns0:id>' % (id)
#            ret += '<ns0:type>ARTIST_BIO</ns0:type>'
#            ret += '</ns0:relatedText>'
#            ret += '<ns0:relatedText>'
#            ret += '<ns0:id>%s</ns0:id>' % (id)
#            ret += '<ns0:type>ALBUM_NOTES</ns0:type>'
#            ret += '</ns0:relatedText>'
            res = ret
        '''
        result = {'{http://www.sonos.com/Services/1.1}getExtendedMetadataResult': '%s' % res}
        log.debug("SMAPI_GETEXTENDEDMETADATA ret: %s\n", result)
        return result

    def soap_getExtendedMetadataText(self, *args, **kwargs):

        log.debug("SMAPI_GETEXTENDEDMETADATATEXT: %s", kwargs)
#        res = self.processExtendedMetadataText(kwargs)
        res = 'This is extended metadata text.\nHopefully it will be displayed on multiple lines.\n.\n.\nEnd.'
        result = {'{http://www.sonos.com/Services/1.1}getExtendedMetadataTextResult': '%s' % res}
        log.debug("SMAPI_GETEXTENDEDMETADATATEXT ret: %s\n", result)
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
                                                                    term=term)

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

        queryID = kwargs['{http://www.sonos.com/Services/1.1}id']
        log.debug("id: %s" % queryID)

        BrowseFlag = 'BrowseDirectChildren'
        index = 0
        count = 1

        try:
            # we know query type, call it direct
            items, total, index, itemtype = self.mediaServer.staticQuery(Controller=controllername,
                                                                            Address=controlleraddress,
                                                                            QueryID=queryID,
                                                                            BrowseFlag=BrowseFlag,
                                                                            StartingIndex=index,
                                                                            RequestedCount=count,
                                                                            SMAPI='',
                                                                            Action='BROWSE')
        except: # catch *all* exceptions
            e = sys.exc_info()[0]
            log.debug(e)
            import traceback
            tb = traceback.format_exc()
            log.debug(tb)

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
            # empty index
            items = [('NIF', self.mediaServer.noitemsfound)]
            canenumerate = False
            canplay = False
            total = 1

        elif total == -1:
            # incomplete keyword search
            items = [('EK', self.mediaServer.enterkeywords)]
            canenumerate = False
            canplay = False
            total = 1

        elif total == -2:
            # invalid keyword search
            items = [('IK', self.mediaServer.novalidkeywords)]
            canenumerate = False
            canplay = False
            total = 1

        prevsearchtype = ''
        for item in items:
            id = item[0]
            title = item[1]
            albumarturi = None
            if len(item) == 3:
                albumarturi = item[2]
            if len(item) == 4:
                searchtype = item[3]
                '''
                if searchtype != prevsearchtype:
                    prevsearchtype = searchtype
                    # is a separator
                    ret += '<ns0:mediaCollection>'
                    ret += '<ns0:id>%s</ns0:id>' % (id)
                    ret += '<ns0:title>%s</ns0:title>' % (self.mediaServer.keywordsearchdelimiter % searchtype)
                    if albumarturi != None:
                        ret += '<ns0:albumArtURI>%s</ns0:albumArtURI>' % (albumarturi)
                    ret += '<ns0:itemType>search</ns0:itemType>'
                    ret += '<ns0:canPlay>%i</ns0:canPlay>' % (False)
                    ret += '<ns0:canScroll>%i</ns0:canScroll>' % (False)
                    ret += '<ns0:canEnumerate>%i</ns0:canEnumerate>' % (False)
                    ret += '</ns0:mediaCollection>'
                    count += 1
#                    index += 1
                    total += 1
                '''
             
            count += 1
            if len(item) == 2 or len(item) == 3 or len(item) == 4:
                # is a container
                ret += '<ns0:mediaCollection>'
                ret += '<ns0:id>%s</ns0:id>' % (id)
                ret += '<ns0:title>%s</ns0:title>' % (title)
                if albumarturi != None:
                    ret += '<ns0:albumArtURI>%s</ns0:albumArtURI>' % (albumarturi)
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

        # fix WMP urls if necessary
        res = res.replace(self.webserverurl, self.wmpurl)

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

        # fix WMP urls if necessary
        ret = ret.replace(self.webserverurl, self.wmpurl)

        return ret

    def make_streammetadataresult(self, metadata):

        ret = ''

        # TODO

        return ret

    def make_uriresult(self, items):

        id, title, mimetype, uri, itemtype, metadatatype, metadata = items[0]

        return uri

##########################
##########################
# ContentDirectory service
##########################
##########################

class ContentDirectory(Service):

    service_name = 'ContentDirectory'
    service_type = 'urn:schemas-upnp-org:service:ContentDirectory:1'
    scpd_xml_path = os.path.join(os.getcwd(), 'content-directory-scpd.xml')

    def __init__(self, proxyaddress, proxy , webserverurl, wmpurl, dbspec, wmpudn, ininame):
        self.proxyaddress = proxyaddress
        self.proxy = proxy
        self.webserverurl = webserverurl
        self.wmpurl = wmpurl
        self.dbspec = dbspec
        dbpath, self.dbname = os.path.split(dbspec)
        self.wmpudn = wmpudn
        self.ininame = ininame

        # check whether user indexes are enabled
        self.load_user_index_flag()

        if not self.user_indexes:

            # create MediaServer with default hierarchical ID
            self.mediaServer = MediaServer(self.proxy, self.dbspec, 'UPNP', 'HIERARCHY_DEFAULT', self.proxyaddress, self.webserverurl, self.wmpurl, self.ininame)

        else:

            # create MediaServer with user defined hierarchical ID
            self.mediaServer = MediaServer(self.proxy, self.dbspec, 'UPNP', 'HIERARCHY', self.proxyaddress, self.webserverurl, self.wmpurl, self.ininame)

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

    def load_user_index_flag(self):

        # get user index setting
        self.user_indexes = False
        try:
            ini_user_indexes = self.proxy.config.get('indexing', 'user_indexes')
            if ini_user_indexes.lower() == 'y':
                self.user_indexes = True
        except ConfigParser.NoSectionError:
            pass
        except ConfigParser.NoOptionError:
            pass
            
    ################################
    # ContentDirectory soap services
    ################################

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

        self.mediaServer.load_ini()

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

        try:
            # call wrapper
            xml, count, total = self.mediaServer.query(Action='BROWSE', **kwargs)
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

        # TODO: what are we going to do with this?

        try:
            # call wrapper
            xml, count, total = self.mediaServer.query(Action='SEARCH', **kwargs)
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
        # TODO: make this pass whatever the user has defined
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

###########################
###########################
# ConnectionManager service
###########################
###########################

class ConnectionManager(Service):

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


