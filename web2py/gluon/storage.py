#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This file is part of web2py Web Framework (Copyrighted, 2007-2010).
Developed by Massimo Di Pierro <mdipierro@cs.depaul.edu>.
License: GPL v2

Provides:

- List; like list but returns None instead of IndexOutOfBounds
- Storage; like dictionary allowing also for `obj.foo` for `obj['foo']`
"""

import cPickle
import portalocker

__all__ = ['List', 'Storage', 'Settings', 'Messages',
           'load_storage', 'save_storage']


class List(list):
    """
    Like a regular python list but a[i] if i is out of bounds return None
    instead of IndexOutOfBounds
    """

    def __call__(self, i, default=None):
        try:
            return self[i]
        except IndexError:
            return default


class Storage(dict):

    """
    A Storage object is like a dictionary except `obj.foo` can be used
    in addition to `obj['foo']`.

        >>> o = Storage(a=1)
        >>> print o.a
        1

        >>> o['a']
        1

        >>> o.a = 2
        >>> print o['a']
        2

        >>> del o.a
        >>> print o.a
        None

    """

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            return None

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError, k:
            raise AttributeError, k

    def __repr__(self):
        return '<Storage ' + dict.__repr__(self) + '>'

    def __getstate__(self):
        return dict(self)

    def __setstate__(self, value):
        for (k, v) in value.items():
            self[k] = v

def load_storage(filename):
    fp = open(filename, 'rb')
    portalocker.lock(fp, portalocker.LOCK_EX)
    storage = cPickle.load(fp)
    portalocker.unlock(fp)
    fp.close()
    return Storage(storage)


def save_storage(storage, filename):
    fp = open(filename, 'wb')
    portalocker.lock(fp, portalocker.LOCK_EX)
    cPickle.dump(dict(storage), fp)
    portalocker.unlock(fp)
    fp.close()


class Settings(Storage):

    def __setattr__(self, key, value):
        if key != 'lock_keys' and self.get('lock_keys', None)\
             and not key in self:
            raise SyntaxError, 'setting key \'%s\' does not exist' % key
        if key != 'lock_values' and self.get('lock_values', None):
            raise SyntaxError, 'setting value cannot be changed: %s' % key
        self[key] = value


class Messages(Storage):

    def __init__(self, T):
        self['T'] = T

    def __setattr__(self, key, value):
        if key != 'lock_keys' and self.get('lock_keys', None)\
             and not key in self:
            raise SyntaxError, 'setting key \'%s\' does not exist' % key
        if key != 'lock_values' and self.get('lock_values', None):
            raise SyntaxError, 'setting value cannot be changed: %s' % key
        self[key] = value

    def __getattr__(self, key):
        value = self[key]
        if isinstance(value, str):
            return str(self['T'](value))
        return value
