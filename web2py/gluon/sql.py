#!/bin/env python
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

This file contains the DAL support for many relational databases,
including SQLite, MySQL, Postgres, Oracle, MS SQL, DB2, Interbase.
Adding Ingres - clach04
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
import copy_reg
import base64
import shutil
import marshal
import decimal
import struct

from utils import md5_hash, web2py_uuid
from serializers import json
from http import HTTP

# internal representation of tables with field
#  <table>.<field>, tables and fields may only be [a-zA-Z0-0_]

table_field = re.compile('[\w_]+\.[\w_]+')
oracle_fix = re.compile("[^']*('[^']*'[^']*)*\:(?P<clob>CLOB\('([^']+|'')*'\))")
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


import portalocker
import validators

sql_locker = thread.allocate_lock()

INGRES_SEQNAME='ii***lineitemsequence' # NOTE invalid database object name (ANSI-SQL wants this form of name to be a delimited identifier)
def gen_ingres_sequencename(table_name):
    """Generate Ingres specific sequencename, pass in self._tablename
    """
    result='%s_iisq' % (table_name)
    # if result len too long, hash and use hexhash?
    return result

# mapping of the field types and some constructs
# per database
SQL_DIALECTS = {
    'sqlite': {
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

        'lower': 'LOWER(%(field)s)',
        'upper': 'UPPER(%(field)s)',
        'is null': 'IS NULL',
        'is not null': 'IS NOT NULL',
        'extract': "web2py_extract('%(name)s',%(field)s)",
        'left join': 'LEFT JOIN',
        'random': 'Random()',
        'notnull': 'NOT NULL DEFAULT %(default)s',
        'substring': 'SUBSTR(%(field)s,%(pos)s,%(length)s)',
        'primarykey': 'PRIMARY KEY (%s)'
        },
    'mysql': {
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
        'lower': 'LOWER(%(field)s)',
        'upper': 'UPPER(%(field)s)',
        'is null': 'IS NULL',
        'is not null': 'IS NOT NULL',
        'extract': 'EXTRACT(%(name)s FROM %(field)s)',
        'left join': 'LEFT JOIN',
        'random': 'RAND()',
        'notnull': 'NOT NULL DEFAULT %(default)s',
        'substring': 'SUBSTRING(%(field)s,%(pos)s,%(length)s)',
        },
    'postgres': {
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
        'lower': 'LOWER(%(field)s)',
        'upper': 'UPPER(%(field)s)',
        'is null': 'IS NULL',
        'is not null': 'IS NOT NULL',
        'extract': 'EXTRACT(%(name)s FROM %(field)s)',
        'left join': 'LEFT JOIN',
        'random': 'RANDOM()',
        'notnull': 'NOT NULL DEFAULT %(default)s',
        'substring': 'SUBSTR(%(field)s,%(pos)s,%(length)s)',
        },
    'oracle': {
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
        'lower': 'LOWER(%(field)s)',
        'upper': 'UPPER(%(field)s)',
        'is null': 'IS NULL',
        'is not null': 'IS NOT NULL',
        'extract': 'EXTRACT(%(name)s FROM %(field)s)',
        'left join': 'LEFT OUTER JOIN',
        'random': 'dbms_random.value',
        'notnull': 'DEFAULT %(default)s NOT NULL',
        'substring': 'SUBSTR(%(field)s,%(pos)s,%(length)s)',
        },
    'mssql': {
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
        'lower': 'LOWER(%(field)s)',
        'upper': 'UPPER(%(field)s)',
        'is null': 'IS NULL',
        'is not null': 'IS NOT NULL',
        'extract': 'DATEPART(%(name)s,%(field)s)',
        'left join': 'LEFT OUTER JOIN',
        'random': 'NEWID()',
        'notnull': 'NOT NULL DEFAULT %(default)s',
        'substring': 'SUBSTRING(%(field)s,%(pos)s,%(length)s)',
        'primarykey': 'PRIMARY KEY CLUSTERED (%s)'
        #' WITH( STATISTICS_NORECOMPUTE = OFF, IGNORE_DUP_KEY = OFF, ALLOW_ROW_LOCKS = ON, ALLOW_PAGE_LOCKS = ON)'
        },
    'mssql2': { # MS SQL unicode
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
        'lower': 'LOWER(%(field)s)',
        'upper': 'UPPER(%(field)s)',
        'is null': 'IS NULL',
        'is not null': 'IS NOT NULL',
        'extract': 'DATEPART(%(name)s,%(field)s)',
        'left join': 'LEFT OUTER JOIN',
        'random': 'NEWID()',
        'notnull': 'NOT NULL DEFAULT %(default)s',
        'substring': 'SUBSTRING(%(field)s,%(pos)s,%(length)s)',
        },
    'firebird': {
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
        'lower': 'LOWER(%(field)s)',
        'upper': 'UPPER(%(field)s)',
        'is null': 'IS NULL',
        'is not null': 'IS NOT NULL',
        'extract': 'EXTRACT(%(name)s FROM %(field)s)',
        'left join': 'LEFT JOIN',
        'random': 'RAND()',
        'notnull': 'DEFAULT %(default)s NOT NULL',
        'substring': 'SUBSTRING(%(field)s,%(pos)s,%(length)s)',
        },
    'informix': {
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
        'lower': 'LOWER(%(field)s)',
        'upper': 'UPPER(%(field)s)',
        'is null': 'IS NULL',
        'is not null': 'IS NOT NULL',
        'extract': 'EXTRACT(%(field)s(%(name)s)',
        'left join': 'LEFT JOIN',
        'random': 'RANDOM()',
        'notnull': 'DEFAULT %(default)s NOT NULL',
        'substring': 'SUBSTR(%(field)s,%(pos)s,%(length)s)',
        },
    'db2': {
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
        'lower': 'LOWER(%(field)s)',
        'upper': 'UPPER(%(field)s)',
        'is null': 'IS NULL',
        'is not null': 'IS NOT NULL',
        'extract': 'EXTRACT(%(name)s FROM %(field)s)',
        'left join': 'LEFT OUTER JOIN',
        'random': 'RAND()',
        'notnull': 'NOT NULL DEFAULT %(default)s',
        'substring': 'SUBSTR(%(field)s,%(pos)s,%(length)s)',
        'primarykey': 'PRIMARY KEY(%s)',
        },
    'ingres': {
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
        'id': 'integer4 not null unique with default next value for %s'%INGRES_SEQNAME,
        'reference': 'integer4, FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        'reference FK': ', CONSTRAINT FK_%(constraint_name)s FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_key)s ON DELETE %(on_delete_action)s',
        'reference TFK': ' CONSTRAINT FK_%(foreign_table)s_PK FOREIGN KEY (%(field_name)s) REFERENCES %(foreign_table)s (%(foreign_key)s) ON DELETE %(on_delete_action)s', ## FIXME TODO
        'lower': 'LOWER(%(field)s)',
        'upper': 'UPPER(%(field)s)',
        'is null': 'IS NULL',
        'is not null': 'IS NOT NULL',
        'extract': 'EXTRACT(%(name)s FROM %(field)s)', # Date/time/timestamp related. Use DatePart for older Ingres releases
        'left join': 'LEFT OUTER JOIN',
        'random': 'RANDOM()',
        'notnull': 'NOT NULL DEFAULT %(default)s',
        'substring': 'SUBSTR(%(field)s,%(pos)s,%(length)s)',
        'primarykey': 'PRIMARY KEY(%s)',
        },
    }

INGRES_USE_UNICODE_STRING_TYPES=True
if INGRES_USE_UNICODE_STRING_TYPES:
    """convert type VARCHAR -> NVARCHAR, i.e. use UCS2/UTF16 support/storage
    leaving as VARCHAR means need to use UTF8 encoding.
    Some people are very passionate about which encoding
    to use for storage, this gives the option.
    """
    for x in ['string', 'password', 'text']:
        SQL_DIALECTS['ingres'][x] = 'N' + SQL_DIALECTS['ingres'][x]

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
    elif not isinstance(field_type,str):
        return []
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
    elif not field.notnull and field_type[:2] in sff and requires:
        requires[-1]=validators.IS_EMPTY_OR(requires[-1])
    return requires

