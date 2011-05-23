# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Provides a way of sleeping safely.
"""

from time import sleep as systemsleep
from time import time
import select
from brisa.core import log


def tsleep(timeout, death_fd):
    if death_fd:
        # Interruptable sleep
        read, dummy1, dummy2 = select.select([death_fd], [], [], timeout)
        if read:
            return False
    else:
        systemsleep(timeout)
    return True


def safe_sleep(t, death_fd=None):
    """ Implementation of a simple smart sleep function. This function makes
    sure the whole sleep time is slept properly.

    @param t: sleep time
    @type t: integer
    """
    if t < 1:
        # We don't need this precision for sleeping. time.sleep() gives almost
        # two decimal points of precision in sleeping
        return tsleep(t, death_fd)

    remaining = t

    # For an interval of 1600 seconds, the rate will be 1600/10.0 = 160 s.
    # For an interval of 10 seconds, the rate will be 10/10 = 1 second.
    rate = t / 10.0

    # Precision of 0.001. For example, if we have an interval of 1600 s,
    # then the precision will be 1600/1000 = 1.6 seconds.
    # For an interval of 10 seconds, the precision will be 10/1000 = 0.01 s.
    precision = t / 1000.0
    initial = time()

    # If remaining is in the interval (0, precision), then leave
    while remaining > precision:
        # Measure the interval (t0, t1) and estimate the remaining
        t0 = time()

        if rate < remaining:
            if not tsleep(rate, death_fd):
                return False
        else:
            # If rate is bigger than the remaining time, then just sleep the
            # remaining. We don't want to sleep more than the interval.
            if remaining > 0:
                if not tsleep(remaining, death_fd):
                    return False
            else:
                # If negative, already slept too much, so, set it to zero
                remaining = 0

        t1 = time()

        remaining -= (t1-t0)

    final = time()
    return True
