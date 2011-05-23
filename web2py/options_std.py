#!/usr/bin/python
# -*- coding: utf-8 -*-

import socket
import os

ip = '127.0.0.1'
port = 8000
password = '<recycle>'  # ## <recycle> means use the previous password
pid_filename = 'httpserver.pid'
log_filename = 'httpserver.log'
profiler_filename = None
ssl_certificate = ''  # ## path to certificate file
ssl_private_key = ''  # ## path to private key file
numthreads = 10
server_name = socket.gethostname()
request_queue_size = 5
timeout = 10
shutdown_timeout = 5
folder = os.getcwd()
extcron = None
nocron = None 
