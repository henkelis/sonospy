#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys

try:
    path = os.path.dirname(os.path.abspath(__file__))
except NameError:
    path=os.getcwd() # Seems necessary for py2exe

if not path in sys.path:
    sys.path.append(path)
os.chdir(path)

import gluon.import_all
import gluon.widget

# Start Web2py and Web2py cron service!
gluon.widget.start(cron=True)
