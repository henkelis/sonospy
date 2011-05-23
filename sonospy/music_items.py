#
# pycpoint
#
# Copyright (c) 2009 Mark Henkelis
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

#import log
from brisa.core import log

import re

from urlparse import urlparse

from xml.etree.ElementTree import _ElementInterface
from xml.etree import cElementTree as ElementTree

from xml.dom import minidom
from xml.dom.minidom import parseString

from brisa.upnp.didl import dlna, didl_lite
from brisa.upnp.didl.didl_lite import MusicTrack, WRITE_STATUS_NOT_WRITABLE

from brisa.core.network import parse_xml
from brisa.core.network import parse_url, url_fetch

from brisa.upnp.soap import SOAPProxy, HTTPError

#from brisa.upnp.control_point.control_point import get_service_control_url
from brisa.upnp.control_point import ControlPointAV

from brisa.upnp.didl.didl_lite import Container, Element, SonosMusicTrack

def dump_element(node):
    print "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ START @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
    for k in node:
        print str(k) + " : " + str(node[k])
        if type(node[k]) != str:
            print "---->"
            prettyPrint(node[k])
    print "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@ END @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"

def prettyPrint(element):
    txt = ElementTree.tostring(element)
#    txt = element.to_string()
    print minidom.parseString(txt).toprettyxml()

class music_item(object):

    def __init__(self):
        self.music_item_class = 'UNKNOWN MUSIC CLASS!'
        self.music_item_type = ''
        self.music_item_title = ''
        self.music_item_duration = ''
        self.music_item_album = ''
        self.music_item_artist = ''
        self.music_item_albumartURI = ''
#        self.music_item_sonos = SonosMusicTrackExtras()
        self.music_item_station = ''
        self.music_item_station_url = ''
        self.music_item_onnow = ''
        self.music_item_info = ''

    def unwrap_metadata(self, events_avt):

        self.music_item_class = ''
        self.music_item_type = ''
        self.music_item_title = ''
        self.music_item_duration = ''
        self.music_item_album = ''
        self.music_item_artist = ''
        self.music_item_albumartURI = ''
        self.music_item_station = ''
        self.music_item_station_url = ''
        self.music_item_onnow = ''
        self.music_item_info = ''
        details = ''
        extras = ''
        audiotype = ''

#        print "events_avt: " + str(events_avt)
        
        if events_avt == {}:
            return ('', '', {}, {}, '')

        metadata = events_avt['CurrentTrackMetaData']

        if metadata != None and metadata != '' and metadata != 'NOT_IMPLEMENTED':
        
            if isinstance(metadata, didl_lite.SonosMusicTrackShow):
                audiotype = 'SonosMusicTrackShow'
            elif isinstance(metadata, didl_lite.SonosMusicTrack):
                audiotype = 'SonosMusicTrack'
            elif isinstance(metadata, didl_lite.MusicTrack):
                audiotype = 'MusicTrack'
#            elif isinstance(metadata, didl_lite.SonosItem):    # these don't contain all the info - fall through to EnqueuedTransportURIMetaData
#                audiotype = 'SonosItem'
# TODO: work out what all the combinations are to get all info
            else:
                metadata = events_avt['{' + ns['rcnw'] + '}EnqueuedTransportURIMetaData']
                if metadata != None and metadata != '' and metadata != 'NOT_IMPLEMENTED':
                    if isinstance(metadata, didl_lite.SonosAudioBroadcast):
                        audiotype = 'SonosAudioBroadcast'
                    elif isinstance(metadata, didl_lite.AudioBroadcast):
                        audiotype = 'AudioBroadcast'
                    elif isinstance(metadata, didl_lite.SonosItem):
                        audiotype = 'SonosMusicTrack'
                else:
                    return ('', '', {}, {}, '')
        else:
            return ('', '', {}, {}, '')

        detailsdict = {}
        extrasdict = {}

        if audiotype == 'SonosMusicTrack':

