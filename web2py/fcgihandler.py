#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This is a handler for lighttpd+fastcgi
This file has to be in the PYTHONPATH
Put something like this in the lighttpd.conf file:

server.port = 8000
server.bind = '127.0.0.1'
server.event-handler = 'freebsd-kqueue'
server.modules = ('mod_rewrite', 'mod_fastcgi')
server.error-handler-404 = '/test.fcgi'
server.document-root = '/somewhere/web2py'
server.errorlog      = '/tmp/error.log'
fastcgi.server = ('.fcgi' =>
                    ('localhost' =>
                        ('min-procs' => 1,
                         'socket'    => '/tmp/fcgi.sock'
                        )
                    )
                 )
"""

LOGGING = False
SOFTCRON = False

import sys
import os

# Append the file path in python path
path = os.path.dirname(os.path.abspath(__file__))
if not path in sys.path:
    sys.path.append(path)
import gluon.main
import gluon.contrib.gateways.fcgi as fcgi

if LOGGING:
    application = gluon.main.wsgibase_with_logging
else:
    application = gluon.main.wsgibase

if SOFTCRON:
    from gluon.contrib.wsgihooks import ExecuteOnCompletion2, callback
    application = ExecuteOnCompletion2(application, callback)

fcgi.WSGIServer(application, bindAddress='/tmp/fcgi.sock').run()
