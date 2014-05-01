import urllib2
import urllib
import time
from brisa.core import log

def post_customsd(zpip, sid, servicename, localip, localport, proxyuuid):

    # update presentation map version
    filename = 'pm.ver'
    try:
        with open(filename, 'r+') as f:
            ver = f.read().strip()
            if ver == '':
                ver = 1
            else:
                ver = int(ver) + 1
            f.seek(0)
            f.write(str(ver))
    except IOError:
        with open(filename, 'w+') as f:
            ver = 1
            f.write(str(ver))

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

    # pause
    time.sleep(1)

    # add service
    if servicename != None:
        args = {'sid': '%s' % sid, 
                'name': servicename,
                'uri': 'http://%s:%s/smapi/control' % (localip, localport),
                'secureUri': 'http://%s:%s/smapi/control' % (localip, localport),
                'pollInterval': '30',
                'authType': 'Anonymous',
#                'stringsVersion': '0',
#                'stringsUri': 'file:///home/mark/sonospy/sonospy/strings.xml',
                'presentationMapVersion': '%s' % ver,
                'presentationMapUri': 'http://%s:%s/%s.xml' % (localip, localport, proxyuuid),
                'containerType': 'MService',
#                'caps': ['search', 'trFavorites', 'alFavorites', 'arFavorites', 'extendedMD', 'ucPlaylists']}
                'caps': ['search', 'trFavorites', 'alFavorites', 'arFavorites', 'ucPlaylists']}
        data = urllib.urlencode(args, doseq=True)
        log.debug(data)
        request = urllib2.Request(url, data)
        response = urllib2.urlopen(request)
        html = response.read()
        log.debug(html)


