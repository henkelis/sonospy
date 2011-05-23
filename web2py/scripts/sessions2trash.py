#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import stat

SLEEP_MINUTES = 5
EXPIRATION_MINUTES = 60

path = os.path.join(request.folder, 'sessions')

while 1:
    now = time.time()

    for file in os.listdir(path):
        filename = os.path.join(path, file)
        t = os.stat(filename)[stat.ST_MTIME]

        if now - t > EXPIRATION_MINUTES * 60:
            os.unlink(filename)

    time.sleep(SLEEP_MINUTES * 60)
