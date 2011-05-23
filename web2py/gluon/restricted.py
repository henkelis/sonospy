#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This file is part of web2py Web Framework (Copyrighted, 2007-2010).
Developed by Massimo Di Pierro <mdipierro@cs.depaul.edu>.
License: GPL v2
"""

import sys
import cPickle
import traceback
import types
import os
import datetime
import logging

from utils import web2py_uuid
from storage import Storage
from http import HTTP

__all__ = ['RestrictedError', 'restricted', 'TicketStorage']


class TicketStorage(Storage):

    """
    defines the ticket object and the default values of its members (None)
    """

    def __init__(
        self,
        db=None,
        tablename='web2py_ticket'
        ):
        self.db = db
        self.tablename = tablename

    def store(self, request, ticket_id, ticket_data):
        """
        stores the ticket. It will figure out if this must be on disk or in db
        """
        if self.db:
            self._store_in_db(request, ticket_id, ticket_data)
        else:
            self._store_on_disk(request, ticket_id, ticket_data)

    def _store_in_db(self, request, ticket_id, ticket_data):
        table = self._get_table(self.db, self.tablename, request.application)
        table.insert(ticket_id=ticket_id,
                     ticket_data=cPickle.dumps(ticket_data),
                     created_datetime=request.now)
        logging.error('In FILE: %(layer)s\n\n%(traceback)s\n' % ticket_data)

    def _store_on_disk(self, request, ticket_id, ticket_data):
        cPickle.dump(ticket_data, self._error_file(request, ticket_id, 'wb'))

    def _error_file(self, request, ticket_id, mode, app=None):
        root = request.folder
        if app:
            root = os.path.join(os.path.join(root, '..'), app)
        errors_folder = os.path.join(root, 'errors') #.replace('\\', '/')
        return open(os.path.join(errors_folder, ticket_id), mode)

    def _get_table(self, db, tablename, app):
        tablename = tablename + '_' + app
        table = db.get(tablename, None)
        if table is None:
            db.rollback()   # not necessary but one day
                            # any app may store tickets on DB
            table = db.define_table(
                tablename,
                db.Field('ticket_id', length=100),
                db.Field('ticket_data', 'text'),
                db.Field('created_datetime', 'datetime'),
                )
        return table

    def load(
        self,
        request,
        app,
        ticket_id,
        ):
        if not self.db:
            return cPickle.load(self._error_file(request, ticket_id, 'rb', app))
        table=self._get_table(self.db, self.tablename, app)
        rows = self.db(table.ticket_id == ticket_id).select()
        if rows:
            return cPickle.loads(rows[0].ticket_data)
        return None


class RestrictedError:
    """
    class used to wrap an exception that occurs in the restricted environment
    below. the traceback is used to log the exception and generate a ticket.
    """

    def __init__(
        self,
        layer='',
        code='',
        output='',
        environment={},
        ):
        """
        layer here is some description of where in the system the exception
        occurred.
        """

        self.layer = layer
        self.code = code
        self.output = output
        if layer:
            self.traceback = traceback.format_exc()
        else:
            self.traceback = '(no error)'
        self.environment = environment

    def log(self, request):
        """
        logs the exception.
        """

        try:
            a = request.application
            d = {
                'layer': str(self.layer),
                'code': str(self.code),
                'output': str(self.output),
                'traceback': str(self.traceback),
                }
            fmt = '%Y-%m-%d.%H-%M-%S'
            f = '%s.%s.%s' % (request.client.replace(':', '_'),
                              datetime.datetime.now().strftime(fmt),
                              web2py_uuid())

            ticket_storage = TicketStorage(db=request.tickets_db)
            ticket_storage.store(request, f, d)
            return '%s/%s' % (a, f)
        except:
            logging.error(self.traceback)
            return None


    def load(self, request, app, ticket_id):
        """
        loads a logged exception.
        """
        ticket_storage = TicketStorage(db=request.tickets_db)
        d = ticket_storage.load(request, app, ticket_id)

        self.layer = d['layer']
        self.code = d['code']
        self.output = d['output']
        self.traceback = d['traceback']


def restricted(code, environment={}, layer='Unknown'):
    """
    runs code in environment and returns the output. if an exception occurs
    in code it raises a RestrictedError containing the traceback. layer is
    passed to RestrictedError to identify where the error occurred.
    """

    try:
        if type(code) == types.CodeType:
            ccode = code
        else:
            ccode = compile(code.replace('\r\n', '\n'), layer, 'exec')

        exec ccode in environment
    except HTTP:
        raise
    except Exception:
        # XXX Show exception in Wing IDE if running in debugger
        if __debug__ and 'WINGDB_ACTIVE' in os.environ:
            etype, evalue, tb = sys.exc_info()
            sys.excepthook(etype, evalue, tb)
        raise RestrictedError(layer, code, '', environment)
