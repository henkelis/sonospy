#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This is a WSGI handler for Apache
Requires apache+mod_wsgi.

In httpd.conf put something like:

    LoadModule wsgi_module modules/mod_wsgi.so
    WSGIScriptAlias / /path/to/wsgihandler.py

"""

# change these parameters as required
LOGGING = False
SOFTCRON = False

import sys
import os
sys.path.insert(0, '')
path = os.path.dirname(os.path.abspath(__file__))
if not path in sys.path:
    sys.path.append(path)
os.chdir(path)
import gluon.main

if LOGGING:
    application = gluon.main.wsgibase_with_logging
else:
    application = gluon.main.wsgibase

if SOFTCRON:
    from gluon.contrib.wsgihooks import ExecuteOnCompletion2, callback
    application = ExecuteOnCompletion2(application, callback)
