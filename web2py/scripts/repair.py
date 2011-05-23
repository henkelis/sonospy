#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os

"""
Written by Kacper Krupa
Refactored by Douglas Soares de Andrade

Re-creates app folders if they are missing
(such as when web2py donwloaded from a GIT repository)
"""

for app in os.listdir('applications'):

    # Get the application dir
    path = os.path.join('applications', app)

    if not os.path.split(app)[-1].startswith('.') and os.path.isdir(path):

        # lambda function just to save some spaces
        is_dir = lambda path: os.path.isdir(os.path.join(path, x))

        # Get the existing folders
        existing_dirs = set([x for x in os.listdir(path) if is_dir(path)])

        # Define web2py standard folders
        web2py_dirs = set(['sessions', 'errors', 'databases',
                           'tests', 'uploads',
                           'cache', 'languages',
                           'private', 'cron'])

        # Get the missing folders...
        dirs_to_create = web2py_dirs.difference(existing_dirs)

        # ...to create then
        for folder in dirs_to_create:
            print "Creating the folder '%s' in %s" % (folder, path)
            os.mkdir(os.path.join(path, folder))