def sql_represent(obj, fieldtype, dbname, db_codec='UTF-8'):
    if type(obj) in (types.LambdaType, types.FunctionType):
        obj = obj()
    if isinstance(obj, (Expression, Field)):
        return obj
    if isinstance(fieldtype, SQLCustomType):
        return fieldtype.encoder(obj)
    if obj is None:
        return 'NULL'
    if obj == '' and not fieldtype[:2] in ['st','te','pa','up']:
        return 'NULL'
    if fieldtype == 'boolean':
        if dbname == 'mssql':
            if obj and not str(obj)[0].upper() == 'F':
                return '1'
            else:
                return '0'
        else:
            if obj and not str(obj)[0].upper() == 'F':
                return "'T'"
            else:
                return "'F'"
    if fieldtype[0] == 'i':
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
        obj = obj.encode(db_codec)
    if fieldtype == 'blob':
        obj = base64.b64encode(str(obj))
        if dbname == 'db2':
            return "BLOB('%s')" % obj
        if dbname == 'oracle':
            return ":CLOB('%s')" % obj
    # FIXME: remove comment lines?
    #elif fieldtype == 'text':
    #    if dbname == 'oracle':
    #        return ":CLOB('%s')" % obj.replace("'","?") ### FIX THIS
    elif fieldtype == 'date':
        # FIXME: remove comment lines?
        # if dbname=='postgres': return "'%s'::bytea" % obj.replace("'","''")

        if isinstance(obj, (datetime.date, datetime.datetime)):
            obj = obj.isoformat()[:10]
        else:
            obj = str(obj)
        if dbname in ['oracle', 'informix']:
            return "to_date('%s','yyyy-mm-dd')" % obj
    elif fieldtype == 'datetime':
        if isinstance(obj, datetime.datetime):
            if dbname == 'db2':
                return "'%s'" % obj.isoformat()[:19].replace('T','-').replace(':','.')
            else:
                obj = obj.isoformat()[:19].replace('T',' ')
        elif isinstance(obj, datetime.date):
            if dbname == 'db2':
                return "'%s'" % obj.isoformat()[:10]+'-00.00.00'
            else:
                obj = obj.isoformat()[:10]+' 00:00:00'
        else:
            obj = str(obj)
        if dbname in ['oracle', 'informix']:
            return "to_date('%s','yyyy-mm-dd hh24:mi:ss')" % obj
    elif fieldtype == 'time':
        if isinstance(obj, datetime.time):
            obj = obj.isoformat()[:10]
        else:
            obj = str(obj)
    if not isinstance(obj,str):
        obj = str(obj)
    try:
        obj.decode(db_codec)
    except:
        obj = obj.decode('latin1').encode(db_codec)
    if dbname == 'mssql2' and (fieldtype == 'string' or fieldtype == 'text'):
        return "N'%s'" % obj.replace("'", "''")
    return "'%s'" % obj.replace("'", "''")


def cleanup(text):
    """
    validates that the given text is clean: only contains [0-9a-zA-Z_]
    """

    if re.compile('[^0-9a-zA-Z_]').findall(text):
        raise SyntaxError, \
            'only [0-9a-zA-Z_] allowed in table and field names, received %s' \
            % text
    return text


def sqlite3_web2py_extract(lookup, s):
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

def oracle_fix_execute(command, execute):
    args = []
    i = 1
    while True:
        m = oracle_fix.match(command)
        if not m:
            break
        command = command[:m.start('clob')] + str(i) + command[m.end('clob'):]
        args.append(m.group('clob')[6:-2].replace("''", "'"))
        i += 1
    return execute(command[:-1], args)


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