#            print events_avt['CurrentTrackMetaData']
#            print events_avt['CurrentTrackMetaData'].to_string()

            self.music_item_class = 'SonosMusicTrack'
            self.music_item_type = 'Track'

#            print '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@'
#            print '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@'
#            print 'class: ' + self.music_item_class
#            print 'title: ' + metadata.title
#            print 'album: ' + metadata.album
#            print 'creator: ' + metadata.creator
#            print 'items: ' + metadata.to_string()
#            print '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@'
#            print '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@'

            self.music_item_title = metadata.title
            self.music_item_duration = metadata.resources[0].duration    # TODO: check whether there can be more than one set of res
            self.music_item_artist = metadata.creator
            self.music_item_album = metadata.album
            self.music_item_albumartURI = metadata.albumArtURI

            '''
            if self.music_item_title != '':
                details += 'TRACK: ' + self.music_item_title + '\n'
                detailsdict['TRACK'] = self.music_item_title
            if self.music_item_duration != '':
                details += 'DURATION: ' + self.music_item_duration + '\n'
                detailsdict['DURATION'] = self.music_item_duration
            if self.music_item_artist != '':
                details += 'ARTIST: ' + self.music_item_artist + '\n'
                detailsdict['ARTIST'] = self.music_item_artist
            if self.music_item_album != '':
                details += 'ALBUM: ' + self.music_item_album + '\n'
                detailsdict['ALBUM'] = self.music_item_album
            if self.music_item_class != '':
                extras += 'CLASS: ' + self.music_item_class + '\n'
                extrasdict['CLASS'] = self.music_item_class
            if self.music_item_type != '':
                extras += 'TYPE: ' + self.music_item_type + '\n'
                extrasdict['TYPE'] = self.music_item_type
            '''
            details += 'TRACK: ' + self.music_item_title + '\n'
            detailsdict['TRACK'] = self.music_item_title
            details += 'DURATION: ' + self.music_item_duration + '\n'
            detailsdict['DURATION'] = self.music_item_duration
            details += 'ARTIST: ' + self.music_item_artist + '\n'
            detailsdict['ARTIST'] = self.music_item_artist
            details += 'ALBUM: ' + self.music_item_album + '\n'
            detailsdict['ALBUM'] = self.music_item_album
            extras += 'CLASS: ' + self.music_item_class + '\n'
            extrasdict['CLASS'] = self.music_item_class
            extras += 'TYPE: ' + self.music_item_type + '\n'
            extrasdict['TYPE'] = self.music_item_type

        elif audiotype == 'SonosMusicTrackShow':

#            print events_avt['CurrentTrackMetaData']
#            print events_avt['CurrentTrackMetaData'].to_string()

            self.music_item_class = 'SonosMusicTrackShow'
            self.music_item_type = 'Track'

#            print '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@'
#            print '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@'
#            print 'class: ' + self.music_item_class
#            print 'title: ' + metadata.title
#            print 'album: ' + metadata.album
#            print 'creator: ' + metadata.creator
#            print 'items: ' + metadata.to_string()
#            print '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@'
#            print '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@'

            self.music_item_title = metadata.title
            self.music_item_duration = metadata.resources[0].duration    # TODO: check whether there can be more than one set of res
            self.music_item_artist = metadata.creator
            self.music_item_album = metadata.album
            self.music_item_albumartURI = metadata.albumArtURI

            details += 'TRACK: ' + self.music_item_title + '\n'
            detailsdict['TRACK'] = self.music_item_title
            details += 'DURATION: ' + self.music_item_duration + '\n'
            detailsdict['DURATION'] = self.music_item_duration
            details += 'ARTIST: ' + self.music_item_artist + '\n'
            detailsdict['ARTIST'] = self.music_item_artist
            details += 'SHOW: ' + self.music_item_album + '\n'
            detailsdict['SHOW'] = self.music_item_album
            extras += 'CLASS: ' + self.music_item_class + '\n'
            extrasdict['CLASS'] = self.music_item_class
            extras += 'TYPE: ' + self.music_item_type + '\n'
            extrasdict['TYPE'] = self.music_item_type

        elif audiotype == 'MusicTrack':

            self.music_item_class = 'MusicTrack'
            self.music_item_type = 'Track'

