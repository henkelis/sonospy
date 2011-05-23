# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" WSGI-based webserver module. Includes a few built-in adapters for working
with different WSGI servers.

If possible, an adapter will be automatically assigned to a WebServer instance -
if not passed by the user.

For retrieving the available adapters, use get_available_adapters(). The results
can be passed to the WebServer, e.g. WebServer(adapter=some_adapter) where
some_adapter was retrieved with get_available_adapters().
"""

__all__ = ('Resource', 'CustomResource', 'WebServer', 'StaticFile', 'adapters',
           'get_available_adapters', 'AdapterInterface', 'CherrypyAdapter',
           'PasteAdapter', 'CircuitsWebAdapter')

import transcode

import os
import random
import os.path
import sys
import rfc822
import warnings
import mimetypes
import mimetools
import wsgiref.util
import wsgiref.headers
import base64
import struct
import StringIO


from brisa import __enable_webserver_logging__, __enable_offline_mode__
from brisa.core import log, config, threaded_call
from brisa.core.network import parse_url, get_active_ifaces, get_ip_address


if not __enable_offline_mode__:
    if not get_active_ifaces():
        raise RuntimeError('Network is down.')

mimetypes.init()
mimetypes.add_type('audio/flac', '.flac')

log = log.getLogger('core.webserver')

invalid_path_exists = 'path does not exist'
invalid_path_abs = 'path must be absolute'
invalid_path_dir = 'path must be a file'

http_codes = {100: 'Continue',
              101: 'Switching Protocols',
              200: 'OK',
              201: 'Created',
              202: 'Accepted',
              203: 'Non-Authoritative Information',
              204: 'No Content',
              205: 'Reset Content',
              206: 'Partial Content',
              300: 'Multiple Choices',
              301: 'Moved Permanently',
              302: 'Found',
              303: 'See Other',
              304: 'Not Modified',
              305: 'Use Proxy',
              307: 'Temporary Redirect',
              400: 'Bad Request',
              401: 'Unauthorized',
              403: 'Forbidden',
              404: 'Not Found',
              405: 'Method Not Allowed',
              416: 'Requested range not satisfiable',
              417: 'Expectation Failed',
              500: 'Internal Server Error',
              501: 'Not Implemented',
              502: 'Bad Gateway',
              503: 'Service Unavailable',
              504: 'Gateway Time-out',
              505: 'HTTP Version not supported'}

chunks_size = 2**16

simple_template = '<html><head><title>%s</title><body>%s</body></html>'


def simple_response(code, start_response, extra_msg=None):
    """ Performs a simple response for a request. Usually used for returning
    errors or empty pages. For example, start_response(404, start_response,
    'File not available on the server') will return a page to the user with the
    404 status and this message on the body, wrapped in a simple html template.

    @param code: status code present on http_codes dict
    @param start_response: start_response wsgi function
    @param extra_msg: message that goes on the body. If not supplied, the status
                      message will take its place on the body.

    @type code: integer
    @type start_response: callable
    @type extra_msg: string

    @note: this function also sends the headers

    @return: final message to return as response body
    @rtype: string
    """
    status_msg = '%d %s' % (code, http_codes[code])
    start_response(status_msg, [('Content-type', 'text/html')])
    if extra_msg:
        return simple_template % (status_msg, '%s<br/>%s' % (status_msg, \
                                  extra_msg))
    else:
        return simple_template % (status_msg, status_msg)


def response(code, start_response, msg):
    """ Performs a response for a request without wrapping in a html template.

    @param code: status code present on http_codes dict
    @param start_response: start_response wsgi function
    @param msg: message that goes on the body. If not supplied, the status
                message will take its place on the body.

    @type code: integer
    @type start_response: callable
    @type msg: string

    @note: this function also sends the headers

    @return: final message to return as response body
    @rtype: string
    """
    status_msg = '%d %s' % (code, http_codes[code])
    start_response(status_msg, [('Content-type', 'text/html')])
    return msg


class Request(object):
    """ Request wrapper class.
    """

    def __init__(self, env):
        """ Constructor for the Request wrapper class. Parses the HTTP headers
        and sets request attributes.

        @param env: wsgi environ dict
        @type env: dict
        """
      
        self.env = env.copy()

        self.body = env.get('wsgi.input', None)
        self.headers = wsgiref.headers.Headers([])

        for k,v in env.items():
            if 'HTTP' in k:
                key = k.replace('HTTP_', '').lower().replace('_', '-')
                self.headers[key] = v

        self.method = env['REQUEST_METHOD']
        self.server_protocol = env['SERVER_PROTOCOL']
        self.protocol = tuple(map(int, self.server_protocol[5:].split('.')))
        self.headers['Content-length'] = env.get('CONTENT_LENGTH', 0)

        if not self.headers['Content-length']:
            del self.headers['Content-length']
        else:
            self.headers['Content-length'] = int(self.headers['Content-length'])

        self.headers['Content-type'] = env.get('CONTENT_TYPE', '')
        self.query = env['QUERY_STRING']
        self.uri = env['SCRIPT_NAME']

        if self.query:
            self.params = dict([(lambda k: k.split('='))(v) for v in \
                                 self.query.split('&')])
        else:
            self.params = {}

    def read(self):
        """ Reads the request payload, if available.
        """
        if 'Content-length' in self.headers and self.body:
            return self.body.read(self.headers['Content-length'])
        else:
            raise RuntimeError('Header does not contain a content-'\
                               'length field. It is possible that this'\
                               ' request does not contain a payload.')


class Response(object):
    """ Response wrapper class.
    """

    def __init__(self, status, start_response):
        """ Constructor for the Response class.

        @param status: response status code, can be modified later
        @param start_response: wsgi start_response function

        @type status: int
        @type start_response: callable
        """
        self.status = status
        self.start_response = start_response
        self.headers = wsgiref.headers.Headers([])
        self.body = None

    def _respond(self):
        """ Sends the headers for this response. After this call, response.body
        should be returned to the WSGI server as the response payload.
        """
#        print "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
#        print "Response._respond: "
#        print "status: " + str(self.status)
#        print "headers: " + str(self.headers)
#        print "body: " + str(self.body)
#        print "start_response: " + str(self.start_response)
        if not self.status:
            raise ValueError('Status code not set for a HTTP response.')
        status_msg = '%d %s' % (self.status, http_codes[self.status])

        log.debug("_respond headers: \n%s", str(self.headers))

        if not 'Content-type' in self.headers:
            self.headers['Content-type'] = 'text/html; charset="utf-8"'
#        self.headers['Content-length'] = '0'   # this is OK for circuits, but not for cherrypy!

#        import traceback        
#        traceback.print_stack()
        
        self.start_response(status_msg, self.headers.items())


def get_byte_ranges(r, clen):
    """ Based on a Range header and on the content length of a file, returns a
    list of byte ranges requested. Returns None if the header was invalid and an
    empty list in case of invalid range.

    Based on Cherrypy 3.1 implementation.

    @param r: range header
    @param clen: content length
    """
    # Byte unit supported by us (HTTP1.1) is "bytes". Get the ranges string.
    log.debug('Range: %s, %d' % (r, clen))

    if not r:
        return None

    bunit, branges = r.split('=', 1)

    log.debug('Bunit, branges: %s %s' % (bunit, branges))

    if bunit != 'bytes':
        # Ignore any other kind of units
        log.warning('Received a request with wrong Range header (unit is not'\
                    'bytes')
        return None

    ranges = []

    for br in branges.split(','):
        start, stop = [b.strip() for b in br.split('-', 1)]
        log.debug('%s %s' % (start, stop))

        if not start:
            # If the first number is missing, should return the last n bytes
            # and stop must be present, or else return the whole body.
            if not stop:
                # Invalid! Return None and indicate the whole body
                return None
            # Last n bytes
            ranges.append((clen - int(stop), clen))
            log.debug('Ranges: %s' % ranges)
        else:
            # Start is present
            if not stop:
                # Whole body
                stop = clen - 1
            if int(start) >= clen:
                # If start is equal to or larger than the size of the document
                # minus one, return the whole body
                continue
            if int(stop) < int(start):
                return None
            ranges.append((int(start), int(stop) + 1))
            log.debug('Ranges: %s' % ranges)


    log.debug('Ranges: %s' % ranges)
    return ranges


def chunk_generator(f, chunk_size, max_chunked):
    """ Generates chunks of a file. Stops when reaches the max_chunked value
    of generated chunks.
    """
    log.debug('Chunk generator of %s, chunks size %d and max chunked data %d' %
              (f, chunk_size, max_chunked))

    while max_chunked > 0:
        chunk = f.read(min(chunk_size, max_chunked))
        clen = len(chunk)
        if clen == 0:
            return
        max_chunked -= clen
        yield chunk


def setup_single_part_response(r, rng, clen):
    """ Setups a response object for a single part response. Based on Cherrypy
    3.1 implementation.

    @param r: response object
    @param rng: 2-tuple of the form (start, stop) with the byte
                range requested
    @param clen: length of the body file
    """
    start, stop = rng
    if stop > clen:
        stop = clen
    res_len = stop - start

    r.headers['Content-range'] = 'bytes %s-%s/%s' % (start, stop - 1, clen)
    r.headers['Content-length'] = str(res_len)

    r.body.seek(start)
    r.body = chunk_generator(r.body, chunks_size, res_len)


def setup_multi_part_response(r, rngs, clen, content_type):
    """ Setups a response object for a multi part response, based on the byte
    ranges requested. Based on Cherrypy 3.1 implementation.

    @param r: response object
    @param rngs: list of ranges
    @param clen: length of the body file
    """
    b = mimetools.choose_boundary()
    r.headers['Content-type'] = 'multipart/byteranges;'\
                                'boundary=%s' % b

    real_file = r.body

    def mpart_body_generator():
        yield '\r\n'

        for start, stop in rngs:
            yield '--%s\r\n' % b
            yield 'Content-type: %s\r\n' % content_type
            yield 'Content-range: bytes\r\n%s-%s/%s\r\n\r\n' % \
                  (start, stop - 1, clen)
            real_file.seek(start)
            for c in chunk_generator(real_file, chunks_size, stop-start):
                yield c
            yield '\r\n'
        yield '--%s--\r\n' % b

    r.body = mpart_body_generator()


class StaticFile(object):
    """ Object that matches with a file and makes it available on the server.
    """

    def __init__(self, name, path, content_type=None, disposition=None):
        """ Constructor for the StaticFile class.

        @param name: file name visible on the webserver
        @param path: file path on the system
        @param content_type: force content type, e.g. "application/x-download"
        @param disposition: file disposition, e.g. "attachment"

        @note: path supplied must exist and point to a file
        """

        log.info('name: %s   path: %s' % (name, path))
        
        if not os.path.exists(path):
            warnings.warn(invalid_path_exists)
        if not os.path.isabs(path):
            log.warning('path---->%s',path)
            warnings.warn(invalid_path_abs)
        if os.path.isdir(path):
            raise TypeError(invalid_path_dir)

        self.name = name
        self.path = path
        self._content_type = content_type
        self._disposition = disposition

        if not self._content_type:
            self._guess_content_type()

        log.debug('name: %s   path: %s   _content_type: %s   _disposition: %s' % (name, path, self._content_type, self._disposition))


    def _guess_content_type(self):
        """ Guesses content type for this file based on the filename.

        Copyright (c) 2002-2008, CherryPy Team (team@cherrypy.org)
        """
        self._content_type = mimetypes.types_map.get('.%s' %
                                                     self.path.split('.')[-1],
                                                     'text/plain')
        log.debug('File %s type %s' % (self.path, self._content_type))

    def application(self, environ, start_response, response=None):
        """ Application wsgi callback that processes a request. Must not be
        called by the user.

        @param response: used when the request was redirected to this file. If
                         not present, then this file was accessed directly (no
                         redirections) and in this case environ and
                         start_response must be passed accordingly.
        """

        log.debug('StaticFile application environ %s' % environ)
        log.debug('StaticFile application response %s' % response)

#        if 'REQUEST_METHOD' in environ:
#            if environ['REQUEST_METHOD'] == 'GET':
#                print "@@@@@@@@@@ StaticFile.application: " + str(environ)
        
        req = Request(environ)

        if response:
            # Redirect mode, see method doc and comments at the end
            r = response
        else:
            # Normal request
            r = Response(200, start_response)

        if not os.path.exists(self.path):
            log.warning('Received request on missing file: %s' % self.path)
            return simple_response(500, r.start_response, 'File not available.')

        try:
            st = os.stat(self.path)
        except OSError:
            return simple_response(404, r.start_response)

        r.body = open(self.path, 'rb')
        content_length = st.st_size

        h = r.headers
        h['Last-modified'] = rfc822.formatdate(st.st_mtime)
        h['Content-type'] = self._content_type

        if self._disposition:
            h['Content-disposition'] = '%s; filename="%s"' % \
                                       (self._disposition, self.name)

        if req.protocol >= (1, 1):
            h['Accept-ranges'] = 'bytes'

            if 'range' not in req.headers:
                # Send the whole response body
                h['Content-length'] = str(content_length)
            else:
                ranges = get_byte_ranges(req.headers['Range'], content_length)

                if ranges == []:
                    # Request range not satisfiable
                    r.status = 416
                    r.headers['Content-range'] = 'bytes */%s' % content_length
                    r.headers['Content-length'] = 0
                    r.body = ['']
                elif ranges:
                    # Partial content status
                    r.status = 206

                    if len(ranges) == 1:
                        # Single part
                        setup_single_part_response(r, ranges[0], content_length)

                    else:
                        # Multipart
                        setup_multi_part_response(r, ranges, content_length,
                                                  self._content_type)

                        # Recalculate content length
                        s = 0
                        for ra in ranges:
                            s += ra[1] - ra[0] + 1
                        h['Content-length'] = str(s)

        else:
            # Lower protocols do not support ranges, whole body
            h['Content-length'] = str(content_length)

        log.debug("headers: %s", str(h))

        if not response:
            # Normal request, not redirected. When redirected, who respond()s is
            # the caller.
            r._respond()

        return r.body

    def render(self, uri, request, response):
        """ Enables the file to receive an URL redirection, that is, a
        resource can return this file on the get_render() method.
        """
        log.debug('StaticFile render. uri: %s, request: %s, response: %s', uri, request, response)
        return self.application(request.env, None, response)





class StaticFileSonos(object):
    """ Object that matches with a file and makes it available on the server.
    """

    def __init__(self, dummyname, name, path, content_type=None, disposition=None, cover=None):
        """ Constructor for the StaticFile class.

        @param name: file name visible on the webserver
        @param path: file path on the system
        @param content_type: force content type, e.g. "application/x-download"
        @param disposition: file disposition, e.g. "attachment"

        @note: path supplied must exist and point to a file
        """

        if not os.path.exists(path):
            warnings.warn(invalid_path_exists)
        if not os.path.isabs(path):
            log.warning('path---->%s',path)
            warnings.warn(invalid_path_abs)
        if os.path.isdir(path):
            raise TypeError(invalid_path_dir)

        self.dummyname = dummyname
        self.name = name
        self.path = path
        self.cover = cover
        self._content_type = content_type
        self._disposition = disposition

        if not self._content_type:
            log.debug('_content_type before: %s' % self._content_type)
            self._guess_content_type()
            log.debug('_content_type after : %s' % self._content_type)

        log.debug('dummyname: %s   name: %s   path: %s   _content_type: %s   _disposition: %s' % (dummyname, name, path, self._content_type, self._disposition))


    def _guess_content_type(self, path=None):
        """ Guesses content type for this file based on the filename.

        Copyright (c) 2002-2008, CherryPy Team (team@cherrypy.org)
        """
        if not path:
            path = self.path
        self._content_type = mimetypes.types_map.get('.%s' %
                                                     path.split('.')[-1],
                                                     'text/plain')
        log.debug('File %s type %s' % (path, self._content_type))


    def application(self, environ, start_response, response=None):
        """ Application wsgi callback that processes a request. Must not be
        called by the user.

        @param response: used when the request was redirected to this file. If
                         not present, then this file was accessed directly (no
                         redirections) and in this case environ and
                         start_response must be passed accordingly.
        """

#        import traceback        
#        traceback.print_stack()

        log.debug('StaticFileSonos application environ %s' % environ)
        log.debug('StaticFileSonos application start_response %s' % start_response)
        log.debug('StaticFileSonos application response %s' % response)

        req = Request(environ)

        if response:
            # Redirect mode, see method doc and comments at the end
            r = response
        else:
            # Normal request
            r = Response(200, start_response)

        path = self.path
        albumart = False
        coveroffsets = None

        log.debug('=========================================')
        log.debug('qs: %s' % environ['QUERY_STRING'])
        log.debug('dn: %s' % self.dummyname)
        log.debug('name: %s' % self.name)
        log.debug('path: %s' % self.path)
        log.debug('cover: %s' % self.cover)
        log.debug('_content_type: %s' % self._content_type)
        log.debug('=========================================')

        # Sonos queries for the album art either via a query string, or directly to the art specified
        # if the art is embedded then we need to extract it (it can be in multiple pieces)
        if environ['QUERY_STRING'] == 'albumArt=true' or self.dummyname.endswith('.coverart'):
            if self.cover.startswith('EMBEDDED_'):
                # art is embedded for this file
                coverparts = self.cover.split('_')
                coveroffsets = coverparts[1].split(',')
                log.debug('coveroffsets: %s' % coveroffsets)
            else:
                path = self.cover
                if not path or path == '':
                    return simple_response(404, r.start_response)
                albumart = True
                self._guess_content_type(path)

        if not os.path.exists(path):
            log.warning('Received request on missing file: %s' % path)
            return simple_response(500, r.start_response, 'File not available.')

        try:
            st = os.stat(path)
        except OSError:
            return simple_response(404, r.start_response)

        fileoffset = open(path, 'rb')
        if coveroffsets:
            # extract art from music file
            image = ''
            coverlength = 0
            enctype = ''
            if len(coveroffsets) % 2:
                enctype = coveroffsets.pop()
            for i in xrange(0, len(coveroffsets), 2):
                offset = int(coveroffsets[i])
                length = int(coveroffsets[i+1])
                coverlength += length
                fileoffset.seek(offset)
                image += fileoffset.read(length)
            fileoffset.close()
            if enctype == 'base64flac':
                try:
                    data = base64.b64decode(image)
                except TypeError, e:
                    data = None
                    log.debug(e)
                if data:
                    temp = StringIO.StringIO(data)
                    itype, length = struct.unpack('>2I', temp.read(8))
                    mime = temp.read(length).decode('UTF-8', 'replace')
                    length, = struct.unpack('>I', temp.read(4))
                    desc = temp.read(length).decode('UTF-8', 'replace')
                    (width, height, depth, colors, length) = struct.unpack('>5I', temp.read(20))
                    image = temp.read(length)
                    coverlength = length
            content_length = coverlength
            r.body = image
        else:
            content_length = st.st_size
            r.body = fileoffset

        h = r.headers
        h['Last-modified'] = rfc822.formatdate(st.st_mtime)
        h['Content-type'] = self._content_type

        if self._disposition:
            h['Content-disposition'] = '%s; filename="%s"' % \
                                       (self._disposition, self.name)

        h['Accept-ranges'] = 'bytes'

#        if albumart:
#            h['TransferMode.DLNA.ORG'] = 'Interactive'
#        else:
#            h['TransferMode.DLNA.ORG'] = 'Streaming'
#        h['Server'] = 'Microsoft-HTTPAPI/1.0'

        if 'range' not in req.headers:
        
            h['Content-length'] = str(content_length)
        
#            self.tcp_transport.send_data(data, (host, port))
        
        else:
            ranges = get_byte_ranges(req.headers['Range'], content_length)

            if ranges == []:
                # Request range not satisfiable
                r.status = 416
                r.headers['Content-range'] = 'bytes */%s' % content_length
                r.headers['Content-length'] = 0
                r.body = ['']
            elif ranges:
                # Partial content status
                r.status = 206

                if len(ranges) == 1:
                    # Single part
                    setup_single_part_response(r, ranges[0], content_length)

                else:
                    # Multipart
                    setup_multi_part_response(r, ranges, content_length,
                                              self._content_type)

                    # Recalculate content length
                    s = 0
                    for ra in ranges:
                        s += ra[1] - ra[0] + 1
                    h['Content-length'] = str(s)


        log.debug("headers: %s", str(h))
        if response:
            log.debug("headers: %s", str(response.headers))

        if not response:
            # Normal request, not redirected. When redirected, who respond()s is
            # the caller.
            r._respond()

        return r.body

    def render(self, uri, request, response):
        """ Enables the file to receive an URL redirection, that is, a
        resource can return this file on the get_render() method.
        """
        log.debug('StaticFileSonos render. uri: %s, request: %s, response: %s', uri, request, response)
        return self.application(request.env, None, response)









class TranscodedFileSonos(object):
    """ Object that matches with a file and makes it available on the server.
    """

    def __init__(self, dummyname, name, path, transcodetype, content_type=None, disposition=None, cover=None):
        """ Constructor for the StaticFile class.

        @param name: file name visible on the webserver
        @param path: file path on the system
        @param content_type: force content type, e.g. "application/x-download"
        @param disposition: file disposition, e.g. "attachment"

        @note: path supplied must exist and point to a file
        """

        if not os.path.exists(path):
            warnings.warn(invalid_path_exists)
        if not os.path.isabs(path):
            log.warning('path---->%s',path)
            warnings.warn(invalid_path_abs)
        if os.path.isdir(path):
            raise TypeError(invalid_path_dir)

        self.dummyname = dummyname
        self.name = name
        self.path = path
        self.cover = cover
        self.transcodetype = transcodetype
        self._content_type = content_type
        self._disposition = disposition

        if not self._content_type:
            self._guess_content_type()

        log.debug('dummyname: %s   name: %s   path: %s   _content_type: %s   _disposition: %s' % (dummyname, name, path, self._content_type, self._disposition))


    def _guess_content_type(self, path=None):
        """ Guesses content type for this file based on the filename.

        Copyright (c) 2002-2008, CherryPy Team (team@cherrypy.org)
        """
        if not path:
            path = self.path
        self._content_type = mimetypes.types_map.get('.%s' %
                                                     path.split('.')[-1],
                                                     'text/plain')
        log.debug('File %s type %s' % (path, self._content_type))


    def application(self, environ, start_response, response=None):
        """ Application wsgi callback that processes a request. Must not be
        called by the user.

        @param response: used when the request was redirected to this file. If
                         not present, then this file was accessed directly (no
                         redirections) and in this case environ and
                         start_response must be passed accordingly.
        """

#        import traceback        
#        traceback.print_stack()

        log.debug('TranscodedFileSonos application environ %s' % environ)
        log.debug('TranscodedFileSonos application start_response %s' % start_response)
        log.debug('TranscodedFileSonos application response %s' % response)

        req = Request(environ)

        if response:
            # Redirect mode, see method doc and comments at the end
            r = response
        else:
            # Normal request
            r = Response(200, start_response)

        path = self.path
        albumart = False

        # Sonos queries for the album art via a query string
        if environ['QUERY_STRING'] == 'albumArt=true':
            path = self.cover
            if not path or path == '':
                return simple_response(404, r.start_response)
            albumart = True
            self._guess_content_type(path)

        if not os.path.exists(path):
            log.warning('Received request on missing file: %s' % path)
            return simple_response(500, r.start_response, 'File not available.')

        try:
            st = os.stat(path)
        except OSError:
            return simple_response(404, r.start_response)

        if albumart:
            r.body = open(path, 'rb')
            content_length = st.st_size
        else:
            r.body = transcode.transcode(path, self.transcodetype)
            content_length = 0

        h = r.headers
        h['Last-modified'] = rfc822.formatdate(st.st_mtime)
        h['Content-type'] = self._content_type

        if self._disposition:
            h['Content-disposition'] = '%s; filename="%s"' % \
                                       (self._disposition, self.name)

        h['Accept-ranges'] = 'bytes'

#        if albumart:
#            h['TransferMode.DLNA.ORG'] = 'Interactive'
#        else:
#            h['TransferMode.DLNA.ORG'] = 'Streaming'
#        h['Server'] = 'Microsoft-HTTPAPI/1.0'

        if 'range' not in req.headers:
        
            h['Content-length'] = str(content_length)
            
        else:
            ranges = get_byte_ranges(req.headers['Range'], content_length)

            if ranges == []:
                # Request range not satisfiable
                r.status = 416
                r.headers['Content-range'] = 'bytes */%s' % content_length
                r.headers['Content-length'] = 0
                r.body = ['']
            elif ranges:
                # Partial content status
                r.status = 206

                if len(ranges) == 1:
                    # Single part
                    setup_single_part_response(r, ranges[0], content_length)

                else:
                    # Multipart
                    setup_multi_part_response(r, ranges, content_length,
                                              self._content_type)

                    # Recalculate content length
                    s = 0
                    for ra in ranges:
                        s += ra[1] - ra[0] + 1
                    h['Content-length'] = str(s)


        log.debug("headers: %s", str(h))
        if response:
            log.debug("headers: %s", str(response.headers))

        if not response:
            # Normal request, not redirected. When redirected, who respond()s is
            # the caller.
            r._respond()

        return r.body

    def render(self, uri, request, response):
        """ Enables the file to receive an URL redirection, that is, a
        resource can return this file on the get_render() method.
        """
        log.debug('TranscodedFileSonos render. uri: %s, request: %s, response: %s', uri, request, response)
        return self.application(request.env, None, response)








class Resource(object):
    """ Represents a resource or a folder on the webserver.

    Inheritance from this class should be used when you need special and
    accessing request attributes.

    When a request arrives at a resource, it looks first inside his files
    and resources. If no handler is found, it asks the get_render() method to
    return who will render(uri, req, resp) the request - default is self.
    """

    def __init__(self, name):
        """ Constructor for the Resource class.

        @param name: resource name visible on the webserver
        @type name: string
        """
        self.name = name
        self._tree = {}

    def render(self, uri, request, response):
        """ Renders a request. Default action on a resource is doing nothing.

        @note: should be overriden as needed
        """
        return None

    def add_static_file(self, file):
        """ Adds a static file to the resource.

        @param file: file to add
        @type file: StaticFile

        @note: if the file name is already present on the tree, it will get
               overriden
        """
        if not isinstance(file, StaticFile):
            raise ValueError('file must be a StaticFile instance.')
#        if file.name in self._tree:
#            warnings.warn('name override: %s' % file.name)
        self._tree[file.name] = file

    def add_resource(self, resource):
        """ Adds a resource to the resource.

        @param resource: resource to add
        @type resource: Resource

        @note: if this resource is already present on the tree, it will get
               overriden
        """
        if not isinstance(resource, Resource):
            raise ValueError('resource must be a Resource instance.')
#        if resource.name in self._tree:
#            warnings.warn('name override: %s' % resource.name)
        self._tree[resource.name] = resource

#        print "ws res add - _tree: " + str(self._tree)

    def application(self, environ, start_response):
        """ WSGI application callback. May not be called directly by the
        user.
        """
        log.debug('Resource application environ %s' % environ)
        
#        if 'REQUEST_METHOD' in environ:
#            if environ['REQUEST_METHOD'] == 'GET':
#                print "@@@@@@@@@@ Resource.application environ: " + str(environ)

#        if 'REQUEST_METHOD' in environ:
#            if environ['REQUEST_METHOD'] == 'NOTIFY':
#                if 'SCRIPT_NAME' in environ:
#                    if environ['SCRIPT_NAME'] != '/eventSub' and environ['SCRIPT_NAME'] != '':
#                        print "@@@@@@@@@@ Resource.application environ: " + str(environ)

        if environ['SCRIPT_NAME'] == '/':
            # HACK - work out why circuits is doing this
            environ['SCRIPT_NAME'] = ''
            environ['PATH_INFO'] = '/' + environ['PATH_INFO']
            
        oldenviron = environ.copy()
        
        path = wsgiref.util.shift_path_info(environ)
#        if path == 'web':
#            path = wsgiref.util.shift_path_info(environ)

#        if 'REQUEST_METHOD' in environ:
#            if environ['REQUEST_METHOD'] == 'GET':
#                print "############## environ: " + str(environ)
#                print "############## path: " + str(path)
#                print "############## _tree: " + str(self._tree)

#        if path == 'res_al8.m3u':
#            path = 'res_al8.asx'
    
        if path in self._tree:
#            if 'REQUEST_METHOD' in environ:
#                if environ['REQUEST_METHOD'] == 'GET':
#                    print "############## AVAILABLE!"
#                    print "############## AVAILABLE: " + str(path)
#                    print "############## AVAILABLE!"

            # Path directly available
            return self._tree[path].application(environ, start_response)
        else:
            # End point or needs redirect. In case get_render is overriden,
            # then a request should be handled by returned get_render()
            # object.
            req = Request(environ)

            resp = Response(200, start_response)

            render = self.get_render(req.uri, req.params)

            if not render:
                log.error('Could not find resource at %s' % req.uri)
                return simple_response(404, start_response)

            if render != self:

                log.debug('environ %s' % environ)
                log.debug('oldenviron %s' % oldenviron)
                log.debug('req.uri %s' % req.uri)
                log.debug('req.params %s' % req.params)
                log.debug('req %s' % req)
                log.debug('resp %s' % resp)

                proxybody = render.render(oldenviron, start_response)

                log.debug('resp headers %s' % resp.headers)
                log.debug('resp status %s' % resp.status)

                if not proxybody and not req.headers:
                        log.error('Body and headers were empty.')
                        return simple_response(404, start_response)
                        
                else:

                    return proxybody

            else:

                resp.body = render.render(req.uri, req, resp)

                if not resp.body and not req.headers:
                    log.error('Body and headers were empty.')
                    return simple_response(404, start_response)
                else:

                    '''
                    if isinstance(resp.body, str):

                        log.debug(len(resp.body))
                        try:
                            import zlib
                            resp.body = zlib.compress(resp.body)
                            log.debug(len(resp.body))
                            log.debug(resp.headers)
                            resp.headers['CONTENT-LENGTH'] = str(len(resp.body))
                            resp.headers['CONTENT-ENCODING'] = 'gzip'
                            log.debug(resp.headers)
                        except zlib.error, e:
                            log.debug(e)
                    '''
                            
                    resp._respond()
                    
                    return resp.body

        return simple_response(404, start_response)

    def get_render(self, uri, params):
        """ Returns the default render for the given request, uri and params.

        Default render is self.
        """
        return self

class CustomResource(Resource):
    """ Same as Resource.
    """
    pass

class SonosResource(Resource):
    """
    """
    def __init__(self, name, proxy):
        """ Constructor for the Resource class.

        @param name: resource name visible on the webserver
        @type name: string
        """
        self.name = name
        self.proxy = proxy
        self._tree = {}

    def add_static_file(self, file):
        """ Adds a static file to the resource.

        @param file: file to add
        @type file: StaticFile

        @note: if the file name is already present on the tree, it will get
               overriden
        """
        log.debug("SonosResource add_static_file file: %s" % file)
        log.debug("SonosResource add_static_file name: %s" % file.name)
        
        if not isinstance(file, StaticFileSonos):
            raise ValueError('file must be a StaticFileSonos instance.')
#        if file.dummyname in self._tree:
#            warnings.warn('name override: %s' % file.dummyname)
        self._tree[file.dummyname] = file

    def add_transcoded_file(self, file):
        """ Adds a static file to the resource.

        @param file: file to add
        @type file: StaticFile

        @note: if the file name is already present on the tree, it will get
               overriden
        """
        log.debug("SonosResource add_transcoded_file file: %s" % file)
        log.debug("SonosResource add_transcoded_file name: %s" % file.name)
        
        if not isinstance(file, TranscodedFileSonos):
            raise ValueError('file must be a TranscodedFileSonos instance.')
#        if file.dummyname in self._tree:
#            warnings.warn('name override: %s' % file.dummyname)
        self._tree[file.dummyname] = file

    def add_resource(self, resource):
        """ Adds a resource to the resource.

        @param resource: resource to add
        @type resource: Resource

        @note: if this resource is already present on the tree, it will get
               overriden
        """
        if not isinstance(resource, SonosResource):
            raise ValueError('resource must be a SonosResource instance.')
#        if resource.name in self._tree:
#            warnings.warn('name override: %s' % resource.name)
        self._tree[resource.name] = resource

    def application(self, environ, start_response):
        """ WSGI application callback. May not be called directly by the
        user.
        """
        log.debug('SonosResource application environ %s' % environ)
        
        if environ['SCRIPT_NAME'] == '/':
            # HACK - work out why circuits is doing this
            environ['SCRIPT_NAME'] = ''
            environ['PATH_INFO'] = '/' + environ['PATH_INFO']
            
        path = wsgiref.util.shift_path_info(environ)

        log.debug('SonosResource application path %s' % path)
        log.debug('SonosResource application tree %s' % self._tree)

        if path in self._tree:
            # Path directly available
            return self._tree[path].application(environ, start_response)
        else:
            # Path not found - may have been called from queue when file has not been browsed
            self.proxy.get_Track(path)
            log.debug('SonosResource application tree now %s' % self._tree)
            if path in self._tree:
                return self._tree[path].application(environ, start_response)

        log.error('Could not find resource %s' % path)
        return simple_response(404, start_response)

    def get_render(self, uri, params):
        """ Returns the default render for the given request, uri and params.

        Default render is self.
        """
        log.debug('SonosResource get_render')
        return self

    def render(self, uri, request, response):
        """ Renders a request. Default action on a resource is doing nothing.

        @note: should be overriden as needed
        """
        return None









class AdapterInterface(object):
    """ Common interface for WSGI-servers adapters.
    """

    def setup(self, server_name, host, port, app_callback):
        """ Setups the adapter.
        """
        raise NotImplementedError

    def start(self):
        """ Starts the WSGI server.
        """
        raise NotImplementedError

    def stop(self):
        """ Stops the WSGI server.
        """
        raise NotImplementedError

    @classmethod
    def is_available(cls):
        """ Returns True if the adapter is available on the system.
        """
        raise NotImplementedError


class CherrypyAdapter(AdapterInterface):
    """ Cherrypy WSGI server adapter.
    """

    def setup(self, server_name, host, port, app_callback):
#        from cherrypy import wsgiserver
        from cherrypy import CherryPyWSGIServer
#        self._server = wsgiserver.CherryPyWSGIServer((host, port),
        self._server = CherryPyWSGIServer((host, port),
                                           app_callback,
                                           server_name=server_name)

    def start(self):
        self._server.start()

    def stop(self):
        self._server.stop()

    @classmethod
    def is_available(cls):
        try:
#        from cherrypy import wsgiserver
            from cherrypy import CherryPyWSGIServer
            return True
        except ImportError:
            return False


class PasteAdapter(AdapterInterface):
    """ Paste WSGI server adapter.
    """

    def setup(self, server_name, host, port, app_callback):
        from paste.httpserver import serve
        self._server = serve(app_callback, host, port,
                             start_loop=False)

    def start(self):
        self._server.serve_forever()

    def stop(self):
        self._server.server_close()

    @classmethod
    def is_available(cls):
        try:
            from paste.httpserver import serve
            return True
        except ImportError:
            return False




class CircuitsWebAdapter(AdapterInterface):
    """ circuits.web WSGI server adapter.
    """
    try:
        from circuits.web import Controller

        class Root(Controller):
            # TODO: do we still need this?
            def index(self):
                return "BRisa Control Point"
            def eventSub(self):
                return "\n"

    except ImportError:
        pass        

    def setup(self, server_name, host, port, app_callback):
        from circuits.web import BaseServer, Server
#        from circuits.lib.web.wsgi import Gateway
        from circuits.web.wsgi import Gateway
        from circuits.web import Controller
#        self._server = BaseServer(port, host)
#        self._server = Server(port, host)
        self._server = Server((host,port))
        self._server += Gateway(app_callback)
        self._server += self.Root()

    def start(self):
        self._server.start()

    def stop(self):
        self._server.stop()

    @classmethod
    def is_available(cls):
        try:
            from circuits.web import BaseServer, Server
            from circuits.web.wsgi import Gateway
            from circuits.web import Controller
            return True
        except ImportError:
            return False


adapters = {'cherrypy': CherrypyAdapter,
            'paste': PasteAdapter,
            'circuits.web': CircuitsWebAdapter}


def client_host(server_host):
    """ Return the host on which a client can connect to the given listener.

    Copyright (c) 2002-2008, CherryPy Team (team@cherrypy.org)
    """
    if server_host == '0.0.0.0':
        # 0.0.0.0 is INADDR_ANY, which should answer on localhost.
        return '127.0.0.1'
    if server_host == '::':
        # :: is IN6ADDR_ANY, which should answer on localhost.
        return '::1'

    return server_host

def check_port(host, port, timeout=1.0):
    """ Raises an error if the given port is not free on the given host.

    Copyright (c) 2002-2008, CherryPy Team (team@cherrypy.org)
    """
    if not host:
        raise ValueError("Host values of '' or None are not allowed.")
    host = client_host(host)
    port = int(port)

    import socket

    # AF_INET or AF_INET6 socket
    # Get the correct address family for our host (allows IPv6 addresses)
    for res in socket.getaddrinfo(host, port, socket.AF_UNSPEC,
                                  socket.SOCK_STREAM):
        af, socktype, proto, canonname, sa = res
        s = None
        try:
            s = socket.socket(af, socktype, proto)
            # See http://groups.google.com/group/cherrypy-users/
            #        browse_frm/thread/bbfe5eb39c904fe0
            s.settimeout(timeout)
            s.connect((host, port))
            s.close()
            raise IOError("Port %s is in use on %s; perhaps the previous "
                          "httpserver did not shut down properly." %
                          (repr(port), repr(host)))
        except socket.error:
            if s:
                s.close()


def get_preferred_adapter():
    """ Returns the preferred adapter, located at brisa.webserver_adapter
    config entry.
    """
    pref = config.get_parameter('brisa', 'webserver_adapter')
    return adapters.get(pref, None)


def get_available_adapters():
    """ Returns a list of the available adapters.
    """
    return [a for a in adapters.values() if a.is_available()]


class WebServer(Resource):
    """ Webserver class.
    """
    msg_already_started = 'tried to start() WebServer when already started'
    msg_already_stopped = 'tried to stop() WebServer when already stopped'
    SonosResource = SonosResource
    CustomResource = CustomResource
    Resource = Resource
    StaticFile = StaticFile

    def __init__(self, server_name='', host=None, port=None, adapter=None):
        """ WebServer class constructor.

        @param server_name: server name
        @param host: host to listen on
        @param port: port to listen on
        @param adapter: optional, can receive an adapter retrieved with
                        get_available_adapters()

        @type server_name: string
        @type host: string
        @type port: int
        @type adapter: AdapterInterface

        @note: the only parameter that should be always passed is the server
               name. In most case scenarios, the others can be guessed/assigned
               automatically by the webserver.
        """
        Resource.__init__(self, '/')
        self.server_name = server_name
        self.host = host
        self.port = port
        
        # force Cherrypy
        adapter = CherrypyAdapter
        
        self.adapter = adapter
        self.running = False

        if adapter and not issubclass(adapter, AdapterInterface):
            # Invalid adapter
            raise TypeError('Adapter must implement AdapterInterface')
        elif adapter:
            # Adapter OK
            self.adapter = adapter()
        else:
        
            pref = get_preferred_adapter()

            if not pref:
                # First available adapter
                available = get_available_adapters()

                if len(available) > 0:
                    self.adapter = available[0]()
            else:
                # Preferred adapter
                self.adapter = pref()

        if not self.adapter:
            log.critical('Could not select an adapter. Check the supported '\
                         'adapters and install one of them on your system.')
            raise SystemExit

        if not self.host and not self.port:
            self._generate_random_address()
        else:
            if not self.host:
                ifaces = get_active_ifaces()
                if ifaces:
                    self.host = get_ip_address(ifaces[0])
                else:
                    self.host = 'localhost'
            self.set_bind_address(self.host, self.port)

        self.adapter.setup(self.server_name, self.host, self.port,
                           self.application)

    def set_adapter(self, adapter):
        """ Sets the adapter (even after construction).

        Do not call this after the webserver is started.
        """
        if adapter and not issubclass(adapter, AdapterInterface):
            raise TypeError('Adapter must implement AdapterInterface')
        self.adapter = adapter()
        self.adapter.setup(self.server_name, self.host, self.port,
                           self._app_callback)

    def start(self):
        """ Starts the webserver.
        """
        if not self.is_running():
            if not self.adapter:
                raise RuntimeError('Adapter not set.')
            threaded_call.run_async_function(self.adapter.start)
            self.running = True
        else:
            log.warning(self.msg_already_started)

    def stop(self):
        """ Stops the webserver.
        """
        if self.is_running():
            if not self.adapter:
                raise RuntimeError('Adapter not set')
            self.adapter.stop()
        else:
            log.warning(self.msg_already_stopped)

    def get_listen_url(self):
        """ Returns the URL currently set to listen on.

        @rtype: string
        """
        return 'http://%s:%d' % (self.host, self.port)

    def get_bind_address(self):
        """ Returns the address currently bind to.

        @return: address (host, port)
        @rtype: tuple
        """
        return (self.host, self.port)

    def set_bind_address(self, host, port):
        """ Sets the listening url, if it is usable.
        """
        if not self.check_url(host, port):
            raise ValueError('URL cannot be used by the webserver.')
        else:
            self.host = host
            self.port = port

    def get_host(self):
        """ Returns the hostname of the URL currently set to listen on.

        @return: host
        @rtype: string
        """
        return self.host

    def get_port(self):
        """ Returns the port of the URL currently set to listen on.

        @return: port
        @rtype: int
        """
        return self.port

    def is_running(self):
        """ Returns True if the webserver is running, False otherwise.
        """
        return self.running

    def check_url(self, host, port):
        """ Returns True if the webserver will be able to listen on this URL,
        False otherwise.

        @param host: host
        @param port: port

        @type host: string
        @type port: int

        @return: if the URL is usable
        @rtype: bool
        """
        try:
#            print "before check_port: " + str(host) + " " + str(port)
            check_port(host, port)
#            print "after check_port"
            return True
        except IOError:
            return False

    def _generate_random_address(self):
        # Default listen url: localhost:port where port is on the dynamic
        # range (non registered ports)
        ifaces = get_active_ifaces()
        host = None
        port = None
        if ifaces:
            host = get_ip_address(ifaces[0])
        else:
            host = 'localhost'

        while not port:
            port = random.randint(49152, 65535)
            try:
                check_port(host, port)
            except IOError:
                port = 0

        self.host = host
        self.port = port
