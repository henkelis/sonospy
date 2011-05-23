# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Glib2/gobject based reactor. Works trasparently with gobject-dependent
things, such as Dbus.
"""

from brisa.core.ireactor import ReactorInterface, EVENT_TYPE_READ, \
                                EVENT_TYPE_WRITE, EVENT_TYPE_EXCEPTION

import signal

try:
    import gobject
    __all__ = ('GLib2Reactor', )
except ImportError:
    __all__ = ()


class GLib2Reactor(ReactorInterface):

    _stop_funcs = []
    _start_funcs = []
    _main_loop = None

    def __init__(self, *args, **kwargs):
        ReactorInterface.__init__(self, *args, **kwargs)
        self._main_loop = gobject.MainLoop()
        signal.signal(signal.SIGTERM, self.main_quit)
        signal.signal(signal.SIGINT, self.main_quit)

    def add_timer(self, interval, callback, threshold=0):
        """ Add timer.

        @note: should return an ID assigned to the timer, so that it can be
               removed by rem_timer().
        """
        return gobject.timeout_add(int(interval*(10**3)), callback)

    def rem_timer(self, timer_id):
        """ Removes a timer.
        """
        return gobject.source_remove(timer_id)

    def add_fd(self, fd, event_callback, event_type):
        """ Adds a fd for watch.
        """
        condition = None
        if event_type & EVENT_TYPE_READ:
            condition = gobject.IO_IN | gobject.IO_PRI
        if event_type & EVENT_TYPE_WRITE:
            if not condition:
                condition = gobject.IO_OUT
            else:
                condition = condition | gobject.IO_OUT
        if event_type & EVENT_TYPE_EXCEPTION:
            if not condition:
                condition = gobject.IO_ERR
            else:
                condition = condition | gobject.IO_ERR

        return gobject.io_add_watch(fd, condition, event_callback)

    def rem_fd(self, fd_handler):
        """ Removes a fd from being watched.
        """
        return gobject.source_remove(fd_handler)

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
        self._main_loop.get_context().iteration()

    def main(self):
        """ Enters the RUNNING state by running the main loop until
        main_quit() is called.
        """
        self._main_call_before_start_funcs()
        try:
            self._main_loop.run()
        except KeyboardInterrupt:
            pass
        self._main_call_after_stop_funcs()

    def main_quit(self):
        """ Terminates the main loop.
        """
        self._main_loop.quit()

    def is_running(self):
        """ Returns True if the main loop is running
        """
        return self._main_loop.get_context().is_running()

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
