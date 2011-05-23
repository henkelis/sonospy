#!/bin/env python
# -*- coding: utf-8 -*-

"""
This file is part of web2py Web Framework (Copyrighted, 2007-2010).
Developed by Massimo Di Pierro <mdipierro@cs.depaul.edu>.
License: GPL v2
"""

import os
import re
import logging
from storage import Storage
from http import HTTP

regex_at = re.compile('(?<!\\\\)\$[\w_]+')
regex_anything = re.compile('(?<!\\\\)\$anything')
regex_iter = re.compile(r'.*code=(?P<code>\d+)&ticket=(?P<ticket>.+).*')

params = Storage()

params.routes_in = []
params.routes_out = []
params.routes_onerror = []
params.routes_apps_raw = []
params.error_handler = None
params.error_message = '<html><body><h1>Invalid request</h1></body></html>'
params.error_message_custom = '<html><body><h1>%s</h1></body></html>'
params.error_message_ticket = \
    '<html><body><h1>Internal error</h1>Ticket issued: <a href="/admin/default/ticket/%(ticket)s" target="_blank">%(ticket)s</a></body><!-- this is junk text else IE does not display the page: '+('x'*512)+' //--></html>'


def load(routes='routes.py'):
    symbols = {}
    if not os.path.exists(routes):
        return
    try:
        routesfp = open(routes, 'r')
        exec routesfp.read() in symbols
        routesfp.close()
        logging.info('URL rewrite is on. configuration in %s' % routes)
    except SyntaxError, e:
        routesfp.close()
        logging.error('Your %s has a syntax error. ' % routes + \
                          'Please fix it before you restart web2py')
        raise e

    params.routes_in=[]
    if 'routes_in' in symbols:
        for (k, v) in symbols['routes_in']:
            if not k[0] == '^':
                k = '^%s' % k
            if not k[-1] == '$':
                k = '%s$' % k
            if k.find(':') < 0:
                k = '^.*?:%s' % k[1:]
            if k.find('://') < 0:
                i = k.find(':/')
                k = r'%s:https?://[^:/]+:[a-z]+ %s' % (k[:i], k[i+1:])
            for item in regex_anything.findall(k):
                k = k.replace(item, '(?P<anything>.*)')
            for item in regex_at.findall(k):
                k = k.replace(item, '(?P<%s>[\\w_]+)' % item[1:])
            for item in regex_at.findall(v):
                v = v.replace(item, '\\g<%s>' % item[1:])
            params.routes_in.append((re.compile(k, re.DOTALL), v))

    params.routes_out=[]
    if 'routes_out' in symbols:
        for (k, v) in symbols['routes_out']:
            if not k[0] == '^':
                k = '^%s' % k
            if not k[-1] == '$':
                k = '%s$' % k
            for item in regex_at.findall(k):
                k = k.replace(item, '(?P<%s>\\w+)' % item[1:])
            for item in regex_at.findall(v):
                v = v.replace(item, '\\g<%s>' % item[1:])
            params.routes_out.append((re.compile(k, re.DOTALL), v))

    if 'routes_onerror' in symbols:
        params.routes_onerror = symbols['routes_onerror']
    if 'error_handler' in symbols:
        params.error_handler = symbols['error_handler']
    if 'error_message' in symbols:
        params.error_message = symbols['error_message']
    if 'error_message_ticket' in symbols:
        params.error_message_ticket = symbols['error_message_ticket']
    if 'routes_apps_raw' in symbols:
        params.routes_apps_raw = symbols['routes_apps_raw']


def filter_in(e):
    if params.routes_in:
        query = e.get('QUERY_STRING', None)
        path = e['PATH_INFO']
        host = e.get('HTTP_HOST', 'localhost').lower()
        original_uri = path + (query and '?'+query or '')
        i = host.find(':')
        if i > 0:
            host = host[:i]
        key = '%s:%s://%s:%s %s' % \
            (e['REMOTE_ADDR'],
             e.get('WSGI_URL_SCHEME', 'http').lower(), host,
             e.get('REQUEST_METHOD', 'get').lower(), path)
        for (regex, value) in params.routes_in:
            if regex.match(key):
                path = regex.sub(value, key)
                break
        if path.find('?') < 0:
            e['PATH_INFO'] = path
        else:
            if query:
                path = path+'&'+query
            e['PATH_INFO'] = ''
            e['REQUEST_URI'] = path
            e['WEB2PY_ORIGINAL_URI'] = original_uri
    return e

def filter_out(url):
    if params.routes_out:
        items = url.split('?', 1)
        for (regex, value) in params.routes_out:
            if regex.match(items[0]):
                return '?'.join([regex.sub(value, items[0])] + items[1:])
    return url


def try_redirect_on_error(http_object, request, ticket=None):
    status = int(str(http_object.status).split()[0])
    if status>399 and params.routes_onerror:
        keys=set(('%s/%s' % (request.application, status),
                  '%s/*' % (request.application),
                  '*/%s' % (status),
                  '*/*'))
        for (key,redir) in params.routes_onerror:
            if key in keys:
                if redir == '!':
                    break
                elif '?' in redir:
                    url = redir + '&' + 'code=%s&ticket=%s&requested_uri=%s' % (status,ticket, request.env.request_uri)
                else:
                    url = redir + '?' + 'code=%s&ticket=%s&requested_uri=%s' % (status,ticket, request.env.request_uri)
                return HTTP(303,
                            'You are being redirected <a href="%s">here</a>' % url,
                            Location=url)
    return http_object

def filter_url(url, method='get', remote='0.0.0.0'):
    "doctest interface to filter_in()"
    regex_url = re.compile('^(?P<scheme>http|https|HTTP|HTTPS)\://(?P<host>[^/]+)(?P<uri>\S*)')
    match = regex_url.match(url)
    scheme = match.group('scheme').lower()
    host = match.group('host').lower()
    uri = match.group('uri')
    k = uri.find('?')
    if k < 0:
        k = len(uri)
    (path_info, query_string) = (uri[:k], uri[k+1:])
    e = {
         'REMOTE_ADDR': remote,
         'REQUEST_METHOD': method,
         'WSGI_URL_SCHEME': scheme,
         'HTTP_HOST': host,
         'REQUEST_URI': uri,
         'PATH_INFO': path_info,
         'QUERY_STRING': query_string
    }
    e = filter_in(e)
    if e['PATH_INFO'] == '':
        path = e['REQUEST_URI']
    elif query_string:
        path = e['PATH_INFO'] + '?' + query_string
    else:
        path = e['PATH_INFO']
    return scheme + '://' + host + path

def filter_err(status, application='app', ticket='tkt'):
    "doctest interface to routes_onerror"
    if status > 399 and params.routes_onerror:
        keys = set(('%s/%s' % (application, status),
                  '%s/*' % (application),
                  '*/%s' % (status),
                  '*/*'))
        for (key,redir) in params.routes_onerror:
            if key in keys:
                if redir == '!':
                    break
                elif '?' in redir:
                    url = redir + '&' + 'code=%s&ticket=%s' % (status,ticket)
                else:
                    url = redir + '?' + 'code=%s&ticket=%s' % (status,ticket)
                return url # redirection
    return status # no action
