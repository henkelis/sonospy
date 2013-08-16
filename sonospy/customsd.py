import urllib2
import urllib
from brisa.core import log

def post_customsd(zpip, sid, servicename, localip, localport):

    url = 'http://%s:1400/customsd' % zpip

    # remove service
    args = {'sid': '%s' % sid, 
            'name': ''}
    data = urllib.urlencode(args)
    log.debug(data)
    request = urllib2.Request(url, data)
    response = urllib2.urlopen(request)
    html = response.read()
    log.debug(html)

    # add service
    if servicename != None:
        args = {'sid': '%s' % sid, 
                'name': servicename,
                'uri': 'http://%s:%s/smapi/control' % (localip, localport),
                'secureUri': 'http://%s:%s/smapi/control' % (localip, localport),
                'pollInterval': '30',
                'authType': 'Anonymous',
                'stringsVersion': '0',
                'stringsUri': '',
                'presentationMapVersion': '0',
                'presentationMapUri': '',
                'containerType': 'MService',
                'caps': 'search'}
#                'caps': 'ucPlaylists'}
        data = urllib.urlencode(args)
        log.debug(data)
        request = urllib2.Request(url, data)
        response = urllib2.urlopen(request)
        html = response.read()
        log.debug(html)


