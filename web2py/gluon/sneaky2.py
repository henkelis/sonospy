"""
Experimetal multi-threaded web server created by Massimo Di Pierro
For lack of a better we'll call it Sneaky.
License: GPL2

This code would have been possible without CherryPy wsgiserver,
a great example of Python web server.

- This code implements WSGI
- This code is API compatible with cherrypy
- It consists of less than 260 lines of code
- It is multi-threaded
- The number of threads changes dynamically between a min and a max
- Can handle chunking (request and response) [to be tested]
- supports SSL via the Cherrypy ssl adaptors

You can find an example of usage at the bottom of this file.

here are some tests and comparisons performed by Garrett Smith

RPS = requests per second
Time = average time in milliseconds to server each request
Benchmark = `ab -t 10 -c <number of concurrent requests>-r http://localhost`

100 Concurrent Requests
-----------------------
===============
App Server         RPS
==============
Fapws             7174
Landshark         4479
PHP-5             4191
modwsgi           3651
Tomcat 6          3554
Tornado           2641
Sneaky WSGI(*)    2372
CherryPy WSGI     2102
Phusion           1873
Jetty 6            937
Django WSGI        785
WEBrick             43
===============

1,000 Concurrent Requests
-------------------------
===============
App Server         RPS
===============
Fapws             5359
Landshark         4477
modwsgi           3449
PHP 5             3062
Tomcat 6          3014
Tornado           2452
Sneaky WSGI(*)    2415
CherryPy WSGI     2126
Phusion           1585
Jetty 6           1095
Django WSGI        953
WEBrick             50
===============

10,000 Concurrent Requests
--------------------------
===============
App Server         RPS
===============
Fapws             5213
Landshark         4239
Tomcat 6          2369
Tornado           2265
PHP 5             2239
Sneaky WSGI (*)   2225
modwsgi           2115
CherryPy WSGI     1731
Phusion           1247
Jetty 6            794
Django WSGI        890
WEBrick             84
===============

20,000 Concurrent Requests
--------------------------
===============
App Server         RPS
===============
Fapws             4788
Landshark         2936
Tornado           2153
Sneaky WSGI(*)    2130
PHP 5             1728
modwsgi           1374
Tomcat 6          1362
CherryPy WSGI     1294
Phusion            961
Django WSGI        790
Jetty 6            616
WEBrick             63
===============

"""

import os
import threading
import socket
import logging
import sys
import re
import errno
import signal
import time
import traceback
import copy

from cStringIO import StringIO
from Queue import Queue
regex_head = re.compile('^((http|https|HTTP|HTTPS)\://[^/]+)?(?P<method>\w+)\s+(?P<uri>\S+)\s+(?P<protocol>\S+)')
regex_header = re.compile('^\s*(?P<key>.*?)\s*\:\s*(?P<value>.*?)\s*$')
regex_chunk = re.compile('^(?P<size>\w+)')

BUF_SIZE = 10000
SERVER_NAME = 'Sneaky'