#            print '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@'
#            print '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@'
#            print 'class: ' + self.music_item_class
#            print 'title: ' + metadata.title
#            print 'albums: ' + str(metadata.albums)
#            print 'creator: ' + metadata.creator
#            print 'artists: ' + str(metadata.artists)
#            print 'items: ' + metadata.to_string()
#            print '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@'
#            print '@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@'

            self.music_item_title = metadata.title
            self.music_item_duration = metadata.resources[0].duration    # TODO: check whether there can be more than one set of res
            self.music_item_artist = metadata.creator
            # TODO: AlbumArt

            details += 'TRACK: ' + self.music_item_title + '\n'
            detailsdict['TRACK'] = self.music_item_title
            details += 'DURATION: ' + self.music_item_duration + '\n'
            detailsdict['DURATION'] = self.music_item_duration
            details += 'ARTIST: ' + self.music_item_artist + '\n'
            detailsdict['ARTIST'] = self.music_item_artist
            details += 'ALBUM: ' + self.music_item_album + '\n'
            detailsdict['ALBUM'] = self.music_item_album
            extras += 'CLASS: ' + self.music_item_class + '\n'
            extrasdict['CLASS'] = self.music_item_class
            extras += 'TYPE: ' + self.music_item_type + '\n'
            extrasdict['TYPE'] = self.music_item_type

        elif audiotype == 'SonosAudioBroadcast':

            '''
            Kerrang
		    <CurrentTrackMetaData 
		    <res protocolInfo="sonos.com-http-get:*:*:*">x-sonosapi-stream:s45579?sid=254</res>
		    <r:streamContent></r:streamContent>
		    <r:radioShowMd></r:radioShowMd>
		    <upnp:albumArtURI>/getaa?s=1&u=x-sonosapi-stream%3as45579%3fsid%3d254</upnp:albumArtURI>
		    <dc:title>x-sonosapi-stream:s45579?sid=254</dc:title>
		    <upnp:class>object.item</upnp:class>

		    <r:NextTrackMetaData 
		    <res protocolInfo="rtsp:*:*:*">rtsp://earth.radica.com/kerrang-70</res>
		    <dc:title>kerrang-70</dc:title>
		    <upnp:class>object.item</upnp:class>

		    <r:EnqueuedTransportURIMetaData 
		    <dc:title>Kerrang! 105.2 (Birmingham, United Kingdom)</dc:title>
		    <upnp:class>object.item.audioItem.audioBroadcast</upnp:class>
		    <desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">SA_RINCON65031_</desc>
		
		    <AVTransportURIMetaData 
		    <dc:title>Kerrang! 105.2 (Birmingham, United Kingdom)</dc:title>
		    <upnp:class>object.item.audioItem.audioBroadcast</upnp:class>
		    <desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">SA_RINCON65031_</desc>

            BBC R1
		    <CurrentTrackMetaData
		    <item id="-1" parentID="-1" restricted="true">
            <res protocolInfo="sonos.com-http-get:*:*:*">x-sonosapi-stream:s24939?sid=254</res>
            <r:streamContent></r:streamContent>
            <r:radioShowMd>Nihal (BBC R1),p180224</r:radioShowMd>
            <upnp:albumArtURI>/getaa?s=1&u=x-sonosapi-stream%3as24939%3fsid%3d254</upnp:albumArtURI>
            <dc:title>x-sonosapi-stream:s24939?sid=254</dc:title>
            <upnp:class>object.item</upnp:class>
            </item>

		    <r:NextTrackMetaData
		    <item id="-1" parentID="-1" restricted="true">
            <res protocolInfo="rtsp:*:*:*">rtsp://wmlive-acl.bbc.co.uk/wms/bbc_ami/radio1/radio1_bb_live_eq1_sl0?BBC-UID=24da270589f6dc6a6400ecc2e1d845620833f3aa10b01134c4ff7436034ac97a&SSO2-UID=</res>
            <dc:title>radio1_bb_live_eq1_sl0?BBC-UID=24da270589f6dc6a6400ecc2e1d845620833f3aa10b01134c4ff7436034ac97a&SSO2-UID=</dc:title>
            <upnp:class>object.item</upnp:class>
            </item>

		    <r:EnqueuedTransportURIMetaData
		    <item id="-1" parentID="-1" restricted="true">
            <dc:title>BBC Radio 1 (London, United Kingdom)</dc:title>
            <upnp:class>object.item.audioItem.audioBroadcast</upnp:class>
            <desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">SA_RINCON65031_</desc>
            </item>

		    <AVTransportURIMetaData
		    <item id="-1" parentID="-1" restricted="true">
            <dc:title>BBC Radio 1 (London, United Kingdom)</dc:title>
            <upnp:class>object.item.audioItem.audioBroadcast</upnp:class>
            <desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">SA_RINCON65031_</desc>
            </item>
            '''

            # for Radio from Sonos, some info is in EnqueuedTransportURIMetaData, some is in CurrentTrackMetaData

            self.music_item_class = 'SonosAudioBroadcast'
            self.music_item_type = 'Radio'
            self.music_item_station = metadata.title

            CTmetadata = events_avt['CurrentTrackMetaData']

            self.music_item_onnow = CTmetadata.radioShowMd
            if self.music_item_onnow == None:
                self.music_item_onnow = ''
            if self.music_item_onnow != '':
                # title is followed by a comma and more info - but title can contain \,
                # e.g. 'Mickey\, Amelia and Spiegel,DATA'
                onnow = CTmetadata.radioShowMd
                onnow = re.sub(r'\\,', '\&comma;', onnow)
                onnow = re.split(',', onnow)[0]
                onnow = re.sub(r'\\&comma;', ',', onnow)
                self.music_item_onnow = onnow
            self.music_item_albumartURI = CTmetadata.albumArtURI
            self.music_item_info = CTmetadata.streamContent
            if self.music_item_info == None:
                self.music_item_info = ''

            details += 'STATION: ' + self.music_item_station + '\n'
            detailsdict['STATION'] = self.music_item_station
            details += 'ONNOW: ' + self.music_item_onnow + '\n'
            detailsdict['ONNOW'] = self.music_item_onnow
            details += 'INFO: ' + self.music_item_info + '\n'
            detailsdict['INFO'] = self.music_item_info
            extras += 'CLASS: ' + self.music_item_class + '\n'
            extrasdict['CLASS'] = self.music_item_class
            extras += 'TYPE: ' + self.music_item_type + '\n'
            extrasdict['TYPE'] = self.music_item_type

        elif audiotype == 'AudioBroadcast':

            self.music_item_class = 'AudioBroadcast'
            self.music_item_type = 'Radio'
            self.music_item_station = metadata.title

            self.music_item_onnow = metadata.radio_call_sign
            if self.music_item_onnow == None:
                self.music_item_onnow = ''
            self.music_item_albumartURI = metadata.albumArtURI
            self.music_item_info = metadata.radio_station_id

            details += 'STATION: ' + self.music_item_station + '\n'
            detailsdict['STATION'] = self.music_item_station
            details += 'ONNOW: ' + self.music_item_onnow + '\n'
            detailsdict['ONNOW'] = self.music_item_onnow
            details += 'INFO: ' + self.music_item_info + '\n'
            detailsdict['INFO'] = self.music_item_info
            extras += 'CLASS: ' + self.music_item_class + '\n'
            extrasdict['CLASS'] = self.music_item_class
            extras += 'TYPE: ' + self.music_item_type + '\n'
            extrasdict['TYPE'] = self.music_item_type

        else:
            details = 'UNKNOWN MUSIC CLASS!'
            detailsdict['UNKNOWN'] = 'UNKNOWN MUSIC CLASS!'
            extrasdict['UNKNOWN'] = 'UNKNOWN MUSIC CLASS!'

        return (details, extras, detailsdict, extrasdict, self.music_item_albumartURI)

