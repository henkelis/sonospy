import urllib2
import urllib
import time
from brisa.core import log
from HTMLParser import HTMLParser

csrftoken = None

class MyHTMLParser(HTMLParser):
    def handle_starttag(self, tag, attrs):
        global csrftoken
        if tag.lower() == 'input':
            hidden = False
            csrf = False
            token = None
            for attr, value in attrs:
#                print "     %s = %s" % (attr, value)
                if attr.lower() == 'type' and value.lower() == 'hidden':
                    hidden = True
                if attr.lower() == 'name' and value.lower() == 'csrftoken':
                    csrf = True
                if attr.lower() == 'value':
                    token = value
            if hidden and csrf and token != None:
                csrftoken = token
#                print "Encountered a hidden input tag:", csrftoken

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

    # remove existing service
    args = {'sid': '%s' % sid, 
            'name': ''}
    log.debug('customsd call args: %s', args)
    success, response = call_sonos(url, args)
    print 'customsd call return: %s,  args: %s' % (success, args)
    log.debug(response)
    if not success:
        return False

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
        log.debug('customsd call args: %s', args)
        success, response = call_sonos(url, args)
        print 'customsd call return: %s,  args: %s' % (success, args)
        log.debug(response)
        
    return success

def call_sonos(url, args):
    #print url
    try:
    
        handle = urllib2.urlopen(url)
        response = handle.read()
        log.debug('customsd response 1: %s', response)
#        print response

        parser = MyHTMLParser()
        parser.feed(response)

        log.debug('customsd csrftoken: %s', csrftoken)
        if csrftoken != None:
#            print csrftoken
            args['csrfToken'] = csrftoken
            
        data = urllib.urlencode(args, doseq=True)
        
        handle = urllib2.urlopen(url, data, 5)
        response = handle.read()
    except IOError, e:
        if hasattr(e, 'code'):
            log.error('The server couldn\'t fulfil the request. Error code: %s, Reason: %s' % (e.code, e.reason))
            print 'The server couldn\'t fulfil the request. Error code: %s, Reason: %s' % (e.code, e.reason)
        elif hasattr(e, 'reason'):
            log.error('Failed to reach server. Reason: %s'% (e.reason))
            print 'Failed to reach server. Reason: %s'% (e.reason)
        return False, e
        
    log.debug('customsd return: %s', response)
#    print 'customsd return: %s', response
    return True, response
