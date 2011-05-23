# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Error presentation wrapper.
"""

import types
import traceback
import sys

global count
count = 0


class NoCurrentExceptionError(Exception):
    pass


class Failure(object):
    pickled = 0
    stack = None
    frames = None

    def __init__(self, exc_value=None, exc_type=None, exc_tb=None):
        global count
        count = count + 1
        self.count = count
        self.type = self.value = tb = None

        if exc_value is None:
            self.type, self.value, tb = sys.exc_info()
            if self.type is None:
                raise NoCurrentExceptionError()
            stackOffset = 1

    def printTraceback(self, file=None, elideFrameworkCode=0,
                       detail='default'):
        """Emulate Python's standard error reporting mechanism. """
        if file is None:
            return
        w = file.write

        if detail == 'verbose':
            w('*--- Failure #%d%s---\n' % (self.count,
                                          (self.pickled and ' (pickled) ') \
                                           or ' '))
        elif detail == 'brief':
            hasFrames = 'Traceback (failure with no frames)'
            w("%s: %s: %s\n" % (hasFrames, self.type, self.value))
        else:
            w('Traceback (most recent call last):\n')

        if not detail == 'brief':
            w("Failure: ")
            w("%s: %s\n" % (qual(self.type), safe_str(self.value)))
        if isinstance(self.value, Failure):
            file.write(" (chained Failure)\n")
            self.value.printTraceback(file, elideFrameworkCode, detail)
        if detail == 'verbose':
            w('*--- End of Failure #%d ---\n' % self.count)

    def printBriefTraceback(self, file=None, elideFrameworkCode=0):
        self.printTraceback(file, elideFrameworkCode, detail='brief')

    def printDetailedTraceback(self, file=None, elideFrameworkCode=0):
        self.printTraceback(file, elideFrameworkCode, detail='verbose')


def qual(c):
    """Return full import path of a class."""
    return c.__module__ + '.' + c.__name__


def safe_str(o):
    try:
        return str(o)
    except:
        strExc = '\n'.join(traceback.format_exception(*sys.exc_info()))
        clsName = _determineClassName(o)
        obId = id(o)
        return '<%s instance at %s with str error %s>' % (
            clsName, obId, strExc)


def _determineClass(x):
    try:
        return x.__class__
    except:
        return type(x)


def _determineClassName(x):
    c = _determineClass(x)
    try:
        return c.__name__
    except:
        try:
            return str(c)
        except:
            return '<BROKEN CLASS AT %s>' % id(c)