def getAlbumArtURL(service, albumartURI):

    if albumartURI == '' or albumartURI == None or albumartURI == []:
        return ''
    else:
        art_url = urlparse(albumartURI)
        if art_url.scheme != '' and art_url.netloc != '' and art_url.path != '':
            return albumartURI
        url_info = parse_url(service.url_base)
        aa_url = "%s://%s%s" % (url_info[0], url_info[1], albumartURI)
        return aa_url

def getAlbumArtFile(service, AlbumArtURI, filename):

#    log.debug('#### GETALBUMART service: %s' % service)
#    log.debug('#### GETALBUMART AlbumArtURI: %s' % AlbumArtURI)

    if AlbumArtURI == '' or AlbumArtURI == None:
        return False
    else:
        url_info = parse_url(service.url_base)
        aa_url = "%s://%s%s" % (url_info[0], url_info[1], AlbumArtURI)
#        log.debug('#### GETALBUMART control_url: %s' % aa_url)
        fd = url_fetch(aa_url)
        try:
            data = fd.read()
        except:
            log.debug("#### GETALBUMART fd is invalid")
            data = ''

    fdout = open(filename,"w")
    fdout.write(data)
    fdout.close()

    return True











ns = {'didl': 'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/',
      'dc': 'http://purl.org/dc/elements/1.1/',
      'upnp': 'urn:schemas-upnp-org:metadata-1-0/upnp/',
      'dlna': 'urn:schemas-dlna-org:metadata-1-0',
      'rcnw' : 'urn:schemas-rinconnetworks-com:metadata-1-0/'
}

