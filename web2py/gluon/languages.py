#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This file is part of web2py Web Framework (Copyrighted, 2007-2010).
Developed by Massimo Di Pierro <mdipierro@cs.depaul.edu>.
License: GPL v2
"""

import os
import re
import cgi
import portalocker
import logging
from fileutils import listdir
from settings import settings

__all__ = ['translator', 'findT', 'update_all_languages']

is_gae = settings.web2py_runtime_gae

# pattern to find T(blah blah blah) expressions

PY_STRING_LITERAL_RE = r'(?<=[^\w]T\()(?P<name>'\
     + r"[uU]?[rR]?(?:'''(?:[^']|'{1,2}(?!'))*''')|"\
     + r"(?:'(?:[^'\\]|\\.)*')|" + r'(?:"""(?:[^"]|"{1,2}(?!"))*""")|'\
     + r'(?:"(?:[^"\\]|\\.)*"))'

regex_translate = re.compile(PY_STRING_LITERAL_RE, re.DOTALL)

# patter for a valid accept_language

regex_language = \
    re.compile('^[a-zA-Z]{2}(\-[a-zA-Z]{2})?(\-[a-zA-Z]+)?$')


def read_dict(filename):
    fp = open(filename, 'r')
    portalocker.lock(fp, portalocker.LOCK_SH)
    lang_text = fp.read().replace('\r\n', '\n')
    portalocker.unlock(fp)
    fp.close()
    if not lang_text.strip():
        return {}
    try:
        return eval(lang_text)
    except:
        logging.error('Syntax error in %s' % filename)
        return {}

def write_dict(filename, contents):
    fp = open(filename, 'w')
    portalocker.lock(fp, portalocker.LOCK_EX)
    fp.write('# coding: utf8\n{\n')
    for key in sorted(contents):
        fp.write('%s: %s,\n' % (repr(key), repr(contents[key])))
    fp.write('}\n')
    portalocker.unlock(fp)
    fp.close()


class lazyT(object):

    """
    never to be called explicitly, returned by translator.__call__
    """

    def __init__(
        self,
        message,
        symbols={},
        T=None,
        ):
        self.m = message
        self.s = symbols
        self.T = T

    def __str__(self):
        return self.T.translate(self.m, self.s)

    def __eq__(self, other):
        return self.T.translate(self.m, self.s) == other

    def __ne__(self, other):
        return self.T.translate(self.m, self.s) != other

    def xml(self):
        return cgi.escape(str(self))

    def encode(self,*a,**b):
        return str(self).encode(*a,**b)

    def decode(self,*a,**b):
        return str(self).decode(*a,**b)

    def read(self):
        return str(self)

    def __mod__(self,symbols):
        return self.T.translate(self.m,symbols)

class translator(object):

    """
    this class is instantiated by gluon.compileapp.build_environment 
    as the T object

    ::

        T.force(None) # turns off translation
        T.force('fr, it') # forces web2py to translate using fr.py or it.py

        T(\"Hello World\") # translates \"Hello World\" using the selected file

    notice 1: there is no need to force since, by default, T uses
    accept_language to determine a translation file.

    notice 2: en and en-en are considered different languages!
    """

    def __init__(self, request):
        self.folder = request.folder
        self.current_languages = ['en']
        self.accepted_language = None
        self.language_file = None
        self.http_accept_language = request.env.http_accept_language
        self.requested_languages = self.force(self.http_accept_language)
        self.lazy = True

    def set_current_languages(self, *languages):
        if len(languages)==1 and isinstance(languages[0], (tuple,list)):
            languages=languages[0]
        self.current_languages = languages
        self.force(self.http_accept_language)

    def force(self, *languages):
        if not languages or languages[0]==None:
            languages = []
        if len(languages)==1 and isinstance(languages[0], (str, unicode)):
            languages=languages[0]
        if languages:
            if isinstance(languages, (str, unicode)):
                accept_languages = languages.split(';')
                languages = []
                [languages.extend(al.split(',')) for al in accept_languages]
                languages = [item.strip().lower() for item in languages \
                                 if regex_language.match(item.strip())]

            for language in languages:
                if language in self.current_languages:
                    self.accepted_language = language
                    break
                filename = os.path.join(self.folder, 'languages/', language + '.py')
                if os.path.exists(filename):
                    self.accepted_language = language
                    self.language_file = filename
                    self.t = read_dict(filename)
                    return languages
        self.language_file = None
        self.t = {}  # ## no language by default
        return languages

    def __call__(self, message, symbols={}):
        if self.lazy:
            return lazyT(message, symbols, self)
        else:
            return self.translate(message, symbols)

    def translate(self, message, symbols):
        mt = self.t.get(message, None)
        if mt == None:
            self.t[message] = mt = message
            if self.language_file and not is_gae:
                write_dict(self.language_file, self.t)
        if symbols or symbols == 0:
            return mt % symbols
        return mt


def findT(path, language='en-us'):
    """
    must be run by the admin app
    """
    filename = os.path.join(path, 'languages', '%s.py' % language)
    sentences = read_dict(filename)
    mp = os.path.join(path, 'models')
    cp = os.path.join(path, 'controllers')
    vp = os.path.join(path, 'views')
    for file in listdir(mp, '.+\.py', 0) + listdir(cp, '.+\.py', 0)\
         + listdir(vp, '.+\.html', 0):
        fp = open(file, 'r')
        portalocker.lock(fp, portalocker.LOCK_SH)
        data = fp.read()
        portalocker.unlock(fp)
        fp.close()
        items = regex_translate.findall(data)
        for item in items:
            try:
                msg = eval(item)
                if msg and not msg in sentences:
                    sentences[msg] = msg
            except:
                pass
    write_dict(filename, sentences)


def update_all_languages(application_path):
    path = os.path.join(application_path, 'languages/')
    for language in listdir(path, '^\w+(\-\w+)?\.py$'):
        findT(application_path, language[:-3])
