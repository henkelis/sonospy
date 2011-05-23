# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Defines a interface to be implemented by reactors. Also defines constants to
be used by reactors.
"""


__all__ = ('ReactorInterface', 'REACTOR_STATE_STOPPED',
           'REACTOR_STATE_RUNNING', 'EVENT_TYPE_READ', 'EVENT_TYPE_WRITE',
           'EVENT_TYPE_EXCEPTION', 'ReactorAlreadyRunningException')

from brisa.core.singleton import Singleton


# Reactor states

REACTOR_STATE_STOPPED, REACTOR_STATE_RUNNING = range(2)

# Event flags may be combined with the OR operator

EVENT_TYPE_READ, EVENT_TYPE_WRITE, EVENT_TYPE_EXCEPTION = (1, 2, 4)


# Reactor Exceptions


class ReactorAlreadyRunningException(Exception):
    pass


class ReactorInterface(Singleton):
    """ Basic reactor interface capable of handling fds and timers.
    """

    state = REACTOR_STATE_STOPPED

    def __init__(self):
        import brisa.core
        import sys

        if 'brisa.core.reactor' in sys.modules:
            from brisa.core import log
            log.warning('reactor already installed')

        brisa.core.reactor = self
        sys.modules['brisa.core.reactor'] = self

    def add_timer(self, interval, callback, threshold):
        """ Add timer.

        @note: should return an ID assigned to the timer, so that it can be
               removed by rem_timer().
        """
        raise NotImplementedError('ReactorInterface.add_timer method not'\
                                  ' implemented.')

    def rem_timer(self, timer_id):
        """ Removes a timer.
        """
        raise NotImplementedError('ReactorInterface.rem_timer method not'\
                                  ' implemented.')

    def add_fd(self, fd, event_callback, event_type):
        """ Adds a fd for watch.
        """
        raise NotImplementedError('ReactorInterface.add_fd method not'\
                                  ' implemented.')

    def rem_fd(self, fd):
        """ Removes a fd from being watched.
        """
        raise NotImplementedError('ReactorInterface.rem_fd method not'\
                                  ' implemented.')

    def add_after_stop_func(self, func):
        """ Registers a function to be called before entering the STOPPED
        state.
        """
        raise NotImplementedError('ReactorInterface.add_after_stop_func'\
                                  ' method not implemented.')

    def rem_after_stop_func(self, func):
        """ Removes a registered function.
        """
        raise NotImplementedError('ReactorInterface.rem_after_stop_func'\
                                  ' method not implemented.')

    def add_before_start_func(self, func):
        """ Registers a function to be called before entering the RUNNING
        state.
        """
        raise NotImplementedError('ReactorInterface.add_before_start_func'\
                                  ' method not implemented.')

    def rem_before_start_func(self, func):
        """ Removes a registered function.
        """
        raise NotImplementedError('ReactorInterface.rem_before_start_func'\
                                  ' method not implemented.')

    def main_loop_iterate(self):
        """ Runs a single iteration of the main loop. Reactor enters the
        RUNNING state while this method executes.
        """
        raise NotImplementedError('ReactorInterface.main_loop_iterate'\
                                  ' method not implemented.')

    def main(self):
        """ Enters the RUNNING state by running the main loop until
        main_quit() is called.
        """
        raise NotImplementedError('ReactorInterface.main'\
                                  ' method not implemented.')

    def main_quit(self):
        """ Terminates the main loop.
        """
        raise NotImplementedError('ReactorInterface.main_quit'\
                                  ' method not implemented.')

    def is_running(self):
        """ Returns True if the main loop is running. Otherwise returns False.
        """
        raise NotImplementedError('ReactorInterface.is_running'\
                                  ' method not implemented.')
