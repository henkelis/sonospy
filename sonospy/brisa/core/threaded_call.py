# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Runs a call asynchronously and forwards the result/error to specified
callbacks.
"""

import thread
import threading


from brisa.core import log
from brisa.utils.safe_sleep import safe_sleep


def run_async_function(f, param_tuple=(), delay=0):
    """ Calls a function passing a parameters tuple. Note that this
    function returns nothing. If you want an asynchronous call with a
    monitor object, see brisa.core.threaded_call.run_async_call and
    brisa.core.threaded_call.ThreadedCall.

    @param f: function to be called
    @param param_tuple: tuple param for the function
    @param delay: wait time before calling the function
    """

#    print "########### run_async_function f: " + str(f) + "  active count: " + str(threading.active_count())
#    print "########### run_async_function param_tuple: " + str(param_tuple)
#    print "########### run_async_function delay: " + str(delay)
#    print "########### run_async_function threads: " + str(threading.enumerate())

    if delay > 0:
        # If delay is valid, schedule a timer for that call
        t = threading.Timer(delay, f, args=list(param_tuple))
        t.start()
    else:
        # Instant call
        thread.start_new_thread(f, param_tuple)


def run_async_call(function, success_callback=None, error_callback=None,
                   success_callback_cargo=None, error_callback_cargo=None,
                   delay=0, *args, **kwargs):
    """ Interface for running an asynchronous call.

    @param function: function to be called passing *args and **kwargs
    @param success_callback: called in case of success, receives call result
    @param error_callback: called in case of error, receives call result
    @param success_callback_cargo: success callback additional parameters
    @param error_callback_cargo: error callback additional parameters
    @param delay: time to be wait before performing the call
    @param args: arguments to the function
    @param kwargs: arguments to the function

    @type function: callable
    @type success_callback: callable
    @type error_callback: callable
    @type delay: float

    @return: object for monitoring the call
    @rtype: ThreadedCall
    """
    
#    print "########### run_async_call function: " + str(function) + "  active count: " + str(threading.active_count())
#    print "########### run_async_call delay: " + str(delay)
#    print "########### run_async_call threads: " + str(threading.enumerate())

    tcall = ThreadedCall(function, success_callback, error_callback,
                                 success_callback_cargo, error_callback_cargo,
                                 delay, *args, **kwargs)

    # Perform the call and return the object
    tcall.start()
    return tcall


class ThreadedCall(threading.Thread):
    """ This class runs a call asynchronously and forwards the result/error
    to specified callbacks.

    One can instantiate this class directly or use the run_async_call function
    located at package brisa.core.threaded_call.

    @param function: function to be called passing *args and **kwargs
    @param success_callback: called in case of success, receives call result
    @param error_callback: called in case of error, receives call result
    @param delay: time to be wait before performing the call
    @param args: arguments to the function
    @param kwargs: arguments to the function

    @type function: callable
    @type success_callback: callable
    @type error_callback: callable
    @type delay: float
    """

    def __init__(self, function, success_callback=None, error_callback=None,
                 success_callback_cargo=None, error_callback_cargo=None,
                 delay=None, *args, **kwargs):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.success_callback = success_callback
        self.success_callback_cargo = success_callback_cargo
        self.error_callback = error_callback
        self.error_callback_cargo = error_callback_cargo
        self.delay = delay
        self.result = None
        self.cancelled = False
        self.completed_flag = False
        self.completed = threading.Semaphore()

    def cleanup(self):
        """ Removes references to objects that may hurt garbage collection
        """
        self.function = lambda: None
        self.args = ()
        self.kwargs = {}
        self.success_callback = self.success_callback_cargo = None
        self.error_callback = self.error_callback_cargo = None

    def is_cancelled(self):
        return self.cancelled

    def run(self):
        """ Implementation of the call procedure.
        """
        if self.delay:
            # This runs in a thread. We can sleep here instead using time
            safe_sleep(self.delay)
            log.debug('sleeping for %d' % self.delay)

        if self.is_cancelled():
            self.cleanup()
            return

        try:
            log.debug('calling function')
            # Performing the call
            self.result = self.function(*self.args, **self.kwargs)
            log.debug('got result %s' % self.result)
            if self.success_callback:
                log.debug('forwarding to success_callback')
                self.success_callback(self.result, self.success_callback_cargo)

            self.set_completed()

        except Exception, e:
            print "async call exception: " + str(e)
            print "    function: " + str(self.function)
            print "    args: " + str(self.args)
            print "    kwargs: " + str(self.kwargs)
            print "    results: " + str(self.result)
            log.debug('exception happened (%s), forwarding...'
                      % e)
#                      % e.message)
            # Storing exception for handling
            self.result = e

            if self.error_callback:
                self.error_callback(self.error_callback_cargo, e)

            self.set_completed()

    def cancel(self):
        """ Cancel the call.
        """
        self.cancelled = True

    def stop(self):
        """ Prepares to stop.
        """
        if not self.is_completed():
            self.cancel()
        self.set_completed()

    def is_completed(self):
        """ Returns whether the call has been completed or not.
        """
        self.completed.acquire()
        res = self.completed_flag
        self.completed.release()
        return res

    def set_completed(self):
        """ Sets the call as completed. This should not be called directly.
        Use stop() instead.
        """
        self.completed.acquire()
        self.completed_flag = True
        self.completed.release()
        self.cleanup()
