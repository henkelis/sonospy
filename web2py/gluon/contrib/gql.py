#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This file is part of web2py Web Framework (Copyrighted, 2007)
Developed by Massimo Di Pierro <mdipierro@cs.depaul.edu> and
Robin B <robi123@gmail.com>
License: GPL v2
"""

__all__ = ['GQLDB', 'Field']

import re
import sys
import os
import types
import cPickle
import datetime
import thread
import cStringIO
import csv
import copy
import socket
import logging
import gluon.validators as validators
import gluon.sqlhtml as sqlhtml
import gluon.sql
from new import classobj
from google.appengine.ext import db as gae

Row = gluon.sql.Row
Rows = gluon.sql.Rows
Reference = gluon.sql.Reference

SQLCallableList = gluon.sql.SQLCallableList

table_field = re.compile('[\w_]+\.[\w_]+')

SQL_DIALECTS = {'google': {
    'boolean': gae.BooleanProperty,
    'string': gae.StringProperty,
    'text': gae.TextProperty,
    'password': gae.StringProperty,
    'blob': gae.BlobProperty,
    'upload': gae.StringProperty,
    'integer': gae.IntegerProperty,
    'double': gae.FloatProperty,
    'date': gae.DateProperty,
    'time': gae.TimeProperty,
    'datetime': gae.DateTimeProperty,
    'id': None,
    'reference': gae.IntegerProperty,
    'lower': None,
    'upper': None,
    'is null': 'IS NULL',
    'is not null': 'IS NOT NULL',
    'extract': None,
    'left join': None,
    }}


def cleanup(text):
    if re.compile('[^0-9a-zA-Z_]').findall(text):
        raise SyntaxError, \
            'only [0-9a-zA-Z_] allowed in table and field names, received %s' \
            % text
    return text


def assert_filter_fields(*fields):
    for field in fields:
        if isinstance(field, (Field, Expression)) \
                and field.type in ['text', 'blob']:
            raise SyntaxError, \
                  'AppEngine does not index by: %s' % field.type


def dateobj_to_datetime(obj):

    # convert dates, times to datetimes for AppEngine

    if isinstance(obj, datetime.datetime):
        pass
    elif isinstance(obj, datetime.date):
        obj = datetime.date(obj.year, obj.month, obj.day)
    elif isinstance(obj, datetime.time):
        obj = datetime.datetime(
            1970, 1, 1, obj.hour, obj.minute, obj.second, obj.microsecond)
    return obj


class GQLDB(gluon.sql.SQLDB):

    """
    an instance of this class represents a database connection

    Example::

       db=GQLDB()
       db.define_table('tablename', Field('fieldname1'),
                                   Field('fieldname2'))
    """

    def __init__(self):
        self._dbname = 'gql'
        self['_lastsql'] = ''
        self.tables = SQLCallableList()
        self._translator = SQL_DIALECTS['google']
        self._db_codec = 'UTF-8'

    def define_table(
        self,
        tablename,
        *fields,
        **args
        ):
        if not fields and tablename.count(':'):
            (tablename, fields) = autofields(self, tablename)

        tablename = cleanup(tablename)
        if tablename in dir(self) or tablename[0] == '_':
            raise SyntaxError, 'invalid table name: %s' % tablename
        if tablename in self.tables:
            raise SyntaxError, 'table already defined: %s'  % tablename
        t = self[tablename] = Table(self, tablename, *fields)
        self.tables.append(tablename)
        t._create_references()
        t._create()
        t._format = args.get('format', None)
        return t

    def __call__(self, where=''):
        if not where:
            where = ''
        return Set(self, where)

    def commit(self):
        pass

    def rollback(self):
        pass

class SQLALL(object):

    def __init__(self, table):
        self.table = table


class Table(gluon.sql.Table):

    """
    an instance of this class represents a database table
    Example:

    db=GQLDB()
    db.define_table('users', Field('name'))
    db.users.insert(name='me') # print db.users._insert(...) to see SQL
    db.users.drop()
    """

    def __init__(
        self,
        db,
        tablename,
        *fields
        ):
        new_fields = [ Field('id', 'id') ]
        for field in fields:
            if hasattr(field,'_db'):
                field = copy.copy(field)
            if isinstance(field, gluon.sql.Field):
                d=field.__dict__
                field=Field('tmp')
                field.__dict__.update(d)
            if isinstance(field, Field):
                new_fields.append(field)
            elif isinstance(field, Table):
                new_fields += [copy.copy(field[f]) for f in field.fields if f != 'id']
            else:
                raise SyntaxError, 'define_table argument \'%s\'is not a Field'%field
        fields = new_fields
        self._db = db
        self._tablename = tablename
        self.fields = SQLCallableList()
        self.virtualfields = []
        fields = list(fields)

        # ## GAE Only, make sure uplodaded files go in datastore

        for field in fields:
            if isinstance(field, Field) and field.type == 'upload'\
                 and field.uploadfield == True:
                tmp = field.uploadfield = '%s_blob' % field.name
                fields.append(self._db.Field(tmp, 'blob', default=''))

        for field in fields:
            self.fields.append(field.name)
            self[field.name] = field
            field._tablename = self._tablename
            field._table = self
            field._db = self._db
            if field.requires == '<default>':
                field.requires = gluon.sql.sqlhtml_validators(field)
        self.ALL = SQLALL(self)

    def _create(self):
        fields = []
        myfields = {}
        for k in self.fields:
            field = self[k]
            attr = {}
            if isinstance(field.type, gluon.sql.SQLCustomType):
                ftype = self._db._translator[field.type.native or field.type.type](**attr)
            elif isinstance(field.type, gae.Property):
                ftype = field.type
            elif field.type[:2] == 'id':
                continue
            elif field.type[:10] == 'reference ':
                if field.notnull:
                    attr = dict(required=True)
                referenced = field.type[10:].strip()
                ftype = self._db._translator[field.type[:9]](self._db[referenced])
            elif not field.type in self._db._translator\
                 or not self._db._translator[field.type]:
                raise SyntaxError, 'Field: unknown field type: %s' % field.type
            else:
                ftype = self._db._translator[field.type](**attr)
            myfields[field.name] = ftype
        self._tableobj = classobj(self._tablename, (gae.Model, ),
                                  myfields)
        return None

    def create(self):

        # nothing to do, here for backward compatibility

        pass

    def drop(self, mode = None):

        self.truncate(mode = mode)

    def truncate(self, mode = None):

        # nothing to do, here for backward compatibility

        self._db(self.id > 0).delete()

    def bulk_insert(self, *items):
        parsed_items = []
        for item in items:
            fields = {}
            for field in self.fields:
                if not field in item and self[field].default != None:
                    fields[field] = self[field].default
                elif not field in item and self[field].compute != None:
                    fields[field] = self[field].compute(item)
                if field in item:
                    fields[field] = obj_represent(item[field],
                                                  self[field].type, self._db)
            parsed_items.append(fields)
        gae.put(parsed_items)
        return True

    def insert(self, **fields):
        self._db['_lastsql'] = 'insert'
        for field in self.fields:
            if not field in fields and self[field].default != None:
                fields[field] = self[field].default
            elif not field in fields and self[field].compute != None:
                fields[field] = self[field].compute(fields)
            if field in fields:
                fields[field] = obj_represent(fields[field],
                        self[field].type, self._db)
        tmp = self._tableobj(**fields)
        tmp.put()
        rid = Reference(tmp.key().id())
        (rid._table, rid._record) = (self, None)
        return rid


class Expression(object):

    def __init__(
        self,
        name,
        type='string',
        db=None,
        ):
        (self.name, self.type, self._db) = (name, type, db)

    def __str__(self):
        return self.name

    def __or__(self, other):  # for use in sortby
        assert_filter_fields(self, other)
        return Expression(self.name + '|' + other.name, None, None)

    def __invert__(self):
        assert_filter_fields(self)
        return Expression('-' + self.name, self.type, None)

    # for use in Query

    def __eq__(self, value):
        return Query(self, '=', value)

    def __ne__(self, value):
        return Query(self, '!=', value)

    def __lt__(self, value):
        return Query(self, '<', value)

    def __le__(self, value):
        return Query(self, '<=', value)

    def __gt__(self, value):
        return Query(self, '>', value)

    def __ge__(self, value):
        return Query(self, '>=', value)

    def belongs(self, value):
        return Query(self, 'IN', value)

    # def like(self, value): return Query(self, ' LIKE ', value)
    # for use in both Query and sortby

    def __add__(self, other):
        return Expression('%s+%s' % (self, other), 'float', None)

    def __sub__(self, other):
        return Expression('%s-%s' % (self, other), 'float', None)

    def __mul__(self, other):
        return Expression('%s*%s' % (self, other), 'float', None)

    def __div__(self, other):
        return Expression('%s/%s' % (self, other), 'float', None)


class Field(Expression, gluon.sql.Field):

    """
    an instance of this class represents a database field

    example::

        a=Field(name, 'string', length=32, required=False, default=None,
                   requires=IS_NOT_EMPTY(), notnull=False, unique=False,
                   uploadfield=True, widget=None, label=None, comment=None,
                   writable=True, readable=True, update=None, authorize=None,
                   autodelete=False, represent=None, uploadfolder=None)

    to be used as argument of GQLDB.define_table

    allowed field types:
    string, boolean, integer, double, text, blob,
    date, time, datetime, upload, password

    strings must have a length or 512 by default.
    fields should have a default or they will be required in SQLFORMs
    the requires argument are used to validate the field input in SQLFORMs

    """

    def __init__(
        self,
        fieldname,
        type='string',
        length=None,
        default=None,
        required=False,
        requires='<default>',
        ondelete='CASCADE',
        notnull=False,
        unique=False,
        uploadfield=True,
        widget=None,
        label=None,
        comment=None,
        writable=True,
        readable=True,
        update=None,
        authorize=None,
        autodelete=False,
        represent=None,
        uploadfolder=None,
        compute=None
        ):

        self.name = fieldname = cleanup(fieldname)
        if fieldname in dir(Table) or fieldname[0] == '_':
            raise SyntaxError, 'Field: invalid field name: %s' % fieldname
        if isinstance(type, Table):
            type = 'reference ' + type._tablename
        if length == None:
            length = 512
        self.type = type  # 'string', 'integer'
        self.length = length  # the length of the string
        self.default = default  # default value for field
        self.required = required  # is this field required
        self.ondelete = ondelete.upper()  # this is for reference fields only
        self.notnull = notnull
        self.unique = unique
        self.uploadfield = uploadfield
        self.uploadfolder = uploadfolder
        self.widget = widget
        self.label = label
        self.comment = comment
        self.writable = writable
        self.readable = readable
        self.update = update
        self.authorize = authorize
        self.autodelete = autodelete
        self.represent = represent
        self.compute = compute
        self.isattachment = True
        if self.label == None:
            self.label = ' '.join([x.capitalize() for x in
                                  fieldname.split('_')])
        if requires is None:
            self.requires = []
        else:
            self.requires = requires

    def __str__(self):
        try:
            return '%s.%s' % (self._tablename, self.name)
        except:
            return '<no table>.%s' % self.name

GQLDB.Field = Field  # ## needed in gluon/globals.py session.connect
GQLDB.Table = Table  # ## needed in gluon/globals.py session.connect

def obj_represent(obj, fieldtype, db):
    if type(obj) in (types.LambdaType, types.FunctionType):
        obj = obj()
    if isinstance(obj, (Expression, Field)):
        raise SyntaxError, "non supported on GAE"
    if isinstance(fieldtype, gluon.sql.SQLCustomType):
        return fieldtype.encoder(obj)
    if isinstance(fieldtype, gae.Property):
        return obj
    if obj == '' and  not fieldtype[:2] in ['st','te','pa','up']:
        return None
    if obj != None:
        if fieldtype == 'date':
            if not isinstance(obj, datetime.date):
                (y, m, d) = [int(x) for x in str(obj).strip().split('-')]
                obj = datetime.date(y, m, d)
        elif fieldtype == 'time':
            if not isinstance(obj, datetime.time):
                time_items = [int(x) for x in str(obj).strip().split(':')[:3]]
                if len(time_items) == 3:
                    (h, mi, s) = time_items
                else:
                    (h, mi, s) = time_items + [0]
                obj = datetime.time(h, mi, s)
        elif fieldtype == 'datetime':
            if not isinstance(obj, datetime.datetime):
                (y, m, d) = [int(x) for x in str(obj)[:10].strip().split('-')]
                time_items = [int(x) for x in
                              str(obj)[11:].strip().split(':')[:3]]
                if len(time_items) == 3:
                    (h, mi, s) = time_items
                else:
                    (h, mi, s) = time_items + [0]
                obj = datetime.datetime(y, m, d, h, mi, s)
        elif fieldtype == 'integer':
            obj = long(obj)
        elif fieldtype == 'double':
            obj = float(obj)
        elif fieldtype[:10] == 'reference ':
            if isinstance(obj, (Row, Reference)):
                obj = obj['id']
            obj = long(obj)
        elif fieldtype == 'blob':
            pass
        elif fieldtype == 'boolean':
            if obj and not str(obj)[0].upper() == 'F':
                obj = True
            else:
                obj = False
        elif isinstance(obj, str):
            obj = obj.decode('utf8')
        elif not isinstance(obj, unicode):
            obj = unicode(obj)
    return obj

class Filter:
    def __init__(self,left,op,right):
        (self.left, self.op, self.right) = (left, op, right)
    def one(self):
        return self.left.type == 'id' and self.op == '='
    def all(self):
        return self.left.type == 'id' and self.op == '>' and self.right == 0
    def __str__(self):
        return '%s %s %s' % (self.left.name, self.op, self.right)

class Query(object):

    """
    A query object necessary to define a set.
    It can be stored or can be passed to GQLDB.__call__() to obtain a Set

    Example:
    query=db.users.name=='Max'
    set=db(query)
    records=set.select()
    """

    def __init__(
        self,
        left,
        op=None,
        right=None,
        ):
        self.get_all =  self.get_one = None
        if isinstance(left, list):
            self.filters = left
            return
        if isinstance(right, (Field, Expression)):
            raise SyntaxError, \
                'Query: right side of filter must be a value or entity: %s' \
                % right
        if isinstance(left, Field):
            # normal filter: field op value
            assert_filter_fields(left)
            if left.type == 'id':
                try:
                    right = long(right or 0)
                except ValueError:
                    raise SyntaxError, 'id value must be integer: %s' % id
                if not (op == '=' or (op == '>' and right == 0)):
                    raise RuntumeError, '(field.id <op> value) is not supported on GAE'
            elif op=='IN':
                right = [dateobj_to_datetime(obj_represent(r, left.type, left._db)) \
                             for r in right]
            else:
                # filter dates/times need to be datetimes for GAE
                right = dateobj_to_datetime(obj_represent(right, left.type, left._db))
            self.filters = [Filter(left, op, right)]
            return
        raise SyntaxError, 'not supported'

    def __and__(self, other):

        # concatenate list of filters
        # make sure all and one appear at the beginning
        if other.filters[0].one():
            return Query(other.filters+self.filters)
        return Query(self.filters + other.filters)

    def __or__(self):
        raise RuntimeError, 'OR is not supported on GAE'

    def __invert__(self):
        if len(self.filters)!=1:
            raise RuntimeError, 'NOT (... AND ...) is not supported on GAE'
        filter = self.filters[0]
        if filter.op == 'IN':
            raise RuntimeError, 'NOT (... IN ...) is not supported on GAE'
        new_op = {'<':'>','>':'<','=':'!=','!=':'=','<=':'>=','>=':'<='}[filter.op]
        return Query(filter.left, new_op, filter.right)

    def __str__(self):
        return ' AND '.join([str(filter) for filter in self.filters])


class Set(gluon.sql.Set):

    """
    As Set represents a set of records in the database,
    the records are identified by the where=Query(...) object.
    normally the Set is generated by GQLDB.__call__(Query(...))

    given a set, for example
       set=db(db.users.name=='Max')
    you can:
       set.update(db.users.name='Massimo')
       set.delete() # all elements in the set
       set.select(orderby=db.users.id, groupby=db.users.name, limitby=(0, 10))
    and take subsets:
       subset=set(db.users.id<5)
    """

    def __init__(self, db, where=None):
        self._db = db
        if where:
            self.where = where
            self._tables = [filter.left._tablename for filter in where.filters]
        else:
            self._tables = []
            self.where = None

    def __call__(self, where):
        if self.where:
            return Set(self._db, self.where & where)
        else:
            return Set(self._db, where)

    def _get_table_or_raise(self):
        tablenames = list(set(self._tables))  # unique
        if len(tablenames) < 1:
            raise SyntaxError, 'Set: no tables selected'
        if len(tablenames) > 1:
            raise SyntaxError, 'Set: no join in appengine'
        return self._db[tablenames[0]]._tableobj

    def _select(self, *fields, **attributes):
        valid_attributes = [
            'orderby',
            'groupby',
            'limitby',
            'required',
            'default',
            'requires',
            'left',
            'cache',
            ]
        if [key for key in attributes.keys() if not key
             in valid_attributes]:
            raise SyntaxError, 'invalid select attribute: %s' % key
        if fields and isinstance(fields[0], SQLALL):
            self._tables.insert(0, fields[0].table._tablename)
        table = self._get_table_or_raise()
        tablename = table.kind()
        items = gae.Query(table)
        if not self.where:
            self.where = Query(fields[0].table.id,'>',0)
        for filter in self.where.filters:
            if filter.all():
                continue
            elif filter.one() and filter.right<=0:
                items = []
            elif filter.one():
                item = self._db[tablename]._tableobj.get_by_id(filter.right)
                items = (item and [item]) or []
            elif isinstance(items,list):
                (name, op, value) = (filter.left.name, filter.op, filter.right)
                if op == '=': op = '=='
                if op == 'IN': op = 'in'
                items = [item for item in items \
                             if eval("getattr(item,'%s') %s %s" % (name, op, repr(value)))]
            else:
                (name, op, value) = (filter.left.name, filter.op, filter.right)
                items = items.filter('%s %s' % (name, op), value)
        if not isinstance(items,list):
            if attributes.get('left', None):
                raise SyntaxError, 'Set: no left join in appengine'
            if attributes.get('groupby', None):
                raise SyntaxError, 'Set: no groupby in appengine'
            orderby = attributes.get('orderby', False)
            if orderby:
                if isinstance(orderby, (list, tuple)):
                    orderby = gluon.sql.xorify(orderby)
                assert_filter_fields(orderby)
                orders = orderby.name.split('|')
                for order in orders:
                    items = items.order(order)
            if attributes.get('limitby', None):
                (lmin, lmax) = attributes['limitby']
                (limit, offset) = (lmax - lmin, lmin)
                items = items.fetch(limit, offset=offset)
        fields = self._db[tablename].fields
        return (items, tablename, fields)

    def select(self, *fields, **attributes):
        """
        Always returns a Rows object, even if it may be empty
        cache attribute ignored on GAE
        """

        (items, tablename, fields) = self._select(*fields, **attributes)
        self._db['_lastsql'] = 'SELECT WHERE %s' % self.where
        rows = []
        for item in items:
            new_item = []
            for t in fields:
                if t == 'id':
                    new_item.append(int(item.key().id()))
                else:
                    new_item.append(getattr(item, t))
            rows.append(new_item)
        colnames = ['%s.%s' % (tablename, t) for t in fields]
        return self.parse(self._db, rows, colnames, False)

    @staticmethod
    def items_count(items):
        try:
            return len(items)
        except TypeError:
            return items.count()

    def count(self):
        (items, tablename, fields) = self._select()
        self._db['_lastsql'] = 'COUNT WHERE %s' % self.where
        return self.items_count(items)

    def delete(self):
        self._db['_lastsql'] = 'DELETE WHERE %s' % self.where
        (items, tablename, fields) = self._select()
        tableobj = self._db[tablename]._tableobj        
        counter = self.items_count(items)
        if counter:
            gae.delete(items)        
        return counter

    def update(self, **update_fields):
        self._db['_lastsql'] = 'UPDATE WHERE %s' % self.where
        db = self._db
        (items, tablename, fields) = self._select()
        table = db[tablename]
        update_fields.update(dict([(fieldname, table[fieldname].update) \
                                       for fieldname in table.fields \
                                       if not fieldname in update_fields \
                                       and table[fieldname].update != None]))
        update_fields.update(dict([(fieldname, table[fieldname].compute(update_fields)) \
                                       for fieldname in table.fields \
                                       if not fieldname in update_fields \
                                       and table[fieldname].compute != None]))
        tableobj = table._tableobj
        counter = 0
        for item in items:
            for (field, value) in update_fields.items():
                value = obj_represent(update_fields[field],
                                      table[field].type, db)
                setattr(item, field, value)
            item.put()
            counter += 1
        return counter


def test_all():
    """
    How to run from web2py dir:
    eg. OSX:
     export PYTHONPATH=.:/usr/local/google_appengine
     python gluon/contrib/gql.py
    no output means all tests passed

    Setup the UTC timezone and database stubs

    >>> import os
    >>> os.environ['TZ'] = 'UTC'
    >>> # dev_server sets APPLICATION_ID, but we are not using dev_server, so manually set it to something
    >>> os.environ['APPLICATION_ID'] = 'test'
    >>> import time
    >>> if hasattr(time, 'tzset'):
    ...   time.tzset()
    >>>
    >>> from google.appengine.api import apiproxy_stub_map
    >>> from google.appengine.api import datastore_file_stub
    >>> apiproxy_stub_map.apiproxy = apiproxy_stub_map.APIProxyStubMap()
    >>> apiproxy_stub_map.apiproxy.RegisterStub('datastore_v3',            datastore_file_stub.DatastoreFileStub('doctests_your_app_id', '/dev/null', '/dev/null'))

        Create a table with all possible field types

    >>> db=GQLDB()
    >>> tmp=db.define_table('users',              Field('stringf', 'string',length=32,required=True),              Field('booleanf','boolean',default=False),              Field('passwordf','password',notnull=True),              Field('blobf','blob'),              Field('uploadf','upload'),              Field('integerf','integer',unique=True),              Field('doublef','double',unique=True,notnull=True),              Field('datef','date',default=datetime.date.today()),              Field('timef','time'),              Field('datetimef','datetime'),              migrate='test_user.table')

   Insert a field

    >>> db.users.insert(stringf='a',booleanf=True,passwordf='p',blobf='0A',                       uploadf=None, integerf=5,doublef=3.14,                       datef=datetime.date(2001,1,1),                       timef=datetime.time(12,30,15),                       datetimef=datetime.datetime(2002,2,2,12,30,15))
    1

    Select all

    # >>> all = db().select(db.users.ALL)

    Drop the table

    >>> db.users.drop()

    Select many entities

    >>> tmp = db.define_table(\"posts\",              Field('body','text'),              Field('total','integer'),              Field('created_at','datetime'))
    >>> many = 20   #2010 # more than 1000 single fetch limit (it can be slow)
    >>> few = 5
    >>> most = many - few
    >>> 0 < few < most < many
    True
    >>> for i in range(many):
    ...     f=db.posts.insert(body='',                total=i,created_at=datetime.datetime(2008, 7, 6, 14, 15, 42, i))
    >>>
    >>> len(db().select(db.posts.ALL)) == many
    True
    >>> len(db().select(db.posts.ALL,limitby=(0,most))) == most
    True
    >>> len(db().select(db.posts.ALL,limitby=(few,most))) == most - few
    True
    >>> order = ~db.posts.total|db.posts.created_at
    >>> results = db().select(db.posts.ALL,limitby=(most,most+few),orderby=order)
    >>> len(results) == few
    True
    >>> results[0].total == few - 1
    True
    >>> results = db().select(db.posts.ALL,orderby=~db.posts.created_at)
    >>> results[0].created_at > results[1].created_at
    True
    >>> results = db().select(db.posts.ALL,orderby=db.posts.created_at)
    >>> results[0].created_at < results[1].created_at
    True

    >>> db(db.posts.total==few).count()
    1

    >>> db(db.posts.id==2*many).count()
    0

    >>> db(db.posts.id==few).count()
    1

    >>> db(db.posts.id==str(few)).count()
    1
    >>> len(db(db.posts.id>0).select()) == many
    True

    >>> db(db.posts.id>0).count() == many
    True

    >>> set=db(db.posts.total>=few)
    >>> len(set.select())==most
    True

    >>> len(set(db.posts.total<=few).select())
    1

    # test timezones
    >>> class TZOffset(datetime.tzinfo):
    ...   def __init__(self,offset=0):
    ...     self.offset = offset
    ...   def utcoffset(self, dt): return datetime.timedelta(hours=self.offset)
    ...   def dst(self, dt): return datetime.timedelta(0)
    ...   def tzname(self, dt): return 'UTC' + str(self.offset)
    ...
    >>> SERVER_OFFSET = -8
    >>>
    >>> stamp = datetime.datetime(2008, 7, 6, 14, 15, 42, 828201)
    >>> post_id = db.posts.insert(created_at=stamp)
    >>> naive_stamp = db(db.posts.id==post_id).select()[0].created_at
    >>> utc_stamp=naive_stamp.replace(tzinfo=TZOffset())
    >>> server_stamp = utc_stamp.astimezone(TZOffset(SERVER_OFFSET))
    >>> stamp == naive_stamp
    True
    >>> utc_stamp == server_stamp
    True
    >>> db(db.posts.id>0).count() == many + 1
    True
    >>> db(db.posts.id==post_id).delete()
    1
    >>> db(db.posts.id>0).count() == many
    True

    >>> id = db.posts.insert(total='0')   # coerce str to integer
    >>> db(db.posts.id==id).delete()
    1
    >>> db(db.posts.id > 0).count() == many
    True
    >>> set=db(db.posts.id>0)
    >>> set.update(total=0)                # update entire set
    20
    >>> db(db.posts.total == 0).count() == many
    True

    >>> db.posts.drop()
    >>> db(db.posts.id>0).count()
    0

    Examples of insert, select, update, delete

    >>> tmp=db.define_table('person',              Field('name'),               Field('birth','date'),              migrate='test_person.table')
    >>> person_id=db.person.insert(name=\"Marco\",birth='2005-06-22')
    >>> person_id=db.person.insert(name=\"Massimo\",birth='1971-12-21')
    >>> len(db().select(db.person.ALL))
    2
    >>> me=db(db.person.id==person_id).select()[0] # test select
    >>> me.name
    'Massimo'
    >>> db(db.person.name=='Massimo').update(name='massimo') # test update
    1
    >>> me = db(db.person.id==person_id).select()[0]
    >>> me.name
    'massimo'
    >>> str(me.birth)
    '1971-12-21'

    # resave date to ensure it comes back the same
    >>> me=db(db.person.name=='Massimo').update(birth=me.birth) # test update
    >>> me = db(db.person.id==person_id).select()[0]
    >>> me.birth
    datetime.date(1971, 12, 21)
    >>> db(db.person.name=='Marco').delete() # test delete
    1
    >>> len(db().select(db.person.ALL))
    1

    Update a single record

    >>> me.update_record(name=\"Max\")
    >>> me.name
    'Max'

    Examples of complex search conditions

    >>> len(db((db.person.name=='Max')&(db.person.birth<'2003-01-01')).select())
    1
    >>> len(db((db.person.name=='Max')&(db.person.birth<datetime.date(2003,01,01))).select())
    1

    # >>> len(db((db.person.name=='Max')|(db.person.birth<'2003-01-01')).select())
    # 1
    >>> me=db(db.person.id==person_id).select(db.person.name)[0]
    >>> me.name
    'Max'

    Examples of search conditions using extract from date/datetime/time

    # >>> len(db(db.person.birth.month()==12).select())
    # 1
    # >>> len(db(db.person.birth.year()>1900).select())
    # 1

    Example of usage of NULL

    >>> len(db(db.person.birth==None).select()) ### test NULL
    0

    # filter api does not support != yet
    # >>> len(db(db.person.birth!=None).select()) ### test NULL
    # 1

    Examples of search consitions using lower, upper, and like

    # >>> len(db(db.person.name.upper()=='MAX').select())
    # 1
    # >>> len(db(db.person.name.like('%ax')).select())
    # 1
    # >>> len(db(db.person.name.upper().like('%AX')).select())
    # 1
    # >>> len(db(~db.person.name.upper().like('%AX')).select())
    # 0

    orderby, groupby and limitby

    >>> people=db().select(db.person.ALL,orderby=db.person.name)
    >>> order=db.person.name|~db.person.birth
    >>> people=db().select(db.person.ALL,orderby=order)

    # no groupby in appengine
    # >>> people=db().select(db.person.ALL,orderby=db.person.name,groupby=db.person.name)

    >>> people=db().select(db.person.ALL,orderby=order,limitby=(0,100))

    Example of one 2 many relation

    >>> tmp=db.define_table('dog',               Field('name'),               Field('birth','date'),               Field('owner',db.person),              migrate='test_dog.table')
    >>> dog_id=db.dog.insert(name='Snoopy',birth=None,owner=person_id)

    A simple JOIN

    >>> len(db(db.dog.owner==person_id).select())
    1

    >>> len(db(db.dog.owner==me.id).select())
    1

    # test a table relation

    >>> dog = db(db.dog.id==dog_id).select()[0]
    >>> me = db(db.person.id==dog.owner).select()[0]
    >>> me.dog.select()[0].name
    'Snoopy'

    Drop tables

    >>> db.dog.drop()
    >>> db.person.drop()

    Example of many 2 many relation and Set

    >>> tmp=db.define_table('author',Field('name'),                            migrate='test_author.table')
    >>> tmp=db.define_table('paper',Field('title'),                            migrate='test_paper.table')
    >>> tmp=db.define_table('authorship',            Field('author_id',db.author),            Field('paper_id',db.paper),            migrate='test_authorship.table')
    >>> aid=db.author.insert(name='Massimo')
    >>> pid=db.paper.insert(title='QCD')
    >>> tmp=db.authorship.insert(author_id=aid,paper_id=pid)

    Define a Set

    >>> authorships=db(db.authorship.author_id==aid).select()
    >>> for authorship in authorships:
    ...     papers=db(db.paper.id==authorship.paper_id).select()
    ...     for paper in papers: print paper.title
    QCD


    Example of search condition using  belongs

    # >>> set=(1,2,3)
    # >>> rows=db(db.paper.id.belongs(set)).select(db.paper.ALL)
    # >>> print rows[0].title
    # QCD

    Example of search condition using nested select

    # >>> nested_select=db()._select(db.authorship.paper_id)
    # >>> rows=db(db.paper.id.belongs(nested_select)).select(db.paper.ALL)
    # >>> print rows[0].title
    # QCD

    Output in csv

    # >>> str(authored_papers.select(db.author.name,db.paper.title))
    # 'author.name,paper.title\r
Massimo,QCD\r
'

    Delete all leftover tables

    # >>> GQLDB.distributed_transaction_commit(db)

    >>> db.authorship.drop()
    >>> db.author.drop()
    >>> db.paper.drop()

    # self reference

    >>> tmp = db.define_table('employees',
    ...   Field('name'),
    ...   Field('email'),
    ...   Field('phone'),
    ...   Field('foto','upload'),
    ...   Field('manager','reference employees')
    ...   )
    >>> id1=db.employees.insert(name='Barack')
    >>> id2=db.employees.insert(name='Hillary',manager=id1)
    >>> barack = db.employees[id1]
    >>> hillary = db.employees[id2]
    >>> hillary.manager == barack.id
    True
    """

SQLField = Field
SQLTable = Table
SQLXorable = Expression
SQLQuery = Query
SQLSet = Set
SQLRows = Rows
SQLStorage = Row

if __name__ == '__main__':
    import doctest
    doctest.testmod()
