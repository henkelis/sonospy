# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Default select-based reactor.
"""

__all__ = ('SelectReactor', )

import os
import time
import random
import select
import socket
import signal

from errno import EINTR, EBADF

from brisa.core import log
from brisa.core.ireactor import *


class Timer(object):
    """ Timer class.
    """

    def __init__(self, callback, timeout_rel, timeout_abs, threshold):
        """ Constructor for the Timer class

        @param callback: function to be called
        @param timeout_rel: seconds from now to sleep before the call
        @param timeout_abs: seconds since epoch when the call is scheduled
        @param threshold: lower acceptable bound for timeout_abs precision
        """
        self.callback = callback
        self.timeout_rel = timeout_rel
        self.timeout_abs = timeout_abs
        self.threshold = threshold

    def __call__(self):
        """ Performs the callback.
        """
        self.callback()

    def update_abs_timeout(self):
        """ Updates absolute timeout based on the time now and the relative
        timeout specified.
        """
        self.timeout_abs = self.timeout_rel + time.time()

    def __str__(self):
        """ String representation of the class.
        """
        return '<Timer callback=%s, timeout_rel=%s, timeout_abs=%s' \
               ', threshold=%s>' % (str(self.callback), str(self.timeout_rel),
               str(self.timeout_abs), str(self.threshold))


class SelectReactor(ReactorInterface):

    _timers = {}
    _read_fds = {}
    _write_fds = {}
    _excpt_fds = {}
    _stop_funcs = []
    _start_funcs = []

    state = REACTOR_STATE_STOPPED

    def __init__(self, *args, **kwargs):
        ReactorInterface.__init__(self, *args, **kwargs)
        p = os.pipe()
        self._death_pipe_w = os.fdopen(p[1], 'w')
        self._death_pipe_r = os.fdopen(p[0], 'r')
        if os.name == 'posix':
            self.add_fd(self._death_pipe_r, lambda a,b: False,
                        EVENT_TYPE_READ)
        signal.signal(signal.SIGTERM, self._main_sig_quit)
        signal.signal(signal.SIGINT, self._main_sig_quit)

    def add_timer(self, interval, callback, threshold=0.01):
        """ Adds a timer.

        @param interval: interval to sleep between calls
        @param callback: function to be called
        @param threshold: lower bound for the time precision

        @type interval: integer
        @type callback: callable
        @type threshold: float

        @return: unique ID for the callback
        @rtype: integer
        """
        id = random.randint(-50000, 50000)

        while id in self._timers:
            id = random.randint(-50000, 50000)

        self._timers[id] = Timer(callback, interval,interval + time.time(),
                                 threshold)
        return id

    def rem_timer(self, id):
        """ Removes a timed callback given its id.

        @param id: unique ID returned by add_timer()
        @type id: integer
        """
        if not id: return
        try:
            self._timers.pop(id)
        except KeyError:
            raise KeyError('No such timeout callback registered with id %d' %
                           id)

    def add_fd(self, fd, evt_callback, evt_type, data=None):
        """ Adds a fd for watch.

        @param fd: file descriptor
        @param evt_callback: callback to be called
        @param evt_type: event type to be watched on this fd. An OR combination
                         of EVENT_TYPE_* flags.
        @param data: data to be forwarded to the callback

        @type fd: file
        @type evt_callback: callable
        @type evt_type: integer
        @type data: any
        """
        if evt_type & EVENT_TYPE_READ:
            log.debug('Added fd %s watch for READ events' % str(fd))
            self._read_fds[fd] = evt_callback
        if evt_type & EVENT_TYPE_WRITE:
            log.debug('Added fd %s watch for WRITE events' % str(fd))
            self._write_fds[fd] = evt_callback
        if evt_type & EVENT_TYPE_EXCEPTION:
            log.debug('Added fd %s watch for EXCEPTION events' % str(fd))
            self._excpt_fds[fd] = evt_callback

        return fd

    def rem_fd(self, fd):
        """ Removes a fd from being watched.

        @param fd: file descriptor to be removed

        @type fd: file
        """
        for d in (self._read_fds, self._write_fds, self._excpt_fds):
            d.pop(fd, None)

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
        """ Registers a function to be called before entering the RUNNING
        state.

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

    def main(self):
        """ Enters the RUNNING state by running the main loop until
        main_quit() is called.
        """
        if self.state != REACTOR_STATE_STOPPED:
            raise ReactorAlreadyRunningException('main() called twice or '\
                'together with main_loop_iterate()')

        self.state = REACTOR_STATE_RUNNING
        log.info('Preparing main loop')
        self._main_call_before_start_funcs()
        log.info('Entering main loop')
        while self.state == REACTOR_STATE_RUNNING:
            try:
                if not self.main_loop_iterate():
                    break
            except:
                break
        log.info('Preparing to exit main loop')
        self._main_call_before_stop_funcs()
        log.info('Exited main loop')

    def main_quit(self):
        """ Terminates the main loop.
        """
        self.state = REACTOR_STATE_STOPPED
        self._death_pipe_w.close()
        log.debug('Writing pipe of death')

    def main_loop_iterate(self):
        """ Runs a single iteration of the main loop. Reactor enters the
        RUNNING state while this method executes.
        """
        if not self._main_select():
            self._main_trigger_timers()
            return False
        if not self._main_trigger_timers():
            return False
        return True

    def is_running(self):
        return bool(self.state)

    def _main_select(self):
        """ Selects and process events.

        @return: True if no exception was raised. False if an exception was
                 raised, meaning that we recommend another _main_select()
        @rtype: boolean
        """
        try:
            revt, wevt, eevt = select.select(self._read_fds.keys(),
                                             self._write_fds.keys(),
                                             self._excpt_fds.keys(),
                                             self._get_min_timeout())
            if not self._main_process_events(revt, wevt, eevt):
                return False
        # Fix problems with problematic file descriptors
        except ValueError, v:
            log.debug('Main loop ValueError: %s' % str(v))
            self._main_cleanup_fds()
        except TypeError, t:
            log.debug('Main loop TypeError %s' % str(t))
            self._main_cleanup_fds()
        except (select.error, IOError), s:
            if s.args[0] in (0, 2):
                if not ((not self._read_fds) and (not self._write_fds)):
                    raise
            elif s.args[0] == EINTR:
                pass
            elif s.args[0] == EBADF:
                self._main_cleanup_fds()
        except socket.error, s:
            if s.args[0] == EBADF:
                self._main_cleanup_fds()
        except KeyboardInterrupt:
            return False
        return True

    def _main_process_events(self, revt, wevt, eevt):
        for read in revt:
            if read == self._death_pipe_w:
                log.debug('Pipe of death read')
                self._read_fds.pop(read)
                return False
            if read not in self._read_fds:
                continue
            try:
                log.debug('Read event on %s, calling %s', read,
                          self._read_fds[read])
                if not self._read_fds[read](read, EVENT_TYPE_READ):
                    # Returned False, remove it
                    self._read_fds.pop(read)
            except Exception, e:
                log.debug('Exception %s raised when handling a READ'\
                          ' event on file %s', e, read)
        for write in wevt:
            if write not in self._write_fds:
                continue
            try:
                log.debug('Write event on %s, calling %s', write,
                          self._write_fds[write])
                if not self._write_fds[write](write, EVENT_TYPE_WRITE):
                    self._write_fds.pop(write)
            except Exception, e:
                log.debug('Exception %s raised when handling a WRITE'\
                          ' event on file %s', e, write)
        for excpt in eevt:
            if excpt not in self._excpt_fds:
                continue
            try:
                log.debug('Exception event on %s, calling %s', excpt,
                          self._excpt_fds[excpt])
                if not self._excpt_fds[excpt](excpt, EVENT_TYPE_EXCEPTION):
                    self._excpt_fds.pop(excpt)
            except Exception, e:
                log.debug('Exception %s raised when handling a EXCEPTION'\
                          ' event on file %s', e, excpt)
        return True

    def _main_trigger_timers(self):
        """ Triggers the timers that are ready.
        """
        for callback in self._timers.values():
            if callback.timeout_abs - callback.threshold < time.time():
                log.debug('Callback ready: %s' % str(callback))
                if self.is_running():
                    try:
                        callback()
                    except KeyboardInterrupt, k:
                        # Ctrl-C would be ignored
                        return False
                    except:
                        log.error('Error while processing timer %s' %
                                  str(callback))
                # Update the absolute timeout anyways
                callback.update_abs_timeout()
        return True

    def _main_cleanup_fds(self):
        """ Cleans up problematic fds.
        """
        log.debug('Problematic fd found. Cleaning up...')

        for d in [self._read_fds, self._write_fds, self._excpt_fds]:
            for s in d.keys():
                try:
                    select.select([s], [s], [s], 0)
                except Exception, e:
                    log.debug('Removing problematic fd: %s' % str(s))
                    d.pop(s)

    def _get_min_timeout(self):
        """ Returns the minimum timeout among registered timers.
        """
        min = 0
        for callback in self._timers.values():
            if min == 0 or callback.timeout_rel < min:
                min = callback.timeout_rel
        return min

    def _main_call_before_stop_funcs(self):
        for cb in self._stop_funcs:
            cb()

    def _main_call_before_start_funcs(self):
        for cb in self._start_funcs:
            cb()

    def _main_sig_quit(self, sig, frame):
        self.main_quit()
