#
# napster
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

import os
import re
import time

import urllib
import exceptions

from xml.etree.ElementTree import ElementTree

from brisa.core.network import parse_xml
from brisa.core import log


class napster(object):

    soapns = '{http://schemas.xmlsoap.org/soap/envelope/}'

    envelopeformat     = '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">%s%s</s:Envelope>'
    headerformat       = '<s:Header>%s</s:Header>'
    bodyformat         = '<s:Body>%s</s:Body>'

    base_headers = {}
    base_headers["CONNECTION"]       = 'close'
    base_headers["ACCEPT-ENCODING"]  = 'gzip'
    base_headers["HOST"]             = 'api.napster.com'
    base_headers["USER-AGENT"]       = 'Linux UPnP/1.0 Sonos/12.3-22140'
    base_headers["CONTENT-TYPE"]     = 'text/xml; charset="utf-8"'
#    base_headers["ACCEPT-LANGUAGE"]  = 'en-US'

    def __init__(self, secureUri, uri, serviceversion):

        self.napstersurl = secureUri
        self.napsterurl  = uri
        self.serviceversion = serviceversion

        self.napsterns = '{%s}' % self.serviceversion

        self.errormetadata  = '<mediaMetadata  xmlns="' + self.serviceversion + '">'
        self.errormetadata += '<title>Error returned from Napster</title>'
        self.errormetadata += '<itemType>error</itemType>'
        self.errormetadata += '<id>error</id>'
        self.errormetadata += '</mediaMetadata>'

        self.credentialsformat  = '<credentials xmlns="' + self.serviceversion + '">'
        self.credentialsformat += '<deviceProvider>Sonos</deviceProvider>'
        self.credentialsformat += '<userId>%s</userId>'
        self.credentialsformat += '</credentials>'

        self.getmetadataformat  = '<getMetadata xmlns="' + self.serviceversion + '"><id>%s</id><index>%s</index><count>%s</count></getMetadata>'

        self.searchformat  = '<search xmlns="' + self.serviceversion + '"><id>%s</id><term>%s</term><index>%s</index><count>%s</count></search>'

        self.username = ''
        self.password = ''
        self.userId = ''
        self.loggedIn = False
        self.credentials = ''

        
    def login(self, username, password):

        self.username = username
        self.password = password

        body =  '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
        body += '<s:Body>'
        body += '<getUserId xmlns="http://www.sonos.com/Services/1.0">'
        body += '<username>' + self.username + '</username>'
        body += '<password>' + self.password + '</password>'
        body += '</getUserId>'
        body += '</s:Body>'
        body += '</s:Envelope>'

        headers = dict(self.base_headers)
        headers["CONTENT-LENGTH"]   = len(body)
        headers["SOAPACTION"]       = '"http://www.sonos.com/Services/1.0#getUserId"'

        response = http_call('POST', self.napstersurl, body=body, headers=headers)
