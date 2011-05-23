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



from xml.etree.ElementTree import _ElementInterface
from xml.etree import cElementTree as ElementTree

from brisa.core import log
from brisa.core.network import parse_xml

from brisa.upnp.didl import dlna

from xml.dom import minidom
from xml.dom.minidom import parseString


########################################################
# TEST

from brisa.upnp.device.service import Service

service_name = 'MyService'
service_type = 'urn:schemas-upnp-org:service:MyService:1'

class MyService(Service):

    def __init__(self):
        Service.__init__(self, service_name, service_type, url_base='', scpd_xml_filepath='MyService-scpd.xml')

    def soap_MyMethod(self, *args, **kwargs):
        inArg = kwargs['TextIn']
        return {'TextOut': inArg + "Out!!"}
        
########################################################

class AvailableServices(_ElementInterface):
    """
    """

    def __init__(self):
#        print "!!!!!!!!!!!!!!!!!!!!! AvailableServices __init__"
        _ElementInterface.__init__(self, 'Services', {})
#        self.attrib['xmlns'] = 'urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/'
#        self.attrib['xmlns:dc'] = 'http://purl.org/dc/elements/1.1/'
#        self.attrib['xmlns:upnp'] = 'urn:schemas-upnp-org:metadata-1-0/upnp/'
#        self.attrib['xmlns:dlna'] = 'urn:schemas-dlna-org:metadata-1-0'
#        self.attrib['xmlns:r'] = 'urn:schemas-rinconnetworks-com:metadata-1-0/'
        self._items = []

    def add_item(self, item):
#        self.append(item.to_didl_element())
        self._items.append(item)

    def num_items(self):
        return len(self)

    def get_items(self):
        return self._items

    def to_string(self):
        return ElementTree.tostring(self)

    def from_string(self, aString):
#        print aString
        elt = parse_xml(aString)
        elt = elt.getroot()
#        print "!!!!!!!!!!!!!!!!!!!!! AvailableServices from_string root - " + str(elt)
        for node in elt.getchildren():
#            print "!!!!!!!!!!!!!!!!!!!!! AvailableServices from_string child - " + str(node)
#            print "!!!!!!!!!!!!!!!!!!!!! AvailableServices from_string child - " + minidom.parseString(ElementTree.tostring(node)).toprettyxml()
            new_node = SonosService()
            new_node.from_element(node)
            self.add_item(new_node)

        return self
          
            
