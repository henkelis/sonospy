#!/usr/bin/env python
# -*- coding: utf-8 -*-

##############################################################################
# Configuration parameters for Google App Engine 
##############################################################################
KEEP_CACHED = False    # request a dummy url every 10secs to force caching app
LOG_STATS = False      # log statistics
DEBUG = False          # debug mode
AUTO_RETRY = True      # force gae to retry commit on failure
##############################################################################
# All tricks in this file developed by Robin Bhattacharyya 
##############################################################################


import time
import os
import sys
import logging
import cPickle
import pickle
import wsgiref.handlers
import datetime


sys.path.append(os.path.dirname(__file__))
sys.modules['cPickle'] = sys.modules['pickle']


from gluon.settings import settings
from google.appengine.api.labs import taskqueue


if os.environ.get('SERVER_SOFTWARE', '').startswith('Devel'):
    (settings.web2py_runtime, settings.web2py_runtime_gae, DEBUG) = \
        ('gae:development', True, True)
else:
    (settings.web2py_runtime, settings.web2py_runtime_gae, DEBUG) = \
        ('gae:production', True, False)


import gluon.main


def log_stats(fun):
    """Function that will act as a decorator to make logging"""
    def newfun(env, res):
        """Log the execution time of the passed function"""        
        timer = lambda t: (t.time(), t.clock())
        (t0, c0) = timer(time)
        executed_function = fun(env, res)
        (t1, c1) = timer(time)
        log_info = """**** Request: %.2fms/%.2fms (real time/cpu time)"""
        log_info = log_info % ((t1 - t0) * 1000, (c1 - c0) * 1000)
        logging.info(log_info)
        return executed_function    
    return newfun


logging.basicConfig(level=35)


def wsgiapp(env, res):
    """Return the wsgiapp"""
    if env['PATH_INFO'] == '/_ah/queue/default':
        if KEEP_CACHED:
            delta = datetime.timedelta(seconds=10)
            taskqueue.add(eta=datetime.datetime.now() + delta)
        res('200 OK',[('Content-Type','text/plain')])
        return ['']
    return gluon.main.wsgibase(env, res)


if LOG_STATS or DEBUG:
    wsgiapp = log_stats(wsgiapp)


if AUTO_RETRY:
    from gluon.contrib.gae_retry import autoretry_datastore_timeouts
    autoretry_datastore_timeouts()


def main():
    """Run the wsgi app"""
    wsgiref.handlers.CGIHandler().run(wsgiapp)


if __name__ == '__main__':
    main()