def find(elt, namespace, key):

    print "NEWFIND NEWFIND NEWFIND NEWFIND " + namespace + " " + key + " " + str(elt)

    f = elt.find('.//{%s}%s' % (ns[namespace], key))
    if f is None:
        return (None)
    return f

class SonosMusicTrackExtras(object):

#    <ns1:streamContent xmlns:ns1="urn:schemas-rinconnetworks-com:metadata-1-0/" />
#    <ns1:radioShowMd xmlns:ns1="urn:schemas-rinconnetworks-com:metadata-1-0/" />
#    <ns1:albumArtURI xmlns:ns1="urn:schemas-upnp-org:metadata-1-0/upnp/">/getaa?s=1&amp;u=x-sonos-mms%3atrack%253a23793135%3fsid%3d0</ns1:albumArtURI>
#    <ns1:album xmlns:ns1="urn:schemas-upnp-org:metadata-1-0/upnp/">Revival in Belfast</ns1:album>

    def __init__(self, streamContent='', radioShowMd='', albumArtURI='', album=''):
        self.streamContent = streamContent
        self.radioShowMd = radioShowMd
        self.albumArtURI = albumArtURI
        self.album = album

    def from_string(self, metadataString):
        self.streamContent = ''
        self.radioShowMd = ''
        self.albumArtURI = ''
        self.album = ''
        elt = parse_xml(metadataString)
        elt = elt.getroot()

        streamContent_elt = find(elt, 'rcnw', 'streamContent')
        radioShowMd_elt = find(elt, 'rcnw', 'radioShowMd')
        albumArtURI_elt = find(elt, 'upnp', 'albumArtURI')
        album_elt = find(elt, 'upnp', 'album')

#        print str(streamContent_elt)
#        print str(radioShowMd_elt)
#        print str(albumArtURI_elt)
#        print str(album_elt)

        if streamContent_elt != None:
            self.streamContent = streamContent_elt.text
        if radioShowMd_elt != None:
            self.radioShowMd = radioShowMd_elt.text
        if albumArtURI_elt != None:
            self.albumArtURI = albumArtURI_elt.text
        if album_elt != None:
            self.album = album_elt.text