class SonosService(object):
    """
    """
    element_name = 'Service'

    def __init__(self, Capabilities= '', Id='', MaxMessagingChars='', Name='', SecureUri='', Uri='', Version='',
                 Policy_Auth='', Policy_PollInterval='',
                 Presentation_Strings_Uri='', Presentation_Strings_Version='',
                 Presentation_Logos_Large='', Presentation_Logos_Small='',
                 ):
        '''
		<Service Capabilities="31" Id="0" MaxMessagingChars="0" Name="Napster" SecureUri="https://api.napster.com/device/soap/v1" Uri="http://api.napster.com/device/soap/v1" Version="1.0">
			<Policy Auth="UserId" PollInterval="30"/>
			<Presentation>
				<Strings Uri="http://update-services.sonos.com/services/napster/string.xml" Version="1"/>
				<Logos Large="http://www.napster.com/services/Sonos/LargeLogo.png" Small="http://www.napster.com/services/Sonos/SmallLogo.png"/>
			</Presentation>
		</Service>
        '''
        self.Capabilities = Capabilities
        self.Id = Id
        self.MaxMessagingChars = MaxMessagingChars
        self.Name = Name
        self.SecureUri = SecureUri
        self.Uri = Uri
        self.Version = Version

        self.Policy_Auth = Policy_Auth
        self.Policy_PollInterval = Policy_PollInterval

        self.Presentation_Strings_Uri = Presentation_Strings_Uri
        self.Presentation_Strings_Version = Presentation_Strings_Version
        self.Presentation_Logos_Large = Presentation_Logos_Large
        self.Presentation_Logos_Small = Presentation_Logos_Small


    def from_element(self, elt):
        """ Sets the object properties from an element.
        """
        self.element_name = elt.tag

        Capabilities_attrib = elt.get('Capabilities')
        if Capabilities_attrib is not None:
            self.Capabilities = Capabilities_attrib
        Id_attrib = elt.get('Id')
        if Id_attrib is not None:
            self.Id = Id_attrib
        MaxMessagingChars_attrib = elt.get('MaxMessagingChars')
        if MaxMessagingChars_attrib is not None:
            self.MaxMessagingChars = MaxMessagingChars_attrib
        Name_attrib = elt.get('Name')
        if Name_attrib is not None:
            self.Name = Name_attrib
        SecureUri_attrib = elt.get('SecureUri')
        if SecureUri_attrib is not None:
            self.SecureUri = SecureUri_attrib
        Uri_attrib = elt.get('Uri')
        if Uri_attrib is not None:
            self.Uri = Uri_attrib
        Version_attrib = elt.get('Version')
        if Version_attrib is not None:
            self.Version = Version_attrib

        Policy_elt = elt.find('Policy')
        if Policy_elt is not None:
            Policy_Auth_attrib = Policy_elt.get('Auth')
            if Policy_Auth_attrib is not None:
                self.Policy_Auth = Policy_Auth_attrib
            Policy_PollInterval_attrib = Policy_elt.get('PollInterval')
            if Policy_PollInterval_attrib is not None:
                self.Policy_PollInterval = Policy_PollInterval_attrib

        Presentation_elt = elt.find('Presentation')
        if Presentation_elt is not None:
            Strings_elt = Presentation_elt.find('Strings')
            if Strings_elt is not None:
                Presentation_Strings_Uri_attrib = Strings_elt.get('Uri')
                if Presentation_Strings_Uri_attrib is not None:
                    self.Presentation_Strings_Uri = Presentation_Strings_Uri_attrib
                Presentation_Strings_Version_attrib = Strings_elt.get('Version')
                if Presentation_Strings_Version_attrib is not None:
                    self.Presentation_Strings_Version = Presentation_Strings_Version_attrib
            Logos_elt = Presentation_elt.find('Logos')
            if Logos_elt is not None:
                Presentation_Logos_Large_attrib = Logos_elt.get('Large')
                if Presentation_Logos_Large_attrib is not None:
                    self.Presentation_Logos_Large = Presentation_Logos_Large_attrib
                Presentation_Logos_Small_attrib = Logos_elt.get('Small')
                if Presentation_Logos_Small_attrib is not None:
                    self.Presentation_Logos_Small = Presentation_Logos_Small_attrib

        '''
        print "Capabilities: " + self.Capabilities
        print "Id: " + self.Id
        print "MaxMessagingChars: " + self.MaxMessagingChars 
        print "Name: " + self.Name
        print "SecureUri: " + self.SecureUri
        print "Uri: " + self.Uri
        print "Version: " + self.Version
        print "Policy_Auth: " + self.Policy_Auth
        print "Policy_PollInterval: " + self.Policy_PollInterval
        print "Presentation_Strings_Uri: " + self.Presentation_Strings_Uri
        print "Presentation_Strings_Version: " + self.Presentation_Strings_Version
        print "Presentation_Logos_Large: " + self.Presentation_Logos_Large
        print "Presentation_Logos_Small: " + self.Presentation_Logos_Small
        '''
        
        '''
		<Service Capabilities="31" Id="0" MaxMessagingChars="0" Name="Napster" SecureUri="https://api.napster.com/device/soap/v1" Uri="http://api.napster.com/device/soap/v1" Version="1.0">
			<Policy Auth="UserId" PollInterval="30"/>
			<Presentation>
				<Strings Uri="http://update-services.sonos.com/services/napster/string.xml" Version="1"/>
				<Logos Large="http://www.napster.com/services/Sonos/LargeLogo.png" Small="http://www.napster.com/services/Sonos/SmallLogo.png"/>
			</Presentation>
		</Service>
        '''

        return self


    @classmethod
    def from_string(cls, xml_string):
        """ Returns an instance generated from a xml string.
        """
        
        # TODO: either fix this or remove it
        
