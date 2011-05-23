# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Network related functions, such as get_ip_address(), http_call(),
parse_url() and others.
"""

import os
import re
import urllib2
import httplib
import shutil
import socket
if os.name != 'nt':
    import fcntl
from time import time, sleep
from struct import pack
from urlparse import urlparse
from xml.etree import ElementTree

import brisa
from brisa.core import log

socket.setdefaulttimeout(15)


def get_ip_address(ifname):
    """ Determine the IP address given the interface name

    http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/439094
    (c) Paul Cannon
    Uses the Linux SIOCGIFADDR ioctl to find the IP address associated
    with a network interface, given the name of that interface, e.g. "eth0".
    The address is returned as a string containing a dotted quad.

    @param ifname: interface name
    @type ifname: string

    @return: ip address in the interface specified
    @rtype: string
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        ip = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915,
                                          pack('256s',
                                          str(ifname[:15])))[20:24])
        return ip
    except:
        return socket.gethostbyname(socket.gethostname())


def get_active_ifaces():
    """ Return a list of the active network interfaces

    Default route of /proc/net/route has the destination field set to 00000000


    @return: active network interfaces
    @rtype: list
    """
    if os.name == 'nt':
        return [socket.gethostbyname(socket.gethostname())]
    else:
        try:
            rd = open('/proc/net/route').readlines()
        except (IOError, OSError):
            return [socket.gethostbyname(socket.gethostname())]
        net = [line.split('\t')[0:2] for line in rd]
        return [v[0] for v in net if v[1] == '00000000']    

def http_call(method, url, body='', headers={}):
    """ Returns a HTTPResponse object for the given call.

    @param method: HTTP method (NOTIFY, POST, etc...)
    @param url: receiver URL
    @param body: body of the message
    @param headers: additional headers

    @type method: string
    @type url: string
    @type body: string
    @type headers: dictionary
    """
    parsed_url = urlparse(url)
    u = parsed_url[1]

    (host, ip, port) = ('', '', 80)

    if ':' in u:
        # host:port
        u = u.split(':')

        host = u[0]
        if len(u) == 2:
            port = int(u[1])

    if host:
        ip = socket.gethostbyname(host)
    else:
        log.debug('error: host is empty')

    log.debug('http call (host, port, ip): (%s, %d, %s)' % \
              (host, port, str(ip)))

    real_path = parsed_url.path
    if parsed_url.query:
        real_path += '?' + parsed_url.query

    con = httplib.HTTPConnection("%s:%d" % (ip, port))
    con.connect()

    log.debug('con: %s, method: %s, real_path: %s, body: %s, headers: %s', con, method, real_path, body, headers)

#    print "@@@@@@@@@@ method: " + str(method)

    if body or headers:
    
#        print "??????? headers: " + str(headers)
#        print "??????? body: " + str(body)
    
        con.request(method, real_path, body=body, headers=headers)
    else:
        return None

#    return con.getresponse()
    cr = con.getresponse()
#    log.debug("cr: %s, %s, %s", cr.msg, cr.reason, cr.status)
    return cr
    
    
    
    

def url_fetch(url, filename='', attempts=0, interval=0, silent=False):
    """ Fetches an URL into a file or returns a file descriptor. If attempts
    and interval are not specified, they get their values from
    brisa.url_fetch_attempts and brisa.url_fetch_attempts_interval.

    @param url: URL to be fetched
    @param filename: if specified fetch result gets written on this path
    @param attempts: number of attempts
    @param interval: interval between attempts in seconds#
    @param silent: silently ignore exception and return none

    @type url: string
    @type filename: string
    @type attempts: integer
    @type interval: float
    """
    if not attempts:
        attempts = brisa.url_fetch_attempts
    if not interval:
        interval = brisa.url_fetch_attempts_interval

    handle = None
    last_exception = None
    for k in range(attempts):
        log.debug('Fetching %r (attempt %d)' % (url, k))
        req = urllib2.Request(url)
        try:
            handle = urllib2.urlopen(req)
        except IOError, e:
            if hasattr(e, 'reason'):
                log.warning('Attempt %d: failed to reach a server. Reason: %s'%
                            (k, e.reason))
            elif hasattr(e, 'code'):
                log.warning('Attempt %d: the server couldn\'t fulfill the '\
                            'request. Error code: %s' % (k, e.code))
            handle = None
            last_exception = e
        finally:
            if handle != None:
                if not filename:
                    # Return mode
                    log.debug('url %r fetched successfully' % url)
                    return handle
                else:
                    log.debug('writing data to filename %s' % filename)
                    # Writing mode
                    shutil.copyfile(handle, open(filename, 'w'))
                    return None
            sleep(interval)
    if silent:
        return None
    if last_exception:
#        log.error('last_exception on %s' % url)
        print 'last_exception on ' + str(url)

        import traceback        
        traceback.print_stack()

        raise last_exception
    else:
        return None


def decode(text):
    """ Converts an arbitrary string to byte string in UTF-8. On failure
    returns the given string.

    @param text: string to be converted
    @type text: string
    """

    if type(text) is unicode:
        return text.encode("utf-8")

    # new code to replace errored code below
    else:
        # assume the text is already utf-8
        return text

    # the code below will not work - the for loop will only ever execute the first time

    encoding_lst = [("iso-8859-15", ), ("utf-8", ), ("latin-1", ),
                    ("utf-8", "replace")]
    for encoding in encoding_lst:
        try:
            return text.decode(*encoding).encode("utf-8")
        except:
            return text


def parse_xml(data):
    """ Parses XML data into an ElementTree.

    @param data: raw XML data
    @type data: string

    @rtype: ElementTree
    """
    p = ElementTree.XMLParser()

    p.feed(decode(data))
    
    return ElementTree.ElementTree(p.close())


def parse_http_response(data):
    """ Parses HTTP response data into a tuple in the form (cmd, headers).

    @param data: HTTP response data
    @type data: string

    @return: (cmd, headers) for the given data
    @rtype: tuple
    """
    
#    print "data: " + str(data)
    
    header, payload = data.split('\r\n\r\n')
    lines = header.split('\r\n')
    cmd = lines[0].split(' ')
    lines = map(lambda x: x.replace(': ', ':', 1), lines[1:])
    lines = filter(lambda x: len(x) > 0, lines)
    headers = [x.split(':', 1) for x in lines]
    headers = dict(map(lambda x: (x[0].lower(), x[1]), headers))

    return cmd, headers


def parse_url(url):
    """ Parse a URL into 6 components.

    @param url: scheme://netloc/path;params?query#fragment
    @type url: string

    @return: a 6-tuple: (scheme, netloc, path, params, query, fragment). Note
    that we don't break the components up in smaller bits (e.g. netloc is a
    single string) and we don't expand % escapes.
    @rtype: tuple
    """
    return urlparse(url)
