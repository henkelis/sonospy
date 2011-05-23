# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>
# Copyright 2007 daemonize function at
#    http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/66012

""" Daemonize tool.
"""

import os
import sys

from brisa.core import log


def daemonize(stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0) # Exit first parent.
    except OSError, e:
        log.error("fork #1 failed: (%d) %s\n", e.errno, e.strerror)
        sys.exit(1)

    # Decouple from parent environment.
    os.chdir("/")
    os.umask(0)
    os.setsid()

    # Do second fork.
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)# Exit second parent.
    except OSError, e:
        log.error("fork #2 failed: (%d) %s\n", e.errno, e.strerror)
        sys.exit(1)

    # Redirect standard file descriptors.
    si = file(stdin, 'r')
    so = file(stdout, 'a+')
    se = file(stderr, 'a+', 0)
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())