#        print "!!!!!!!!!!!!!!!!!!!! Object from_string"
#        print cls
#        print xml_string
        
        instance = cls()
        elt = parse_xml(xml_string)
        instance.from_element(elt.getroot())
        return instance

    def to_didl_element(self):
        """ Returns an Element based on this Resource.
        """
        
        # TODO: either fix this or remove it
        
        root = ElementTree.Element(self.element_name)
        root.attrib['id'] = str(self.id)
        root.attrib['parentID'] = str(self.parent_id)
        ElementTree.SubElement(root, 'dc:title').text = self.title
        ElementTree.SubElement(root, 'upnp:class').text = self.upnp_class

        if self.restricted:
            root.attrib['restricted'] = 'true'
        else:
            root.attrib['restricted'] = 'false'

        if self.creator:
            ElementTree.SubElement(root, 'dc:creator').text = self.creator
        if self.write_status:
            ElementTree.SubElement(root, 'upnp:writeStatus').text = \
                self.write_status

        for r in self.resources:
            root.append(r.to_didl_element())

        return root

    def to_string(self):
        """ String representation of this object.
        """
        return ElementTree.tostring(self.to_didl_element())


class radiotimeMediaCollection(object):
    """
    """
    element_name = 'mediaCollection'

    def __init__(self, id='', title='', itemType='', authRequired='', canPlay='', canEnumerate='',
                 canCache='', homogeneous='', canAddToFavorite='', canScroll=''):
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
        '''
        self.id = id
        self.title = title
        self.itemType = itemType
        self.authRequired = authRequired
        self.canPlay = canPlay
        self.canEnumerate = canEnumerate
        self.canCache = canCache
        self.homogeneous = homogeneous
        self.canAddToFavorite = canAddToFavorite
        self.canScroll = canScroll


    def from_element(self, elt):
        """ Sets the object properties from an element.
        """
        self.element_name = elt.tag

        id = elt.find('{http://www.sonos.com/Services/1.1}id')
        if id is not None:
            self.id = id.text
        title = elt.find('{http://www.sonos.com/Services/1.1}title')
        if title is not None:
            self.title = title.text
        itemType = elt.find('{http://www.sonos.com/Services/1.1}itemType')
        if itemType is not None:
            self.itemType = itemType.text
        authRequired = elt.find('{http://www.sonos.com/Services/1.1}authRequired')
        if authRequired is not None:
            self.authRequired = authRequired.text
        canPlay = elt.find('{http://www.sonos.com/Services/1.1}canPlay')
        if canPlay is not None:
            self.canPlay = canPlay.text
        canEnumerate = elt.find('{http://www.sonos.com/Services/1.1}canEnumerate')
        if canEnumerate is not None:
            self.canEnumerate = canEnumerate.text
        canCache = elt.find('{http://www.sonos.com/Services/1.1}canCache')
        if canCache is not None:
            self.canCache = canCache.text
        homogeneous = elt.find('{http://www.sonos.com/Services/1.1}homogeneous')
        if homogeneous is not None:
            self.homogeneous = homogeneous.text
        canAddToFavorite = elt.find('{http://www.sonos.com/Services/1.1}canAddToFavorite')
        if canAddToFavorite is not None:
            self.canAddToFavorite = canAddToFavorite.text
        canScroll = elt.find('{http://www.sonos.com/Services/1.1}canScroll')
        if canScroll is not None:
            self.canScroll = canScroll.text

        '''
        print "id: " + self.id
        print "title: " + self.title
        print "itemType: " + self.itemType
        print "authRequired: " + self.authRequired
        print "canPlay: " + self.canPlay
        print "canEnumerate: " + self.canEnumerate
        print "canCache: " + self.canCache
        print "homogeneous: " + self.homogeneous
        print "canAddToFavorite: " + self.canAddToFavorite
        print "canScroll: " + self.canScroll
        '''
        
        return self


    @classmethod
    def from_string(cls, xml_string):
        """ Returns an instance generated from a xml string.
        """
        
        # TODO: either fix this or remove it
        
#        print "!!!!!!!!!!!!!!!!!!!! Object from_string"
#        print cls
#        print xml_string
        
        instance = cls()
        elt = parse_xml(xml_string)
        instance.from_element(elt.getroot())
        return instance

    def to_didl_element(self):
        """ Returns an Element based on this Resource.
        """
        
        # TODO: either fix this or remove it
        
        root = ElementTree.Element(self.element_name)
        root.attrib['id'] = str(self.id)
        root.attrib['parentID'] = str(self.parent_id)
        ElementTree.SubElement(root, 'dc:title').text = self.title
        ElementTree.SubElement(root, 'upnp:class').text = self.upnp_class

        if self.restricted:
            root.attrib['restricted'] = 'true'
        else:
            root.attrib['restricted'] = 'false'

        if self.creator:
            ElementTree.SubElement(root, 'dc:creator').text = self.creator
        if self.write_status:
            ElementTree.SubElement(root, 'upnp:writeStatus').text = \
                self.write_status

        for r in self.resources:
            root.append(r.to_didl_element())

        return root

    def to_string(self):
        """ String representation of this object.
        """
        return ElementTree.tostring(self.to_didl_element())


class radiotimeMediaMetadata(object):
    """
    """
    element_name = 'mediaMetadata'

    def __init__(self, id='', title='', itemType='', language='', country='', genreId='',
                 genre='', twitterId='', liveNow='', onDemand='',
                 stream_bitrate='', stream_reliability='', stream_logo='', stream_title='',
                 stream_subtitle='', stream_secondsRemaining='', stream_secondsToNextShow='', stream_nextShowSeconds=''
                 ):
        '''
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
        '''
        self.id = id
        self.title = title
        self.itemType = itemType
        self.language=language
        self.country=country
        self.genreId=genreId
        self.genre=genre
        self.twitterId=twitterId
        self.liveNow=liveNow
        self.onDemand=onDemand
        self.stream_bitrate=stream_bitrate
        self.stream_reliability=stream_reliability
        self.stream_logo=stream_logo
        self.stream_title=stream_title
        self.stream_subtitle=stream_subtitle
        self.stream_secondsRemaining=stream_secondsRemaining
        self.stream_secondsToNextShow=stream_secondsToNextShow
        self.stream_nextShowSeconds=stream_nextShowSeconds


    def from_element(self, elt):
        """ Sets the object properties from an element.
        """
        self.element_name = elt.tag
        
#        print elt
#        print elt.tag        

        id = elt.find('{http://www.sonos.com/Services/1.1}id')
        if id is not None:
            self.id = id.text
        title = elt.find('{http://www.sonos.com/Services/1.1}title')
        if title is not None:
            self.title = title.text
        itemType = elt.find('{http://www.sonos.com/Services/1.1}itemType')
        if itemType is not None:
            self.itemType = itemType.text
        language = elt.find('language')
        if language is not None:
            self.language = language.text
        country = elt.find('{http://www.sonos.com/Services/1.1}country')
        if country is not None:
            self.country = country.text
        genreId = elt.find('{http://www.sonos.com/Services/1.1}genreId')
        if genreId is not None:
            self.genreId = genreId.text
        genre = elt.find('{http://www.sonos.com/Services/1.1}genre')
        if genre is not None:
            self.genre = genre.text
        twitterId = elt.find('{http://www.sonos.com/Services/1.1}twitterId')
        if twitterId is not None:
            self.twitterId = twitterId.text
        liveNow = elt.find('{http://www.sonos.com/Services/1.1}liveNow')
        if liveNow is not None:
            self.liveNow = liveNow.text
        onDemand = elt.find('{http://www.sonos.com/Services/1.1}onDemand')
        if onDemand is not None:
            self.onDemand = onDemand.text

        streamMetadata_elt = elt.find('{http://www.sonos.com/Services/1.1}streamMetadata')
        if streamMetadata_elt is not None:
            stream_bitrate = streamMetadata_elt.find('{http://www.sonos.com/Services/1.1}bitrate')
            if stream_bitrate is not None:
                self.stream_bitrate = stream_bitrate.text
            stream_reliability = streamMetadata_elt.find('{http://www.sonos.com/Services/1.1}reliability')
            if stream_reliability is not None:
                self.stream_reliability = stream_reliability.text
            stream_logo = streamMetadata_elt.find('{http://www.sonos.com/Services/1.1}logo')
            if stream_logo is not None:
                self.stream_logo = stream_logo.text
            stream_title = streamMetadata_elt.find('{http://www.sonos.com/Services/1.1}title')
            if stream_title is not None:
                self.stream_title = stream_title.text
            stream_subtitle = streamMetadata_elt.find('{http://www.sonos.com/Services/1.1}subtitle')
            if stream_subtitle is not None:
                self.stream_subtitle = stream_subtitle.text
            stream_secondsRemaining = streamMetadata_elt.find('{http://www.sonos.com/Services/1.1}secondsRemaining')
            if stream_secondsRemaining is not None:
                self.stream_secondsRemaining = stream_secondsRemaining.text
            stream_secondsToNextShow = streamMetadata_elt.find('{http://www.sonos.com/Services/1.1}secondsToNextShow')
            if stream_secondsToNextShow is not None:
                self.stream_secondsToNextShow = stream_secondsToNextShow.text
            stream_nextShowSeconds = streamMetadata_elt.find('{http://www.sonos.com/Services/1.1}nextShowSeconds')
            if stream_nextShowSeconds is not None:
                self.stream_nextShowSeconds = stream_nextShowSeconds.text

        '''
        print "id: " + str(self.id)
        print "title: " + str(self.title)
        print "itemType: " + str(self.itemType)
        print "language: " + str(self.language)
        print "country: " + str(self.country)
        print "genreId: " + str(self.genreId)
        print "genre: " + str(self.genre)
        print "twitterId: " + str(self.twitterId)
        print "liveNow: " + str(self.liveNow)
        print "onDemand: " + str(self.onDemand)

        print "stream_bitrate: " + str(self.stream_bitrate)
        print "stream_reliability: " + str(self.stream_reliability)
        print "stream_logo: " + str(self.stream_logo)
        print "stream_title: " + str(self.stream_title)
        print "stream_subtitle: " + str(self.stream_subtitle)
        print "stream_secondsRemaining: " + str(self.stream_secondsRemaining)
        print "stream_secondsToNextShow: " + str(self.stream_secondsToNextShow)
        print "stream_nextShowSeconds: " + str(self.stream_nextShowSeconds)
        '''
        
        return self


    @classmethod
    def from_string(cls, xml_string):
        """ Returns an instance generated from a xml string.
        """
        
        # TODO: either fix this or remove it
        
#        print "!!!!!!!!!!!!!!!!!!!! Object from_string"
#        print cls
#        print xml_string
        
        instance = cls()
        elt = parse_xml(xml_string)
        instance.from_element(elt.getroot())
        return instance

    def to_didl_element(self):
        """ Returns an Element based on this Resource.
        """
        
        # TODO: either fix this or remove it
        
        root = ElementTree.Element(self.element_name)
        root.attrib['id'] = str(self.id)
        root.attrib['parentID'] = str(self.parent_id)
        ElementTree.SubElement(root, 'dc:title').text = self.title
        ElementTree.SubElement(root, 'upnp:class').text = self.upnp_class

        if self.restricted:
            root.attrib['restricted'] = 'true'
        else:
            root.attrib['restricted'] = 'false'

        if self.creator:
            ElementTree.SubElement(root, 'dc:creator').text = self.creator
        if self.write_status:
            ElementTree.SubElement(root, 'upnp:writeStatus').text = \
                self.write_status

        for r in self.resources:
            root.append(r.to_didl_element())

        return root

    def to_string(self):
        """ String representation of this object.
        """
        return ElementTree.tostring(self.to_didl_element())



			

            
