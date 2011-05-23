#!/env python
# -*- coding: utf-8 -*-

"""
This file is part of web2py Web Framework (Copyrighted, 2007-2010).
Developed by Massimo Di Pierro <mdipierro@cs.depaul.edu>.
License: GPL v2

Thanks to
    * Niall Sweeny <niall.sweeny@fonjax.com> for MS SQL support
    * Marcel Leuthi <mluethi@mlsystems.ch> for Oracle support
    * Denes
    * Chris Clark
    * clach05
    * Denes Lengyel

This file contains the DAL support for many relational databases,
including SQLite, MySQL, Postgres, Oracle, MS SQL, DB2, Interbase, Ingres

Completely refactored by MDP on Dec 12, 2009

TODO:
- create more funcitons in adapters to abstract more
- check logger and folder interaction not sure it works
"""

__all__ = ['DAL', 'Field']

import re
import sys
import locale
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
import traceback
import copy_reg
import base64
import shutil
import marshal
import decimal
import struct

from utils import md5_hash, web2py_uuid
from serializers import json
import portalocker
import validators

sql_locker = thread.allocate_lock()

# internal representation of tables with field
#  <table>.<field>, tables and fields may only be [a-zA-Z0-0_]

table_field = re.compile('[\w_]+\.[\w_]+')
regex_content = re.compile('([\w\-]+\.){3}(?P<name>\w+)\.\w+$')
regex_cleanup_fn = re.compile('[\'"\s;]+')

# list of drivers will be built on the fly
# and lists only what is available
drivers = []
try:
    from pysqlite2 import dbapi2 as sqlite3
    drivers.append('pysqlite2')
except:
    try:
        import sqlite3
        drivers.append('SQLite3')
    except:
        logging.debug('no sqlite3 or pysqlite2.dbapi2 driver')

try:
    import MySQLdb
    drivers.append('MySQL')
except:
    logging.debug('no MySQLdb driver')

try:
    import psycopg2
    drivers.append('PostgreSQL')
except:
    logging.debug('no psycopg2 driver')

try:
    import cx_Oracle
    drivers.append('Oracle')
except:
    logging.debug('no cx_Oracle driver')

try:
    import pyodbc
    drivers.append('MSSQL/DB2')
except:
    logging.debug('no MSSQL/DB2 driver')

try:
    import kinterbasdb
    drivers.append('Interbase')
except:
    logging.debug('no kinterbasdb driver')

try:
    import informixdb
    drivers.append('Informix')
    logging.warning('Informix support is experimental')
except:
    logging.debug('no informixdb driver')

try:
    from com.ziclix.python.sql import zxJDBC
    import java.sql
    from org.sqlite import JDBC
    drivers.append('zxJDBC')
    logging.warning('zxJDBC support is experimental')
    is_jdbc = True
except:
    logging.debug('no zxJDBC driver')
    is_jdbc = False

try:
    import ingresdbi
    drivers.append('Ingres')
except:
    logging.debug('no Ingres driver')
    # NOTE could try JDBC.......


class Logger(object):

    def __init__(self,folder,name='sql.log'):
        if isinstance(folder,(str,unicode)):
            print os.path.join(folder,name)
            self.file = open(os.path.join(folder,name),'a')
        else:
            self.file = None
        self.active = False

    def write(self,data):
        if not self.active or not self.file:
            return
        portalocker.lock(self.file,portalocker.LOCK_EX)
        ret = self.file.write(data)
        portalocker.unlock(self.file)
        return ret

    def __zero__(self):
        return not self.active


class ConnectionPool(object):
    _folders = {}
    _connection_pools = {}
    _instances = {}

    @staticmethod
    def set_thread_folder(folder):
        sql_locker.acquire()
        ConnectionPool._folders[thread.get_ident()] = folder
        sql_locker.release()

    # ## this allows gluon to commit/rollback all dbs in this thread

    @staticmethod
    def close_all_instances(action):
        """ to close cleanly databases in a multithreaded environment """
        sql_locker.acquire()
        pid = thread.get_ident()
        if pid in ConnectionPool._folders:
            del ConnectionPool._folders[pid]
        if pid in ConnectionPool._instances:
            instances = ConnectionPool._instances[pid]
            while instances:
                instance = instances.pop()
                sql_locker.release()
                action(instance)
                sql_locker.acquire()

                # ## if you want pools, recycle this connection
                really = True
                if instance.pool_size:
                    pool = ConnectionPool._connection_pools[instance.uri]
                    if len(pool) < instance.pool_size:
                        pool.append(instance.connection)
                        really = False
                if really:
                    sql_locker.release()
                    instance.connection.close()
                    sql_locker.acquire()
            del ConnectionPool._instances[pid]
        sql_locker.release()
        return

    def find_or_make_work_folder(self):
        """ this actually does not make the folder. it has to be there """
        pid = thread.get_ident()
        if not self.folder:
            sql_locker.acquire()
            if pid in self._folders:
                self.folder = self._folders[pid]
            else:
                self.folder = self._folders[pid] = ''
            sql_locker.release()

        # Creating the folder if it does not exist
        if False and self.folder and not os.path.exists(self.folder):
            os.mkdir(self._folder)

    def pool_connection(self, f):
        pid = thread.get_ident()
        if not self.pool_size:
            self.connection = f()
        else:
            uri = self.uri
            sql_locker.acquire()
            if not uri in ConnectionPool._connection_pools:
                ConnectionPool._connection_pools[uri] = []
            if ConnectionPool._connection_pools[uri]:
                self.connection = ConnectionPool._connection_pools[uri].pop()
                sql_locker.release()
            else:
                sql_locker.release()
                self.connection = f()

        sql_locker.acquire()
        if not pid in self._instances:
            self._instances[pid] = []
        self._instances[pid].append(self)
        sql_locker.release()
        self.cursor = self.connection.cursor()


class BaseAdapter(ConnectionPool):
    def __init__(self,db,uri,pool_size=0,folder=None,db_codec ='UTF-8'):
        self.db = db
        self.uri = uri
        self.pool_size = pool_size
        self.folder = folder
        self.db_codec = db_codec

    def LOWER(self,first):
        return 'LOWER(%s)' % self.expand(first)

    def UPPER(self,first):
        return 'UPPER(%s)' % self.expand(first)

    def EXTRACT(self,first,what):
        return "EXTRACT('%s' FROM %s)" % (what, self.expand(first))

    def AGGREGATE(self,first,what):
        return "%s(%s)" % (what,self.expand(first))

    def LEFT_JOIN(self):
        return 'LEFT JOIN'

    def RANDOM(self):
        return 'Random()'

    def NOT_NULL(self,default,field_type):
        return 'NOT NULL DEFAULT %s' % self.represent(default,field_type)

    def SUBSTRING(self,field,parameters):
        return 'SUBSTR(%s,%s,%s)' % (self.expand(field), paramters[0], parameters[1])

    def PRIMARY_KEY(self,key):
        return 'PRIMARY KEY(%s)' % key

    def DROP(self,table,mode):
        return ['DROP TABLE %s;' % table]

    def INSERT(self,table,fields):
        keys = ','.join([field.name for (field,value) in fields])
        values = ','.join([self.expand(value,field.type) for (field,value) in fields])
        return 'INSERT INTO %s(%s) VALUES (%s);' % (table, keys, values)

    def VERBATIM(self,first):
        return first

    def NOT(self,first):
        return '(NOT %s)' % self.expand(first)

    def AND(self,first,second):
        return '(%s AND %s)' % (self.expand(first),self.expand(second))

    def OR(self,first,second):
        return '(%s OR %s)' % (self.expand(first),self.expand(second))

    def BELONGS(self,first,second):
        if isinstance(second,str):
            return '(%s IN (%s))' % (self.expand(first),second[:-1])
        return '(%s IN (%s))' % (self.expand(first),self.expand(second,first.type))

    def LIKE(self,first,second):
        return '(%s LIKE %s)' % (self.expand(first),self.expand(second,'string'))

    def EQ(self,first,second=None):
        if second is None:
            return '(%s IS NULL)' % self.expand(first)
        return '(%s = %s)' % (self.expand(first),self.expand(second,first.type))

    def NE(self,first,second=None):
        if second==None:
            return '(%s IS NOT NULL)' % self.expand(first)
        return '(%s <> %s)' % (self.expand(first),self.expand(second,first.type))

    def LT(self,first,second=None):
        return '(%s < %s)' % (self.expand(first),self.expand(second,first.type))

    def LE(self,first,second=None):
        return '(%s <= %s)' % (self.expand(first),self.expand(second,first.type))

    def GT(self,first,second=None):
        return '(%s > %s)' % (self.expand(first),self.expand(second,first.type))

    def GE(self,first,second=None):
        return '(%s >= %s)' % (self.expand(first),self.expand(second,first.type))

    def ADD(self,first,second):
        return '(%s + %s)' % (self.expand(first),self.expand(second,first.type))

    def SUB(self,first,second):
        return '(%s - %s)' % (self.expand(first),self.expand(second,first.type))

    def MUL(self,first,second):
        return '(%s * %s)' % (self.expand(first),self.expand(second,first.type))

    def DIV(self,first,second):
        return '(%s / %s)' % (self.expand(first),self.expand(second,first.type))

    def ON(self,first,second):
        return '%s ON %s' % (self.expand(first),self.expand(second))

    def DESC(self,first):
        return '%s DESC' % self.expand(first)

    def COMMA(self,first,second):
        return '%s, %s' % (self.expand(first),self.expand(second))

    def VERBATIM(self,first):
        return str(first)

    def expand(self,expression,field_type=None):
        if isinstance(expression,Field):
            return str(expression)
        elif isinstance(expression, (Expression, Query)):
            if not expression._second is None:
                return expression._op(expression._first, expression._second)
            elif not expression._first is None:
                return expression._op(expression._first)
            else:
                return expression._op()
        elif isinstance(expression,(list,tuple)):
            return ','.join([self.represent(item,field_type) for item in expression])
        elif field_type:
            return self.represent(expression,field_type)
        else:
            return str(expression)

    def alias(self,table,alias):
        """
        given a table object, makes a new table object
        with alias name.
        """
        other = copy.copy(table)
        other['_ot'] = other._tablename
        other['ALL'] = SQLALL(other)
        other['_tablename'] = alias
        for fieldname in other.fields:
            other[fieldname] = copy.copy(other[fieldname])
            other[fieldname]._tablename = alias
        table._db[alias] = table
        return other

    def TRUNCATE(self,table,mode = ''):
        tablename = table._tablename
        return ['TRUNCATE TABLE %s %s;' % (tablename, mode or '')]

    def UPDATE(self,query,tablename,fields):
        if query:
            sql_w = ' WHERE ' + self.expand(query)
        else:
            sql_w = ''
        sql_v = ','.join(['%s=%s' % (field.name, self.expand(value,field.type)) for (field,value) in fields])
        return 'UPDATE %s SET %s%s;' % (tablename, sql_v, sql_w)

    def DELETE(self,query,tablename):
        if query:
            sql_w = ' WHERE ' + self.expand(query)
        else:
            sql_w = ''
        return 'DELETE FROM %s%s;' % (tablename, sql_w)

    def COUNT(self,query, tablenames):
        if query:
            sql_w = ' WHERE ' + self.expand(query)
        else:
            sql_w = ''
        sql_t = ','.join(tablenames)
        return 'SELECT count(*) FROM %s%s' % (sql_t, sql_w)

    def count(self,query,tablenames):
        self.execute(self.COUNT(query,tablenames))
        return self.cursor.fetchone()[0]

    def SELECT(self, query, *fields, **attributes):
        for key in set(attributes.keys())-set(('orderby','groupby','limitby',
                                               'required','cache','left','distinct','having')):
            raise SyntaxError, 'invalid select attribute: %s' % key
        # ## if not fields specified take them all from the requested tables
        new_fields = []
        for item in fields:
            if isinstance(item,SQLALL):
                new_fields += item.table
            else:
                new_fields.append(item)
        fields = new_fields
        tablenames = self.tables(query)
        if not fields:
            for table in tablenames:
                for field in self.db[table]:
                    fields.append(field)
        else:
            for f in fields:
                if not f in tablenames:
                    tablenames.append(f._tablename)
        if len(tablenames) < 1:
            raise SyntaxError, 'Set: no tables selected'
        sql_f = ', '.join([self.expand(f) for f in fields])
        self._colnames = [c.strip() for c in sql_f.split(', ')]
        if query:
            sql_w = ' WHERE ' + self.expand(query)
        else:
            sql_w = ''
        sql_o = ''
        sql_s = ''
        left = attributes.get('left', False)
        distinct = attributes.get('distinct', False)
        groupby = attributes.get('groupby', False)
        orderby = attributes.get('orderby', False)
        having = attributes.get('having', False)
        limitby = attributes.get('limitby', False)
        if distinct is True:
            sql_s += 'DISTINCT'
        elif distinct:
            sql_s += 'DISTINCT ON (%s)' % distinct
        if left:
            join = attributes['left']
            command = self.db._adapter.LEFT_JOIN()
            if not isinstance(join, (tuple, list)):
                join = [join]
            joint = [t._tablename for t in join if not isinstance(t,Expression)]
            joinon = [t for t in join if isinstance(t, Expression)]
            joinont = [t._first._tablename for t in joinon]
            excluded = [t for t in tablenames if not t in joint + joinont]
            sql_t = ', '.join(excluded)
            if joint:
                sql_t += ' %s %s' % (command, ', '.join(joint))
            for t in joinon:
                sql_t += ' %s %s' % (command, str(t))
        else:
            sql_t = ', '.join(tablenames)
        if groupby:
            sql_o += ' GROUP BY %s' % attributes['groupby']
            if having:
                sql_o += ' HAVING %s' % attributes['having']
        if orderby:
            if isinstance(orderby, (list, tuple)):
                orderby = xorify(orderby)
            if str(orderby) == '<random>':
                sql_o += ' ORDER BY %s' % self.db._adapter.RANDOM()
            else:
                sql_o += ' ORDER BY %s' % self.db._adapter.expand(orderby)
        if limitby:
            if not orderby and tablenames:
                sql_o += ' ORDER BY %s' % ', '.join(['%s.%s'%(t,x) for t in tablenames for x in (self.db[t]._primarykey or ['id'])])
            # oracle does not support limitby
        return self.SELECT_LIMITBY(sql_s, sql_f, sql_t, sql_w, sql_o, limitby)

    def SELECT_LIMITBY(self, sql_s, sql_f, sql_t, sql_w, sql_o, limitby):
        if limitby:
            (lmin, lmax) = limitby
            sql_o += ' LIMIT %i OFFSET %i' % (lmax - lmin, lmin)
        return 'SELECT %s %s FROM %s%s%s;' % (sql_s, sql_f, sql_t, sql_w, sql_o)

    def select(self,query,*fields,**attributes):
        """
        Always returns a Rows object, even if it may be empty
        """
        db=self.db

        def response(query):
            self.execute(query)
            return self.cursor.fetchall()
        query = self.SELECT(query,*fields, **attributes)
        if attributes.get('cache', None):
            (cache_model, time_expire) = attributes['cache']
            del attributes['cache']
            key = self._uri + '/' + query
            rows = cache_model(key, lambda: response(query), time_expire)
        else:
            rows = response(query)
        if isinstance(rows,tuple):
            rows = list(rows)
        rows = self.rowslice(rows,attributes.get('limitby',(0,))[0],None)
        return self.parse(rows,self._colnames)

    def tables(self,query):
        tables = []
        if isinstance(query, (Query, Expression, Field)):
            if query._first:
                if hasattr(query._first, '_tablename'):
                    tables = [query._first._tablename]
                else:
                    tables = self.tables(query._first)
            if query._second:
                if hasattr(query._second, '_tablename'):
                    if not query._second._tablename in tables:
                        tables.append(query._second._tablename)
                else:
                    tables = tables + [t for t in self.tables(query._second) if not t in tables]
        return tables

    def commit(self):
        self.db._logger.write('commit\n');
        try:
            ret = self.connection.commit()
        finally :
            self.db._logger.write(traceback.format_exc());
        return ret

    def rollback(self):
        self.db._logger.write('rollback\n');
        try:
            ret = self.connection.rollback()
        finally:
            self.db._logger.write(traceback.format_exc());
        return ret

    def support_distributed_transaction(self):
        return False

    def distributed_transaction_begin(self,key):
        return

    def prepare(self,key):
        self.connection.prepare()

    def commit_prepared(self,key):
        self.connection.commit()

    def rollback_prepared(self,key):
        self.connection.rollback()

    def concat_add(self,table):
        return ', ADD '

    def contraint_name(self, table, fieldname):
        return '%s_%s__constraint' % (table,fieldname)

    def create_sequence_and_triggers(self, query, table):
        self.execute(query)

    def commit_on_alter_table(self):
        return False

    def log_execute(self,*a,**b):
        self.db._lastsql = a[0]
        self.db._logger.write(datetime.datetime.now().isoformat()+'\n'+a[0]+'\n')
        try:
            ret = self.cursor.execute(*a,**b)
        finally:
            self.db._logger.write(traceback.format_exc())
        return ret

    def execute(self,*a,**b):
        return self.log_execute(*a, **b)

    def represent(self, obj, fieldtype):
        if type(obj) in (types.LambdaType, types.FunctionType):
            obj = obj()
        if isinstance(fieldtype, SQLCustomType):
            return fieldtype.encoder(obj)
        if obj is None:
            return 'NULL'
        if obj == '' and not fieldtype[:2] in ['st','te','pa','up']:
            return 'NULL'
        r = BaseAdapter.represent_exceptions(self,obj,fieldtype)
        if r != None:
            return r
        if fieldtype == 'boolean':
            if obj and not str(obj)[0].upper() in ['F', '0']:
                return "'T'"
            else:
                return "'F'"
        if fieldtype == 'id' or fieldtype == 'integer':
            return str(int(obj))
        if fieldtype[:7] == 'decimal':
            return str(obj)
        elif fieldtype[0] == 'r': # reference
            if fieldtype.find('.')>0:
                return repr(obj)
            elif isinstance(obj, (Row, Reference)):
                return str(obj['id'])
            return str(int(obj))
        elif fieldtype == 'double':
            return repr(float(obj))
        if isinstance(obj, unicode):
            obj = obj.encode(self.db_codec)
        if fieldtype == 'blob':
            obj = base64.b64encode(str(obj))
        elif fieldtype == 'date':
            if isinstance(obj, (datetime.date, datetime.datetime)):
                obj = obj.isoformat()[:10]
            else:
                obj = str(obj)
        elif fieldtype == 'datetime':
            if isinstance(obj, datetime.datetime):
                obj = obj.isoformat()[:19].replace('T',' ')
            elif isinstance(obj, datetime.date):
                obj = obj.isoformat()[:10]+' 00:00:00'
            else:
                obj = str(obj)
        elif fieldtype == 'time':
            if isinstance(obj, datetime.time):
                obj = obj.isoformat()[:10]
            else:
                obj = str(obj)
        if not isinstance(obj,str):
            obj = str(obj)
        try:
            obj.decode(self.db_codec)
        except:
            obj = obj.decode('latin1').encode(self.db_codec)
        return "'%s'" % obj.replace("'", "''")

    def represent_exceptions(self, obj, fieldtype):
        return None

    def lastrowid(self,tablename):
        return None

    def integrity_error_class(self):
        return type(None)

    def rowslice(self,rows,minimum=0,maximum=None):
        """ by default this function does nothing, oreload when db does no do slicing """
        return rows

    def parse(self,rows,colnames,blob_decode=True):
        virtualtables = []
        new_rows = []
        for (i,row) in enumerate(rows):
            new_row = Row()
            for j in xrange(len(colnames)):
                value = row[j]
                if not table_field.match(colnames[j]):
                    if not '_extra' in new_row:
                        new_row['_extra'] = Row()
                    new_row['_extra'][colnames[j]] = value
                    continue
                (tablename, fieldname) = colnames[j].split('.')
                table = self.db[tablename]
                field = table[fieldname]
                if field.type != 'blob' and isinstance(value, str):
                    value = value.decode(self.db_codec)
                if isinstance(value, unicode):
                    value = value.encode('utf-8')
                if tablename in new_row:
                    colset = new_row[tablename]
                else:
                    colset = new_row[tablename] = Row()
                    virtualtables.append((tablename, self.db[tablename].virtualfields))
                if field.type[:10] == 'reference ':
                    referee = field.type[10:].strip()
                    if value and '.' in referee:
                        # Reference not by id
                        colset[fieldname] = value
                    else:
                        # Reference by id
                        colset[fieldname] = rid = Reference(value)
                        (rid._table, rid._record) = (self.db[referee], None)
                elif field.type == 'blob' and value != None and blob_decode:
                    colset[fieldname] = base64.b64decode(str(value))
                elif field.type == 'boolean' and value != None:
                    if value == True or value == 'T' or value == 't':
                        colset[fieldname] = True
                    else:
                        colset[fieldname] = False
                elif field.type == 'date' and value != None\
                        and (not isinstance(value, datetime.date)\
                                 or isinstance(value, datetime.datetime)):
                    (y, m, d) = [int(x) for x in
                                 str(value)[:10].strip().split('-')]
                    colset[fieldname] = datetime.date(y, m, d)
                elif field.type == 'time' and value != None\
                        and not isinstance(value, datetime.time):
                    time_items = [int(x) for x in
                                  str(value)[:8].strip().split(':')[:3]]
                    if len(time_items) == 3:
                        (h, mi, s) = time_items
                    else:
                        (h, mi, s) = time_items + [0]
                    colset[fieldname] = datetime.time(h, mi, s)
                elif field.type == 'datetime' and value != None\
                        and not isinstance(value, datetime.datetime):
                    (y, m, d) = [int(x) for x in
                                 str(value)[:10].strip().split('-')]
                    time_items = [int(x) for x in
                                  str(value)[11:19].strip().split(':')[:3]]
                    if len(time_items) == 3:
                        (h, mi, s) = time_items
                    else:
                        (h, mi, s) = time_items + [0]
                    colset[fieldname] = datetime.datetime(y, m, d, h, mi, s)
                elif field.type[:7] == 'decimal' and value != None:
                    decimals = [int(x) for x in field.type[8:-1].split(',')][-1]
                    if field._db._dbname == 'sqlite':
                        value = ('%.'+str(decimals)+'f') % value
                    if not isinstance(value,decimal.Decimal):
                        value = decimal.Decimal(value)
                    colset[fieldname] = value
                elif isinstance(field.type,SQLCustomType) and value != None:
                    colset[fieldname] = field.type.decoder(value)
                else:
                    colset[fieldname] = value
                if field.type == 'id':
                    id = colset[field.name]
                    colset.update_record = lambda c = colset, t = table, \
                        i = id, **a: update_record(c, t, i, a)
                    colset.delete_record = lambda t = table, i = id: \
                        t._db(t.id==i).delete()
                    for (referee_table, referee_name) in \
                            table._referenced_by:
                        s = self.db[referee_table][referee_name]
                        colset[referee_table] = Set(self.db, s == id)
                    colset['id'] = id
            new_rows.append(new_row)
        rowsobj = Rows(self.db, new_rows, colnames)
        for table, virtualfields in virtualtables:
            for item in virtualfields:
                rowsobj = rowsobj.setvirtualfields(**{table:item})
        return rowsobj