class SQLDB(dict):

    """
    an instance of this class represents a database connection

    Example::

       db = SQLDB('sqlite://test.db')
       db.define_table('tablename', Field('fieldname1'),
                                   Field('fieldname2'))

    """

    # ## this allows gluon to comunite a folder for this thread

    _folders = {}
    _connection_pools = {}
    _instances = {}

    @staticmethod
    def _set_thread_folder(folder):
        sql_locker.acquire()
        SQLDB._folders[thread.get_ident()] = folder
        sql_locker.release()

    # ## this allows gluon to commit/rollback all dbs in this thread

    @staticmethod
    def close_all_instances(action):
        """ to close cleanly databases in a multithreaded environment """

        sql_locker.acquire()
        pid = thread.get_ident()
        if pid in SQLDB._folders:
            del SQLDB._folders[pid]
        if pid in SQLDB._instances:
            instances = SQLDB._instances[pid]
            while instances:
                instance = instances.pop()
                sql_locker.release()
                action(instance)
                sql_locker.acquire()

                # ## if you want pools, recycle this connection
                really = True
                if instance._pool_size:
                    pool = SQLDB._connection_pools[instance._uri]
                    if len(pool) < instance._pool_size:
                        pool.append(instance._connection)
                        really = False
                if really:
                    sql_locker.release()
                    instance._connection.close()
                    sql_locker.acquire()
            del SQLDB._instances[pid]
        sql_locker.release()
        return

    @staticmethod
    def distributed_transaction_begin(*instances):
        if not instances:
            return
        instances = enumerate(instances)
        for (i, db) in instances:
            if db._dbname == 'mysql':
                db._execute('XA START;')
            elif db._dbname == 'postgres':
                pass
            else:
                raise SyntaxError, \
                    'distributed transaction only supported by postgresql'

    @staticmethod
    def distributed_transaction_commit(*instances):
        if not instances:
            return
        instances = enumerate(instances)
        thread_key = '%s.%i' % (socket.gethostname(), thread.get_ident())
        keys = ['%s.%i' % (thread_key, i) for (i,db) in instances]
        for (i, db) in instances:
            if not db._dbname in ['postgres', 'mysql', 'firebird']:
                raise SyntaxError, \
                    'distributed transaction only supported by postgresql, firebir'
        try:
            for (i, db) in instances:
                if db._dbname == 'postgres':
                    db._execute("PREPARE TRANSACTION '%s';" % keys[i])
                elif db._dbname == 'mysql':
                    db._execute("XA END;")
                    db._execute("XA PREPARE;")
                elif db._dbname == 'firebird':
                    db.prepare()
        except:
            for (i, db) in instances:
                if db._dbname == 'postgres':
                    db._execute("ROLLBACK PREPARED '%s';" % keys[i])
                elif db._dbname == 'mysql':
                    db._execute("XA ROLLBACK;")
                elif db._dbname == 'firebird':
                    db.rollback()
            raise Exception, 'failure to commit distributed transaction'
        else:
            for (i, db) in instances:
                if db._dbname == 'postgres':
                    db._execute("COMMIT PREPARED '%s';" % keys[i])
                elif db._dbname == 'mysql':
                    db._execute("XA COMMIT;")
                elif db._dbname == 'firebird':
                    db.commit()
        return

    def _pool_connection(self, f):

        # ## deal with particular case first:

        if not self._pool_size:
            self._connection = f()
            return
        uri = self._uri
        sql_locker.acquire()
        if not uri in self._connection_pools:
            self._connection_pools[uri] = []
        if self._connection_pools[uri]:
            self._connection = self._connection_pools[uri].pop()
            sql_locker.release()
        else:
            sql_locker.release()
            self._connection = f()

    def __init__(self, uri='sqlite://dummy.db', pool_size=0,
                 folder=None, db_codec='UTF-8', check_reserved=None):
        self._uri = str(uri) # NOTE: assuming it is in utf8!!!
        self._pool_size = pool_size
        self._db_codec = db_codec
        self.check_reserved = check_reserved
        if self.check_reserved:
            from reserved_sql_keywords import ADAPTERS as RSK
            self.RSK = RSK
        self['_lastsql'] = ''
        self.tables = SQLCallableList()
        pid = thread.get_ident()

        # Check if there is a folder for this thread else use ''

        if folder:
            self._folder = folder
        else:
            sql_locker.acquire()
            if pid in self._folders:
                self._folder = self._folders[pid]
            else:
                self._folder = self._folders[pid] = ''
            sql_locker.release()

        # Now connect to database

        if self._uri[:14] == 'sqlite:memory:':
            self._dbname = 'sqlite'
            self._pool_connection(lambda: \
                    sqlite3.Connection(':memory:',
                                       check_same_thread=False))
            self._connection.create_function('web2py_extract', 2,
                    sqlite3_web2py_extract)
            # self._connection.row_factory = sqlite3.Row
            self._cursor = self._connection.cursor()
            self._execute = lambda *a, **b: self._cursor.execute(*a, **b)
        elif not is_jdbc and self._uri[:9] == 'sqlite://':
            self._dbname = 'sqlite'
            path_encoding = sys.getfilesystemencoding() or \
                locale.getdefaultlocale()[1]
            if uri[9] != '/':
                dbpath = os.path.join(
                  self._folder.decode(path_encoding).encode('utf8'),
                  uri[9:])
            else:
                dbpath = uri[9:]
            self._pool_connection(lambda : sqlite3.Connection(dbpath,
                                           check_same_thread=False))
            self._connection.create_function('web2py_extract', 2,
                                             sqlite3_web2py_extract)
            # self._connection.row_factory = sqlite3.Row
            self._cursor = self._connection.cursor()
            self._execute = lambda *a, **b: self._cursor.execute(*a, **b)
        elif self._uri[:8] == 'mysql://':
            self._dbname = 'mysql'
            m = re.compile('^(?P<user>[^:@]+)(\:(?P<passwd>[^@]*))?@(?P<host>[^\:/]+)(\:(?P<port>[0-9]+))?/(?P<db>[^?]+)(\?set_encoding=(?P<charset>\w+))?$'
                ).match(self._uri[8:])
            if not m:
                raise SyntaxError, \
                    "Invalid URI string in SQLDB: %s" % self._uri
            user = m.group('user')
            if not user:
                raise SyntaxError, 'User required'
            passwd = m.group('passwd')
            if not passwd:
                passwd = ''
            host = m.group('host')
            if not host:
                raise SyntaxError, 'Host name required'
            db = m.group('db')
            if not db:
                raise SyntaxError, 'Database name required'
            port = m.group('port') or '3306'

            charset = m.group('charset') or 'utf8'

            self._pool_connection(lambda : MySQLdb.Connection(
                    db=db,
                    user=user,
                    passwd=passwd,
                    host=host,
                    port=int(port),
                    charset=charset,
                    ))
            self._cursor = self._connection.cursor()
            self._execute = lambda *a, **b: self._cursor.execute(*a, **b)
            self._execute('SET FOREIGN_KEY_CHECKS=1;')
            self._execute("SET sql_mode='NO_BACKSLASH_ESCAPES';")
        elif not is_jdbc and self._uri[:11] == 'postgres://':
            self._dbname = 'postgres'
            m = \
                re.compile('^(?P<user>[^:@]+)(\:(?P<passwd>[^@]*))?@(?P<host>[^\:/]+)(\:(?P<port>[0-9]+))?/(?P<db>.+)$'
                           ).match(self._uri[11:])
            if not m:
                raise SyntaxError, "Invalid URI string in SQLDB"
            user = m.group('user')
            if not user:
                raise SyntaxError, 'User required'
            passwd = m.group('passwd')
            if not passwd:
                passwd = ''
            host = m.group('host')
            if not host:
                raise SyntaxError, 'Host name required'
            db = m.group('db')
            if not db:
                raise SyntaxError, 'Database name required'
            port = m.group('port') or '5432'

            msg = \
                "dbname='%s' user='%s' host='%s' port=%s password='%s'"\
                 % (db, user, host, port, passwd)
            self._pool_connection(lambda : psycopg2.connect(msg))
            self._connection.set_client_encoding('UTF8')
            self._cursor = self._connection.cursor()
            self._execute = lambda *a, **b: self._cursor.execute(*a, **b)
            query = 'BEGIN;'
            self['_lastsql'] = query
            self._execute(query)
            self._execute("SET CLIENT_ENCODING TO 'UNICODE';")  # ## not completely sure but should work
            self._execute("SET standard_conforming_strings=on;")
        elif self._uri[:9] == 'oracle://':
            self._dbname = 'oracle'
            self._pool_connection(lambda : \
                                  cx_Oracle.connect(self._uri[9:]))
            self._cursor = self._connection.cursor()
            self._execute = lambda a: \
                oracle_fix_execute(a,self._cursor.execute)
            self._execute("ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';")
            self._execute("ALTER SESSION SET NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD HH24:MI:SS';")
        elif self._uri[:8] == 'mssql://' or self._uri[:9] == 'mssql2://':

            # ## read: http://bytes.com/groups/python/460325-cx_oracle-utf8

            if self._uri[:8] == 'mssql://':
                skip = 8
                self._dbname = 'mssql'
            elif self._uri[:9] == 'mssql2://':
                skip = 9
                self._dbname = 'mssql2'
            if '@' not in self._uri[skip:]:
                try:
                    m = re.compile('^(?P<dsn>.+)$'
                                   ).match(self._uri[skip:])
                    if not m:
                        raise SyntaxError, \
                            'Parsing uri string(%s) has no result' % (self._uri[skip:])
                    dsn = m.group('dsn')
                    if not dsn:
                        raise SyntaxError, 'DSN required'
                except SyntaxError, e:
                    logging.error('NdGpatch error')
                    raise e
                cnxn = 'DSN=%s' % dsn
            else:
                m = \
                    re.compile('^(?P<user>[^:@]+)(\:(?P<passwd>[^@]*))?@(?P<host>[^\:/]+)(\:(?P<port>[0-9]+))?/(?P<db>[^\?]+)(\?(?P<urlargs>.*))?$'
                               ).match(self._uri[skip:])
                if not m:
                    raise SyntaxError, \
                        "Invalid URI string in SQLDB: %s" % self._uri
                user = m.group('user')
                if not user:
                    raise SyntaxError, 'User required'
                passwd = m.group('passwd')
                if not passwd:
                    passwd = ''
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

                cnxn = \
                    'SERVER=%s;PORT=%s;DATABASE=%s;UID=%s;PWD=%s;%s' \
                    % (host, port, db, user, passwd, urlargs)
            self._pool_connection(lambda : pyodbc.connect(cnxn))
            self._cursor = self._connection.cursor()
            if self._uri[:8] == 'mssql://':
                self._execute = lambda *a, **b: self._cursor.execute(*a, **b)
            elif self._uri[:9] == 'mssql2://':
                self._execute = lambda a: \
                    self._cursor.execute(unicode(a, 'utf8'))
        elif self._uri[:11] == 'firebird://':
            self._dbname = 'firebird'
            m = re.compile('^(?P<user>[^:@]+)(\:(?P<passwd>[^@]*))?@(?P<host>[^\:/]+)(\:(?P<port>[0-9]+))?/(?P<db>.+?)(\?set_encoding=(?P<charset>\w+))?$').match(self._uri[11:])
            if not m:
                raise SyntaxError, \
                    "Invalid URI string in SQLDB: %s" % self._uri
            user = m.group('user')
            if not user:
                raise SyntaxError, 'User required'
            passwd = m.group('passwd')
            if not passwd:
                passwd = ''
            host = m.group('host')
            if not host:
                raise SyntaxError, 'Host name required'
            db = m.group('db')
            if not db:
                raise SyntaxError, 'Database name required'
            port = m.group('port') or '3050'

            charset = m.group('charset') or 'UTF8'

            self._pool_connection(lambda : \
                    kinterbasdb.connect(dsn='%s/%s:%s' % (host, port, db),
                                        user=user,
                                        password=passwd,
                                        charset=charset))
            self._cursor = self._connection.cursor()
            self._execute = lambda *a, **b: self._cursor.execute(*a, **b)
        elif self._uri[:20] == 'firebird_embedded://':
            self._dbname = 'firebird'
            m = re.compile('^(?P<user>[^:@]+)(\:(?P<passwd>[^@]*))?@(?P<path>[^\?]+)(\?set_encoding=(?P<charset>\w+))?$').match(self._uri[20:])
            if not m:
                raise SyntaxError, \
                    "Invalid URI string in SQLDB: %s" % self._uri
            user = m.group('user')
            if not user:
                raise SyntaxError, 'User required'
            passwd = m.group('passwd')
            if not passwd:
                passwd = ''
            pathdb = m.group('path')
            if not pathdb:
                raise SyntaxError, 'Path required'
            charset = m.group('charset')
            if not charset:
                charset = 'UTF8'
            self._pool_connection(lambda : \
                    kinterbasdb.connect(host='',
                                        database=pathdb,
                                        user=user,
                                        password=passwd,
                                        charset=charset))
            self._cursor = self._connection.cursor()
            self._execute = lambda *a, **b: self._cursor.execute(*a, **b)
        elif self._uri[:11] == 'informix://':
            self._dbname = 'informix'
            m = \
                re.compile('^(?P<user>[^:@]+)(\:(?P<passwd>[^@]*))?@(?P<host>[^\:/]+)(\:(?P<port>[0-9]+))?/(?P<db>.+)$'
                           ).match(self._uri[11:])
            if not m:
                raise SyntaxError, \
                    "Invalid URI string in SQLDB: %s" % self._uri
            user = m.group('user')
            if not user:
                raise SyntaxError, 'User required'
            passwd = m.group('passwd')
            if not passwd:
                passwd = ''
            host = m.group('host')
            if not host:
                raise SyntaxError, 'Host name required'
            db = m.group('db')
            if not db:
                raise SyntaxError, 'Database name required'
            port = m.group('port') or '3050'

            self._pool_connection(lambda : informixdb.connect('%s@%s'
                                   % (db, host), user=user,
                                  password=passwd, autocommit=False))
            self._cursor = self._connection.cursor()
            self._execute = lambda a: self._cursor.execute(a[:-1])
        elif self._uri[:4] == 'db2:':
            self._dbname, cnxn = self._uri.split(':', 1)
            self._pool_connection(lambda : pyodbc.connect(cnxn))
            self._cursor = self._connection.cursor()
            self._execute = lambda a: self._cursor.execute(a[:-1])
        elif is_jdbc and self._uri[:9] == 'sqlite://':
            self._dbname='sqlite'
            if uri[9] != '/':
                dbpath = os.path.join(self._folder, uri[14:])
            else:
                dbpath = uri[14:]
            self._pool_connection(lambda dbpath=dbpath: zxJDBC.connect(java.sql.DriverManager.getConnection('jdbc:sqlite:'+dbpath)))
            self._cursor = self._connection.cursor()
            self._execute = lambda a: self._cursor.execute(a[:-1])
        elif is_jdbc and self._uri[:11] == 'postgres://':
            self._dbname = 'postgres'
            m = \
                re.compile('^(?P<user>[^:@]+)(\:(?P<passwd>[^@]*))?@(?P<host>[^\:/]+)(\:(?P<port>[0-9]+))?/(?P<db>.+)$'
                           ).match(self._uri[11:])
            if not m:
                raise SyntaxError, "Invalid URI string in SQLDB"
            user = m.group('user')
            if not user:
                raise SyntaxError, 'User required'
            passwd = m.group('passwd')
            if not passwd:
                passwd = ''
            host = m.group('host')
            if not host:
                raise SyntaxError, 'Host name required'
            db = m.group('db')
            if not db:
                raise SyntaxError, 'Database name required'
            port = m.group('port') or '5432'

            msg = \
                "dbname='%s' user='%s' host='%s' port=%s password='%s'"\
                 % (db, user, host, port, passwd)
            params = ('jdbc:postgresql://%s:%s/%s' % (host, port, db),
                      user,passwd)
            self._pool_connection(lambda params=params:zxJDBC.connect(*params))
            self._connection.set_client_encoding('UTF8')
            self._cursor = self._connection.cursor()
            self._execute = lambda *a, **b: self._cursor.execute(*a, **b)
            query = 'BEGIN;'
            self['_lastsql'] = query
            self._execute(query)
            self._execute("SET CLIENT_ENCODING TO 'UNICODE';")  # ## not completely sure but should work
            self._execute("SET standard_conforming_strings=on;")
        elif self._uri.startswith('ingres:'):
            """Currently only one URI form supported:

                    ingres://LOCAL_DATABASE_NAME

            NOTE may also use: "ingres:LOCAL_DATABASE_NAME"
            and avoid the slashes "/".
            """
            self._dbname, connstr = self._uri.split(':', 1)
            # Simple URI processing
            connstr=connstr.lstrip()
            while connstr.startswith('/'):
                connstr = connstr[1:]

            database_name=connstr # Assume only (local) dbname is passed in
            vnode='(local)'
            servertype='ingres'
            trace=(0, None) # No tracing
            self._pool_connection(lambda : \
                                    ingresdbi.connect(
                                        database=database_name,
                                        vnode=vnode,
                                        servertype=servertype,
                                        trace=trace))
            self._cursor = self._connection.cursor()
            self._execute = lambda *a, **b: self._cursor.execute(*a, **b)
        elif self._uri == 'None':


            class Dummy:

                lastrowid = 1

                def __getattr__(self, value):
                    return lambda *a, **b: ''


            self._dbname = 'sqlite'
            self._connection = Dummy()
            self._cursor = Dummy()
            self._execute = lambda a: []
        else:
            raise SyntaxError, \
                'database type not supported: %s' % self._uri
        self._translator = SQL_DIALECTS[self._dbname]

        # ## register this instance of SQLDB

        sql_locker.acquire()
        if not pid in self._instances:
            self._instances[pid] = []
        self._instances[pid].append(self)
        sql_locker.release()
        pass
        
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
            
        if 'primarykey' in args:
            t = self[tablename] = KeyedTable(self, tablename, *fields,
                                             **dict(primarykey=args['primarykey']))
        else:
            t = self[tablename] = Table(self, tablename, *fields)
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
        if key in self:
            raise SyntaxError, \
                'Object %s exists and cannot be redefined' % key
        self[key] = value

    def __repr__(self):
        return '<SQLDB ' + dict.__repr__(self) + '>'

    def __call__(self, where=None):
        return Set(self, where)

    def prepare(self):
        self._connection.prepare()

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

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
        self['_lastsql'] = query
        if placeholders:
            self['_lastsql'] +="  with "+str(placeholders)
            self._execute(query, placeholders)
        else:
            self._execute(query)
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
        s = ['%s.%s' % (self.table._tablename, name) for name in
             self.table.fields]
        return ', '.join(s)