#        print response

        result = self.parse_login_response(response)
        if result == True:
            self.loggedIn = True

        return result


    def makemessage(self, bodycontent, headercontent=''):

        if headercontent == '':
            headercontent = self.credentials
        body = self.bodyformat % bodycontent
        header = self.headerformat % headercontent
        message = self.envelopeformat % (header, body)
        return message


    def getMetadata(self, id, index, count):

        getmetadata = self.getmetadataformat % (id, index, count)
        body = self.makemessage(getmetadata)

        headers = dict(self.base_headers)
        headers["CONTENT-LENGTH"]   = len(body)
        headers["SOAPACTION"]       = '"http://www.sonos.com/Services/1.0#getMetadata"'
        response = http_call('POST', self.napsterurl, body=body, headers=headers)
        result = self.parse_result(response)

        return result


    def search(self, id, term, index, count):

        nsearch = self.searchformat % (id, term, index, count)
        body = self.makemessage(nsearch)

        headers = dict(self.base_headers)
        headers["CONTENT-LENGTH"]   = len(body)
        headers["SOAPACTION"]       = '"http://www.sonos.com/Services/1.0#search"'
        response = http_call('POST', self.napsterurl, body=body, headers=headers)
        result = self.parse_result(response)

        return result


    def parse_result(self, data):

        print "??????????????????????????????????"
        print "parse_result"
        print data

        kwargs = {}
        collectionargs = []

        tree = parse_xml(data)
        body = tree.find(self.soapns + 'Body')
        method = body.getchildren()[0]
        
        if method.tag == self.soapns + 'Fault':
            # error returned from Napster
            '''
            <soap:Fault>
                <faultcode>soap:Server</faultcode>
                <faultstring>Can't use an undefined value as an ARRAY reference at /mp3/tools/napster-glueware/lib/Napster/DataObject/Radio.pm line 618.</faultstring>
            </soap:Fault>
            '''
            # rather than display returned message, announce unable to browse

            kwargs[self.napsterns + 'index'] = '0'            
            kwargs[self.napsterns + 'count'] = '0'            
            kwargs[self.napsterns + 'total'] = '0'
            collectionargs.append(parse_xml(self.errormetadata).getroot())
            kwargs['collections'] = collectionargs
            kwargs['success'] = '0'
                        
            return kwargs
        
        result = method.getchildren()[0]

        for child in result.getchildren():
            if child.text != None:
                # TODO: find a better way to separate collections and literals
                kwargs[child.tag] = child.text
            else:
                collectionargs.append(child)
        kwargs['collections'] = collectionargs
        kwargs['success'] = '1'

        print kwargs

        return kwargs


    def parse_login_response(self, response):

        element = parse_xml(response)
        success = False
        for child in element.getiterator():
            if child.tag == '{http://www.sonos.com/Services/1.0}getUserIdResult':
                if child.text != None:
                    success = True        
                    self.userId = child.text
                    self.credentials = self.credentialsformat % self.userId

        return success


class HTTPError(exceptions.Exception):
    """ Represents an error of a HTTP request.
    """

    def __init__(self, code, msg):
        """ Constructor for the HTTPError class.

        @param code: error code
        @param msg: error message

        @type code: string
        @type msg: string
        """
        self.code = code
        self.msg = msg

    def __repr__(self):
        return "<HTTPError %s %s>" % (self.code, self.msg)

    def __call___(self):
        return (self.code, self.msg, )


def http_call(method, url, body='', headers={}):

    import urllib2
    import httplib
    import shutil
    import socket
    from urlparse import urlparse

    parsed_url = urlparse(url)

    if parsed_url.port == None:
        if parsed_url.scheme == 'https':
            port = 443
        else:
            port = 80
    else:
        port = parsed_url.port

    ip = socket.gethostbyname(parsed_url.hostname)

    real_path = parsed_url.path
    if parsed_url.query:
        real_path += '?' + parsed_url.query
    if parsed_url.fragment:
        real_path += '#' + parsed_url.fragment

    if parsed_url.scheme == 'https':
        con = httplib.HTTPSConnection("%s:%d" % (ip, port))
    else:
        con = httplib.HTTPConnection("%s:%d" % (ip, port))

    con.connect()

    con.request(method, real_path, body=body, headers=headers)

    response = con.getresponse()

    code = response.status
    msg = response.reason
    headers = response.msg

    content_length = headers.get("Content-Length")
    if content_length == None:
        data = response.read()
        message_len = len(data)
    else:
        message_len = int(content_length)
        data = response.read(message_len)

    if code not in (200, 500):
        raise HTTPError(code, msg)

    content_encoding = headers.get("Content-Encoding")
    
    if content_encoding == 'gzip':

        import StringIO
        stream = StringIO.StringIO(data)
        import gzip
        gzipper = gzip.GzipFile(fileobj=stream)
        try:
            gdata = gzipper.read()
        except IOError:
            # probably not a gzip body
            gdata = data
        data = gdata

    return data


