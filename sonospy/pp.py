from brisa.core.network import parse_xml

from xml.etree.ElementTree import _ElementInterface
from xml.etree.ElementTree import dump as dd

from xml.etree import cElementTree as ElementTree

import xml.dom
from xml.dom import minidom
from xml.dom.minidom import parseString



unescape_entities = {'&quot;' : '"', '&apos;' : "'", '%20' : " ", '&amp;' : "&"}

def dump(nodedict):
    for k in nodedict:
        print "Node: " + str(k)
        print_node(nodedict[k])

def print_node(xml_string):
    elt = parse_xml(xml_string)
    elt = elt.getroot()
    for e in elt.findall('*'):
        tag = e.tag
        val = e.get('val')
        if val == None: val = ''
        print "%s : %s" % (tag, val)
        for child in e.findall('*'):
            nodename = child.tag
            val = child.get('val')
            print str(nodename) + " = " + str(val)
            # check for metadata associated with tag
            if nodename.endswith('MetaData'):
                if val != '' and val != 'NOT_IMPLEMENTED':
                    if val.endswith('</DIDL-Lite>'):
                        eitem = print_node(val)
                        if eitem:
                            for child in eitem.findall('*'):
                                nodename = child.tag
                                val = child.get('val')
                                print str(nodename) + " = " + str(val)


def remove_namespace(doc, ns):
    """Remove namespace in the passed document in place."""
    nsl = len(ns)
    for elem in doc.getiterator():
        if elem.tag.startswith(ns):
            elem.tag = elem.tag[nsl:]








s = {'LastChange': '<Event xmlns="urn:schemas-upnp-org:metadata-1-0/AVT/" xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/"><InstanceID val="0"><TransportState val="STOPPED"/><CurrentPlayMode val="NORMAL"/><CurrentCrossfadeMode val="0"/><NumberOfTracks val="0"/><CurrentTrack val="0"/><CurrentSection val="0"/><CurrentTrackURI val=""/><CurrentTrackDuration val="0:00:00"/><CurrentTrackMetaData val=""/><r:NextTrackURI val=""/><r:NextTrackMetaData val=""/><r:EnqueuedTransportURI val=""/><r:EnqueuedTransportURIMetaData val=""/><PlaybackStorageMedium val="NETWORK"/><AVTransportURI val="lastfm://artist/Bruce%20Springsteen%20%26%20The%20E%20Street%20Band/similarartists"/><AVTransportURIMetaData val="&lt;DIDL-Lite xmlns:dc=&quot;http://purl.org/dc/elements/1.1/&quot; xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot; xmlns:r=&quot;urn:schemas-rinconnetworks-com:metadata-1-0/&quot; xmlns=&quot;urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/&quot;&gt;&lt;item id=&quot;RP:SA_RINCON11_henkelis:0:LFM%3aARTIST%3aBruce%2520Springsteen%2520%2526%2520The%2520E%2520Street%2520Band&quot; parentID=&quot;RECENT&quot; restricted=&quot;true&quot;&gt;&lt;dc:title&gt;Bruce Springsteen &amp;amp; The E Street Band Similar Artists&lt;/dc:title&gt;&lt;upnp:class&gt;object.item.audioItem.audioBroadcast&lt;/upnp:class&gt;&lt;desc id=&quot;cdudn&quot; nameSpace=&quot;urn:schemas-rinconnetworks-com:metadata-1-0/&quot;&gt;SA_RINCON11_henkelis&lt;/desc&gt;&lt;/item&gt;&lt;/DIDL-Lite&gt;"/><CurrentTransportActions val="Play, Stop, Pause, Next"/></InstanceID></Event>'}
dump(s)