class SQLJoin(object):
    """
    Helper class providing the join statement between the given tables/queries.

    Normally only called from gluon.sql
    """

    def __init__(self, table, query):
        self.table = table
        self.query = query

    def __str__(self):
        return '%s ON %s' % (self.table, self.query)


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

        db = SQLDB(...)
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
        """
        Initializes the table and performs checking on the provided fields.

        Each table will have automatically an 'id'.

        If a field is of type Table, the fields (excluding 'id') from that table
        will be used instead.

        :raises SyntaxError: when a supplied field is of incorrect type.
        """
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
                               field.fields[1:]]
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

    def _create_references(self):
        self._referenced_by = []
        for fieldname in self.fields:
            field=self[fieldname]
            if isinstance(field.type,str) and field.type[:10] == 'reference ':
                referenced = field.type[10:].strip()
                if not referenced:
                    raise SyntaxError, 'Table: reference to nothing: %s' % referenced
                if not referenced in self._db:
                    raise SyntaxError, 'Table: table "%s" does not exist' % referenced
                referee = self._db[referenced]
                if self._tablename in referee.fields:
                    raise SyntaxError, 'Field: table %s has same name as a field in referenced table %s' % (self._tablename, referee._tablename)
                referee._referenced_by.append((self._tablename, field.name))

    def _filter_fields(self, record, id=False):
        return dict([(k, v) for (k, v) in record.items() if k
                     in self.fields and (k!='id' or id)])

    def __getitem__(self, key):
        if not key:
            return None
        elif str(key).isdigit():
            return self._db(self.id == key).select().first()
        else:
            return dict.__getitem__(self, str(key))

    def __setitem__(self, key, value):
        if str(key).isdigit():
            if key == 0:
                self.insert(**self._filter_fields(value))
            elif not self._db(self.id == key)\
                    .update(**self._filter_fields(value)):
                raise SyntaxError, 'No such record: %s' % key
        else:
            dict.__setitem__(self, str(key), value)

    def __delitem__(self, key):
        if not str(key).isdigit() or not self._db(self.id == key).delete():
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
        other = copy.copy(self)
        other['_ot'] = other._tablename
        other['ALL'] = SQLALL(other)
        other['_tablename'] = alias
        for fieldname in other.fields:
            other[fieldname] = copy.copy(other[fieldname])
            other[fieldname]._tablename = alias
        self._db[alias] = self
        return other

    def _create(self, migrate=True, fake_migrate=False):
        fields = []
        sql_fields = {}
        sql_fields_aux = {}
        for k in self.fields:
            field = self[k]
            if isinstance(field.type,SQLCustomType):
                ftype = field.type.native or field.type.type
            elif field.type[:10] == 'reference ':
                referenced = field.type[10:].strip()
                constraint_name = '%s_%s__constraint' % (self._tablename, field.name)
                if self._db._dbname == 'oracle' and len(constraint_name)>30:
                    constraint_name = '%s_%s__constraint' % (self._tablename[:10], field.name[:7])
                ftype = self._db._translator[field.type[:9]]\
                     % dict(table_name=self._tablename,
                            field_name=field.name,
                            constraint_name=constraint_name,
                            foreign_key=referenced + ('(%s)' % self._db[referenced].fields[0]),
                            on_delete_action=field.ondelete)
            elif field.type[:7] == 'decimal':
                precision, scale = [int(x) for x in field.type[8:-1].split(',')]
                ftype = self._db._translator[field.type[:7]] % \
                    dict(precision=precision,scale=scale)
            elif not field.type in self._db._translator:
                raise SyntaxError, 'Field: unknown field type: %s for %s' % \
                    (field.type, field.name)
            else:
                ftype = self._db._translator[field.type]\
                     % dict(length=field.length)
            if not field.type[:10] in ['id', 'reference ']:
                if field.notnull:
                    ftype += ' NOT NULL'
                if field.unique:
                    ftype += ' UNIQUE'

            # add to list of fields
            sql_fields[field.name] = ftype

            if field.default:
                sql_fields_aux[field.name] = ftype.replace('NOT NULL',
                        self._db._translator['notnull']
                         % dict(default=sql_represent(field.default,
                        field.type, self._db._dbname, self._db._db_codec)))
            else:
                sql_fields_aux[field.name] = ftype

            fields.append('%s %s' % (field.name, ftype))
        other = ';'

        # backend-specific extensions to fields
        if self._db._dbname == 'mysql':
            fields.append('PRIMARY KEY(%s)' % self.fields[0])
            other = ' ENGINE=InnoDB CHARACTER SET utf8;'

        fields = ',\n    '.join(fields)
        query = '''CREATE TABLE %s(\n    %s\n)%s''' % \
           (self._tablename, fields, other)

        if self._db._uri[:10] == 'sqlite:///':
            path_encoding = sys.getfilesystemencoding() or \
                locale.getdefaultlocale()[1]
            dbpath = self._db._uri[9:self._db._uri.rfind('/')]\
                .decode('utf8').encode(path_encoding)
        else:
            dbpath = self._db._folder
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
            self._logfilename = os.path.join(dbpath, 'sql.log')
            logfile = open(self._logfilename, 'a')
        else:
            logfile = None
        if not self._dbt or not os.path.exists(self._dbt):
            if self._dbt:
                logfile.write('timestamp: %s\n'
                               % datetime.datetime.today().isoformat())
                logfile.write(query + '\n')
            self._db['_lastsql'] = query
            if self._db._dbname == 'ingres':
                # pre-create table auto inc code (if needed)
                tmp_seqname=gen_ingres_sequencename(self._tablename)
                query=query.replace(INGRES_SEQNAME, tmp_seqname)
                self._db._execute('create sequence %s' % tmp_seqname)
            if not fake_migrate:
                self._db._execute(query)
                if self._db._dbname in ['oracle']:
                    t = self._tablename
                    self._db._execute('CREATE SEQUENCE %s_sequence START WITH 1 INCREMENT BY 1 NOMAXVALUE;'
                                   % t)
                    self._db._execute('CREATE OR REPLACE TRIGGER %s_trigger BEFORE INSERT ON %s FOR EACH ROW BEGIN SELECT %s_sequence.nextval INTO :NEW.id FROM DUAL; END;\n'
                                   % (t, t, t))
                elif self._db._dbname == 'firebird':
                    t = self._tablename
                    self._db._execute('create generator GENID_%s;' % t)
                    self._db._execute('set generator GENID_%s to 0;' % t)
                    self._db._execute('''create trigger trg_id_%s for %s active before insert position 0 as\nbegin\nif(new.id is null) then\nbegin\nnew.id = gen_id(GENID_%s, 1);\nend\nend;
''' % (t, t, t))
                elif self._db._dbname == 'ingres':
                    # post create table auto inc code (if needed)
                    # modify table to btree for performance....
                    # Older Ingres releases could use rule/trigger like Oracle above.
                    modify_tbl_sql='modify %s to btree unique on %s' % (self._tablename, 'id') # hard coded id column
                    self._db._execute(modify_tbl_sql)
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
        if self._db._dbname == 'mssql':
            new_add = '; ALTER TABLE %s ADD ' % self._tablename
        else:
            new_add = ', ADD '
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
                self._db['_lastsql'] = '\n'.join(query)
                for sub_query in query:
                    logfile.write(sub_query + '\n')
                    if not fake_migrate:
                        self._db._execute(sub_query)
                        if self._db._dbname in ['mysql', 'oracle']:
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

    def create(self):
        """nothing to do; here for backward compatibility"""

        pass

    def _drop(self, mode = None):
        t = self._tablename
        c = mode or ''
        if self._db._dbname in ['oracle']:
            return ['DROP TABLE %s %s;' % (t, c), 'DROP SEQUENCE %s_sequence;'
                     % t]
        elif self._db._dbname == 'firebird':
            return ['DROP TABLE %s %s;' % (t, c), 'DROP GENERATOR GENID_%s;'
                     % t]
        elif self._db._dbname == 'mysql':
            # breaks db integrity but without this mysql does not drop table
            return ['SET FOREIGN_KEY_CHECKS=0;','DROP TABLE %s;' % t,'SET FOREIGN_KEY_CHECKS=1;']
        return ['DROP TABLE %s;' % t]

    def drop(self, mode = None):
        if self._dbt:
            logfile = open(self._logfilename, 'a')
        queries = self._drop(mode = mode)
        self._db['_lastsql'] = '\n'.join(queries)
        for query in queries:
            if self._dbt:
                logfile.write(query + '\n')
            self._db._execute(query)
        self._db.commit()
        del self._db[self._tablename]
        del self._db.tables[self._db.tables.index(self._tablename)]
        self._db._update_referenced_by(self._tablename)
        if self._dbt:
            os.unlink(self._dbt)
            logfile.write('success!\n')

    def _insert(self, **fields):
        (fs, vs) = ([], [])
        invalid_fieldnames = [key for key in fields if not key in self.fields]
        if invalid_fieldnames:
            raise SyntaxError, 'invalid field names: %s' \
                % repr(invalid_fieldnames)
        for fieldname in self.fields:
            if fieldname == 'id':
                continue
            field = self[fieldname]
            (ft, fd) = (field.type, field._db._dbname)
            if fieldname in fields:
                fs.append(fieldname)
                value = fields[fieldname]
                if hasattr(value,'id'):
                    value = value.id
                elif ft == 'string' and isinstance(value,(str,unicode)):
                    value = value[:field.length]
                vs.append(sql_represent(value, ft, fd, self._db._db_codec))
            elif field.default != None:
                fs.append(fieldname)
                vs.append(sql_represent(field.default, ft, fd, self._db._db_codec))
            elif field.compute != None:
                fs.append(fieldname)
                vs.append(sql_represent(field.compute(fields), ft, fd, self._db._db_codec))
            elif field.required is True:
                raise SyntaxError,'Table: missing required field: %s'%field
        sql_f = ', '.join(fs)
        sql_v = ', '.join(vs)
        sql_t = self._tablename
        return 'INSERT INTO %s(%s) VALUES (%s);' % (sql_t, sql_f, sql_v)

    def bulk_insert(self, *items):
        """ this is here for competibility reasons with GAE """
        return [self.insert(**item) for item in items]

    def insert(self, **fields):
        query = self._insert(**fields)
        self._db['_lastsql'] = query
        self._db._execute(query)
        if self._db._dbname == 'sqlite':
            id = self._db._cursor.lastrowid
        elif self._db._dbname == 'postgres':
            self._db._execute("select currval('%s_id_Seq')"
                               % self._tablename)
            id = int(self._db._cursor.fetchone()[0])
        elif self._db._dbname == 'mysql':
            self._db._execute('select last_insert_id();')
            id = int(self._db._cursor.fetchone()[0])
        elif self._db._dbname in ['oracle']:
            t = self._tablename
            self._db._execute('SELECT %s_sequence.currval FROM dual;'
                               % t)
            id = int(self._db._cursor.fetchone()[0])
        elif self._db._dbname == 'mssql' or self._db._dbname\
             == 'mssql2':
            self._db._execute('SELECT @@IDENTITY;')
            id = int(self._db._cursor.fetchone()[0])
        elif self._db._dbname == 'firebird':
            self._db._execute('SELECT gen_id(GENID_%s, 0) FROM rdb$database'
                               % self._tablename)
            id = int(self._db._cursor.fetchone()[0])
        elif self._db._dbname == 'informix':
            id = self._db._cursor.sqlerrd[1]
        elif self._db._dbname == 'db2':
            self._db._execute('SELECT DISTINCT IDENTITY_VAL_LOCAL() FROM %s;'%self._tablename)
            id = int(self._db._cursor.fetchone()[0])
        elif self._db._dbname == 'ingres':
            tmp_seqname=gen_ingres_sequencename(self._tablename)
            self._db._execute('select current value for %s' % tmp_seqname)
            id = int(self._db._cursor.fetchone()[0]) # don't really need int type cast here...
        else:
            id = None
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
        return SQLJoin(self, query)

    def _truncate(self, mode = None):
        t = self._tablename
        c = mode or ''
        if self._db._dbname == 'sqlite':
            return ['DELETE FROM %s;' % t,
                    "DELETE FROM sqlite_sequence WHERE name='%s';" % t]
        return ['TRUNCATE TABLE %s %s;' % (t, c)]

    def truncate(self, mode = None):
        if self._dbt:
            logfile = open(self._logfilename, 'a')
        queries = self._truncate(mode = mode)
        self._db['_lastsql'] = '\n'.join(queries)
        for query in queries:
            if self._dbt:
                logfile.write(query + '\n')
            self._db._execute(query)
        self._db.commit()
        if self._dbt:
            logfile.write('success!\n')


