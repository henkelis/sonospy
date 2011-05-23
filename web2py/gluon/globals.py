#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This file is part of web2py Web Framework (Copyrighted, 2007-2010).
Developed by Massimo Di Pierro <mdipierro@cs.depaul.edu>.
License: GPL v2

Contains the classes for the global used variables:

- Request
- Response
- Session

"""

from storage import Storage, List
from compileapp import run_view_in
from streamer import streamer, stream_file_or_304_or_206, DEFAULT_CHUNK_SIZE
from xmlrpc import handler
from contenttype import contenttype
from html import xmlescape
from http import HTTP
from fileutils import up
from serializers import json
from settings import settings
from utils import web2py_uuid

import portalocker
import cPickle
import cStringIO
import stat
import datetime
import re
import Cookie
import os

regex_session_id = re.compile('^[\w\-]+$')

__all__ = ['Request', 'Response', 'Session']


class Request(Storage):

    """
    defines the request object and the default values of its members

    - env: environment variables, by gluon.main.wsgibase()
    - cookies
    - get_vars
    - post_vars
    - vars
    - folder
    - application
    - function
    - args
    - extension
    - now: datetime.datetime.today()

    """

    def __init__(self):
        self.wsgi = Storage() # hooks to environ and start_response
        self.env = Storage()
        self.cookies = Cookie.SimpleCookie()
        self.get_vars = Storage()
        self.post_vars = Storage()
        self.vars = Storage()
        self.folder = None
        self.application = None
        self.function = None
        self.args = List()
        self.extension = None
        self.now = datetime.datetime.today()


class Response(Storage):

    """
    defines the response object and the default values of its members
    response.write(   ) can be used to write in the output html
    """

    def __init__(self):
        self.status = 200
        self.headers = Storage()
        self.body = cStringIO.StringIO()
        self.session_id = None
        self.cookies = Cookie.SimpleCookie()
        self.postprocessing = []
        self.flash = ''           # used by the default view layout
        self.meta = Storage()     # used by web2py_ajax.html
        self.menu = []            # used by the default view layout
        self.files = []           # used by web2py_ajax.html
        self._vars = None
        self._caller = lambda f: f()
        self._view_environment = None
        self._custom_commit = None
        self._custom_rollback = None

    def write(self, data, escape=True):
        if not escape:
            self.body.write(str(data))
        else:
            self.body.write(xmlescape(data))

    def render(self, *a, **b):
        if len(a) > 2:
            raise SyntaxError, 'Response.render can be called with two arguments, at most'
        elif len(a) == 2:
            (view, self._vars) = (a[0], a[1])
        elif len(a) == 1 and isinstance(a[0], str):
            (view, self._vars) = (a[0], {})
        elif len(a) == 1 and hasattr(a[0], 'read') and callable(a[0].read):
            (view, self._vars) = (a[0], {})
        elif len(a) == 1 and isinstance(a[0], dict):
            (view, self._vars) = (None, a[0])
        else:
            (view, self._vars) = (None, {})
        self._vars.update(b)
        self._view_environment.update(self._vars)
        if view:
            import cStringIO
            (obody, oview) = (self.body, self.view)
            (self.body, self.view) = (cStringIO.StringIO(), view)
            run_view_in(self._view_environment)
            page = self.body.getvalue()
            self.body.close()
            (self.body, self.view) = (obody, oview)
        else:
            run_view_in(self._view_environment)
            page = self.body.getvalue()
        return page

    def stream(
        self,
        stream,
        chunk_size = DEFAULT_CHUNK_SIZE,
        request=None,
        ):
        """
        if a controller function::

            return response.stream(file, 100)

        the file content will be streamed at 100 bytes at the time
        """

        if isinstance(stream, (str, unicode)):
            stream_file_or_304_or_206(stream, request=request,
                                      headers=self.headers)

        # ## the following is for backward compatibility

        if hasattr(stream, 'name'):
            filename = stream.name
        else:
            filename = None
        keys = [item.lower() for item in self.headers]
        if filename and not 'content-type' in keys:
            self.headers['Content-Type'] = contenttype(filename)
        if filename and not 'content-length' in keys:
            try:
                self.headers['Content-Length'] = \
                    os.stat(filename)[stat.ST_SIZE]
            except OSError:
                pass
        if request and request.env.web2py_use_wsgi_file_wrapper:
            wrapped = request.env.wsgi_file_wrapper(stream, chunk_size)
        else:
            wrapped = streamer(stream, chunk_size=chunk_size)
        return wrapped

    def download(self, request, db, chunk_size = DEFAULT_CHUNK_SIZE, attachment=True):
        """
        example of usage in controller::

            def download():
                return response.download(request, db)

        downloads from http://..../download/filename
        """

        import os
        import contenttype as c
        if not request.args:
            raise HTTP(404)
        name = request.args[-1]
        items = re.compile('(?P<table>.*?)\.(?P<field>.*?)\..*')\
                           .match(name)
        if not items:
            raise HTTP(404)
        (t, f) = (items.group('table'), items.group('field'))
        field = db[t][f]
        (filename, stream) = field.retrieve(name)
        self.headers['Content-Type'] = c.contenttype(name)
        if attachment:
            self.headers['Content-Disposition'] = \
                "attachment; filename=%s" % filename
        return self.stream(stream, chunk_size = chunk_size, request=request)

    def json(self, data):
        return json(data)

    def xmlrpc(self, request, methods):
        """
        assuming::

            def add(a, b):
                return a+b

        if a controller function \"func\"::

            return response.xmlrpc(request, [add])

        the controller will be able to handle xmlrpc requests for
        the add function. Example::

            import xmlrpclib
            connection = xmlrpclib.ServerProxy('http://hostname/app/contr/func')
            print connection.add(3, 4)

        """

        return handler(request, self, methods)

class Session(Storage):

    """
    defines the session object and the default values of its members (None)
    """

    def connect(
        self,
        request,
        response,
        db=None,
        tablename='web2py_session',
        masterapp=None,
        migrate=True,
        ):
        self._unlock(response)
        if not masterapp:
            masterapp = request.application
        response.session_id_name = 'session_id_%s' % masterapp
        if not db:
            if response.session_id_name in request.cookies:
                response.session_id = \
                    request.cookies[response.session_id_name].value
                if regex_session_id.match(response.session_id):
                    response.session_filename = \
                        os.path.join(up(request.folder), masterapp,
                            'sessions', response.session_id)
                else:
                    response.session_id = None
            if response.session_id:
                try:
                    response.session_file = \
                        open(response.session_filename, 'rb+')
                    portalocker.lock(response.session_file,
                            portalocker.LOCK_EX)
                    self.update(cPickle.load(response.session_file))
                    response.session_file.seek(0)
                except:
                    self._unlock(response)
                    response.session_id = None
            if not response.session_id:
                response.session_id = '%s-%s'\
                     % (request.client.replace(':', '-').replace('.',
                        '-'), web2py_uuid())
                response.session_filename = \
                    os.path.join(up(request.folder), masterapp,
                                 'sessions', response.session_id)
                response.session_new = True
        else:
            if settings.web2py_runtime_gae:
                # in principle this could work without GAE
                request.tickets_db = db
            if masterapp == request.application:
                table_migrate = migrate
            else:
                table_migrate = False
            tname = tablename + '_' + masterapp
            table = db.get(tname, None)
            if table is None:
                table = db.define_table(
                    tname,
                    db.Field('locked', 'boolean', default=False),
                    db.Field('client_ip', length=64),
                    db.Field('created_datetime', 'datetime',
                             default=request.now),
                    db.Field('modified_datetime', 'datetime'),
                    db.Field('unique_key', length=64),
                    db.Field('session_data', 'blob'),
                    migrate=table_migrate,
                    )
            try:
                key = request.cookies[response.session_id_name].value
                (record_id, unique_key) = key.split(':')
                if record_id == '0':
                    raise Exception, 'record_id == 0'
                rows = db(table.id == record_id).select()
                if len(rows) == 0 or rows[0].unique_key != unique_key:
                    raise Exception, 'No record'

                 # rows[0].update_record(locked=True)

                session_data = cPickle.loads(rows[0].session_data)
                self.update(session_data)
            except Exception:
                record_id = None
                unique_key = web2py_uuid()
                session_data = {}
            response._dbtable_and_field = \
                (response.session_id_name, table, record_id, unique_key)
            response.session_id = '%s:%s' % (record_id, unique_key)
        response.cookies[response.session_id_name] = response.session_id
        response.cookies[response.session_id_name]['path'] = '/'
        if self.flash:
            (response.flash, self.flash) = (self.flash, None)

    def is_new(self):
        if self._start_timestamp:
            return False
        else:
            self._start_timestamp = datetime.datetime.today()
            return True

    def is_expired(self, seconds = 3600):
        now = datetime.datetime.today()
        if not self._last_timestamp or \
                self._last_timestamp + datetime.timedelta(seconds = seconds) > now:
            self._last_timestamp = now
            return False
        else:
            return True

    def secure(self):
        self._secure = True

    def forget(self, response=None):
        self._unlock(response)
        self._forget = True

    def _try_store_in_db(self, request, response):
        if not response._dbtable_and_field or not response.session_id\
             or self._forget:
            return
        (record_id_name, table, record_id, unique_key) = \
            response._dbtable_and_field
        dd = dict(locked=False, client_ip=request.env.remote_addr,
                  modified_datetime=request.now,
                  session_data=cPickle.dumps(dict(self)),
                  unique_key=unique_key)
        if record_id:
            table._db(table.id == record_id).update(**dd)
        else:
            record_id = table.insert(**dd)
        response.cookies[response.session_id_name] = '%s:%s'\
             % (record_id, unique_key)
        response.cookies[response.session_id_name]['path'] = '/'

    def _try_store_on_disk(self, request, response):
        if response._dbtable_and_field \
                or not response.session_id \
                or self._forget:
            self._unlock(response)
            return
        if response.session_new:
            # Tests if the session folder exists, if not, create it
            session_folder = os.path.dirname(response.session_filename)
            response.session_file = open(response.session_filename, 'wb')
            portalocker.lock(response.session_file, portalocker.LOCK_EX)

        cPickle.dump(dict(self), response.session_file)
        self._unlock(response)

    def _unlock(self, response):
        if response and response.session_file:
            try:
                portalocker.unlock(response.session_file)
                response.session_file.close()
                del response.session_file
            except: ### this should never happen but happens in Windows
                pass
