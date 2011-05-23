#!/usr/bin/env python
# -*- coding: utf-8 -*-

__name__ = 'WSGI_hooks'
__version__ = (0, 1, 1)
__author__ = 'Attila Csipa <web2py@csipa.in.rs>'

_generator_name = __name__ + '-' + '.'.join(map(str, __version__))

import sys
import os
import threading
import logging
import time
import gluon.contrib.cron


class Generator2:

    def __init__(
        self,
        generator,
        callback,
        environ,
        ):
        self.__generator = generator
        self.__callback = callback
        self.__environ = environ

    def __iter__(self):
        for item in self.__generator:
            yield item

    def close(self):
        if hasattr(self.__generator, 'close'):
            self.__generator.close()
        self.__callback(self.__environ)


class ExecuteOnCompletion2:

    def __init__(self, application, callback):
        self.__application = application
        self.__callback = callback

    def __call__(self, environ, start_response):
        try:
            result = self.__application(environ, start_response)
        except:
            self.__callback(environ)
            raise
        return Generator2(result, self.__callback, environ)


globalposttasks = []
localposttasks = []
localsema = threading.Semaphore()


class PostConnectionTask(threading.Thread):

    def __init__(self, env):
        threading.Thread.__init__(self)
        self.env = env


def callback(env):
    global globalposttasks
    global localposttasks

    for i in globalposttasks:
        try:
            i.start()
        except Exception, e:
            logging.error(
                'Callback execution failed for global PostConnectionTask: %s',
                e)

    localsema.acquire()
    tmptasklist = localposttasks
    localposttasks = []
    localsema.release()
    for i in tmptasklist:
        try:
            i.start()
        except Exception, e:
            logging.error(
                'Callback execution failed for PostConnectionTask: %s', e)

    if gluon.contrib.cron.crontype == 'soft':
        scron = gluon.contrib.cron.softcron(env)
        scron.start()