class SQLiteAdapter(BaseAdapter):
    types = {
        'boolean': 'CHAR(1)',
        'string': 'CHAR(%(length)s)',
        'text': 'TEXT',
        'password': 'CHAR(%(length)s)',
        'blob': 'BLOB',
        'upload': 'CHAR(%(length)s)',
        'integer': 'INTEGER',
        'double': 'DOUBLE',
        'decimal': 'DOUBLE',
        'date': 'DATE',
        'time': 'TIME',
        'datetime': 'TIMESTAMP',
        'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
        'reference': 'REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        }

    def EXTRACT(self,field,what):
        return "web2py_extract('%s',%s)" % (what,self.expand(field))

    @staticmethod
    def web2py_extract(lookup, s):
        table = {
            'year': (0, 4),
            'month': (5, 7),
            'day': (8, 10),
            'hour': (11, 13),
            'minute': (14, 16),
            'second': (17, 19),
            }
        try:
            (i, j) = table[lookup]
            return int(s[i:j])
        except:
            return None

    def __init__(self,db,uri,pool_size=0,folder=None,db_codec ='UTF-8'):
        self.db = db
        self.uri = uri
        self.pool_size = pool_size
        self.folder = folder
        self.db_codec = db_codec
        self.find_or_make_work_folder()
        path_encoding = sys.getfilesystemencoding() or locale.getdefaultlocale()[1]
        if uri=='sqlite:memory:':
            dbpath = ':memory:'
        else:
            dbpath = uri.split('://')[1]
            if dbpath[0] != '/':
                dbpath = os.path.join(self.folder.decode(path_encoding).encode('utf8'),dbpath)
        self.pool_connection(lambda dbpath=dbpath: sqlite3.Connection(dbpath, check_same_thread=False))
        self.connection.create_function('web2py_extract', 2, SQLiteAdapter.web2py_extract)

    def TRUNCATE(self,table,mode = ''):
        tablename = table._tablename
        return ['DELETE FROM %s;' % tablename,
                "DELETE FROM sqlite_sequence WHERE name='%s';" % tablename]

    def lastrowid(self,tablename):
        return self.cursor.lastrowid


class JDBCSQLiteAdapter(SQLiteAdapter):

    def __init__(self,db,uri,pool_size=0,folder=None,db_codec ='UTF-8'):
        self.db = db
        self.uri = uri
        self.pool_size = pool_size
        self.folder = folder
        self.db_codec = db_codec
        self.find_or_make_work_folder()
        path_encoding = sys.getfilesystemencoding() or locale.getdefaultlocale()[1]
        if uri=='sqlite:memory:':
            dbpath = ':memory:'
        else:
            dbpath = uri.split('://')[1]
            if dbpath[0] != '/':
                dbpath = os.path.join(self.folder.decode(path_encoding).encode('utf8'),dbpath)
        self.pool_connection(lambda dbpath=dbpath: zxJDBC.connect(java.sql.DriverManager.getConnection('jdbc:sqlite:'+dbpath)))
        self.connection.create_function('web2py_extract', 2, SQLiteAdapter.web2py_extract)

    def execute(self,a):
        return self.log_execute(a[:-1])


class MySQLAdapter(BaseAdapter):
    types = {
        'boolean': 'CHAR(1)',
        'string': 'VARCHAR(%(length)s)',
        'text': 'LONGTEXT',
        'password': 'VARCHAR(%(length)s)',
        'blob': 'LONGBLOB',
        'upload': 'VARCHAR(%(length)s)',
        'integer': 'INT',
        'double': 'DOUBLE',
        'decimal': 'NUMERIC(%(precision)s,%(scale)s)',
        'date': 'DATE',
        'time': 'TIME',
        'datetime': 'DATETIME',
        'id': 'INT AUTO_INCREMENT NOT NULL',
        'reference': 'INT, INDEX %(field_name)s__idx (%(field_name)s), FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        }

    def RANDOM(self):
        return 'RAND()'

    def SUBSTRING(self,field,parameters):
        return 'SUBSTRING(%s,%s,%s)' % (self.expand(field), paramters[0], parameters[1])

    def DROP(self,table,mode):
        # breaks db integrity but without this mysql does not drop table
        return ['SET FOREIGN_KEY_CHECKS=0;','DROP TABLE %s;' % table,'SET FOREIGN_KEY_CHECKS=1;']

    def support_distributed_transaction(self):
        return True

    def distributed_transaction_begin(self,key):
        self.execute('XA START;')

    def prepare(self,key):
        self.execute("XA END;")
        self.execute("XA PREPARE;")

    def commit_prepared(self,ley):
        self.execute("XA COMMIT;")

    def rollback_prepared(self,key):
        self.execute("XA ROLLBACK;")

    def concat_add(self,table):
        return '; ALTER TABLE %s ADD ' % table

    def __init__(self,db,uri,pool_size=0,folder=None,db_codec ='UTF-8'):
        self.db = db
        self.uri = uri
        self.pool_size = pool_size
        self.folder = folder
        self.db_codec = db_codec
        self.find_or_make_work_folder()
        uri = uri.split('://')[1]
        m = re.compile('^(?P<user>[^:@]+)(\:(?P<password>[^@]*))?@(?P<host>[^\:/]+)(\:(?P<port>[0-9]+))?/(?P<db>[^?]+)(\?set_encoding=(?P<charset>\w+))?$').match(uri)
        if not m:
            raise SyntaxError, \
                "Invalid URI string in DAL: %s" % self.uri
        user = m.group('user')
        if not user:
            raise SyntaxError, 'User required'
        password = m.group('password')
        if not password:
            password = ''
        host = m.group('host')
        if not host:
            raise SyntaxError, 'Host name required'
        db = m.group('db')
        if not db:
            raise SyntaxError, 'Database name required'
        port = int(m.group('port') or '3306')
        charset = m.group('charset') or 'utf8'
        self.pool_connection(lambda db=db,
                             user=user,
                             password=password,
                             host=host,
                             port=port,
                             charset=charset: MySQLdb.Connection(db=db,
                                                                 user=user,
                                                                 password=password,
                                                                 host=host,
                                                                 port=port,
                                                                 charset=charset,
                                                                 ))
        self.execute('SET FOREIGN_KEY_CHECKS=1;')
        self.execute("SET sql_mode='NO_BACKSLASH_ESCAPES';")

    def commit_on_alter_table(self):
        return True

    def lastrowid(self,tablename):
        self.execute('select last_insert_id();')
        return int(self.cursor.fetchone()[0])


class PostgreSQLAdapter(BaseAdapter):
    types = {
        'boolean': 'CHAR(1)',
        'string': 'VARCHAR(%(length)s)',
        'text': 'TEXT',
        'password': 'VARCHAR(%(length)s)',
        'blob': 'BYTEA',
        'upload': 'VARCHAR(%(length)s)',
        'integer': 'INTEGER',
        'double': 'FLOAT8',
        'decimal': 'NUMERIC(%(precision)s,%(scale)s)',
        'date': 'DATE',
        'time': 'TIME',
        'datetime': 'TIMESTAMP',
        'id': 'SERIAL PRIMARY KEY',
        'reference': 'INTEGER REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        }

    def RANDOM(self):
        return 'RANDOM()'

    def support_distributed_transaction(self):
        return True

    def distributed_transaction_begin(self,key):
        return

    def prepare(self,key):
        self.execute("PREPARE TRANSACTION '%s';" % key)

    def commit_prepared(self,key):
        self.execute("COMMIT PREPARED '%s';" % key)

    def rollback_prepared(self,key):
        self.execute("ROLLBACK PREPARED '%s';" % key)

    def __init__(self,db,uri,pool_size=0,folder=None,db_codec ='UTF-8'):
        self.db = db
        self.uri = uri
        self.pool_size = pool_size
        self.folder = folder
        self.db_codec = db_codec
        self.find_or_make_work_folder()
        uri = uri.split('://')[1]
        m = re.compile('^(?P<user>[^:@]+)(\:(?P<password>[^@]*))?@(?P<host>[^\:/]+)(\:(?P<port>[0-9]+))?/(?P<db>.+)$').match(uri)
        if not m:
            raise SyntaxError, "Invalid URI string in DAL"
        user = m.group('user')
        if not user:
            raise SyntaxError, 'User required'
        password = m.group('password')
        if not password:
            password = ''
        host = m.group('host')
        if not host:
            raise SyntaxError, 'Host name required'
        db = m.group('db')
        if not db:
            raise SyntaxError, 'Database name required'
        port = m.group('port') or '5432'
        msg = "dbname='%s' user='%s' host='%s' port=%s password='%s'"\
            % (db, user, host, port, password)
        self.pool_connection(lambda msg=msg: psycopg2.connect(msg))
        self.connection.set_client_encoding('UTF8')
        self.execute('BEGIN;')
        self.execute("SET CLIENT_ENCODING TO 'UNICODE';")
        self.execute("SET standard_conforming_strings=on;")

    def lastrowid(self,tablename):
        self.execute("select currval('%s_id_Seq')" % tablename)
        return int(self.cursor.fetchone()[0])


class JDBCPostgreSQLAdapter(PostgreSQLAdapter):

    def __init__(self,db,uri,pool_size=0,folder=None,db_codec ='UTF-8'):
        self.db = db
        self.uri = uri
        self.pool_size = pool_size
        self.folder = folder
        self.db_codec = db_codec
        self.find_or_make_work_folder()
        uri = uri.split('://')[1]
        m = re.compile('^(?P<user>[^:@]+)(\:(?P<password>[^@]*))?@(?P<host>[^\:/]+)(\:(?P<port>[0-9]+))?/(?P<db>.+)$').match(uri)
        if not m:
            raise SyntaxError, "Invalid URI string in DAL"
        user = m.group('user')
        if not user:
            raise SyntaxError, 'User required'
        password = m.group('password')
        if not password:
            password = ''
        host = m.group('host')
        if not host:
            raise SyntaxError, 'Host name required'
        db = m.group('db')
        if not db:
            raise SyntaxError, 'Database name required'
        port = m.group('port') or '5432'
        msg = ('jdbc:postgresql://%s:%s/%s' % (host, port, db), user, password)
        self.pool_connection(lambda msg=msg: zxJDBC.connect(*msg))
        self.connection.set_client_encoding('UTF8')
        self.execute('BEGIN;')
        self.execute("SET CLIENT_ENCODING TO 'UNICODE';")


class OracleAdapter(BaseAdapter):
    types = {
        'boolean': 'CHAR(1)',
        'string': 'VARCHAR2(%(length)s)',
        'text': 'CLOB',
        'password': 'VARCHAR2(%(length)s)',
        'blob': 'CLOB',
        'upload': 'VARCHAR2(%(length)s)',
        'integer': 'INT',
        'double': 'FLOAT',
        'decimal': 'NUMERIC(%(precision)s,%(scale)s)',
        'date': 'DATE',
        'time': 'CHAR(8)',
        'datetime': 'DATE',
        'id': 'NUMBER PRIMARY KEY',
        'reference': 'NUMBER, CONSTRAINT %(constraint_name)s FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        }

    def LEFT_JOIN(self):
        return 'LEFT OUTER JOIN'

    def RANDOM(self):
        return 'dbms_random.value'

    def NOT_NULL(self,default,field_type):
        return 'DEFAULT %s NOT NULL' % self.represent(default,field_type)

    def DROP(self,table,mode):
        return ['DROP TABLE %s %s;' % (table, mode), 'DROP SEQUENCE %s_sequence;' % table]

    def SELECT_LIMITBY(self, sql_s, sql_f, sql_t, sql_w, sql_o, limitby):
        if limitby:
            (lmin, lmax) = limitby
            if len(sql_w) > 1:
                sql_w_row = sql_w + ' AND w_row > %i' % lmin
            else:
                sql_w_row = 'WHERE w_row > %i' % lmin
            return 'SELECT %s %s FROM (SELECT w_tmp.*, ROWNUM w_row FROM (SELECT %s FROM %s%s%s) w_tmp WHERE ROWNUM<=%i) %s %s;' % (sql_s, sql_f, sql_f, sql_t, sql_w, sql_o, lmax, sql_t, sql_w_row)
        return 'SELECT %s %s FROM %s%s%s;' % (sql_s, sql_f, sql_t, sql_w, sql_o)

    def contraint_name(self, tablename, fieldname):
        constraint_name = BaseAdapter.contraint_name(self, tablename, fieldname)
        if len(constraint_name)>30:
            constraint_name = '%s_%s__constraint' % (tablename[:10], fieldname[:7])
        return constraint_name

    def represent_exceptions(self, obj, fieldtype):
        if fieldtype == 'blob':
            obj = base64.b64encode(str(obj))
            return ":CLOB('%s')" % obj
        elif fieldtype == 'date':
            if isinstance(obj, (datetime.date, datetime.datetime)):
                obj = obj.isoformat()[:10]
            else:
                obj = str(obj)
            return "to_date('%s','yyyy-mm-dd')" % obj
        elif fieldtype == 'datetime':
            if isinstance(obj, datetime.datetime):
                obj = obj.isoformat()[:19].replace('T',' ')
            elif isinstance(obj, datetime.date):
                obj = obj.isoformat()[:10]+' 00:00:00'
            else:
                obj = str(obj)
            return "to_date('%s','yyyy-mm-dd hh24:mi:ss')" % obj
        return None

    def __init__(self,db,uri,pool_size=0,folder=None,db_codec ='UTF-8'):
        self.db = db
        self.uri = uri
        self.pool_size = pool_size
        self.folder = folder
        self.db_codec = db_codec
        self.find_or_make_work_folder()
        uri = uri.split('://')[1]
        self.pool_connection(lambda uri=uri: cx_Oracle.connect(uri))
        self.execute("ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';")
        self.execute("ALTER SESSION SET NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD HH24:MI:SS';")
    oracle_fix = re.compile("[^']*('[^']*'[^']*)*\:(?P<clob>CLOB\('([^']+|'')*'\))")

    def execute(self, command):
        args = []
        i = 1
        while True:
            m = self.oracle_fix.match(command)
            if not m:
                break
            command = command[:m.start('clob')] + str(i) + command[m.end('clob'):]
            args.append(m.group('clob')[6:-2].replace("''", "'"))
            i += 1
        return self.log_execute(command[:-1], args)

    def create_sequence_and_triggers(self, query, table):
        tablename = table._tablename
        self.execute(query)
        self.execute('CREATE SEQUENCE %s_sequence START WITH 1 INCREMENT BY 1 NOMAXVALUE;' % tablename)
        self.execute('CREATE OR REPLACE TRIGGER %s_trigger BEFORE INSERT ON %s FOR EACH ROW BEGIN SELECT %s_sequence.nextval INTO :NEW.id FROM DUAL; END;\n' % (tablename, tablename, tablename))

    def commit_on_alter_table(self):
        return True

    def lastrowid(self,tablename):
        self.execute('SELECT %s_sequence.currval FROM dual;' % tablename)
        return int(self.cursor.fetchone()[0])


class MSSQLAdapter(BaseAdapter):
    types = {
        'boolean': 'BIT',
        'string': 'VARCHAR(%(length)s)',
        'text': 'TEXT',
        'password': 'VARCHAR(%(length)s)',
        'blob': 'IMAGE',
        'upload': 'VARCHAR(%(length)s)',
        'integer': 'INT',
        'double': 'FLOAT',
        'decimal': 'NUMERIC(%(precision)s,%(scale)s)',
        'date': 'DATETIME',
        'time': 'CHAR(8)',
        'datetime': 'DATETIME',
        'id': 'INT IDENTITY PRIMARY KEY',
        'reference': 'INT, CONSTRAINT %(constraint_name)s FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        'reference FK': ', CONSTRAINT FK_%(constraint_name)s FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        'reference TFK': ' CONSTRAINT FK_%(foreign_table)s_PK FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_table)s (%(foreign_key)s) ON DELETE %(on_delete_action)s',
        }

    def EXTRACT(self,field,what):
        return "DATEPART('%s' FROM %s)" % (what, self.expand(field))

    def LEFT_JOIN(self):
        return 'LEFT OUTER JOIN'

    def RANDOM(self):
        return 'NEWID()'

    def SUBSTRING(self,field,parameters):
        return 'SUBSTRING(%s,%s,%s)' % (self.expand(field), parameters[0], parameters[1])

    def PRIMARY_KEY(self,key):
        return 'PRIMARY KEY CLUSTERED (%s)' % key

    def SELECT_LIMITBY(self, sql_s, sql_f, sql_t, sql_w, sql_o, limitby):
        if limitby:
            (lmin, lmax) = limitby
            sql_s += ' TOP %i' % lmax
        return 'SELECT %s %s FROM %s%s%s;' % (sql_s, sql_f, sql_t, sql_w, sql_o)

    def represent_exceptions(self, obj, fieldtype):
        if fieldtype == 'boolean':
            if obj and not str(obj)[0].upper() == 'F':
                return '1'
            else:
                return '0'
        return None

    def __init__(self,db,uri,pool_size=0,folder=None,db_codec ='UTF-8'):
        self.db = db
        self.uri = uri
        self.pool_size = pool_size
        self.folder = folder
        self.db_codec = db_codec
        self.find_or_make_work_folder()
        # ## read: http://bytes.com/groups/python/460325-cx_oracle-utf8
        uri = uri.split('://')[1]
        if '@' not in uri:
            try:
                m = re.compile('^(?P<dsn>.+)$').match(uri)
                if not m:
                    raise SyntaxError, \
                        'Parsing uri string(%s) has no result' % self.uri
                dsn = m.group('dsn')
                if not dsn:
                    raise SyntaxError, 'DSN required'
            except SyntaxError, e:
                logging.error('NdGpatch error')
                raise e
            cnxn = 'DSN=%s' % dsn
        else:
            m = re.compile('^(?P<user>[^:@]+)(\:(?P<password>[^@]*))?@(?P<host>[^\:/]+)(\:(?P<port>[0-9]+))?/(?P<db>[^\?]+)(\?(?P<urlargs>.*))?$').match(uri)
            if not m:
                raise SyntaxError, \
                    "Invalid URI string in DAL: %s" % uri
            user = m.group('user')
            if not user:
                raise SyntaxError, 'User required'
            password = m.group('password')
            if not password:
                password = ''
            host = m.group('host')
            if not host:
                raise SyntaxError, 'Host name required'
            db = m.group('db')
            if not db:
                raise SyntaxError, 'Database name required'
            port = m.group('port') or '1433'
            # Parse the optional url name-value arg pairs after the '?'
            # (in the form of arg1=value1&arg2=value2&...)
            # Default values (drivers like FreeTDS insist on uppercase parameter keys)
            argsdict = { 'DRIVER':'{SQL Server}' }
            urlargs = m.group('urlargs') or ''
            argpattern = re.compile('(?P<argkey>[^=]+)=(?P<argvalue>[^&]*)')
            for argmatch in argpattern.finditer(urlargs):
                argsdict[str(argmatch.group('argkey')).upper()] = argmatch.group('argvalue')
            urlargs = ';'.join(['%s=%s' % (ak, av) for (ak, av) in argsdict.items()])
            cnxn = 'SERVER=%s;PORT=%s;DATABASE=%s;UID=%s;PWD=%s;%s' \
                % (host, port, db, user, password, urlargs)
        self.pool_connection(lambda cnxn=cnxn : pyodbc.connect(cnxn))

    def lastrowid(self,tablename):
        self.execute('SELECT @@IDENTITY;')
        return int(self.cursor.fetchone()[0])

    def integrity_error_class(self):
        return pyodbc.IntegrityError

    def rowslice(self,rows,minimum=0,maximum=None):
        if maximum==None:
            return rows[minimum:]
        return rows[minimum:maximum]


class MSSQLAdapter2(MSSQLAdapter):
    types = {
        'boolean': 'CHAR(1)',
        'string': 'NVARCHAR(%(length)s)',
        'text': 'NTEXT',
        'password': 'NVARCHAR(%(length)s)',
        'blob': 'IMAGE',
        'upload': 'NVARCHAR(%(length)s)',
        'integer': 'INT',
        'double': 'FLOAT',
        'decimal': 'NUMERIC(%(precision)s,%(scale)s)',
        'date': 'DATETIME',
        'time': 'CHAR(8)',
        'datetime': 'DATETIME',
        'id': 'INT IDENTITY PRIMARY KEY',
        'reference': 'INT, CONSTRAINT %(constraint_name)s FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        'reference FK': ', CONSTRAINT FK_%(constraint_name)s FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        'reference TFK': ' CONSTRAINT FK_%(foreign_table)s_PK FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_table)s (%(foreign_key)s) ON DELETE %(on_delete_action)s',
        }

    def represent(self, obj, fieldtype):
        value = BaseAdapter.represent(self, obj, fieldtype)
        if fieldtype == 'string' or fieldtype == 'text' and value[:1]=="'":
            value = 'N'+value
        return value

    def execute(self,a):
        return self.log_execute(a,'utf8')


class FireBirdAdapter(BaseAdapter):
    types = {
        'boolean': 'CHAR(1)',
        'string': 'VARCHAR(%(length)s)',
        'text': 'BLOB SUB_TYPE 1',
        'password': 'VARCHAR(%(length)s)',
        'blob': 'BLOB SUB_TYPE 0',
        'upload': 'VARCHAR(%(length)s)',
        'integer': 'INTEGER',
        'double': 'FLOAT',
        'decimal': 'NUMERIC(%(precision)s,%(scale)s)',
        'date': 'DATE',
        'time': 'TIME',
        'datetime': 'TIMESTAMP',
        'id': 'INTEGER PRIMARY KEY',
        'reference': 'INTEGER REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        }

    def RANDOM(self):
        return 'RAND()'

    def NOT_NULL(self,default,field_type):
        return 'DEFAULT %s NOT NULL' % self.represent(default,field_type)

    def SUBSTRING(self,field,parameters):
        return 'SUBSTRING(%s,%s,%s)' % (self.expand(field), parameters[0], parameters[1])

    def DROP(self,table,mode):
        return ['DROP TABLE %s %s;' % (table, mode), 'DROP GENERATOR GENID_%s;' % table]

    def SELECT_LIMITBY(self, sql_s, sql_f, sql_t, sql_w, sql_o, limitby):
        if limitby:
            (lmin, lmax) = limitby
            sql_s += ' FIRST %i SKIP %i' % (lmax - lmin, lmin)
        return 'SELECT %s %s FROM %s%s%s;' % (sql_s, sql_f, sql_t, sql_w, sql_o)

    def support_distributed_transaction(self):
        return True

    def __init__(self,db,uri,pool_size=0,folder=None,db_codec ='UTF-8'):
        self.db = db
        self.uri = uri
        self.pool_size = pool_size
        self.folder = folder
        self.db_codec = db_codec
        self.find_or_make_work_folder()
        uri = uri.split('://')[1]
        m = re.compile('^(?P<user>[^:@]+)(\:(?P<password>[^@]*))?@(?P<host>[^\:/]+)(\:(?P<port>[0-9]+))?/(?P<db>.+?)(\?set_encoding=(?P<charset>\w+))?$').match(uri)
        if not m:
            raise SyntaxError, "Invalid URI string in DAL: %s" % uri
        user = m.group('user')
        if not user:
            raise SyntaxError, 'User required'
        password = m.group('password')
        if not password:
            password = ''
        host = m.group('host')
        if not host:
            raise SyntaxError, 'Host name required'
        db = m.group('db')
        if not db:
            raise SyntaxError, 'Database name required'
        charset = m.group('charset') or 'UTF8'
        self.pool_connection(lambda dsn='%s/%s:%s' % (host,port,db),
                             user=user,
                             password=password,
                             charset=charset: \
                                 kinterbasdb.connect(dsn=dsn,
                                                     user=user,
                                                     password=password,
                                                     charset=charset))

    def create_sequence_and_triggers(self, query, table):
        tablename = table._tablename
        self.execute(query)
        self.execute('create generator GENID_%s;' % tablename)
        self.execute('set generator GENID_%s to 0;' % tablename)
        self.execute('create trigger trg_id_%s for %s active before insert position 0 as\nbegin\nif(new.id is null) then\nbegin\nnew.id = gen_id(GENID_%s, 1);\nend\nend;' % (tablename,tablename,tablename))

    def lastrowid(self,tablename):
        self.execute('SELECT gen_id(GENID_%s, 0) FROM rdb$database' % tablename)
        return int(self.db._adapter.cursor.fetchone()[0])


class FireBirdEmbeddedAdapter(FireBirdAdapter):

    def __init__(self,db,uri,pool_size=0,folder=None,db_codec ='UTF-8'):
        self.db = db
        self.uri = uri
        self.pool_size = pool_size
        self.folder = folder
        self.db_codec = db_codec
        self.find_or_make_work_folder()
        uri = uri.split('://')[1]
        m = re.compile('^(?P<user>[^:@]+)(\:(?P<password>[^@]*))?@(?P<path>[^\?]+)(\?set_encoding=(?P<charset>\w+))?$').match(uri)
        if not m:
            raise SyntaxError, \
                "Invalid URI string in DAL: %s" % self.uri
        user = m.group('user')
        if not user:
            raise SyntaxError, 'User required'
        password = m.group('password')
        if not password:
            password = ''
        pathdb = m.group('path')
        if not pathdb:
            raise SyntaxError, 'Path required'
        charset = m.group('charset')
        if not charset:
            charset = 'UTF8'
        host = ''
        self.pool_connection(lambda host=host,
                             database=dbpath,
                             user=user,
                             password=password,
                             charset=charset: \
                                 kinterbasdb.connect(host=host,
                                                     database=database,
                                                     user=user,
                                                     password=password,
                                                     charset=charset))


class InformixAdapter(BaseAdapter):
    types = {
        'boolean': 'CHAR(1)',
        'string': 'VARCHAR(%(length)s)',
        'text': 'BLOB SUB_TYPE 1',
        'password': 'VARCHAR(%(length)s)',
        'blob': 'BLOB SUB_TYPE 0',
        'upload': 'VARCHAR(%(length)s)',
        'integer': 'INTEGER',
        'double': 'FLOAT',
        'decimal': 'NUMERIC(%(precision)s,%(scale)s)',
        'date': 'DATE',
        'time': 'CHAR(8)',
        'datetime': 'DATETIME',
        'id': 'SERIAL',
        'reference': 'INTEGER REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        'reference FK': 'REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s CONSTRAINT FK_%(table_name)s_%(field_name)s',
        'reference TFK': 'FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_table)s (%(foreign_key)s) ON DELETE %(on_delete_action)s CONSTRAINT TFK_%(table_name)s_%(field_name)s',
        }

    def RANDOM(self):
        return 'Random()'

    def NOT_NULL(self,default,field_type):
        return 'DEFAULT %s NOT NULL' % self.represent(default,field_type)

    def SELECT_LIMITBY(self, sql_s, sql_f, sql_t, sql_w, sql_o, limitby):
        if limitby:
            (lmin, lmax) = limitby
            fetch_amt = lmax - lmin
            dbms_version = int(self.connection.dbms_version.split('.')[0])
            if lmin and (dbms_version >= 10):
                # Requires Informix 10.0+
                sql_s += ' SKIP %d' % (lmin, )
            if fetch_amt and (dbms_version >= 9):
                # Requires Informix 9.0+
                sql_s += ' FIRST %d' % (fetch_amt, )
        return 'SELECT %s %s FROM %s%s%s;' % (sql_s, sql_f, sql_t, sql_w, sql_o)

    def represent_exceptions(self, obj, fieldtype):
        if fieldtype == 'date':
            if isinstance(obj, (datetime.date, datetime.datetime)):
                obj = obj.isoformat()[:10]
            else:
                obj = str(obj)
            return "to_date('%s','yyyy-mm-dd')" % obj
        elif fieldtype == 'datetime':
            if isinstance(obj, datetime.datetime):
                obj = obj.isoformat()[:19].replace('T',' ')
            elif isinstance(obj, datetime.date):
                obj = obj.isoformat()[:10]+' 00:00:00'
            else:
                obj = str(obj)
            return "to_date('%s','yyyy-mm-dd hh24:mi:ss')" % obj
        return None

    def __init__(self,db,uri,pool_size=0,folder=None,db_codec ='UTF-8'):
        self.db = db
        self.uri = uri
        self.pool_size = pool_size
        self.folder = folder
        self.db_codec = db_codec
        self.find_or_make_work_folder()
        uri = uri.split('://')[1]
        m = re.compile('^(?P<user>[^:@]+)(\:(?P<password>[^@]*))?@(?P<host>[^\:/]+)(\:(?P<port>[0-9]+))?/(?P<db>.+)$').match(uri)
        if not m:
            raise SyntaxError, \
                "Invalid URI string in DAL: %s" % self.uri
        user = m.group('user')
        if not user:
            raise SyntaxError, 'User required'
        password = m.group('password')
        if not password:
            password = ''
        host = m.group('host')
        if not host:
            raise SyntaxError, 'Host name required'
        db = m.group('db')
        if not db:
            raise SyntaxError, 'Database name required'
        self.pool_connection(lambda dsn='%s@%s' % (db,user), user=user,password=password:
                                 informixdb.connect(dsn, user=user, password=password, autocommit=True))

    def execute(self,command):
        if command[-1:]==';':
            command = command[:-1]
        return self.log_execute(command)

    def lastrowid(self,tablename):
        return self.cursor.sqlerrd[1]

    def integrity_error_class(self):
        return informixdb.IntegrityError


class DB2Adapter(BaseAdapter):
    types = {
        'boolean': 'CHAR(1)',
        'string': 'VARCHAR(%(length)s)',
        'text': 'CLOB',
        'password': 'VARCHAR(%(length)s)',
        'blob': 'BLOB',
        'upload': 'VARCHAR(%(length)s)',
        'integer': 'INT',
        'double': 'DOUBLE',
        'decimal': 'NUMERIC(%(precision)s,%(scale)s)',
        'date': 'DATE',
        'time': 'TIME',
        'datetime': 'TIMESTAMP',
        'id': 'INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY NOT NULL',
        'reference': 'INT, FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        'reference FK': ', CONSTRAINT FK_%(constraint_name)s FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        'reference TFK': ' CONSTRAINT FK_%(foreign_table)s_PK FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_table)s (%(foreign_key)s) ON DELETE %(on_delete_action)s',
        }

    def LEFT_JOIN(self):
        return 'LEFT OUTER JOIN'

    def RANDOM(self):
        return 'RAND()'

    def SELECT_LIMITBY(self, sql_s, sql_f, sql_t, sql_w, sql_o, limitby):
        if limitby:
            (lmin, lmax) = limitby
            sql_o += ' FETCH FIRST %i ROWS ONLY' % lmax
        return 'SELECT %s %s FROM %s%s%s;' % (sql_s, sql_f, sql_t, sql_w, sql_o)

    def represent_exceptions(self, obj, fieldtype):
        if fieldtype == 'blob':
            obj = base64.b64encode(str(obj))
            return "BLOB('%s')" % obj
        elif fieldtype == 'datetime':
            if isinstance(obj, datetime.datetime):
                obj = obj.isoformat()[:19].replace('T','-').replace(':','.')
            elif isinstance(obj, datetime.date):
                obj = obj.isoformat()[:10]+'-00.00.00'
            return "'%s'" % obj
        return None

    def __init__(self,db,uri,pool_size=0,folder=None,db_codec ='UTF-8'):
        self.db = db
        self.uri = uri
        self.pool_size = pool_size
        self.folder = folder
        self.db_codec = db_codec
        self.find_or_make_work_folder()
        cnxn = uri.split(':', 1)[1]
        self.pool_connection(lambda cnxn=cnxn: pyodbc.connect(cnxn))

    def execute(self,command):
        if command[-1:]==';':
            command = command[:-1]
        return self.log_execute(command)

    def lastrowid(self,tablename):
        self.execute('SELECT DISTINCT IDENTITY_VAL_LOCAL() FROM %s;' % tablename)
        return int(self.db._adapter.cursor.fetchone()[0])

    def rowslice(self,rows,minimum=0,maximum=None):
        if maximum==None:
            return rows[minimum:]
        return rows[minimum:maximum]

INGRES_SEQNAME='ii***lineitemsequence' # NOTE invalid database object name
                                       # (ANSI-SQL wants this form of name
                                       # to be a delimited identifier)


class IngresAdapter(BaseAdapter):
    types = {
        'boolean': 'CHAR(1)',
        'string': 'VARCHAR(%(length)s)',
        'text': 'CLOB',
        'password': 'VARCHAR(%(length)s)',  ## Not sure what this contains utf8 or nvarchar. Or even bytes?
        'blob': 'BLOB',
        'upload': 'VARCHAR(%(length)s)',  ## FIXME utf8 or nvarchar... or blob? what is this type?
        'integer': 'INTEGER4', # or int8...
        'double': 'FLOAT8',
        'decimal': 'NUMERIC(%(precision)s,%(scale)s)',
        'date': 'ANSIDATE',
        'time': 'TIME WITHOUT TIME ZONE',
        'datetime': 'TIMESTAMP WITHOUT TIME ZONE',
        'id': 'integer4 not null unique with default next value for %s' % INGRES_SEQNAME,
        'reference': 'integer4, FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        'reference FK': ', CONSTRAINT FK_%(constraint_name)s FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        'reference TFK': ' CONSTRAINT FK_%(foreign_table)s_PK FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_table)s (%(foreign_key)s) ON DELETE %(on_delete_action)s', ## FIXME TODO
        }

    def LEFT_JOIN(self):
        return 'LEFT OUTER JOIN'

    def RANDOM(self):
        return 'RANDOM()'

    def SELECT_LIMITBY(self, sql_s, sql_f, sql_t, sql_w, sql_o, limitby):
        if limitby:
            (lmin, lmax) = limitby
            fetch_amt = lmax - lmin
            if fetch_amt:
                sql_s += ' FIRST %d ' % (fetch_amt, )
            if lmin:
                # Requires Ingres 9.2+
                sql_o += ' OFFSET %d' % (lmin, )
        return 'SELECT %s %s FROM %s%s%s;' % (sql_s, sql_f, sql_t, sql_w, sql_o)

    def __init__(self,db,uri,pool_size=0,folder=None,db_codec ='UTF-8'):
        self.db = db
        self.uri = uri
        self.pool_size = pool_size
        self.folder = folder
        self.db_codec = db_codec
        self.find_or_make_work_folder()
        connstr = self._uri.split(':', 1)[1]
        # Simple URI processing
        connstr=connstr.lstrip()
        while connstr.startswith('/'):
            connstr = connstr[1:]
        database_name=connstr # Assume only (local) dbname is passed in
        vnode='(local)'
        servertype='ingres'
        trace=(0, None) # No tracing
        self.pool_connection(lambda database=database_name,
                             vnode=vnode,
                             servertype=serverttype,
                             trace=trace: \
                                 ingresdbi.connect(database=database,
                                                   vnode=vnode,
                                                   servertype=servertype,
                                                   trace=trace))

    def create_sequence_and_triggers(self, query, table):
        # post create table auto inc code (if needed)
        # modify table to btree for performance....
        # Older Ingres releases could use rule/trigger like Oracle above.
        if hasattr(table,'_primarykey'):
            modify_tbl_sql = 'modify %s to btree unique on %s' % \
                (table._tablename,
                 ', '.join(["'%s'" % x for x in table.primarykey]))
            self.execute(modify_tbl_sql)
        else:
            tmp_seqname='%s_iisq' % table._tablename
            query=query.replace(INGRES_SEQNAME, tmp_seqname)
            self.execute('create sequence %s' % tmp_seqname)
            self.execute(query)
            self.execute('modify %s to btree unique on %s' % (table._tablename, 'id'))


    def lastrowid(self,tablename):
        tmp_seqname='%s_iisq' % tablename
        self.execute('select current value for %s' % tmp_seqname)
        return int(self.cursor.fetchone()[0]) # don't really need int type cast here...

    def integrity_error_class(self):
        return ingresdbi.IntegrityError


class IngresUnicodeAdapter(IngresAdapter):
    types = {
        'boolean': 'CHAR(1)',
        'string': 'NVARCHAR(%(length)s)',
        'text': 'NCLOB',
        'password': 'NVARCHAR(%(length)s)',  ## Not sure what this contains utf8 or nvarchar. Or even bytes?
        'blob': 'BLOB',
        'upload': 'VARCHAR(%(length)s)',  ## FIXME utf8 or nvarchar... or blob? what is this type?
        'integer': 'INTEGER4', # or int8...
        'double': 'FLOAT8',
        'decimal': 'NUMERIC(%(precision)s,%(scale)s)',
        'date': 'ANSIDATE',
        'time': 'TIME WITHOUT TIME ZONE',
        'datetime': 'TIMESTAMP WITHOUT TIME ZONE',
        'id': 'integer4 not null unique with default next value for %s'% INGRES_SEQNAME,
        'reference': 'integer4, FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        'reference FK': ', CONSTRAINT FK_%(constraint_name)s FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        'reference TFK': ' CONSTRAINT FK_%(foreign_table)s_PK FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_table)s (%(foreign_key)s) ON DELETE %(on_delete_action)s', ## FIXME TODO
        }

ADAPTERS = {
    'sqlite': SQLiteAdapter,
    'mysql': MySQLAdapter,
    'postgres': PostgreSQLAdapter,
    'oracle': OracleAdapter,
    'mssql': MSSQLAdapter,
    'mssql2': MSSQLAdapter2,
    'db2': DB2Adapter,
    'informix': InformixAdapter,
    'firebird': FireBirdAdapter,
    'firebird_embedded': FireBirdAdapter,
    'ingres': IngresAdapter,
    'ingresu': IngresUnicodeAdapter,
    'jdbc:sqlite': JDBCSQLiteAdapter,
    'jdbc:postgres': JDBCPostgreSQLAdapter,
}


def sqlhtml_validators(field):
    """
    Field type validation, using web2py's validators mechanism.

    makes sure the content of a field is in line with the declared
    fieldtype
    """
    field_type, field_length = field.type, field.length
    if isinstance(field_type, SQLCustomType):
        if hasattr(field_type,'validator'):
            return field_type.validator
        else:
            field_type = field_type.type
    requires=[]
    if field_type == 'string':
        requires.append(validators.IS_LENGTH(field_length))
    elif field_type == 'text':
        requires.append(validators.IS_LENGTH(2 ** 16))
    elif field_type == 'password':
        requires.append(validators.IS_LENGTH(field_length))
    elif field_type == 'double':
        requires.append(validators.IS_FLOAT_IN_RANGE(-1e100, 1e100))
    elif field_type == 'integer':
        requires.append(validators.IS_INT_IN_RANGE(-1e100, 1e100))
    elif field_type[:7] == 'decimal':
        requires.append(validators.IS_DECIMAL_IN_RANGE(-10**10, 10**10))
    elif field_type == 'date':
        requires.append(validators.IS_DATE())
    elif field_type == 'time':
        requires.append(validators.IS_TIME())
    elif field_type == 'datetime':
        requires.append(validators.IS_DATETIME())
    elif field._db and field_type[:9] == 'reference' and \
            field_type.find('.')<0 and \
            field_type[10:] in field._db.tables:
        referenced = field._db[field_type[10:]]

        if hasattr(referenced,'_format') and referenced._format:
            def f(r,id):
                row=r[id]
                if not row:
                    return id
                elif isinstance(r._format,str):
                    return r._format % row
                else:
                    return r._format(row)
            field.represent = lambda id, r=referenced, f=f: f(r,id)
            requires = validators.IS_IN_DB(field._db,referenced.id,
                                           referenced._format)
            if field.unique:
                requires._and = validators.IS_NOT_IN_DB(field._db,field)
            return requires

    if field.unique:
        requires.insert(0,validators.IS_NOT_IN_DB(field._db,field))
    sff=['in','do','da','ti','de']
    if field.notnull and not field_type[:2] in sff:
        requires.insert(0,validators.IS_NOT_EMPTY())
    elif not field.notnull and field_type[:2] in sff:
        requires[-1]=validators.IS_EMPTY_OR(requires[-1])
    return requires


def cleanup(text):
    """
    validates that the given text is clean: only contains [0-9a-zA-Z_]
    """

    if re.compile('[^0-9a-zA-Z_]').findall(text):
        raise SyntaxError, \
            'only [0-9a-zA-Z_] allowed in table and field names, received %s' \
            % text
    return text


def autofields(db, text):
    raise SyntaxError, "work in progress"
    m = re.compile('(?P<i>\w+)')
    (tablename, fields) = text.lower().split(':', 1)
    tablename = tablename.replace(' ', '_')
    newfields = []
    for field in fields.split(','):
        if field.find(' by ') >= 0:
            (items, keys) = field.split(' by ')
        else:
            (items, keys) = (field, '%(id)s')
        items = m.findall(items)
        if not items:
            break
        keys = m.sub('%(\g<i>)s', keys)
        (requires, notnull, unique) = (None, False, False)
        if items[-1] in ['notnull']:
            (notnull, items) = (True, items[:-1])
        if items[-1] in ['unique']:
            (unique, items) = (True, items[:-1])
        if items[-1] in ['text', 'date', 'datetime', 'time', 'blob', 'upload', 'password',
                         'integer', 'double', 'boolean', 'string']:
            (items, t) = (items[:-1], items[-1])
        elif items[-1] in db.tables:
            t = 'reference %s' % items[-1]
            requires = validators.IS_IN_DB(db, '%s.%s' % (items[-1], db.tables[items[-1]].id.name), keys)
        else:
            t = 'string'
        name = '_'.join(items)
        if unique:
            if requires:
                raise SyntaxError, "Sorry not supported"
            requires = validators.IS_NOT_IN_DB(db, '%s.%s' % (tablename, name))
        if requires and not notnull:
            requires = validators.IS_EMPTY_OR(requires)
        label = ' '.join([i.capitalize() for i in items])
        newfields.append(db.Field(name, t, label=label, requires=requires,
                                  notnull=notnull, unique=unique))
    return tablename, newfields


class Row(dict):

    """
    a dictionary that lets you do d['a'] as well as d.a
    this is only used to store a Row
    """

    def __getitem__(self, key):
        key=str(key)
        if key in self.get('_extra',{}):
            return self._extra[key]
        return dict.__getitem__(self, key)

    def __call__(self,key):
        key=str(key)
        if key in self.get('_extra',{}):
            return self._extra[key]
        return dict.__getitem__(self, key) #### are we sure

    def __setitem__(self, key, value):
        dict.__setitem__(self, str(key), value)

    def __getattr__(self, key):
        return dict.__getitem__(self,key)

    def __setattr__(self, key, value):
        dict.__setitem__(self,key,value)

    def __repr__(self):
        return '<Row ' + dict.__repr__(self) + '>'

    def __int__(self):
        return dict.__getitem__(self,'id')

    def __eq__(self,other):
        try:
            return self.as_dict() == other.as_dict()
        except AttributeError:
            return False

    def __ne__(self,other):
        return not (self == other)

    def as_dict(self,datetime_to_str=False):
        d = dict(self)
        for k in copy.copy(d.keys()):
            v=d[k]
            if isinstance(v,Row):
                d[k]=v.as_dict()
            elif isinstance(v,Reference):
                d[k]=int(v)
            elif isinstance(v, (datetime.date, datetime.datetime, datetime.time)):
                if datetime_to_str:
                    d[k] = v.isoformat().replace('T',' ')[:19]
            elif not isinstance(v,(str,unicode,int,long,float,bool)):
                del d[k]
        return d


def Row_unpickler(data):
    return Row(marshal.loads(data))

def Row_pickler(data):
    return Row_unpickler, (marshal.dumps(data.as_dict()),)

copy_reg.pickle(Row, Row_pickler, Row_unpickler)


class SQLCallableList(list):

    def __call__(self):
        return copy.copy(self)


class DAL(dict):

    """
    an instance of this class represents a database connection

    Example::

       db = DAL('sqlite://test.db')
       db.define_table('tablename', Field('fieldname1'),
                                    Field('fieldname2'))
    """

    @staticmethod
    def _set_thread_folder(folder):
        """
        # ## this allows gluon to comunite a folder for this thread
        # ## <<<<<<<<< Should go away as new DAL replaces old sql.py
        """
        BaseAdapter.set_thread_folder(folder)

    @staticmethod
    def distributed_transaction_begin(*instances):
        if not instances:
            return
        thread_key = '%s.%i' % (socket.gethostname(), thread.get_ident())
        keys = ['%s.%i' % (thread_key, i) for (i,db) in instances]
        instances = enumerate(instances)
        for (i, db) in instances:
            if not db._adapter.support_distributed_transaction():
                raise SyntaxError, \
                    'distributed transaction not suported by %s' % db._dbname
        for (i, db) in instances:
            db._adapter.distributed_transaction_begin(keys[i])

    @staticmethod
    def distributed_transaction_commit(*instances):
        if not instances:
            return
        instances = enumerate(instances)
        thread_key = '%s.%i' % (socket.gethostname(), thread.get_ident())
        keys = ['%s.%i' % (thread_key, i) for (i,db) in instances]
        for (i, db) in instances:
            if not db._adapter.support_distributed_transaction():
                raise SyntaxError, \
                    'distributed transaction not suported by %s' % db._dbanme
        try:
            for (i, db) in instances:
                db._adapter.prepare(keys[i])
        except:
            for (i, db) in instances:
                db._adapter.rollback_prepared(keys[i])
            raise Exception, 'failure to commit distributed transaction'
        else:
            for (i, db) in instances:
                db._adapter.commit_prepared(keys[i])
        return

    def __init__(self, uri='sqlite://dummy.db', pool_size=0, folder=None,
                 db_codec='UTF-8', check_reserved=None):
        """
        Creates a new Database Abstraction Layer instance.

        Keyword arguments:

        :uri: string that contains information for connecting to a database.
               (default: 'sqlite://dummy.db')
        :pool_size: How many open connections to make to the database object.
        :folder: <please update me>
        :db_codec: string encoding of the database (default: 'UTF-8')
        :check_reserve: list of adapters to check tablenames and column names
                         against sql reserved keywords. (Default None)

        * 'common' List of sql keywords that are common to all database types
                such as "SELECT, INSERT". (recommended)
        * 'all' Checks against all known SQL keywords. (not recommended)
                <adaptername> Checks against the specific adapters list of keywords
                (recommended)
        * '<adaptername>_nonreserved' Checks against the specific adapters
                list of nonreserved keywords. (if available)
        """
        self._uri = str(uri) # NOTE: assuming it is in utf8!!!
        self._pool_size = pool_size
        self._db_codec = db_codec
        self._lastsql = ''
        self._logger = Logger(folder)
        if is_jdbc:
            prefix = 'jdbc:'
        else:
            prefix = ''
        if uri and uri.find(':')>=0:
            self._dbname = uri.split(':')[0]
            self._adapter = ADAPTERS[prefix+self._dbname](self,uri,pool_size,folder,db_codec)
        else:
            self._adapter = BaseAdapter(self,uri)
        self.tables = SQLCallableList()
        self.check_reserved = check_reserved
        if self.check_reserved:
            from reserved_sql_keywords import ADAPTERS as RSK
            self.RSK = RSK

    def check_reserved_keyword(self, name):
        """
        Validates ``name`` against SQL keywords
        Uses self.check_reserve which is a list of
        operators to use.
        self.check_reserved
        ['common', 'postgres', 'mysql']
        self.check_reserved
        ['all']
        """
        for backend in self.check_reserved:
            if name.upper() in self.RSK[backend]:
                raise SyntaxError, 'invalid table/column name "%s" is a "%s" reserved SQL keyword' % (name, backend.upper())

    def define_table(
        self,
        tablename,
        *fields,
        **args
        ):

        for key in args:
            if key not in ['migrate','primarykey','fake_migrate','format']:
                raise SyntaxError, 'invalid table "%s" attribute: %s' % (tablename, key)
        migrate = args.get('migrate',True)
        fake_migrate = args.get('fake_migrate', False)
        format = args.get('format',None)
        tablename = cleanup(tablename)
        if hasattr(self,tablename) or tablename[0] == '_':
            raise SyntaxError, 'invalid table name: %s' % tablename
        if tablename in self.tables:
            raise SyntaxError, 'table already defined: %s' % tablename
        if self.check_reserved:
            self.check_reserved_keyword(tablename)

        t = self[tablename] = Table(self, tablename, *fields,
                                    **dict(primarykey=args.get('primarykey',None)))
        # db magic
        if self._uri == 'None':
            return t

        t._create_references()

        if migrate:
            sql_locker.acquire()
            try:
                t._create(migrate=migrate, fake_migrate=fake_migrate)
            finally:
                sql_locker.release()
        else:
            t._dbt = None
        self.tables.append(tablename)
        t._format = format
        return t

    def __iter__(self):
        for tablename in self.tables:
            yield self[tablename]

    def __getitem__(self, key):
        return dict.__getitem__(self, str(key))

    def __setitem__(self, key, value):
        dict.__setitem__(self, str(key), value)

    def __getattr__(self, key):
        return dict.__getitem__(self,key)

    def __setattr__(self, key, value):
        if key[:1]!='_' and key in self:
            raise SyntaxError, \
                'Object %s exists and cannot be redefined' % key
        self[key] = value

    def __repr__(self):
        return '<DAL ' + dict.__repr__(self) + '>'

    def __call__(self, query=None):
        return Set(self, query)

    def commit(self):
        self._adapter.commit()

    def rollback(self):
        self._adapter.rollback()

    def executesql(self, query, placeholders=None, as_dict=False):
        """
        placeholders is optional and will always be None when using DAL
        if using raw SQL with placeholders, placeholders may be
        a sequence of values to be substituted in
        or, *if supported by the DB driver*, a dictionary with keys
        matching named placeholders in your SQL.

        Added 2009-12-05 "as_dict" optional argument. Will always be
        None when using DAL. If using raw SQL can be set to True
        and the results cursor returned by the DB driver will be
        converted to a sequence of dictionaries keyed with the db
        field names. Tested with SQLite but should work with any database
        since the cursor.description used to get field names is part of the
        Python dbi 2.0 specs. Results returned with as_dict = True are
        the same as those returned when applying .to_list() to a DAL query.

        [{field1: value1, field2: value2}, {field1: value1b, field2: value2b}]

        --bmeredyk
        """
        if placeholders:
            self._adapter.execute(query, placeholders)
        else:
            self._adapter.execute(query)
        if as_dict:
            if not hasattr(self._cursor,'description'):
                raise RuntimeError, "database does not support executesql(...,as_dict=True)"
            # Non-DAL legacy db query, converts cursor results to dict.
            # sequence of 7-item sequences. each sequence tells about a column.
            # first item is always the field name according to Python Database API specs
            columns = self._cursor.description
            # reduce the column info down to just the field names
            fields = [f[0] for f in columns]
            # will hold our finished resultset in a list
            data = self._cursor.fetchall()
            # convert the list for each row into a dictionary so it's
            # easier to work with. row['field_name'] rather than row[0]
            return [dict(zip(fields,row)) for row in data]
        # see if any results returned from database
        try:
            return self._cursor.fetchall()
        except:
            return None

    def _update_referenced_by(self, other):
        for tablename in self.tables:
            by = self[tablename]._referenced_by
            by[:] = [item for item in by if not item[0] == other]

    def export_to_csv_file(self, ofile, *args, **kwargs):
        for table in self.tables:
            ofile.write('TABLE %s\r\n' % table)
            self(self[table]['id'] > 0).select().export_to_csv_file(ofile, *args, **kwargs)
            ofile.write('\r\n\r\n')
        ofile.write('END')

    def import_from_csv_file(self, ifile, id_map={}, null='<NULL>', unique='uuid', *args, **kwargs):
        for line in ifile:
            line = line.strip()
            if not line:
                continue
            elif line == 'END':
                return
            elif not line[:6] == 'TABLE ' or not line[6:] in self.tables:
                raise SyntaxError, 'invalid file format'
            else:
                tablename = line[6:]
                self[tablename].import_from_csv_file(ifile, id_map, null, unique, *args, **kwargs)


class SQLALL(object):
    """
    Helper class providing a comma-separated string having all the field names
    (prefixed by table name and '.')

    normally only called from within gluon.sql
    """

    def __init__(self, table):
        self.table = table

    def __str__(self):
        return ', '.join([str(field) for field in self.table])


class Reference(int):

    def __allocate(self):
        if not self._record:
            self._record = self._table[int(self)]
        if not self._record:
            raise Exception, "undefined record"

    def __getattr__(self,key):
        if key == 'id':
            return int(self)
        self.__allocate()
        return self._record.get(key,None)

    def __setattr__(self,key,value):
        if key[:1]=='_':
            int.__setattr__(self,key,value)
            return
        self.__allocate()
        self._record[key] =  value

    def __getitem__(self,key):
        if key == 'id':
            return int(self)
        self.__allocate()
        return self._record.get(key, None)

    def __setitem__(self,key,value):
        self.__allocate()
        self._record[key] =  value

def Reference_unpickler(data):
    return marshal.loads(data)

def Reference_pickler(data):
    try:
        marshal_dump = marshal.dumps(int(data))
    except AttributeError:
        marshal_dump = 'i%s' % struct.pack('<i',int(data))
    return (Reference_unpickler, (marshal_dump,))

copy_reg.pickle(Reference, Reference_pickler, Reference_unpickler)


class Table(dict):

    """
    an instance of this class represents a database table

    Example::

        db = DAL(...)
        db.define_table('users', Field('name'))
        db.users.insert(name='me') # print db.users._insert(...) to see SQL
        db.users.drop()
    """

    def __init__(
        self,
        db,
        tablename,
        *fields,
        **args
        ):
        """
        Initializes the table and performs checking on the provided fields.

        Each table will have automatically an 'id'.

        If a field is of type Table, the fields (excluding 'id') from that table
        will be used instead.

        :raises SyntaxError: when a supplied field is of incorrect type.
        """
        primarykey = args.get('primarykey',None)
        if primarykey and not isinstance(primarykey,list):
            raise SyntaxError, "primarykey must be a list of fields from table '%s'" % tablename
        elif primarykey:
            self._primarykey = primarykey
            new_fields = []
        else:
            new_fields = [ Field('id', 'id') ]
        for field in fields:
            if hasattr(field,'_db'):
                field = copy.copy(field)
            if isinstance(field, Field):
                if field.type == 'id':
                    # Keep this alias for the primary key.
                    new_fields[0] = field
                else:
                    new_fields.append(field)
            elif isinstance(field, Table):
                new_fields += [copy.copy(field[f]) for f in
                               field.fields if field[f].type!='id']
            else:
                raise SyntaxError, \
                    'define_table argument is not a Field: %s' % field
        fields = new_fields
        self._db = db
        self._tablename = tablename
        self.fields = SQLCallableList()
        self.virtualfields = []
        fields = list(fields)

        for field in fields:
            if db and db.check_reserved:
                db.check_reserved_keyword(field.name)

            self.fields.append(field.name)
            self[field.name] = field
            if field.type == 'id':
                self['id'] = field
            field._tablename = self._tablename
            field._table = self
            field._db = self._db
            if field.requires == '<default>':
                field.requires = sqlhtml_validators(field)
        self.ALL = SQLALL(self)

        if hasattr(self,'_primarykey'):
            for k in self._primarykey:
                if k not in self.fields:
                    raise SyntaxError, \
                        "primarykey must be a list of fields from table '%s " % tablename
                else:
                    self[k].notnull = True

    def _create_references(self):
        self._referenced_by = []
        for fieldname in self.fields:
            field=self[fieldname]
            if isinstance(field.type,str) and field.type[:10] == 'reference ':
                ref = field.type[10:].strip()
                if not ref.split():
                    raise SyntaxError, 'Table: reference to nothing: %s' %ref
                refs = ref.split('.')
                rtablename = refs[0]
                rtable = self._db[rtablename]
                if not rtablename in self._db:
                    raise SyntaxError, "Table: table '%s'does not exist" % rtablename
                if self._tablename in rtable.fields:
                    raise SyntaxError, \
                        'Field: table %s has same name as a field in referenced table %s' \
                        % (self._tablename, rtablename)
                elif len(refs)==2:
                    rfieldname = refs[1]
                    if not hasattr(rtable,'_primarykey'):
                        raise SyntaxError,\
                            'keyed tables can only reference other keyed tables (for now)'
                    if rfieldname not in rtable.fields:
                        raise SyntaxError,\
                            "invalid field '%s' for referenced table '%s' in table '%s'" \
                            % (rfieldname, rtablename, self._tablename)
                rtable._referenced_by.append((self._tablename, field.name))

    def _filter_fields(self, record, id=False):
        return dict([(k, v) for (k, v) in record.items() if k
                     in self.fields and (self[k].type!='id' or id)])

    def _build_query(self,key):
        """ for keyed table only """
        query = None
        for k,v in key.iteritems():
            if k in self._primarykey:
                if query:
                    query = query & (self[k] == v)
                else:
                    query = (self[k] == v)
            else:
                raise SyntaxError, \
                'Field %s is not part of the primary key of %s' % \
                (k,self._tablename)
        return query

    def __getitem__(self, key):
        if not key:
            return None
        elif isinstance(key, dict):
            """ for keyed table """
            query = self._build_query(key)
            rows = self._db(query).select()
            if rows:
                return rows[0]
            return None
        elif str(key).isdigit():
            return self._db(self.id == key).select()._first()
        elif key:
            return dict.__getitem__(self, str(key))


    def __setitem__(self, key, value):
        if isinstance(key, dict) and isinstance(value, dict):
            """ option for keyed table """
            if set(key.keys()) == set(self._primarykey):
                value = self._filter_fields(value)
                kv = {}
                kv.update(value)
                kv.update(key)
                if not self.insert(**kv):
                    query = self._build_query(key)
                    self._db(query).update(**self._filter_fields(value))
            else:
                raise SyntaxError,\
                    'key must have all fields from primary key: %s'%\
                    (self._primarykey)
        elif str(key).isdigit():
            if key == 0:
                self.insert(**self._filter_fields(value))
            elif not self._db(self.id == key)\
                    .update(**self._filter_fields(value)):
                raise SyntaxError, 'No such record: %s' % key
        else:
            if isinstance(key, dict):
                raise SyntaxError,\
                    'value must be a dictionary: %s' % value
            dict.__setitem__(self, str(key), value)

    def __delitem__(self, key):
        if isinstance(key, dict):
            query = self._build_query(key)
            if not self._db(query).delete():
                raise SyntaxError, 'No such record: %s' % key
        elif not str(key).isdigit() or not self._db(self.id == key).delete():
            raise SyntaxError, 'No such record: %s' % key

    def __getattr__(self, key):
        return dict.__getitem__(self,key)

    def __setattr__(self, key, value):
        if key in self:
            raise SyntaxError, 'Object exists and cannot be redefined: %s' % key
        dict.__setitem__(self,key,value)

    def __iter__(self):
        for fieldname in self.fields:
            yield self[fieldname]

    def __repr__(self):
        return '<Table ' + dict.__repr__(self) + '>'

    def __str__(self):
        if self.get('_ot', None):
            return '%s AS %s' % (self._ot, self._tablename)
        return self._tablename

    def with_alias(self, alias):
        return self._db._adapter.alias(self,alias)

    def _create(self, migrate=True, fake_migrate=False):
        fields = []
        sql_fields = {}
        sql_fields_aux = {}
        TFK = {}
        for k in self.fields:
            field = self[k]
            if isinstance(field.type,SQLCustomType):
                ftype = field.type.native or field.type.type
            elif field.type[:10] == 'reference ':
                referenced = field.type[10:].strip()
                constraint_name = self._db._adapter.contraint_name(self._tablename, field.name)
                if hasattr(self,'_primarykey'):
                    rtablename,rfieldname = ref.split('.')
                    rtable = self._db[rtablename]
                    rfield = rtable[rfieldname]
                    # must be PK reference or unique
                    if rfieldname in rtable._primarykey or rfield.unique:
                        ftype = self._db._adapter.types[rfield.type[:9]] %dict(length=rfield.length)
                        # multicolumn primary key reference?
                        if not rfield.unique and len(rtable._primarykey)>1 :
                            # then it has to be a table level FK
                            if rtablename not in TFK:
                                TFK[rtablename] = {}
                            TFK[rtablename][rfieldname] = field.name
                        else:
                            ftype = ftype + \
                                self._db._adapter.types['reference FK'] %dict(\
                                constraint_name=constraint_name,
                                table_name=self._tablename,
                                field_name=field.name,
                                foreign_key='%s (%s)'%(rtablename, rfieldname),
                                on_delete_action=field.ondelete)
                else:
                    ftype = self._db._adapter.types[field.type[:9]]\
                        % dict(table_name=self._tablename,
                               field_name=field.name,
                               constraint_name=constraint_name,
                               foreign_key=referenced + ('(%s)' % self._db[referenced].fields[0]),
                               on_delete_action=field.ondelete)
            elif field.type[:7] == 'decimal':
                precision, scale = [int(x) for x in field.type[8:-1].split(',')]
                ftype = self._db._adapter.types[field.type[:7]] % \
                    dict(precision=precision,scale=scale)
            elif not field.type in self._db._adapter.types:
                raise SyntaxError, 'Field: unknown field type: %s for %s' % \
                    (field.type, field.name)
            else:
                ftype = self._db._adapter.types[field.type]\
                     % dict(length=field.length)
            if not field.type[:10] in ['id', 'reference ']:
                if field.notnull:
                    ftype += ' NOT NULL'
                if field.unique:
                    ftype += ' UNIQUE'

            # add to list of fields
            sql_fields[field.name] = ftype

            if field.default:
                not_null = self._db._adapter.NOT_NULL(field.default,field.type)
                sql_fields_aux[field.name] = ftype.replace('NOT NULL',not_null)
            else:
                sql_fields_aux[field.name] = ftype

            fields.append('%s %s' % (field.name, ftype))
        other = ';'

        # backend-specific extensions to fields
        if self._db._dbname == 'mysql':
            if not self._primerykey:
                fields.append('PRIMARY KEY(%s)' % self.fields[0])
            other = ' ENGINE=InnoDB CHARACTER SET utf8;'

        fields = ',\n    '.join(fields)
        for rtablename in TFK:
            rfields = TFK[rtablename]
            pkeys = self._db[rtablename]._primarykey
            fkeys = [ rfields[k] for k in pkeys ]
            fields = fields + ',\n    ' + \
                     self._db._adapter.types['reference TFK'] %\
                     dict(table_name=self._tablename,
                     field_name=', '.join(fkeys),
                     foreign_table=rtablename,
                     foreign_key=', '.join(pkeys),
                     on_delete_action=field.ondelete)

        if hasattr(self,'_primarykey'):
            query = '''CREATE TABLE %s(\n    %s,\n`    %s) %s''' % \
               (self._tablename, fields, self._db._adapter.PRIMARY_KEY(', '.join(self._primarykey),other))
        else:
            query = '''CREATE TABLE %s(\n    %s\n)%s''' % \
                (self._tablename, fields, other)

        if self._db._uri[:10] == 'sqlite:///':
            path_encoding = sys.getfilesystemencoding() or \
                locale.getdefaultlocale()[1]
            dbpath = self._db._uri[9:self._db._uri.rfind('/')]\
                .decode('utf8').encode(path_encoding)
        else:
            dbpath = self._db._adapter.folder
        if not migrate:
            return query
        elif self._db._uri[:14] == 'sqlite:memory:':
            self._dbt = None
        elif isinstance(migrate, str):
            self._dbt = os.path.join(dbpath, migrate)
        else:
            self._dbt = os.path.join(dbpath, '%s_%s.table' \
                     % (md5_hash(self._db._uri), self._tablename))
        if self._dbt:
            self._loggername = os.path.join(dbpath, 'sql.log')
            logfile = open(self._loggername, 'a')
        else:
            logfile = None
        if not self._dbt or not os.path.exists(self._dbt):
            if self._dbt:
                logfile.write('timestamp: %s\n'
                               % datetime.datetime.today().isoformat())
                logfile.write(query + '\n')
            if not fake_migrate:
                self._db._adapter.create_sequence_and_triggers(query,self)
                self._db.commit()
            if self._dbt:
                tfile = open(self._dbt, 'w')
                portalocker.lock(tfile, portalocker.LOCK_EX)
                cPickle.dump(sql_fields, tfile)
                portalocker.unlock(tfile)
                tfile.close()
            if self._dbt:
                if fake_migrate:
                    logfile.write('faked!\n')
                else:
                    logfile.write('success!\n')
        else:
            tfile = open(self._dbt, 'r')
            portalocker.lock(tfile, portalocker.LOCK_SH)
            sql_fields_old = cPickle.load(tfile)
            portalocker.unlock(tfile)
            tfile.close()
            if sql_fields != sql_fields_old:
                self._migrate(sql_fields, sql_fields_old,
                              sql_fields_aux, logfile,
                              fake_migrate=fake_migrate)

        return query

    def _migrate(
        self,
        sql_fields,
        sql_fields_old,
        sql_fields_aux,
        logfile,
        fake_migrate=False,
        ):
        keys = sql_fields.keys()
        for key in sql_fields_old:
            if not key in keys:
                keys.append(key)
        new_add = self._db._adapter.concat_add(self)
        for key in keys:
            if not key in sql_fields_old:
                query = ['ALTER TABLE %s ADD %s %s;' % \
                         (self._tablename, key, sql_fields_aux[key].replace(', ', new_add))]
            elif self._db._dbname == 'sqlite':
                query = None
            elif not key in sql_fields:
                query = ['ALTER TABLE %s DROP COLUMN %s;' % (self._tablename, key)]
            elif sql_fields[key] != sql_fields_old[key] and \
                 not (self[key].type[:10]=='reference ' and \
                      sql_fields[key][:4]=='INT,' and \
                      sql_fields_old[key][:13]=='INT NOT NULL,'):

                # ## FIX THIS WHEN DIFFERENCES IS ONLY IN DEFAULT
                # 2

                t = self._tablename
                tt = sql_fields_aux[key].replace(', ', new_add)
                query = ['ALTER TABLE %s ADD %s__tmp %s;' % (t, key, tt),
                         'UPDATE %s SET %s__tmp=%s;' % (t, key, key),
                         'ALTER TABLE %s DROP COLUMN %s;' % (t, key),
                         'ALTER TABLE %s ADD %s %s;' % (t, key, tt),
                         'UPDATE %s SET %s=%s__tmp;' % (t, key, key),
                         'ALTER TABLE %s DROP COLUMN %s__tmp;' % (t, key)]
            else:
                query = None

            if query:
                logfile.write('timestamp: %s\n'
                               % datetime.datetime.today().isoformat())
                for sub_query in query:
                    logfile.write(sub_query + '\n')
                    if not fake_migrate:
                        self._db._adapter.execute(sub_query)
                        if self._db._adapter.commit_on_alter_table():
                            self._db.commit()
                            logfile.write('success!\n')
                    else:
                        logfile.write('faked!\n')
                if key in sql_fields:
                    sql_fields_old[key] = sql_fields[key]
                else:
                    del sql_fields_old[key]
        tfile = open(self._dbt, 'w')
        portalocker.lock(tfile, portalocker.LOCK_EX)
        cPickle.dump(sql_fields_old, tfile)
        portalocker.unlock(tfile)
        tfile.close()

    def _drop(self, mode = ''):
        return self._db._adapter.DROP(self, mode)

    def drop(self, mode = ''):
        if self._dbt:
            logfile = open(self._loggername, 'a')
        queries = self._db._adapter.DROP(self, mode)
        for query in queries:
            if self._dbt:
                logfile.write(query + '\n')
            self._db._adapter.execute(query)
        self._db.commit()
        del self._db[self._tablename]
        del self._db.tables[self._db.tables.index(self._tablename)]
        self._db._update_referenced_by(self._tablename)
        if self._dbt:
            os.unlink(self._dbt)
            logfile.write('success!\n')

    def _insert(self, **fields):
        new_fields = []
        for fieldname in fields:
            if not fieldname in self.fields:
                raise SyntaxError, 'Field %s does not belong to the table' % fieldname
        for field in self:
            if field.name in fields:
                new_fields.append((field,fields[field.name]))
            elif field.default:
                new_fields.append((field,field.default))
            elif field.compute:
                new_fields.append((field,field.compute(Row(fields))))
            elif field.required:
                raise SyntaxError,'Table: missing required field: %s'%field
        return self._db._adapter.INSERT(self,new_fields)


    def insert(self, **fields):
        query = self._insert(**fields)
        try:
            self._db._adapter.execute(query)
        except Exception, e:
            if isinstance(e,self._db._adapter.integrity_error_class()):
                return None
            raise e
        if hasattr(self,'_primarykey'):
            return dict( [ (k,fields[k]) for k in self._primarykey ])
        id = self._db._adapter.lastrowid(self._tablename)
        if not isinstance(id,int):
            return id
        rid = Reference(id)
        (rid._table, rid._record) = (self, None)
        return rid


    def import_from_csv_file(
        self,
        csvfile,
        id_map=None,
        null='<NULL>',
        unique='uuid',
        *args, **kwargs
        ):
        """
        import records from csv file. Column headers must have same names as
        table fields. field 'id' is ignored. If column names read 'table.file'
        the 'table.' prefix is ignored.
        'unique' argument is a field which must be unique
        (typically a uuid field)
        """

        delimiter = kwargs.get('delimiter', ',')
        quotechar = kwargs.get('quotechar', '"')
        quoting = kwargs.get('quoting', csv.QUOTE_MINIMAL)

        reader = csv.reader(csvfile, delimiter=delimiter, quotechar=quotechar, quoting=quoting)
        colnames = None
        if isinstance(id_map, dict):
            if not self._tablename in id_map:
                id_map[self._tablename] = {}
            id_map_self = id_map[self._tablename]

        def fix(field, value, id_map):
            if value == null:
                value = None
            elif id_map and field.type[:10] == 'reference ':
                try:
                    value = id_map[field.type[9:].strip()][value]
                except KeyError:
                    pass
            return (field.name, value)

        for line in reader:
            if not line:
                break
            if not colnames:
                colnames = [x[x.find('.') + 1:] for x in line]
                c = [i for i in xrange(len(line)) if colnames[i] != 'id']
                cid = [i for i in xrange(len(line)) if colnames[i] == 'id']
                if cid:
                    cid = cid[0]
            else:
                items = [fix(self[colnames[i]], line[i], id_map) for i in c]
                if not unique or unique not in colnames:
                    new_id = self.insert(**dict(items))
                else:
                    # Validation. Check for duplicate of 'unique' &,
                    # if present, update instead of insert.
                    for i in c:
                        if colnames[i] == unique:
                            _unique = line[i]
                    query = self._db[self][unique]==_unique
                    if self._db(query).count():
                        self._db(query).update(**dict(items))
                        new_id = self._db(query).select()[0].id
                    else:
                        new_id = self.insert(**dict(items))
                if id_map and cid != []:
                    id_map_self[line[cid]] = new_id

    def on(self, query):
        return Expression(self._db,self._db._adapter.ON,self,query)

    def _truncate(self, mode = None):
        return self._db._adapter.TRUNCATE(self, mode)

    def truncate(self, mode = None):
        if self._dbt:
            logfile = open(self._loggername, 'a')
        queries = self._db_adapter.TRUNCATE(self, mode)
        for query in queries:
            if self._dbt:
                logfile.write(query + '\n')
            self._db._adapter.execute(query)
        self._db.commit()
        if self._dbt:
            logfile.write('success!\n')


class Expression(object):

    def __init__(
        self,
        db,
        op,
        first=None,
        second=None,
        type=None,
        ):

        self._db = db
        self._op = op
        self._first = first
        self._second = second
        if not type and first and hasattr(first,'type'):
            self.type = first.type
        else:
            self.type = type

    def __str__(self):
        return self._db._adapter.expand(self,self.type)

    def __or__(self, other):  # for use in sortby
        return Expression(self._db,self._db._adapter.COMMA,self,other,self.type)

    def __invert__(self):
        return Expression(self._db,self._db._adapter.DESC,self,type=self.type)

    def __add__(self, other):
        return Expression(self._db,self._db._adapter.ADD,self,other,self.type)

    def __sub__(self, other):
        if self.type == 'integer':
            result_type = 'integer'
        elif self.type in ['date','time','datetime','double']:
            result_type = 'double'
        else:
            raise SyntaxError, "subscraction operation not supported for type"
        return Expression(self._db,self._db._adapter.SUB,self,other,
                          result_type)

    def __mul__(self, other):
        return Expression(self._db,self._db._adapter.MUL,self,other,self.type)

    def __div__(self, other):
        return Expression(self._db,self._db._adapter.DIV,self,other,self.type)

    def __eq__(self, value):
        return Query(self._db, self._db._adapter.EQ, self, value)

    def __ne__(self, value):
        return Query(self._db, self._db._adapter.NE, self, value)

    def __lt__(self, value):
        return Query(self._db, self._db._adapter.LT, self, value)

    def __le__(self, value):
        return Query(self._db, self._db._adapter.LE, self, value)

    def __gt__(self, value):
        return Query(self._db, self._db._adapter.GT, self, value)

    def __ge__(self, value):
        return Query(self._db, self._db._adapter.GE, self, value)

    def like(self, value):
        return Query(self._db, self._db._adapter.LIKE, self, value)

    def belongs(self, value):
        return Query(self._db, self._db._adapter.BELONGS, self, value)

    # for use in both Query and sortby


class SQLCustomType:
    """
    allows defining of custom SQL types

    Example::

        decimal = SQLCustomType(
            type ='double',
            native ='integer',
            encoder =(lambda x: int(float(x) * 100)),
            decoder = (lambda x: Decimal("0.00") + Decimal(str(float(x)/100)) )
            )

        db.define_table(
            'example',
            Field('value', type=decimal)
            )

    :param type: the web2py type (default = 'string')
    :param native: the backend type
    :param encoder: how to encode the value to store it in the backend
    :param decoder: how to decode the value retrieved from the backend
    :param validator: what validators to use ( default = None, will use the
        default validator for type)
    """

    def __init__(
        self,
        type='string',
        native=None,
        encoder=None,
        decoder=None,
        validator=None,
        _class=None,
        ):

        self.type = type
        self.native = native
        self.encoder = encoder or (lambda x: x)
        self.decoder = decoder or (lambda x: x)
        self.validator = validator
        self._class = _class or type

    def __getslice__(self, a=0, b=100):
        return None

    def __getitem__(self, i):
        return None

    def __str__(self):
        return self._class


class Field(Expression):

    """
    an instance of this class represents a database field

    example::

        a = Field(name, 'string', length=32, default=None, required=False,
            requires=IS_NOT_EMPTY(), ondelete='CASCADE',
            notnull=False, unique=False,
            uploadfield=True, widget=None, label=None, comment=None,
            uploadfield=True, # True means store on disk,
                              # 'a_field_name' means store in this field in db
                              # False means file content will be discarded.
            writable=True, readable=True, update=None, authorize=None,
            autodelete=False, represent=None, uploadfolder=None)

    to be used as argument of DAL.define_table

    allowed field types:
    string, boolean, integer, double, text, blob,
    date, time, datetime, upload, password

    strings must have a length or 512 by default.
    fields should have a default or they will be required in SQLFORMs
    the requires argument is used to validate the field input in SQLFORMs

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
        compute=None,
        ):
        self._db=None
        self._op=None
        self._first=None
        self._second=None
        self.name = fieldname = cleanup(fieldname)
        if hasattr(Table,fieldname) or fieldname[0] == '_':
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

    def store(self, file, filename=None, path=None):
        if not filename:
            filename = file.name
        filename = os.path.basename(filename.replace('/', os.sep)\
                                        .replace('\\', os.sep))
        m = re.compile('\.(?P<e>\w{1,5})$').search(filename)
        extension = m and m.group('e') or 'txt'
        uuid_key = web2py_uuid().replace('-', '')[-16:]
        encoded_filename = base64.b16encode(filename).lower()
        newfilename = '%s.%s.%s.%s' % \
            (self._tablename, self.name, uuid_key, encoded_filename)
        newfilename = newfilename[:500] + '.' + extension
        if self.uploadfield == True:
            if path:
                pass
            elif self.uploadfolder:
                path = self.uploadfolder
            else:
                path = os.path.join(self._db._adapter.folder, '..', 'uploads')
            pathfilename = os.path.join(path, newfilename)
            dest_file = open(pathfilename, 'wb')
            shutil.copyfileobj(file, dest_file)
            dest_file.close()
        return newfilename

    def retrieve(self, name, path=None):
        import http
        if self.authorize or isinstance(self.uploadfield, str):
            row = self._db(self == name).select()._first()
            if not row:
                raise http.HTTP(404)
        if self.authorize and not self.authorize(row):
            raise http.HTTP(403)
        try:
            m = regex_content.match(name)
            if not m or not self.isattachment:
                raise TypeError, 'Can\'t retrieve %s' % name
            filename = base64.b16decode(m.group('name'), True)
            filename = regex_cleanup_fn.sub('_', filename)
        except (TypeError, AttributeError):
            filename = name
        if isinstance(self.uploadfield, str):  # ## if file is in DB
            return (filename, cStringIO.StringIO(row[self.uploadfield]))
        else:
            # ## if file is on filesystem
            if path:
                pass
            elif self.uploadfolder:
                path = self.uploadfolder
            else:
                path = os.path.join(self._db._adapter.folder, '..', 'uploads')
            return (filename, open(os.path.join(path, name), 'rb'))

    def formatter(self, value):
        if value is None or not self.requires:
            return value
        if not isinstance(self.requires, (list, tuple)):
            requires = [self.requires]
        elif isinstance(self.requires, tuple):
            requires = list(self.requires)
        else:
            requires = copy.copy(self.requires)
        requires.reverse()
        for item in requires:
            if hasattr(item, 'formatter'):
                value = item.formatter(value)
        return value

    def validate(self, value):
        if not self.requires:
            return (value, None)
        requires = self.requires
        if not isinstance(requires, (list, tuple)):
            requires = [requires]
        for validator in requires:
            (value, error) = validator(value)
            if error:
                return (value, error)
        return (value, None)

    def lower(self):
        return Expression(self._db, self._db._adapter.LOWER, self, None, self.type)

    def upper(self):
        return Expression(self._db, self._db._adapter.UPPER, self, None, self.type)

    def year(self):
        return Expression(self._db, self._db._adapter.EXTRACT, self, 'year', 'integer')

    def month(self):
        return Expression(self._db, self._db._adapter.EXTRACT, self, 'month', 'integer')

    def day(self):
        return Expression(self._db, self._db._adapter.EXTRACT, self, 'day', 'integer')

    def hour(self):
        return Expression(self._db, self._db._adapter.EXTRACT, self, 'hour', 'integer')

    def minutes(self):
        return Expression(self._db, self._db._adapter.EXTRACT, self, 'minute', 'integer')

    def seconds(self):
        return Expression(self._db, self._db._adapter.EXTRACT, self, 'second', 'integer')

    def count(self):
        return Expression(self._db, self._db._adapter.AGGREGATE, self, 'count', 'integer')

    def sum(self):
        return Expression(self._db, self._db._adapter.AGGREGATE, self, 'sum', self.type)

    def max(self):
        return Expression(self._db, self._db._adapter.AGGREGATE, self, 'max', self.type)

    def min(self):
        return Expression(self._db, self._db._adapter.AGGREGATE, self, 'min', self.type)

    def len(self):
        return Expression(self._db, self._db._adapter.AGGREGATE, self, 'length', 'integer')

    def __nonzero__(self):
        return True

    def __getslice__(self, start, stop):
        """
        <<<< THIS IS BROKEN FOR start<0 or stop<0
        """
        if start < 0 or stop < start:
            raise SyntaxError, 'not supported: %s - %s' % (start, stop)
        pos=start + 1
        length=stop - start

        if start < 0:
            pos0 = '(%s - %d)' % (self.len(), -start)
        else:
            pos0 = start + 1

        if stop < 0:
            length = '(%s - %d - %s)' % (self.len(), -stop, str(pos0))
        else:
            length = '(%s - %s)' % (str(stop), str(pos0))

        return self._db._adapter.Expression(self._db,seld._db._adapter.SUBSTRING,
                                           self, (pos, length), self.type)

    def __getitem__(self, i):
        return self[i:i + 1]

    def __str__(self):
        try:
            return '%s.%s' % (self._tablename, self.name)
        except:
            return '<no table>.%s' % self.name


class Query(object):

    """
    a query object necessary to define a set.
    t can be stored or can be passed to DAL.__call__() to obtain a Set

    Example::

        query = db.users.name=='Max'
        set = db(query)
        records = set.select()

    :raises SyntaxError: when the query cannot be recognized
    """

    def __init__(
        self,
        db,
        op,
        first=None,
        second=None,
        ):
        self._db = db
        self._op = op
        self._first = first
        self._second = second

    def __str__(self):
        return self._db._adapter.expand(self)

    def __and__(self, other):
        return Query(self._db,self._db._adapter.AND,self,other)

    def __or__(self, other):
        return Query(self._db,self._db._adapter.OR,self,other)

    def __invert__(self):
        return Query(self._db,self._db._adapter.NOT,self)


regex_quotes = re.compile("'[^']*'")


def xorify(orderby):
    if not orderby:
        return None
    orderby2 = orderby[0]
    for item in orderby[1:]:
        orderby2 = orderby2 | item
    return orderby2


class Set(object):

    """
    a Set represents a set of records in the database,
    the records are identified by the where=Query(...) object.
    normally the Set is generated by DAL.__call__(Query(...))

    given a set, for example
       set = db(db.users.name=='Max')
    you can:
       set.update(db.users.name='Massimo')
       set.delete() # all elements in the set
       set.select(orderby=db.users.id, groupby=db.users.name, limitby=(0,10))
    and take subsets:
       subset = set(db.users.id<5)
    """

    def __init__(self, db, query):
        self._db = db
        self._query = query

    def __call__(self, query):
        if self._query:
            return Set(self._db, self._query & query)
        else:
            return Set(self._db, query)

    def _select(self, *fields, **attributes):
        return self._db._adapter.SELECT(self._query,*fields,**attributes)

    def select(self, *fields, **attributes):
        return self._db._adapter.select(self._query,*fields,**attributes)

    def _count(self):
        tablenames = self._db._adapter.tables(self._query)
        return self.COUNT(self._query,tablenames)

    def count(self):
        tablenames = self._db._adapter.tables(self._query)
        return self._db._adapter.count(self._query,tablenames)

    def _delete(self):
        self._tables = tablenames = self._db._adapter.tables(self._query)
        if len(tablenames) != 1:
            raise SyntaxError, \
                'Set: unable to determine what to delete'
        return self._db._adapter.DELETE(self._query,tablenames[0])

    def delete(self):
        query = self._delete()
        self.delete_uploaded_files()
        ### special code to handle CASCADE in SQLite
        db=self._db
        t = self._tables[0]
        if db._dbname=='sqlite' and db[t]._referenced_by:
            deleted = [x.id for x in self.select(db[t].id)]
        ### end special code to handle CASCADE in SQLite
        self._db._adapter.execute(query)
        try:
            counter = self._db._adapter.cursor.rowcount
        except:
            counter =  None
        ### special code to handle CASCADE in SQLite
        if db._dbname=='sqlite' and counter:
            for tablename,fieldname in db[t]._referenced_by:
                f = db[tablename][fieldname]
                if f.type=='reference '+t and f.ondelete=='CASCADE':
                    db(db[tablename][fieldname].belongs(deleted)).delete()
        ### end special code to handle CASCADE in SQLite
        return counter

    def _update(self, **update_fields):
        tablenames = self._db._adapter.tables(self._query)
        if len(tablenames) != 1:
            raise SyntaxError, 'Query involves multiple tables, do not know which to update'
        table = self._db[tablenames[0]]
        fields = [(table[fieldname],value) for (fieldname,value) in update_fields.items()]
        for field in table:
            if not field.name in update_fields:
                if field.update:
                    fields.append((field, field.update))
                elif field.compute:
                    fields.append((field, field.compute(Row(update_fields))))
        return self._db._adapter.UPDATE(self._query,tablenames[0],fields)

    def update(self, **update_fields):
        query = self._update(**update_fields)
        self.delete_uploaded_files(update_fields)
        self._db._adapter.execute(query)
        try:
            return self._db._adapter.cursor.rowcount
        except:
            return None

    def delete_uploaded_files(self, upload_fields=None):
        table = self._db[self._db._adapter.tables(self._query)[0]]

        # ## mind uploadfield==True means file is not in DB

        if upload_fields:
            fields = upload_fields.keys()
        else:
            fields = table.fields
        fields = [f for f in fields if table[f].type == 'upload'
                   and table[f].uploadfield == True
                   and table[f].autodelete]
        if not fields:
            return
        for record in self.select(*[table[f] for f in fields]):
            for fieldname in fields:
                oldname = record.get(fieldname, None)
                if not oldname:
                    continue
                if upload_fields and oldname == upload_fields[fieldname]:
                    continue
                uploadfolder = table[fieldname].uploadfolder
                if not uploadfolder:
                    uploadfolder = os.path.join(self._db._adapter.folder, '..', 'uploads')
                oldpath = os.path.join(uploadfolder, oldname)
                if os.path.exists(oldpath):
                    os.unlink(oldpath)

def update_record(colset, table, id, a={}):
    b = a or dict(colset)
    c = dict([(k,v) for (k,v) in b.items() \
                  if k in table.fields and not k=='id'])
    table._db(table.id==id).update(**c)
    for (k, v) in c.items():
        colset[k] = v


class Rows(object):

    """
    A wrapper for the return value of a select. It basically represents a table.
    It has an iterator and each row is represented as a dictionary.
    """

    # ## TODO: this class still needs some work to care for ID/OID

    def __init__(
        self,
        db=None,
        records=[],
        colnames=[],
        compact=True
        ):
        self.db = db
        self.records = records
        self.colnames = colnames
        self.compact = compact

    def setvirtualfields(self,**keyed_virtualfields):
        if not keyed_virtualfields:
            return self
        for row in self.records:
            for (tablename,virtualfields) in keyed_virtualfields.items():
                attributes = dir(virtualfields)
                virtualfields.__dict__.update(row)
                if not tablename in row:
                    box = row[tablename] = Row()
                else:
                    box = row[tablename]
                for attribute in attributes:
                    if attribute[0] != '_':
                        method = getattr(virtualfields,attribute)
                        if callable(method) and len(method.im_func.func_code.co_varnames)==1:
                            box[attribute]=method()
        return self

    def __and__(self,other):
        if self.colnames!=other.colnames: raise Exception, 'Rows: different colnames'
        records = self.records+other.records
        return Rows(self.db,records,self.colnames)

    def __or__(self,other):
        if self.colnames!=other.colnames: raise Exception, 'Rows: different colnames'
        records = self.records
        records += [record for record in other.records \
                        if not record in records]
        return Rows(self.db,records,self.colnames)

    def first(self):
        if not self.records:
            return None
        return self[0]

    def last(self):
        if not self.records:
            return None
        return self[-1]

    def __nonzero__(self):
        if len(self.records):
            return 1
        return 0

    def __len__(self):
        return len(self.records)

    def __getslice__(self, a, b):
        return Rows(self.db,self.records[a:b],self.colnames)

    def find(self,f):
        """
        returns a set of rows of sorted elements (not filtered in place)
        """
        if not self.records:
            return []
        records = []
        for i in range(0,len(self)):
            row = self[i]
            if f(row):
                records.append(self.records[i])
        return Rows(self.db,records,self.colnames)

    def exclude(self,f):
        """
        returns a set of rows of sorted elements (not filtered in place)
        """
        if not self.records:
            return []
        removed = []
        i=0
        while i<len(self):
            row = self[i]
            if f(row):
                removed.append(self.records[i])
                del self.records[i]
            else:
                i += 1
        return Rows(self.db,removed,self.colnames)

    def sort(self,f,reverse=False):
        """
        returns a list of sorted elements (not sorted in place)
        """
        return Rows(self.db,sorted(self,key=f,reverse=reverse),self.colnames)

    def __getitem__(self, i):
        row = self.records[i]
        keys = row.keys()
        if self.compact and len(keys) == 1 and keys[0] != '_extra':
            return row[row.keys()[0]]
        return row

    def as_list(self,
                compact=True,
                storage_to_dict=True,
                datetime_to_str=True):
        """
        returns the data as a list or dictionary.
        :param storage_to_dict: when True returns a dict, otherwise a list(default True)
        :param datetime_to_str: convert datetime fields as strings (default True)
        """
        (oc, self.compact) = (self.compact, compact)
        if storage_to_dict:
            items = [item.as_dict(datetime_to_str) for item in self]
        else:
            items = [item for item in self]
        self.compact = compact
        return items


    def as_dict(self,
                key='id',
                compact=True,
                storage_to_dict=True,
                datetime_to_str=True):
        """
        returns the data as a dictionary of dictionaries (storage_to_dict=True) or records (False)

        :param key: the name of the field to be used as dict key, normally the id
        :param compact: ? (default True)
        :param storage_to_dict: when True returns a dict, otherwise a list(default True)
        :param datetime_to_str: convert datetime fields as strings (default True)
        """
        rows = self.as_list(compact, storage_to_dict, datetime_to_str)
        if isinstance(key,str) and key.count('.')==1:
            (table, field) = key.split('.')
            return dict([(r[table][field],r) for r in rows])
        elif isinstance(key,str):
            return dict([(r[key],r) for r in rows])
        else:
            return dict([(key(r),r) for r in rows])

    def __iter__(self):
        """
        iterator over records
        """

        for i in xrange(len(self)):
            yield self[i]

    def export_to_csv_file(self, ofile, null='<NULL>', *args, **kwargs):
        """
        export data to csv, the first line contains the column names

        :param ofile: where the csv must be exported to
        :param null: how null values must be represented (default '<NULL>')
        :param delimiter: delimiter to separate values (default ',')
        :param quotechar: character to use to quote string values (default '"')
        :param quoting: quote system, use csv.QUOTE_*** (default csv.QUOTE_MINIMAL)
        :param represent: use the fields .represent value (default False)
        :param colnames: list of column names to use (default self.colnames)
                         This will only work when exporting rows objects!!!!
                         DO NOT use this with db.export_to_csv()
        """
        delimiter = kwargs.get('delimiter', ',')
        quotechar = kwargs.get('quotechar', '"')
        quoting = kwargs.get('quoting', csv.QUOTE_MINIMAL)
        represent = kwargs.get('represent', False)
        writer = csv.writer(ofile, delimiter=delimiter,
                            quotechar=quotechar, quoting=quoting)
        colnames = kwargs.get('colnames', self.colnames)
        # a proper csv starting with the column names
        writer.writerow(colnames)

        def none_exception(value):
            """
            returns a cleaned up value that can be used for csv export:
            - unicode text is encoded as such
            - None values are replaced with the given representation (default <NULL>)
            """
            if value == None:
                return null
            elif isinstance(value, unicode):
                return value.encode('utf8')
            elif isinstance(value,Reference):
                return int(value)
            elif hasattr(value, 'isoformat'):
                return value.isoformat()[:19].replace('T', ' ')
            return value

        for record in self:
            row = []
            for col in self.colnames:
                if not table_field.match(col):
                    row.append(record._extra[col])
                else:
                    (t, f) = col.split('.')
                    if isinstance(record.get(t, None), (Row,dict)):
                        row.append(none_exception(record[t][f]))
                    else:
                        if represent:
                            if self.db[t][f].represent:
                                row.append(none_exception(self.db[t][f].represent(record[f])))
                            else:
                                row.append(none_exception(record[f]))
                        else:
                            row.append(none_exception(record[f]))
            writer.writerow(row)

    def __str__(self):
        """
        serializes the table into a csv file
        """

        s = cStringIO.StringIO()
        self.export_to_csv_file(s)
        return s.getvalue()

    def xml(self):
        """
        serializes the table using sqlhtml.SQLTABLE (if present)
        """

        import sqlhtml
        return sqlhtml.SQLTABLE(self).xml()

    def json(self, mode='object'):
        """
        serializes the table to a JSON list of objects
        """

        mode = mode.lower()
        if not mode in ['object', 'array']:
            raise SyntaxError, 'Invalid JSON serialization mode: %s' % mode

        def inner_loop(record, col):
            (t, f) = col.split('.')
            res = None
            if not table_field.match(col):
                res = record._extra[col]
            else:
                if isinstance(record.get(t, None), Row):
                    res = record[t][f]
                else:
                    res = record[f]
            if mode == 'object':
                return (f, res)
            else:
                return res

        if mode == 'object':
            items = [dict([inner_loop(record, col) for col in
                     self.colnames]) for record in self]
        else:
            items = [[inner_loop(record, col) for col in self.colnames]
                     for record in self]
        return json(items)


def Rows_unpickler(data):
    return marshal.loads(data)

def Rows_pickler(data):
    return Rows_unpickler, (marshal.dumps(data.as_list(storage_to_dict=True)),)
copy_reg.pickle(Rows, Rows_pickler, Rows_unpickler)


def test_all():
    """

    Create a table with all possible field types
    'sqlite://test.db'
    'mysql://root:none@localhost/test'
    'postgres://mdipierro:none@localhost/test'
    'mssql://web2py:none@A64X2/web2py_test'
    'oracle://username:password@database'
    'firebird://user:password@server:3050/database'
    'db2://DSN=dsn;UID=user;PWD=pass'
    'firebird_embedded://username:password@c://path')
    'informix://user:password@server:3050/database'
    'gae' # for google app engine

    >>> if len(sys.argv)<2: db = DAL(\"sqlite://test.db\")
    >>> if len(sys.argv)>1: db = DAL(sys.argv[1])
    >>> tmp = db.define_table('users',\
              Field('stringf', 'string', length=32, required=True),\
              Field('booleanf', 'boolean', default=False),\
              Field('passwordf', 'password', notnull=True),\
              Field('blobf', 'blob'),\
              Field('uploadf', 'upload'),\
              Field('integerf', 'integer', unique=True),\
              Field('doublef', 'double', unique=True,notnull=True),\
              Field('datef', 'date', default=datetime.date.today()),\
              Field('timef', 'time'),\
              Field('datetimef', 'datetime'),\
              migrate='test_user.table')

   Insert a field

    >>> db.users.insert(stringf='a', booleanf=True, passwordf='p', blobf='0A',\
                       uploadf=None, integerf=5, doublef=3.14,\
                       datef=datetime.date(2001, 1, 1),\
                       timef=datetime.time(12, 30, 15),\
                       datetimef=datetime.datetime(2002, 2, 2, 12, 30, 15))
    1

    Drop the table

    >>> db.users.drop()

    Examples of insert, select, update, delete

    >>> tmp = db.define_table('person',\
              Field('name'),\
              Field('birth','date'),\
              migrate='test_person.table')
    >>> person_id = db.person.insert(name=\"Marco\",birth='2005-06-22')
    >>> person_id = db.person.insert(name=\"Massimo\",birth='1971-12-21')

    commented len(db().select(db.person.ALL))
    commented 2

    >>> me = db(db.person.id==person_id).select()[0] # test select
    >>> me.name
    'Massimo'
    >>> db(db.person.name=='Massimo').update(name='massimo') # test update
    1
    >>> db(db.person.name=='Marco').delete() # test delete
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
    >>> len(db((db.person.name=='Max')|(db.person.birth<'2003-01-01')).select())
    1
    >>> me = db(db.person.id==person_id).select(db.person.name)[0]
    >>> me.name
    'Max'

    Examples of search conditions using extract from date/datetime/time

    >>> len(db(db.person.birth.month()==12).select())
    1
    >>> len(db(db.person.birth.year()>1900).select())
    1

    Example of usage of NULL

    >>> len(db(db.person.birth==None).select()) ### test NULL
    0
    >>> len(db(db.person.birth!=None).select()) ### test NULL
    1

    Examples of search consitions using lower, upper, and like

    >>> len(db(db.person.name.upper()=='MAX').select())
    1
    >>> len(db(db.person.name.like('%ax')).select())
    1
    >>> len(db(db.person.name.upper().like('%AX')).select())
    1
    >>> len(db(~db.person.name.upper().like('%AX')).select())
    0

    orderby, groupby and limitby

    >>> people = db().select(db.person.name, orderby=db.person.name)
    >>> order = db.person.name|~db.person.birth
    >>> people = db().select(db.person.name, orderby=order)

    >>> people = db().select(db.person.name, orderby=db.person.name, groupby=db.person.name)

    >>> people = db().select(db.person.name, orderby=order, limitby=(0,100))

    Example of one 2 many relation

    >>> tmp = db.define_table('dog',\
               Field('name'),\
               Field('birth','date'),\
               Field('owner',db.person),\
               migrate='test_dog.table')
    >>> db.dog.insert(name='Snoopy', birth=None, owner=person_id)
    1

    A simple JOIN

    >>> len(db(db.dog.owner==db.person.id).select())
    1

    >>> len(db().select(db.person.ALL, db.dog.name,left=db.dog.on(db.dog.owner==db.person.id)))
    1

    Drop tables

    >>> db.dog.drop()
    >>> db.person.drop()

    Example of many 2 many relation and Set

    >>> tmp = db.define_table('author', Field('name'),\
                            migrate='test_author.table')
    >>> tmp = db.define_table('paper', Field('title'),\
                            migrate='test_paper.table')
    >>> tmp = db.define_table('authorship',\
            Field('author_id', db.author),\
            Field('paper_id', db.paper),\
            migrate='test_authorship.table')
    >>> aid = db.author.insert(name='Massimo')
    >>> pid = db.paper.insert(title='QCD')
    >>> tmp = db.authorship.insert(author_id=aid, paper_id=pid)

    Define a Set

    >>> authored_papers = db((db.author.id==db.authorship.author_id)&(db.paper.id==db.authorship.paper_id))
    >>> rows = authored_papers.select(db.author.name, db.paper.title)
    >>> for row in rows: print row.author.name, row.paper.title
    Massimo QCD

    Example of search condition using  belongs

    >>> set = (1, 2, 3)
    >>> rows = db(db.paper.id.belongs(set)).select(db.paper.ALL)
    >>> print rows[0].title
    QCD

    Example of search condition using nested select

    >>> nested_select = db()._select(db.authorship.paper_id)
    >>> rows = db(db.paper.id.belongs(nested_select)).select(db.paper.ALL)
    >>> print rows[0].title
    QCD

    Example of expressions

    >>> mynumber = db.define_table('mynumber', Field('x', 'integer'))
    >>> db(mynumber.id>0).delete()
    0
    >>> for i in range(10): tmp = mynumber.insert(x=i)
    >>> db(mynumber.id>0).select(mynumber.x.sum())[0](mynumber.x.sum())
    45

    >>> db(mynumber.x+2==5).select(mynumber.x + 2)[0](mynumber.x + 2)
    5

    Output in csv

    >>> print str(authored_papers.select(db.author.name, db.paper.title)).strip()
    author.name,paper.title\r
    Massimo,QCD

    Delete all leftover tables

    >>> DAL.distributed_transaction_commit(db)

    >>> db.mynumber.drop()
    >>> db.authorship.drop()
    >>> db.author.drop()
    >>> db.paper.drop()
    """

# deprecated since the new DAL
SQLField = Field
SQLTable = Table
SQLXorable = Expression
SQLQuery = Query
SQLSet = Set
SQLRows = Rows
SQLStorage = Row
SQLDB = DAL
GQLDB = DAL
DAL.Field = Field  # necessary in gluon/globals.py session.connect
DAL.Table = Table  # necessary in gluon/globals.py session.connect



if __name__ == '__main__':
    import doctest
    doctest.testmod()
    print 'done!'
    """
    os.system('rm *.table *.db *.sqlite *.log')
    db=DAL('sqlite://test.db')
    db.define_table('person',Field('name'),Field('birth','datetime'))
    print db(db.person.birth.month()==12)._select()

    me = db.person.insert(name='Max')
    db.person.insert(name='Max1')
    db.person.insert(name='Max2')
    print db().select(db.person.ALL)
    db(db.person.id==1).update(name='Massimo')
    db(db.person.id>10).delete()
    print db(db.person.id>0).count()
    print db((db.person.name + 10< 100) | (db.person.name == (db.person.name+'')-db.person.id))._select()
    print db()._select(db.person.name,orderby=db.person.name|~db.person.id)
    print db().select(db.person.name,orderby=db.person.name|~db.person.id)
    print db(db.person.id.belongs(db(db.person.id>0)._select(db.person.id)))._select(db.person.ALL)
    print db(db.person.id>0)._select(db.person.name.count(),groupby=db.person.name)
    import time
    t = time.time()
    for i in range(1):
        db((db.person.id>0)&((db.person.id==1)|(db.person.name.like('%Max%')))).select()
    print time.time()-t
    db.define_table('dog',Field('name'),Field('owner',db.person))
    db.dog.insert(name='Skipper',owner=me)
    print db(db.dog.id>0).select()
    print db(db.dog.owner==db.person.id).select()
    """

