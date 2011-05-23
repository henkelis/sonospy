# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright (C) 2007-2009 Renato
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Provides a inheritable singleton class.
"""

__all__ = ('Singleton', )


class SingletonType(type):

    def __call__(cls, *args, **kwargs):
        if getattr(cls, '__instance__', None) is None:
            instance = cls.__new__(cls)
            instance.__init__(*args, **kwargs)
            cls.__instance__ = instance
        return cls.__instance__


class Singleton(object):
    __metaclass__ = SingletonType
    pass