# added by Denes Lengyel (2009)
class KeyedTable(Table):

    """
    an instance of this class represents a database keyed table

    Example::

        db = DAL(...)
        db.define_table('account',
          Field('accnum','integer'),
          Field('acctype'),
          Field('accdesc'),
          primarykey=['accnum','acctype'])
        db.users.insert(accnum=1000,acctype='A',accdesc='Assets')
        db.users.drop()

        db.define_table('subacct',
          Field('sanum','integer'),
          Field('refnum','reference account.accnum'),
          Field('reftype','reference account.acctype'),
          Field('sadesc','string'),
          primarykey=['sanum']))

    Notes:
    1) primarykey is a list of the field names that make up the primary key
    2) all primarykey fields will have NOT NULL set even if not specified
    3) references are to other keyed tables only
    4) references must use tablename.fieldname format, as shown above
    5) update_record function is not available

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

        If a field is of type Table, the fields (excluding 'id') from that table
        will be used instead.

        :raises SyntaxError: when a supplied field is of incorrect type.
        """

        for k,v in args.iteritems():
            if k != 'primarykey':
                raise SyntaxError, 'invalid table "%s" attribute: %s' % (tablename, k)
            elif isinstance(v,list):
                self._primarykey=v
            else:
                raise SyntaxError, 'primarykey must be a list of fields from table "%s" ' %tablename

        new_fields = []

        for field in fields:
            if hasattr(field,'_db'):
                field = copy.copy(field)
            if isinstance(field, Field):
                new_fields.append(field)
            elif isinstance(field, Table):
                new_fields += [copy.copy(field[f]) for f in
                               field.fields if f != 'id']
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
            self.fields.append(field.name)
            self[field.name] = field
            field._tablename = self._tablename
            field._table = self
            field._db = self._db
            if field.requires == '<default>':
                field.requires = sqlhtml_validators(field)
        self.ALL = SQLALL(self)

        for k in self._primarykey:
            if k not in self.fields:
                raise SyntaxError,\
                'primarykey must be a list of fields from table "%s" ' %\
                 tablename
            else:
                self[k].notnull = True

    # KeyedTable
    def _create_references(self):
        self._referenced_by = []
        for fieldname in self.fields:
            field=self[fieldname]
            if isinstance(field.type,str) and field.type[:10] == 'reference ':
                ref = field.type[10:].strip()
                refs = ref.split('.')
                if not ref:
                    raise SyntaxError, 'Table: reference to nothing: %s' %ref
                if len(refs)!=2:
                    raise SyntaxError, 'invalid reference: %s' %ref
                rtablename,rfieldname = refs
                if not rtablename in self._db.tables:
                    raise SyntaxError,\
                    'Table: table "%s" does not exist' %rtablename
                rtable = self._db[rtablename]
                if not isinstance(rtable, KeyedTable):
                    raise SyntaxError,\
                    'keyed tables can only reference other keyed tables (for now)'
                if self._tablename in rtable.fields:
                    raise SyntaxError,\
                    'Field: table %s has same name as a field in referenced table "%s"' %\
                    (self._tablename, rtablename)
                if rfieldname not in rtable.fields:
                    raise SyntaxError,\
                    "invalid field '%s' for referenced table '%s' in table '%s'" %(rfieldname, rtablename, self._tablename)
                rtable._referenced_by.append((self._tablename, field.name))


    # KeyedTable
    def _build_query(self,key):
        query = None
        for k,v in key.iteritems():
            if k in self._primarykey:
                if query:
                    query = query & (self[k] == v)
                else:
                    query = (self[k] == v)
            else:
                raise SyntaxError,\
                'Field %s is not part of the primary key of %s'%\
                (k,self._tablename)
        return query

    # KeyedTable ok
    def __getitem__(self, key):
        if not key:
            return None
        if isinstance(key, dict):
            query = self._build_query(key)
            rows = self._db(query).select()
            if rows:
                return rows[0]
            return None
        else:
            return dict.__getitem__(self, str(key))

    # KeyedTable ok
    def __setitem__(self, key, value):
        # ??? handle special case where primarykey has all fields ???
        if isinstance(key, dict) and isinstance(value, dict):
            if set(key.keys())==set(self._primarykey):
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
        else:
            if isinstance(key, dict):
                raise SyntaxError,\
                'value must be a dictionary: %s'%value