'''
class Resource(object):
        @type protocol_info: string
        @type import_uri: string
        @type size: int
        @type duration: string
        @type bitrate: int
        @type sample_frequency: int
        @type bits_per_sample: int
        @type nr_audio_channels: int
        @type resolution: string
        @type color_depth: int
        @type protection: string

class Object(object):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer

class Container(Object):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list

class Item(Object):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type ref_id: string

class AudioItem(Item):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type ref_id: string
        @type genres: list
        @type description: string
        @type long_description: string
        @type publishers: list
        @type language: string
        @type relations: list
        @type rights: list
'''
def DumpMusicTrack(mt):

    '''
class MusicTrack(AudioItem):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type ref_id: string
        @type genres: list
        @type description: string
        @type long_description: string
        @type publishers: list
        @type language: string
        @type relations: list
        @type rights: list
        @type artists: list
        @type albums: list
        @type original_track_number: int
        @type playlists: list
        @type storage_medium: string
        @type contributors: list
        @type date: string
'''
    print "MUSICTRACK ******************************** START ********************************************"
    print "id                     :" + mt.id
    print "parent_id              :" + mt.parent_id
    print "title                  :" + mt.title
    print "restricted             :" + str(mt.restricted) # bool
    print "creator                :" + mt.creator
    print "write_status           :" + str(mt.write_status) # int
    print "ref_id                 :" + mt.ref_id
    print "genres                 :" + str(mt.genres) # list
    print "description            :" + mt.description
    print "long_description       :" + mt.long_description
    print "publishers             :" + str(mt.publishers) # list
    print "language               :" + mt.language
    print "relations              :" + str(mt.relations) # list
    print "rights                 :" + str(mt.rights) # list
    print "artists                :" + str(mt.artists) # list
    print "albums                 :" + str(mt.albums) # list
    print "original_track_number  :" + str(mt.original_track_number) # int
    print "playlists              :" + str(mt.playlists) # list
    print "storage_medium         :" + mt.storage_medium
    print "contributors           :" + str(mt.contributors) # list
    print "date                   :" + mt.date
    print "MUSICTRACK ********************************* END *********************************************"

'''
class AudioBroadcast(AudioItem):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type ref_id: string
        @type genres: list
        @type description: string
        @type long_description: string
        @type publishers: list
        @type language: string
        @type relations: list
        @type rights: list
        @type region: string
        @type radio_call_sign: string
        @type radio_station_id: string
        @type radio_band: string
        @type channel_nr: int

class PlaylistItem(Item):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type ref_id: string
        @type authors: list
        @type protection: string
        @type long_description: string
        @type storage_medium: string
        @type rating: string
        @type description: string
        @type publishers: list
        @type contributors: list
        @type date: string
        @type relations: list
        @type languages: list
        @type rights: list

class Album(Container):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type storage_medium: string
        @type long_description: string
        @type description: string
        @type publishers: list
        @type contributors: list
        @type date: string
        @type relations: list
        @type rights: list

class MusicAlbum(Album):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type storage_medium: string
        @type long_description: string
        @type description: string
        @type publishers: list
        @type contributors: list
        @type date: string
        @type relations: list
        @type rights: list
        @type artists: list
        @type genres: list
        @type producers: list
        @type album_art_uri: string
        @type toc: string

class Genre(Container):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list

class PlaylistContainer(Container):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type artists: list
        @type genres: list
        @type long_description: string
        @type producers: list
        @type storage_medium: string
        @type description: string
        @type contributors: list
        @type date: string
        @type languages: list
        @type rights: list

class Person(Container):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type languages: list

class MusicArtist(Person):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type languages: list
        @type genres: list
        @type artist_discography_uri: string

class StorageSystem(Container):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type storage_total: signed long
        @type storage_used: signed long
        @type storage_free: signed long
        @type storage_max_partition: signed long
        @type storage_medium: string

class StorageVolume(Container):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type storage_total: signed long
        @type storage_used: signed long
        @type storage_free: signed long
        @type storage_medium: string

class StorageFolder(Container):
        @type id: string
        @type parent_id: string
        @type title: string
        @type restricted: bool
        @type creator: string
        @type write_status: integer
        @type searchable: bool
        @type search_classes: list
        @type create_classes: list
        @type storage_used: signed long
'''

