#!/usr/bin/python
# -*- coding: utf-8 -*-

import socket
import os

#ip = '127.0.0.1'
ip = '0.0.0.0'
port = 8000
password = '<recycle>'
pid_filename = 'httpserver.pid'
log_filename = 'httpserver.log'
profiler_filename = None
ssl_certificate = ''
ssl_private_key = ''
numthreads = 10
#server_name = socket.gethostname()
server_name = 'sonospy'
request_queue_size = 5
timeout = 10
shutdown_timeout = 5
folder = os.getcwd()
extcron = None
nocron = None 
nogui = True