#                 'key must be a dictionary with primary key fields: %s'%\
#                 self._primarykey
            dict.__setitem__(self, str(key), value)

    # KeyedTable
    def __delitem__(self, key):
        if isinstance(key, dict):
            query = self._build_query(key)
            if not self._db(query).delete():
                raise SyntaxError, 'No such record: %s' % key
#             else:
#                 raise SyntaxError,\
#                 'key must have all fields from primary key: %s'%\
#                 (self._primarykey)
        else:
            raise SyntaxError,\
            'key must be a dictionary with primary key fields: %s'%\
            self._primarykey
#         if not str(key).isdigit() or not self._db(self.id == key).delete():
#             raise SyntaxError, 'No such record: %s' % key

    # KeyedTable
    def __repr__(self):
        return '<KeyedTable ' + dict.__repr__(self) + '>'

    # KeyedTable
    def _create(self, migrate=True, fake_migrate=False):
        fields = []
        sql_fields = {}
        sql_fields_aux = {}
        TFK = {} # table level FK
        for k in self.fields:
            field = self[k]
            if isinstance(field.type,SQLCustomType):
                ftype = field.type.native or field.type.type
            elif field.type[:10] == 'reference ':
                ref = field.type[10:].strip()
                constraint_name = '%s_%s__constraint' % (self._tablename, field.name)
                if self._db._dbname == 'oracle' and len(constraint_name)>30:
                    constraint_name = '%s_%s__constraint' % (self._tablename[:10], field.name[:7])
                rtablename,rfieldname = ref.split('.')
                rtable = self._db[rtablename]
                rfield = rtable[rfieldname]
                # must be PK reference or unique
                if rfieldname in rtable._primarykey or rfield.unique:
                    ftype = self._db._translator[rfield.type[:9]] %dict(length=rfield.length)
                    # multicolumn primary key reference?
                    if not rfield.unique and len(rtable._primarykey)>1 :
                        # then it has to be a table level FK
                        if rtablename not in TFK:
                            TFK[rtablename] = {}
                        TFK[rtablename][rfieldname] = field.name
                    else:
                        ftype = ftype + \
                                self._db._translator['reference FK'] %dict(\
                                constraint_name=constraint_name,
                                table_name=self._tablename,
                                field_name=field.name,
                                foreign_key='%s (%s)'%(rtablename, rfieldname),
                                on_delete_action=field.ondelete)
                else:
                    raise SyntaxError,\
                    'primary key or unique field required in reference %s' %ref

            elif not field.type in self._db._translator:
                raise SyntaxError, 'Field: unknown field type: %s for %s' % \
                    (field.type, field.name)
            else:
                ftype = self._db._translator[field.type]\
                     % dict(length=field.length)
            if not field.type[:10] in ['id', 'reference ']:
                if field.notnull:
                    ftype += ' NOT NULL'
                if field.unique:
                    ftype += ' UNIQUE'

            # add to list of fields
            sql_fields[field.name] = ftype

            if field.default:
                sql_fields_aux[field.name] = ftype.replace('NOT NULL',
                        self._db._translator['notnull']
                         % dict(default=sql_represent(field.default,
                        field.type, self._db._dbname, self._db._db_codec)))
            else:
                sql_fields_aux[field.name] = ftype

            fields.append('%s %s' % (field.name, ftype))
        other = ';'

        # backend-specific extensions to fields
        if self._db._dbname == 'mysql':
            other = ' ENGINE=InnoDB CHARACTER SET utf8;'

        fields = ',\n    '.join(fields)

        for rtablename in TFK:
            rfields = TFK[rtablename]
            pkeys = self._db[rtablename]._primarykey
            fkeys = [ rfields[k] for k in pkeys ]
            fields = fields + ',\n    ' + \
                     self._db._translator['reference TFK'] %\
                     dict(table_name=self._tablename,
                     field_name=', '.join(fkeys),
                     foreign_table=rtablename,
                     foreign_key=', '.join(pkeys),
                     on_delete_action=field.ondelete)

        if self._primarykey:
            query = '''CREATE TABLE %s(\n    %s,\n`    %s) %s''' % \
               (self._tablename, fields, self._db._translator['primarykey']%', '.join(self._primarykey),other)
        else:
            query = '''CREATE TABLE %s(\n    %s\n)%s''' % \
               (self._tablename, fields, other)
        if self._db._uri[:10] == 'sqlite:///':
            path_encoding = sys.getfilesystemencoding() or \
                locale.getdefaultlocale()[1]
            dbpath = self._db._uri[9:self._db._uri.rfind('/')]\
                .decode('utf8').encode(path_encoding)
        else:
            dbpath = self._db._folder
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
            self._logfilename = os.path.join(dbpath, 'sql.log')
            logfile = open(self._logfilename, 'a')
        else:
            logfile = None
        if not self._dbt or not os.path.exists(self._dbt):
            if self._dbt:
                logfile.write('timestamp: %s\n'
                               % datetime.datetime.today().isoformat())
                logfile.write(query + '\n')
            self._db['_lastsql'] = query
            if self._db._dbname == 'ingres':
                # pre-create table auto inc code (if needed)
                # keyed table already handled
                pass
            if not fake_migrate:
                self._db._execute(query)
                if self._db._dbname in ['oracle']:
                    t = self._tablename
                    self._db._execute('CREATE SEQUENCE %s_sequence START WITH 1 INCREMENT BY 1 NOMAXVALUE;'
                                      % t)
                    self._db._execute('CREATE OR REPLACE TRIGGER %s_trigger BEFORE INSERT ON %s FOR EACH ROW BEGIN SELECT %s_sequence.nextval INTO :NEW.id FROM DUAL; END;\n'
                                      % (t, t, t))
                elif self._db._dbname == 'firebird':
                    t = self._tablename
                    self._db._execute('create generator GENID_%s;' % t)
                    self._db._execute('set generator GENID_%s to 0;' % t)
                    self._db._execute('''create trigger trg_id_%s for %s active before insert position 0 as\nbegin\nif(new.id is null) then\nbegin\nnew.id = gen_id(GENID_%s, 1);\nend\nend;
''' % (t, t, t))
                elif self._db._dbname == 'ingres':
                    # post create table auto inc code (if needed)
                    # modify table to btree for performance.... NOT sure if this will be faster or not.
                    modify_tbl_sql='modify %s to btree unique on %s' % (self._tablename, ', '.join(['"%s"'%x for x in self._primarykey])) # could use same code for Table (with id column, if _primarykey is defined as ['id']
                    self._db._execute(modify_tbl_sql)
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
                              sql_fields_aux, logfile)

        return query

    # KeyedTable
    def insert(self, **fields):
        if self._db._dbname in ['mssql', 'mssql2', 'db2', 'ingres', 'informix']:
            query = self._insert(**fields)
            self._db['_lastsql'] = query
            try:
                self._db._execute(query)
            except Exception, e:
                if 'ingresdbi' in globals() and isinstance(e,ingresdbi.IntegrityError):
                    return None
                if 'pyodbc' in globals() and isinstance(e,pyodbc.IntegrityError):
                    return None
                if 'informixdb' in globals() and isinstance(e,informixdb.IntegrityError):
                    return None
                raise e
            return dict( [ (k,fields[k]) for k in self._primarykey ])
        else:
            return Table.insert(self,**fields)


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
        return Expression(str(self) + ', ' + str(other), None, None)

    def __invert__(self):
        return Expression(str(self) + ' DESC', None, None)

    # for use in Query

    def __eq__(self, value):
        return Query(self, '=', value)

    def __ne__(self, value):
        return Query(self, '<>', value)

    def __lt__(self, value):
        return Query(self, '<', value)

    def __le__(self, value):
        return Query(self, '<=', value)

    def __gt__(self, value):
        return Query(self, '>', value)

    def __ge__(self, value):
        return Query(self, '>=', value)

    def like(self, value):
        return Query(self, ' LIKE ', value)

    def belongs(self, value):
        return Query(self, ' IN ', value)

    # for use in both Query and sortby

    def __add__(self, other):
        return Expression('(%s+%s)' % (self, sql_represent(other,
                          self.type, self._db._dbname, self._db._db_codec)), self.type,
                          self._db)

    def __sub__(self, other):
        if self.type == 'integer':
            result_type = 'integer'
        elif self.type in ['date','time','datetime','double']:
            result_type = 'double'
        else:
            raise SyntaxError, "subscraction operation not supported for type"
        return Expression('(%s-%s)' % (self, sql_represent(other,
                          self.type, self._db._dbname, self._db._db_codec)), 
                          result_type,
                          self._db)

    def __mul__(self, other):
        return Expression('(%s*%s)' % (self, sql_represent(other,
                          self.type, self._db._dbname, self._db._db_codec)), self.type,
                          self._db)

    def __div__(self, other):
        return Expression('(%s/%s)' % (self, sql_represent(other,
                          self.type, self._db._dbname, self._db._db_codec)), self.type,
                          self._db)

    def len(self):
        return Expression('LENGTH(%s)' % self, 'integer', self._db)

    def __nonzero__(self):
        return True

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

    to be used as argument of SQLDB.define_table

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
        if hasattr(self,'custom_store'):
            return self.custom_store(file,filename,path)
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
                path = os.path.join(self._db._folder, '..', 'uploads')
            pathfilename = os.path.join(path, newfilename)
            dest_file = open(pathfilename, 'wb')
            shutil.copyfileobj(file, dest_file)
            dest_file.close()
        return newfilename

    def retrieve(self, name, path=None):
        if hasattr(self,'custom_retrieve'):
            return self.custom_retrieve(name, path)
        if self.authorize or isinstance(self.uploadfield, str):
            row = self._db(self == name).select().first()
            if not row:
                raise HTTP(404)
        if self.authorize and not self.authorize(row):
            raise HTTP(403)
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
                path = os.path.join(self._db._folder, '..', 'uploads')
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
        s = self._db._translator['lower'] % dict(field=str(self))
        return Expression(s, 'string', self._db)

    def upper(self):
        s = self._db._translator['upper'] % dict(field=str(self))
        return Expression(s, 'string', self._db)

    def year(self):
        s = self._db._translator['extract'] % dict(name='year',
                field=str(self))
        return Expression(s, 'integer', self._db)

    def month(self):
        s = self._db._translator['extract'] % dict(name='month',
                field=str(self))
        return Expression(s, 'integer', self._db)

    def day(self):
        s = self._db._translator['extract'] % dict(name='day',
                field=str(self))
        return Expression(s, 'integer', self._db)

    def hour(self):
        s = self._db._translator['extract'] % dict(name='hour',
                field=str(self))
        return Expression(s, 'integer', self._db)

    def minutes(self):
        s = self._db._translator['extract'] % dict(name='minute',
                field=str(self))
        return Expression(s, 'integer', self._db)

    def seconds(self):
        s = self._db._translator['extract'] % dict(name='second',
                field=str(self))
        return Expression(s, 'integer', self._db)

    def count(self):
        return Expression('COUNT(%s)' % str(self), 'integer', self._db)

    def sum(self):
        return Expression('SUM(%s)' % str(self), 'integer', self._db)

    def max(self):
        return Expression('MAX(%s)' % str(self), 'integer', self._db)

    def min(self):
        return Expression('MIN(%s)' % str(self), 'integer', self._db)

    def __getslice__(self, start, stop):
        if start < 0:
            pos0 = '(%s - %d)' % (self.len(), -start)
        else:
            pos0 = start

        if stop < 0:
            length = '(%s - %d - %s)' % (self.len(), -stop, pos0)
        else:
            length = '(%s - %s)' % (stop, pos0)

        d = dict(field=str(self), pos=int(pos0)+1, length=length)
        s = self._db._translator['substring'] % d
        return Expression(s, 'string', self._db)

    def __getitem__(self, i):
        if i < 0:
            pos0 = '(%s - %d)' % (self.len(), -i)
        else:
            pos0 = str(i)

        d = dict(field=str(self), pos=pos0+1, length=1)
        s = self._db._translator['substring'] % d
        return Expression(s, 'string', self._db)

    def __getitem__(self, i):
        return self[i:i + 1]

    def __str__(self):
        try:
            return '%s.%s' % (self._tablename, self.name)
        except:
            return '<no table>.%s' % self.name


