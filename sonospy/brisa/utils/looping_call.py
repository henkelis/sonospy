# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Performs repeated function calls.
"""
import inspect

from threading import Timer
from brisa.core import log, reactor


class LoopingCall(object):
    """ Class that performs repeated function calls in a interval.
    """

    msg_already_started = 'tried to start() LoopingCall when already started'
    msg_already_stopped = 'tried to stop() LoopingCall when already stopped'

    def __init__(self, f, *a, **kw):
        """ Constructor for the LoopingCall class.
        """
        
#        print "@@@@@@@@ LoopingCall init: " + str(self)
#        print "@@@@@@@@ LoopingCall init function: " + str(f)
        
        self._function = f
        self._args = a
        self._kwargs = kw
        self.interval = 0
        self.running = False
        self._callback_handler = None

    def is_running(self):
        """ Returns True if the looping call is active, otherwise False.
        """
        return self.running

    def start(self, interval, now=True):
        """ Starts the function calls in the interval specified. If now is
        False, it waits the interval before starting doing calls.

        @param interval: interval between calls
        @param now: whether it will start calling now or not

        @type interval: float
        @type now: boolean
        """
#        print "@@@@@@@@ LoopingCall start: " + str(self)
#        print "@@@@@@@@ LoopingCall start interval: " + str(interval)
#        print "@@@@@@@@ LoopingCall start now: " + str(now)

        if not self.is_running():
            self.interval = interval
            self.running = True
            assert interval != 0, ('(warning) starting LoopingCall with \
                                    interval %f' % self.interval)
            if now:
                self._register()
            else:
                Timer(interval, self._register).start()
        else:
            log.warning(self.msg_already_started)

    def stop(self):
        """ Stops the LoopingCall.
        """
        if self.running:
            self.running = False
            self._unregister()
        else:
            log.warning(self.msg_already_stopped)

    def destroy(self):
        if self.is_running():
            self.stop()
        self._cleanup()

    def _cleanup(self):
        self._function = lambda: None
        self._args = []
        self._kwargs = {}
        self._callback_handler = None

    def _register(self):
#        print "    _register()"
#        print "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
#        print "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
#        print "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
#        for (a,b,c,d,e,f) in inspect.stack():
#            print "@@@@@@@@@@: " + str(b) + " - " + str(c) + " - "+ str(d) + " - "+ str(e)
#        print "@@@@@@@@@@: " + str(self)
#        print "@@@@@@@@@@: " + str(self.interval)
#        print "@@@@@@@@@@: " + str(self._call)
#        print "@@@@@@@@@@ b: " + str(self._callback_handler)
        self._call()
#        if self._callback_handler != None:   # TODO: check this!
        self._callback_handler = reactor.add_timer(self.interval, self._call)
#        print "@@@@@@@@@@ a: " + str(self._callback_handler)
#        print "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
#        print "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
#        print "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"

    def _unregister(self):
#        print "r @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
#        print "r @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
#        print "r @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
#        for (a,b,c,d,e,f) in inspect.stack():
#            print "r @@@@@@@@@@: " + str(b) + " - " + str(c) + " - "+ str(d) + " - "+ str(e)
#        print "r @@@@@@@@@@: " + str(self)
#        print "r @@@@@@@@@@: " + str(self._callback_handler)
#        print "r @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
#        print "r @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
#        print "r @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"
#        if self._callback_handler != None:   # TODO: check this!
        reactor.rem_timer(self._callback_handler)

    def _call(self):
#        print "    _call()"
#        print "    _call() - running: " + str(self.running)
        if not self.running:
#            log.debug('LoopingCall on function %s cancelled' %
#                      str(self._function))
            return False

        self._function(*self._args, **self._kwargs)
        return True
