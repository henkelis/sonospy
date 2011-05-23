#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Usage:
    python setup.py py2exe
"""

from distutils.core import setup
import py2exe
from gluon.import_all import base_modules, contributed_modules

setup(
  console=['web2py.py'],
  windows=[{'script':'web2py.py',
    'dest_base':'web2py_no_console',    #MUST NOT be just 'web2py' otherwise
                                        #it overrides the standard web2py.exe
    }],
  data_files=[
    'admin.w2p',
    'examples.w2p',
    'welcome.w2p',
    'ABOUT',
    'LICENSE',
    'VERSION',
    ],
  options={'py2exe': {
    'packages': contributed_modules,
    'includes': base_modules,
    }},
  )
