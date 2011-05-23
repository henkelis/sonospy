#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import time
import stat
import datetime

from gluon.utils import md5_hash
from gluon.restricted import RestrictedError

SLEEP_MINUTES = 5
DB_URI = 'sqlite://tickets.db'
ALLOW_DUPLICATES = True

path = os.path.join(request.folder, 'errors')

db = SQLDB(DB_URI)
db.define_table('ticket', SQLField('app'), SQLField('name'),
                SQLField('date_saved', 'datetime'), SQLField('layer'),
                SQLField('traceback', 'text'), SQLField('code', 'text'))

hashes = {}

while 1:
    for file in os.listdir(path):
        filename = os.path.join(path, file)

        if not ALLOW_DUPLICATES:
            file_data = open(filename, 'r').read()
            key = md5_hash(file_data)

            if key in hashes:
                continue

            hashes[key] = 1

        error = RestrictedError()
        error.load(request, request.application, filename)

        modified_time = os.stat(filename)[stat.ST_MTIME]
        modified_time = datetime.datetime.fromtimestamp(modified_time)

        db.ticket.insert(app=request.application,
                         date_saved=modified_time,
                         name=file,
                         layer=error.layer,
                         traceback=error.traceback,
                         code=error.code)

        os.unlink(filename)

    db.commit()
    time.sleep(SLEEP_MINUTES * 60)