def formatdateRFC822():
    t=time.gmtime(time.time())
    w=("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[t[6]]
    return w+time.strftime(", %d %b %Y %H:%M%S GMT",t)

class ChunkedReader:
    """ class used to read chunked input """
    def __init__(self,stream):
        self.stream = stream
        self.buffer = None

    def __chunk_read(self):
        if not self.buffer or self.buffer.tell() == self.buffer_size:
            self.buffer_size = \
                int(regex_chunk.match(self.stream.readline()).group('size'),16)
            if self.buffer_size:
                self.buffer = StringIO(self.stream.read(self.buffer_size))

    def read(self,size):
        data = ''
        while size:
            self.__chunk_read()
            if not self.buffer_size:
                break
            read_size = min(size,self.buffer_size)
            data += self.buffer.read(read_size)
            size -= read_size
        return data

    def readline(self):
        data = ''
        for c in self.read(1):
            if not c:
                break
            data += c
            if c == '\n':
                break
        return data

    def readlines(self):
        yield self.readline()

def errors_numbers(errnames):
    """utility to build a list of socket errors"""
    return set([getattr(errno, k) for k in errnames if hasattr(errno,k)])

socket_errors_to_ignore = errors_numbers((
    "EPIPE",
    "EBADF", "WSAEBADF",
    "ENOTSOCK", "WSAENOTSOCK",
    "ETIMEDOUT", "WSAETIMEDOUT",
    "ECONNREFUSED", "WSAECONNREFUSED",
    "ECONNRESET", "WSAECONNRESET",
    "ECONNABORTED", "WSAECONNABORTED",
    "ENETRESET", "WSAENETRESET",
    "EHOSTDOWN", "EHOSTUNREACH",
    ))

class Worker(threading.Thread):
    """class representing a worker node"""
    queue = Queue()               # queue of requests to process (socket,address)
    threads = set()               # set of threads (instances or Worker class
    wsgi_apps = []                # [the_wsgi_app]
    server_name = SERVER_NAME
    min_threads = 10
    max_threads = 10

    def run(self):
        """runs the thread:
        - pick a request from queue
        - parse input
        - run wsgi_app
        - send response
        - resize set of threads
        """
        if not self.pid_parent:
            while True:
                (self.client_socket,self.client_address) = self.queue.get()
                if not self.client_socket:
                    return self.die()
                self.talk_to_client()
                self.resize_thread_pool()
        else:
            time.sleep(1)
            while True:
                try:
                    parent_socket = socket.socket(socket.AF_INET,socket.SOCK_STREAM,0)
                    logging.info('connecting to %s' % repr(('127.0.0.1',self.dispatcherport)))
                    parent_socket.connect(('127.0.0.1',self.dispatcherport))
                    logging.warn('here 1')
                    (self.client_socket,self.client_address) = eval(parent_socket.recv(256))
                    logging.warn('here 2')
                    parent_socket.close()
                    print self.client_socket,self.client_address
                    if not self.client_socket:
                        return self.die()
                    self.talk_to_client()
                    self.resize_thread_pool()
                except:
                    logging.warn(str(traceback.format_exc()))
                parent_socket.close()

    def talk_to_client(self):
        if hasattr(self.client_socket,'settimeout'):
            self.client_socket.settimeout(self.timeout)
        while True:
            wsgi_file = self.client_socket.makefile('rb',BUF_SIZE)
            try:
                environ = self.build_environ(wsgi_file)
                data_items = self.wsgi_apps[0](environ,self.start_response)
                if self.respond(environ, data_items):
                    break
            except:
                logging.warn(str(traceback.format_exc()))
                self.try_error_response()
                break
        wsgi_file.close()
        self.client_socket.close()


    def die(self):
        """kills this thread, must be called by run()"""
        self.threads.remove(self)
        return

    def build_environ(self,wsgi_file):
        """parse request and build WSGI environ"""
        first_line = wsgi_file.readline()
        match = regex_head.match(first_line)
        self.request_method = match.group('method')
        uri = match.group('uri')
        request_protocol = match.group('protocol')
        actual_server_protocol = request_protocol
        k = uri.find('?')
        if k<0:
            k = len(uri)
        (path_info,query_string) = (uri[:k],uri[k+1:])
        environ = {'wsgi.version': (1,0),
                   'wsgi.input': wsgi_file,
                   'wsgi.url_encoding': 'utf-8',
                   'wsgi.url_scheme': 'http',
                   'wsgi.errors': sys.stderr,
                   'ACTUAL_SERVER_PROTOCOL': actual_server_protocol,
                   'REMOTE_ADDR': self.client_address[0],
                   'REMOTE_PORT': self.client_address[1],
                   'SERVER_PORT': self.server_port,
                   'PATH_INFO': path_info,
                   'REQUEST_URI': uri,
                   'REQUEST_METHOD': self.request_method,
                   'PATH_INFO': path_info,
                   'SCRIPT_NAME': '',
                   'QUERY_STRING': query_string}
        for line in wsgi_file:
            if line == '\r\n':
                break
            match = regex_header.match(line)
            if not match:
                continue
            key = match.group('key').upper().replace('-','_')
            if isinstance(key,unicode):
                key = key.encode('ISO-8859-1')
            value = match.group('value')
            try:
                value = value.decode('ISO-8859-1').encode('utf-8')
            except:
                pass
            environ['HTTP_'+key] = value
            if key == 'CONTENT_LENGTH':
                environ[key]=value
            if key == 'CONTENT_TYPE':
                environ[key]=value
            if key == 'TRANSFER_ENCODING' and value[:7].lower() == 'chunked':
                environ['wsgi.input'] = ChunkedReader(wsgi_file)
        return environ

    def start_response(self,status,headers):
        """to be passed as second argument to wsgi_app"""
        self.status = status
        self.headers = headers

    def respond(self,environ,data_items):
        """called after wsgi_app successfully retruns"""
        headers = self.headers
        header_dict = dict([(x.lower(),y.strip()) for (x,y) in headers])
        if not 'date' in header_dict:
            headers.append(('Date',formatdateRFC822()))
        if not 'server' in header_dict:
            headers.append(('Server',self.server_name))
        # not a good idea but for now we are letting wsgi_app decide on chunking
        chunked = header_dict.get('transfer-encoding','')[:7].lower() == 'chunked'
        content_length = 'content-length' in header_dict
        connection = environ.get('HTTP_CONNECTION','close')
        keep_alive = connection == 'keep-alive'
        if keep_alive and (content_length or chunked):
            headers.append(('Connection','keep-alive'))
            break_loop = False
        else:
            headers.append(('Connection','close'))
            break_loop = True
        serialized_headers = \
            ''.join(['%s: %s\r\n' % (k,v) for (k,v) in headers])
        data = "HTTP/1.1 %s\r\n%s\r\n" % (self.status, serialized_headers)
        self.client_socket.sendall(data)
        if self.request_method != 'HEAD':
            for data in data_items:
                try:
                    if chunked:
                        self.client_socket.sendall('%x\r\n%s\r\n' % (len(data),data))
                    else:
                        self.client_socket.sendall(data)
                except socket.error, e:
                    if e.args[0] not in socket_errors_to_ignore:
                        raise
            if chunked:
                self.client_socket.sendall('0\r\n')
        return break_loop

    def try_error_response(self, status = "500 INSERTNAL SERVER ERROR"):
        """called if thread fails"""
        try:
            self.client_socket.sendall(
                "HTTP/1.0 %s\r\nContent-Length: 0\r\nContent-Type: text/plain\r\n\r\n" % status)
        except: pass

    def resize_thread_pool(self):
        """created new Worker(s) or kills some Worker(s)"""
        if self.max_threads>self.min_threads:
            qe = Worker.queue.empty()
            ql = len(Worker.threads)
            if qe and ql>self.min_threads:
                for k in range(self.min_threads):
                    Worker.queue.put((None,None))
            elif not qe and ql<self.max_threads:
                for k in range(self.min_threads):
                    new_worker = Worker()
                    Worker.threads.add(new_worker)
                    new_worker.start()



class Sneaky:
    """the actual web server"""
    def __init__(self,  bind_addr, wsgi_app,
                 numthreads = 10,
                 server_name = SERVER_NAME,
                 max_threads = None,
                 request_queue_size = None,
                 timeout = 10,
                 shutdown_timeout = 5,
                 numprocesses=1,
                 dispatcherport=8765):
        """
        Example::

        s = Sneaky('127.0.0.1:8000',test_wsgi_app,100)
        s.start()

        :bind_addr can be ('127.0.0.1',8000) or '127.0.0.1:8000'
        :wsgi_app is a generic WSGI application
        :numthreads is the min number of threads (10 by default)
        :server_name ("Skeaky" by default)
        :max_threads is the max number of threads or None (default)
                     should be a multiple of numthreads
        :request_queue_size if set to None (default) adjusts automatically
        :timeout on socket IO in seconds (10 secs default)
        :shotdown_timeout in seconds (5 secs default)
        """
        if isinstance(bind_addr,str):
            bind_addr = bind_addr.split(':')
        self.address = bind_addr[0]
        self.port = bind_addr[1]
        self.request_queue_size = request_queue_size
        self.shutdown_timeout = shutdown_timeout
        self.ssl_interface = None
        self.numprocesses = numprocesses

        Worker.dispatcherport=dispatcherport
        Worker.wsgi_apps.append(wsgi_app)
        Worker.server_name = server_name
        Worker.server_port = bind_addr[1]
        Worker.min_threads = numthreads
        Worker.max_threads = max_threads
        Worker.timeout = timeout

    def set_listen_queue_size(self):
        """tries a listen argument that works"""
        if self.request_queue_size:
            self.socket.listen(self.request_queue_size)
        else:
            for request_queue_size in [1024,128,5,1]:
                try:
                    self.socket.listen(request_queue_size)
                    break
                except:
                    pass

    def start(self):
        """starts the server"""
        print 'Experimental "Sneaky" WSGI web server. Starting...'
        Worker.pid_parent=None
        for numprocess in range(1,self.numprocesses):
            Worker.pid_parent=os.fork()
            if Worker.pid_parent<=0: break
        if not Worker.pid_parent:
            pthread=DispatcherThread(Worker.queue,Worker.dispatcherport)
            pthread.start()
        Worker.threads.update([Worker() for k in range(Worker.min_threads)])
        if Worker.pid_parent:
            for thread in Worker.threads:
                thread.start()
        if Worker.pid_parent:
            os.waitpid(Worker.pid_parent,0)
            self.stop()
            return
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        if not self.socket:
            raise IOException # unable to connect
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except:
            logging.error("Unable to set SO_REUSEADDR")
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except:
            logging.error("Unable to set TCP_NODELAY")
        try:
            self.socket.bind((self.address,int(self.port)))
        except:
            logging.error("Port taken by other process. Unable to bind")
            sys.exit(1)
        self.set_listen_queue_size()
        if self.ssl_interface:
            self.socket = self.ssl_interface(self.socket)
        try:
            while True:
                try:
                    (client_socket,client_address) = self.socket.accept()
                    Worker.queue.put((client_socket,client_address))
                except KeyboardInterrupt:
                    return self.stop()
                except Exception:
                    logging.warn(str(traceback.format_exc()))
                    continue
        except Exception:
            logging.warn(str(traceback.format_exc()))
            return self.stop()

    def stop(self):
        """tries to gracefully quit the server"""
        for k in range(len(Worker.threads)):
            Worker.queue.put((None,None))
        while len(Worker.threads):
            try:
                Worker.threads.client_socket.shutdown(0)
            except:
                pass

class DispatcherThread(threading.Thread):
    def __init__(self,queue,dispatcherport):
        self.queue = queue
        threading.Thread.__init__(self)
        self.dispatcherport=dispatcherport
    def run(self):
        logging.info('starting DispatcherThread on port %s...' % self.dispatcherport)
        psocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if not psocket:
            raise IOException # unable to connect
        psocket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        try:
            psocket.bind(('127.0.0.1',self.dispatcherport))
        except:
            logging.error("Port %s taken by other process. Unable to bind" % self.dispatcherport)
            sys.exit(1)
        psocket.listen(5)
        while True:
            logging.info('Dispacter accepting...')
            (child_socket,child_address) = psocket.accept()
            try:
                message=repr(self.queue.get())+" "*256
                print message
                child_socket.write(message[:256])
            except:
                pass
            child_socket.close()

def test_wsgi_app(environ, start_response):
    """just a test app"""
    status = '200 OK'
    response_headers = [('Content-type','text/plain'),('Content-Length','13')]
    start_response(status, response_headers)
    return ['hello world!\n']

if __name__ == '__main__':

    if '-debug' in sys.argv[1:]:
        logging.basicConfig(level = logging.INFO)
    else:
        logging.basicConfig(level = logging.ERROR)

    address = ([a for a in sys.argv[1:] if a[0]!='-'] + ['127.0.0.1:8000'])[0]

    print 'serving from: '+address

    server = Sneaky(address, # the ip:port
                    test_wsgi_app,  # the SWGI application
                    numthreads = 1, # min number of threads
                    max_threads = 1, # max number of threads
                    numprocesses=2, dispatcherport=8765
                    )
    server.start()
