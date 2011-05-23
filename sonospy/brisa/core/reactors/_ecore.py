# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Ecore based reactor.
"""

from brisa.core import log
from brisa.core.ireactor import *


try:
    import ecore
    __all__ = ('EcoreReactor', )
except ImportError:
    __all__ = ()

log = log.getLogger('reactor.ecore')


class EcoreReactor(ReactorInterface):

    _stop_funcs = []
    _start_funcs = []

    def add_timer(self, interval, callback, threshold=0):
        """ Add timer.

        @note: should return an ID assigned to the timer, so that it can be
               removed by rem_timer().
        """
        return ecore.Timer(interval, callback)

    def rem_timer(self, timer):
        """ Removes a timer.
        """
        return timer.delete()

    def add_fd(self, fd, event_callback, event_type):
        """ Adds a fd for watch.
        """
        condition = None
        if event_type & EVENT_TYPE_READ:
            condition = ecore.ECORE_FD_READ
        if event_type & EVENT_TYPE_WRITE:
            if not condition:
                condition = ecore.ECORE_FD_WRITE
            else:
                condition = condition | ecore.ECORE_FD_WRITE
        if event_type & EVENT_TYPE_EXCEPTION:
            if not condition:
                condition = ecore.ECORE_FD_ERROR
            else:
                condition = condition | ecore.ECORE_FD_ERROR

        return ecore.fd_handler_add(fd, condition, event_callback)

    def rem_fd(self, fd_handler):
        """ Removes a fd from being watched.
        """
        return fd_handler.delete()

    def add_after_stop_func(self, func):
        """ Registers a function to be called before entering the STOPPED
        state.

        @param func: function
        @type func: callable
        """
        if func not in self._stop_funcs:
            self._stop_funcs.append(func)

    def rem_after_stop_func(self, func):
        """ Removes a registered function.

        @param func: function
        @type func: callable
        """
        if func in self._stop_funcs:
            self._stop_funcs.remove(func)

    def add_before_start_func(self, func):
        """ Registers a function to be called before starting the main loop.

        @param func: function
        @type func: callable
        """
        if func not in self._start_funcs:
            self._start_funcs.append(func)

    def rem_before_start_func(self, func):
        """ Removes a registered function.

        @param func: function
        @type func: callable
        """
        if func in self._start_funcs:
            self._start_funcs.remove(func)

    def main_loop_iterate(self):
        """ Runs a single iteration of the main loop. Reactor enters the
        RUNNING state while this method executes.
        """
        ecore.main_loop_iterate()

    def main(self):
        """ Enters the RUNNING state by running the main loop until
        main_quit() is called.
        """
        self._main_call_before_start_funcs()
        self.state = REACTOR_STATE_RUNNING
        ecore.main_loop_begin()
        self.state = REACTOR_STATE_STOPPED
        self._main_call_after_stop_funcs()

    def main_quit(self):
        """ Terminates the main loop.
        """
        ecore.main_loop_quit()

    def is_running(self):
        """ Returns True if the main loop is running
        """
        return True if self.state else False

    def _main_call_after_stop_funcs(self):
        """ Calls registered functions to be called after the main loop is
        stopped.
        """
        for cb in self._stop_funcs:
            cb()

    def _main_call_before_start_funcs(self):
        """ Call registered functions to be called before starting the main
        loop.
        """
        for cb in self._start_funcs:
            cb()