SQLDB.Field = Field  # necessary in gluon/globals.py session.connect
SQLDB.Table = Table  # necessary in gluon/globals.py session.connect


class Query(object):

    """
    a query object necessary to define a set.
    t can be stored or can be passed to SQLDB.__call__() to obtain a Set

    Example::

        query = db.users.name=='Max'
        set = db(query)
        records = set.select()

    :raises SyntaxError: when the query cannot be recognized
    """

    def __init__(
        self,
        left,
        op=None,
        right=None,
        ):
        if op is None and right is None:
            self.sql = left
        elif right is None:
            if op == '=':
                self.sql = '%s %s' % (left,
                        left._db._translator['is null'])
            elif op == '<>':
                self.sql = '%s %s' % (left,
                        left._db._translator['is not null'])
            else:
                raise SyntaxError, 'Operation %s can\'t be used with None' % op
        elif op == ' IN ':
            if isinstance(right, str):
                self.sql = '%s%s(%s)' % (left, op, right[:-1])
            elif hasattr(right, '__iter__'):
                r = ','.join([sql_represent(i, left.type, left._db, left._db._db_codec)
                             for i in right])
                self.sql = '%s%s(%s)' % (left, op, r)
            else:
                raise SyntaxError, 'Right argument of "IN" is not suitable'
        elif isinstance(right, (Field, Expression)):
            self.sql = '%s%s%s' % (left, op, right)
        else:
            right = sql_represent(right, left.type, left._db._dbname, left._db._db_codec)
            self.sql = '%s%s%s' % (left, op, right)

    def __and__(self, other):
        return Query('(%s AND %s)' % (self, other))

    def __or__(self, other):
        return Query('(%s OR %s)' % (self, other))

    def __invert__(self):
        return Query('(NOT %s)' % self)

    def __str__(self):
        return self.sql


regex_tables = re.compile('(?P<table>[a-zA-Z]\w*)\.')
regex_quotes = re.compile("'[^']*'")


