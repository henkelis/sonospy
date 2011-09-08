#!/usr/bin/env python

import os.path
import wsgiref.util
import wsgiref.headers
import rfc822

from cherrypy import wsgiserver

from circuits.web import Controller
from circuits.web import BaseServer, Server
from circuits.web.wsgi import Gateway

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
        if not self.status:
            raise ValueError('Status code not set for a HTTP response.')
        status_msg = '%d %s' % (self.status, http_codes[self.status])

        if not 'Content-type' in self.headers:
            self.headers['Content-type'] = 'text/html; charset="utf-8"'
#        self.headers['Content-length'] = '0'   # this is OK for circuits, but not for cherrypy!
        
        self.start_response(status_msg, self.headers.items())

class CircuitsWebAdapter(object):

    class Root(Controller):
        def index(self):
            return "circuits"
        def eventSub(self):
            return "\n"

    def setup(self, host, port, app_callback):
        self._server = Server((host,port))
        self._server += Gateway(app_callback)
        self._server += self.Root()
        sfile = StaticFile('test.flac', '/mnt/nas/Anastacia/Anastacia/03 Time.flac')
        self._tree = {}
        self._tree[sfile.name] = sfile

    def start(self):
        self._server.start()

    def stop(self):
        self._server.stop()

    def application(self, environ, start_response):
        if environ['SCRIPT_NAME'] == '/':
            environ['SCRIPT_NAME'] = ''
            environ['PATH_INFO'] = '/' + environ['PATH_INFO']
            
        oldenviron = environ.copy()
        path = wsgiref.util.shift_path_info(environ)
        return self._tree[path].application(environ, start_response)

class CherrypyAdapter(object):

    def setup(self, host, port, app_callback):
        self._server = wsgiserver.CherryPyWSGIServer((host, port),
                                                     app_callback,
                                                     server_name="CP")
        sfile = StaticFile('test.flac', '/mnt/nas/Anastacia/Anastacia/03 Time.flac')
        self._tree = {}
        self._tree[sfile.name] = sfile

    def start(self):
        self._server.start()

    def stop(self):
        self._server.stop()

    def application(self, environ, start_response):
        if environ['SCRIPT_NAME'] == '/':
            environ['SCRIPT_NAME'] = ''
            environ['PATH_INFO'] = '/' + environ['PATH_INFO']
            
        oldenviron = environ.copy()
        path = wsgiref.util.shift_path_info(environ)
        return self._tree[path].application(environ, start_response)

class StaticFile(object):
    def __init__(self, name, path, content_type=None):
        self.name = name
        self.path = path
        self._content_type = 'text/html'

    def application(self, environ, start_response, response=None):
        req = Request(environ)
        r = Response(200, start_response)
        st = os.stat(self.path)
        r.body = open(self.path, 'rb')
        content_length = st.st_size
        h = r.headers
        h['Last-modified'] = rfc822.formatdate(st.st_mtime)
        h['Content-type'] = self._content_type
        h['Accept-ranges'] = 'bytes'
        h['Content-length'] = str(content_length)
        if not response:
            r._respond()
        return r.body

    def render(self, uri, request, response):
        return self.application(request.env, None, response)

if __name__ == "__main__":
#    web = CherrypyAdapter()
#    web.setup('192.168.0.3', 7000, web.application)
#    web.start()
    raw_input("Press ENTER to continue")
    web = CircuitsWebAdapter()
    web.setup('192.168.0.3', 7000, web.application)
    web.start()
    raw_input("Press ENTER to exit")
    

