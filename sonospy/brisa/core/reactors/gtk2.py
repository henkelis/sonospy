# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Gtk2 based reactor.

BRisa can be easily embedded in applications with Gtk GUI's. For achieving that,
the FIRST THING you should do in your application is to install this reactor.

>>> from brisa.core.reactors import Gtk2Reactor
>>> reactor = Gtk2Reactor()

On the first time you call Gtk2Reactor() the reactor will be installed and
BRisa modules will adapt themselves to work with this reactor. Subsequent
calls to it will only retrieve the already installed reactor - so, any internal
module of your application can retrieve the reactor when you need to add timers
or file descriptors.

When starting up your application, instead of calling gtk.main(), you should
call reactor.main() (which is internally the same thing but you should use the
name "reactor" for avoiding confusions).

Calling reactor.main_quit() is also recommended instead of gtk.main_quit().
"""

from brisa.core.ireactor import ReactorInterface, EVENT_TYPE_READ, \
                                EVENT_TYPE_WRITE, EVENT_TYPE_EXCEPTION

from brisa.core import log


try:
    import gobject
    import gtk
    gtk.gdk.threads_init()
    __all__ = ('Gtk2Reactor', )
except ImportError:
    __all__ = ()

log = log.getLogger('reactor.gtk2')


class Gtk2Reactor(ReactorInterface):

    _stop_funcs = []
    _start_funcs = []

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

        ret = gobject.io_add_watch(fd, condition, event_callback)
        return ret

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
        gtk.main_iteration()

    def main(self):
        """ Enters the RUNNING state by running the main loop until
        main_quit() is called.
        """
        self._main_call_before_start_funcs()
        gtk.main()
        self._main_call_after_stop_funcs()

    def main_quit(self):
        """ Terminates the main loop.
        """
        gtk.main_quit()

    def is_running(self):
        """ Returns True if the main loop is running
        """
        return True if gtk.main_level() else False

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