def parse_tablenames(text):
    text = regex_quotes.sub('', text)
    while 1:
        i = text.find('IN (SELECT ')
        if i == -1:
            break
        (k, j, n) = (1, i + 11, len(text))
        while k and j < n:
            c = text[j]
            if c == '(':
                k += 1
            elif c == ')':
                k -= 1
            j += 1
        text = text[:i] + text[j + 1:]
    items = regex_tables.findall(text)
    tables = {}
    for item in items:
        tables[item] = True
    return tables.keys()


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
    normally the Set is generated by SQLDB.__call__(Query(...))

    given a set, for example
       set = db(db.users.name=='Max')
    you can:
       set.update(db.users.name='Massimo')
       set.delete() # all elements in the set
       set.select(orderby=db.users.id, groupby=db.users.name, limitby=(0,10))
    and take subsets:
       subset = set(db.users.id<5)
    """

    def __init__(self, db, where=''):
        self._db = db
        self._tables = []

        # find out wchich tables are involved

        self.sql_w = str(where or '')
        self._tables = parse_tablenames(self.sql_w)


    def __call__(self, where):
        if self.sql_w:
            return Set(self._db, Query(self.sql_w) & where)
        else:
            return Set(self._db, where)

    def _select(self, *fields, **attributes):
        valid_attributes = [
            'orderby',
            'groupby',
            'limitby',
            'required',
            'cache',
            'default',
            'requires',
            'left',
            'distinct',
            'having',
            ]
        if [key for key in attributes if not key
             in valid_attributes]:
            raise SyntaxError, 'invalid select attribute: %s' % key

        # ## if not fields specified take them all from the requested tables

        if not fields:
            fields = [self._db[table].ALL for table in self._tables]
        sql_f = ', '.join([str(f) for f in fields])
        tablenames = parse_tablenames(self.sql_w + ' ' + sql_f)
        if len(tablenames) < 1:
            raise SyntaxError, 'Set: no tables selected'
        w2p_tablenames = [ t for t in tablenames if isinstance(self._db[t],Table) ]
        self.colnames = [c.strip() for c in sql_f.split(', ')]
        if self.sql_w:
            sql_w = ' WHERE ' + self.sql_w
        else:
            sql_w = ''
        sql_o = ''
        sql_s = 'SELECT'
        distinct = attributes.get('distinct', False)
        if distinct is True:
            sql_s += ' DISTINCT'
        elif distinct:
            sql_s += ' DISTINCT ON (%s)' % distinct
        if attributes.get('left', False):
            join = attributes['left']
            command = self._db._translator['left join']
            if not isinstance(join, (tuple, list)):
                join = [join]
            joint = [t._tablename for t in join if not isinstance(t,
                     SQLJoin)]
            joinon = [t for t in join if isinstance(t, SQLJoin)]
            joinont = [t.table._tablename for t in joinon]
            excluded = [t for t in tablenames if not t in joint
                         + joinont]
            sql_t = ', '.join(excluded)
            if joint:
                sql_t += ' %s %s' % (command, ', '.join(joint))
            for t in joinon:
                sql_t += ' %s %s' % (command, str(t))
        else:
            sql_t = ', '.join(tablenames)
        if attributes.get('groupby', False):
            sql_o += ' GROUP BY %s' % attributes['groupby']
            if attributes.get('having', False):
                sql_o += ' HAVING %s' % attributes['having']
        orderby = attributes.get('orderby', False)
        if orderby:
            if isinstance(orderby, (list, tuple)):
                orderby = xorify(orderby)
            if str(orderby) == '<random>':
                sql_o += ' ORDER BY %s' % self._db._translator['random']
            else:
                sql_o += ' ORDER BY %s' % orderby
        if attributes.get('limitby', False):
            # oracle does not support limitby
            (lmin, lmax) = attributes['limitby']
            if self._db._dbname in ['oracle']:
                if not attributes.get('orderby', None) and w2p_tablenames:
                    sql_o += ' ORDER BY %s' % ', '.join([t + '.id'
                            for t in w2p_tablenames])
                if len(sql_w) > 1:
                    sql_w_row = sql_w + ' AND w_row > %i' % lmin
                else:
                    sql_w_row = 'WHERE w_row > %i' % lmin
                return '%s %s FROM (SELECT w_tmp.*, ROWNUM w_row FROM (SELECT %s FROM %s%s%s) w_tmp WHERE ROWNUM<=%i) %s %s;' % (sql_s, sql_f, sql_f, sql_t, sql_w, sql_o, lmax, sql_t, sql_w_row)
                #return '%s %s FROM (SELECT w_tmp.*, ROWNUM w_row FROM (SELECT %s FROM %s%s%s) w_tmp WHERE ROWNUM<=%i) %s WHERE w_row>%i;' % (sql_s, sql_f, sql_f, sql_t, sql_w, sql_o, lmax, sql_t, lmin)
                #return '%s %s FROM (SELECT *, ROWNUM w_row FROM (SELECT %s FROM %s%s%s) WHERE ROWNUM<=%i) WHERE w_row>%i;' % (sql_s, sql_f, sql_f, sql_t, sql_w, sql_o, lmax, lmin)
            elif self._db._dbname == 'mssql' or \
                 self._db._dbname == 'mssql2':
                if not attributes.get('orderby', None) and w2p_tablenames:
#                     sql_o += ' ORDER BY %s' % ', '.join([t + '.id'
#                             for t in w2p_tablenames ])
                    sql_o += ' ORDER BY %s' % ', '.join(['%s.%s'%(t,x) for t in w2p_tablenames for x in ((hasattr(self._db[t],'_primarykey') and self._db[t]._primarykey) or ['id'])])
                sql_s += ' TOP %i' % lmax
            elif self._db._dbname == 'firebird':
                if not attributes.get('orderby', None) and w2p_tablenames:
                    sql_o += ' ORDER BY %s' % ', '.join([t + '.id'
                            for t in w2p_tablenames])
                sql_s += ' FIRST %i SKIP %i' % (lmax - lmin, lmin)
            elif self._db._dbname == 'db2':
                if not attributes.get('orderby', None) and w2p_tablenames:
#                     sql_o += ' ORDER BY %s' % ', '.join([t + '.id'
#                             for t in w2p_tablenames])
                    sql_o += ' ORDER BY %s' % ', '.join(['%s.%s'%(t,x) for t in w2p_tablenames for x in ((hasattr(self._db[t],'_primarykey') and self._db[t]._primarykey) or ['id'])])
                sql_o += ' FETCH FIRST %i ROWS ONLY' % lmax
            elif self._db._dbname == 'ingres':
                fetch_amt = lmax - lmin
                if fetch_amt:
                    sql_s += ' FIRST %d ' % (fetch_amt, )
                if lmin:
                    # Requires Ingres 9.2+
                    sql_o += ' OFFSET %d' % (lmin, )
            elif self._db._dbname == 'informix':
                fetch_amt = lmax - lmin
                dbms_version = int(self._db._connection.dbms_version.split('.')[0])
                if lmin and (dbms_version >= 10):
                    # Requires Informix 10.0+
                    sql_s += ' SKIP %d' % (lmin, )
                if fetch_amt and (dbms_version >= 9):
                    # Requires Informix 9.0+
                    sql_s += ' FIRST %d' % (fetch_amt, )
            else:
                sql_o += ' LIMIT %i OFFSET %i' % (lmax - lmin, lmin)
        return '%s %s FROM %s%s%s;' % (sql_s, sql_f, sql_t, sql_w,
                sql_o)

    def select(self, *fields, **attributes):
        """
        Always returns a Rows object, even if it may be empty
        """

        db=self._db
        def response(query):
            db['_lastsql'] = query
            db._execute(query)
            return db._cursor.fetchall()

        if not attributes.get('cache', None):
            query = self._select(*fields, **attributes)
            rows = response(query)
        else:
            (cache_model, time_expire) = attributes['cache']
            del attributes['cache']
            query = self._select(*fields, **attributes)
            key = self._db._uri + '/' + query
            rows = cache_model(key, lambda : response(query), time_expire)

        if isinstance(rows,tuple):
            rows = list(rows)
        if db._dbname in ['mssql', 'mssql2', 'db2']:
            rows = rows[(attributes.get('limitby', None) or (0,))[0]:]
        return self.parse(db,rows,self.colnames)

    @staticmethod
    def parse(db,rows,colnames,blob_decode=True):
        virtualtables = []
        new_rows = []
        for (i,row) in enumerate(rows):
            new_row = Row()
            for j,colname in enumerate(colnames):
                value = row[j]
                if not table_field.match(colnames[j]):
                    if not '_extra' in new_row:
                        new_row['_extra'] = Row()
                    new_row['_extra'][colnames[j]] = value
                    continue
                (tablename, fieldname) = colname.split('.')
                table = db[tablename]
                field = table[fieldname]
                field_type = field.type
                if isinstance(field_type,SQLCustomType):
                    field_type = field_type.type
                if field.type != 'blob' and isinstance(value, str):
                    try:
                        value = value.decode(db._db_codec)
                    except Exception, e:
                        pass
                if isinstance(value, unicode):
                    value = value.encode('utf-8')
                if not tablename in new_row:
                    colset = new_row[tablename] = Row()
                    virtualtables.append((tablename,db[tablename].virtualfields))
                else:
                    colset = new_row[tablename]
                if not isinstance(field_type,str):
                    colset[fieldname] = value
                elif isinstance(field.type,str) and field.type[:10] == 'reference ':
                    referee = field.type[10:].strip()
                    if not value:
                        colset[fieldname] = value
                    elif not '.' in referee:
                        colset[fieldname] = rid = Reference(value)
                        (rid._table, rid._record) = (db[referee], None)
                    else: ### reference not by id
                        colset[fieldname] = value
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
                        s = db[referee_table][referee_name]
                        colset[referee_table] = Set(db, s == id)
                    colset['id'] = id
            new_rows.append(new_row)
        rowsobj = Rows(db, new_rows, colnames)
        for table, virtualfields in virtualtables:
            for item in virtualfields:
                rowsobj = rowsobj.setvirtualfields(**{table:item})
        return rowsobj

    def _count(self):
        return self._select('count(*)')

    def count(self):
        return self.select('count(*)')[0]._extra['count(*)']

    def _delete(self):
        if len(self._tables) != 1:
            raise SyntaxError, \
                'Set: unable to determine what to delete'
        tablename = self._tables[0]
        if self.sql_w:
            sql_w = ' WHERE ' + self.sql_w
        else:
            sql_w = ''
        return 'DELETE FROM %s%s;' % (tablename, sql_w)

    def delete(self):
        query = self._delete()
        self.delete_uploaded_files()
        ### special code to handle CASCADE in SQLite
        db=self._db
        t = self._tables[0]
        if db._dbname=='sqlite' and db[t]._referenced_by:
            deleted = [x.id for x in self.select(db[t].id)]
        ### end special code to handle CASCADE in SQLite
        self._db['_lastsql'] = query
        self._db._execute(query)
        try:
            counter = self._db._cursor.rowcount
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
        tablenames = self._tables
        if len(tablenames) != 1:
            raise SyntaxError, 'Set: unable to determine what to do'
        sql_t = tablenames[0]
        (table, dbname) = (self._db[sql_t], self._db._dbname)
        update_fields.update(dict([(fieldname, table[fieldname].update) \
                                       for fieldname in table.fields \
                                       if not fieldname in update_fields \
                                       and table[fieldname].update != None]))
        update_fields.update(dict([(fieldname, table[fieldname].compute(update_fields)) \
                                       for fieldname in table.fields \
                                       if not fieldname in update_fields \
                                       and table[fieldname].compute != None]))
        sql_v = 'SET ' + ', '.join(['%s=%s' % (field,
                                   sql_represent(value,
                                   table[field].type, dbname, self._db._db_codec))
                                   for (field, value) in
                                   update_fields.items()])
        if self.sql_w:
            sql_w = ' WHERE ' + self.sql_w
        else:
            sql_w = ''
        return 'UPDATE %s %s%s;' % (sql_t, sql_v, sql_w)

    def update(self, **update_fields):
        query = self._update(**update_fields)
        self.delete_uploaded_files(update_fields)
        self._db['_lastsql'] = query
        self._db._execute(query)
        try:
            return self._db._cursor.rowcount
        except:
            return None

    def delete_uploaded_files(self, upload_fields=None):
        table = self._db[self._tables[0]]

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
                    uploadfolder = os.path.join(self._db._folder, '..', 'uploads')
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
                    elif represent:
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

    >>> if len(sys.argv)<2: db = SQLDB(\"sqlite://test.db\")
    >>> if len(sys.argv)>1: db = SQLDB(sys.argv[1])
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
    >>> len(db().select(db.person.ALL))
    2
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
    >>> db(mynumber.id>0).select(mynumber.x.sum())[0]._extra[mynumber.x.sum()]
    45
    >>> db(mynumber.x+2==5).select(mynumber.x + 2)[0]._extra[mynumber.x + 2]
    5

    Output in csv

    >>> print str(authored_papers.select(db.author.name, db.paper.title)).strip()
    author.name,paper.title\r
    Massimo,QCD

    Delete all leftover tables

    # >>> SQLDB.distributed_transaction_commit(db)

    >>> db.mynumber.drop()
    >>> db.authorship.drop()
    >>> db.author.drop()
    >>> db.paper.drop()
    """

SQLField = Field
SQLTable = Table
SQLXorable = Expression
SQLQuery = Query
SQLSet = Set
SQLRows = Rows
SQLStorage = Row
BaseAdapter = SQLDB

def DAL(uri='sqlite:memory:',
        pool_size=0,
        folder=None, 
        db_codec='UTF-8',
        check_reserved=None):
    if uri == 'gae':
        import gluon.contrib.gql
        return gluon.contrib.gql.GQLDB()
    else:
        return SQLDB(uri, pool_size=pool_size, folder=folder,
                     db_codec=db_codec, check_reserved=check_reserved)

if __name__ == '__main__':
    import doctest
    doctest.testmod()
