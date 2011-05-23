#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This file is part of web2py Web Framework (Copyrighted, 2007-2010).
Developed by Massimo Di Pierro <mdipierro@cs.depaul.edu>.
License: GPL v2
"""

import re
import os
import cStringIO

__all__ = ['parse', 'reindent', 'parse_template', 'render']

re_block = re.compile('^(elif |else:|except:|except |finally:).*$',
                      re.DOTALL)
re_unblock = re.compile('^(return|continue|break)( .*)?$', re.DOTALL)
re_pass = re.compile('^pass( .*)?$', re.DOTALL)
re_write = re.compile('\{\{=(?P<value>.*?)\}\}', re.DOTALL)
re_html = re.compile('\}\}.*?\{\{', re.DOTALL)
re_strings = re.compile(r'(?P<name>'
                         + r"[uU]?[rR]?'''([^']+|'{1,2}(?!'))*'''|"
                         + r"'([^'\\]|\\.)*'|"
                         + r'"""([^"]|"{1,2}(?!"))*"""|'
                         + r'"([^"\\]|\\.)*")', re.DOTALL)

re_include_nameless = re.compile('\{\{\s*include\s*\}\}')
re_include = re.compile('\{\{\s*include\s+(?P<name>.+?)\s*\}\}',
                        re.DOTALL)
re_extend = re.compile('\{\{\s*extend\s+(?P<name>.+?)\s*\}\}',
                       re.DOTALL)

def __re_strings(text):
    ''''
    expose re_strings regex for doctest

    >>> __re_strings('"abc"')
    ['"abc"']
    >>> __re_strings(r'"abc\\"" "x"')
    ['"abc\\\\""', '"x"']
    >>> __re_strings('"abc"xy"def"')
    ['"abc"', '"def"']
    >>> __re_strings('"""abc""""')
    ['"""abc"""']
    >>> __re_strings('"""a"b"c""""xy"')
    ['"""a"b"c"""', '"xy"']
    '''
    result = re_strings.findall(text)
    return result

def reindent(text):
    (new_lines, credit, k) = ([], 0, 0)
    for raw_line in text.split('\n'):
        line = raw_line.strip()
        if not line:
            continue
        if line[0] == '=':
            line = 'response.write(%s)' % line[1:]
        if re_block.match(line):
            k = (k + credit) - 1
        if k < 0:
            k = 0
        new_lines.append('    ' * k + line)
        credit = 0
        if re_pass.match(line):
            (credit, k) = (0, k - 1)
        if re_unblock.match(line):
            (credit, k) = (1, k - 1)
        if line[-1] == ':' and line[0] != '#':
            k += 1
    return '\n'.join(new_lines)

def parse(text):
    text = '}}%s{{' % re_write.sub('{{response.write(\g<value>)}}',
                                   text)
    text = replace(re_html, text, lambda x: \
                   '''\nresponse.write(%s,escape=False)\n'''\
                    % repr(x[2:-2]))
    text = replace(re_strings, text, lambda x: x.replace('\n', '\\n'))
    return reindent(text)


def replace(
    regex,
    text,
    f,
    count=0,
    ):
    i = 0
    output = []
    for item in regex.finditer(text, i):
        output.append(text[i:item.start()])
        output.append(f(item.group()))
        i = item.end()
        count -= 1
        if count == 0:
            break
    output.append(text[i:len(text)])
    return ''.join(output)


def parse_template(
    filename,
    path='views/',
    cache='cache/',
    context=dict(),
    ):
    """
    filename can be a view filename in the views/ folder or an imput stream
    path is the path of a views folder
    context is a dictionary of symbols used to render the template
    """
    import restricted

    # ## read the template

    if isinstance(filename, str):
        try:
            fp = open(os.path.join(path, filename), 'rb')
            text = fp.read()
            fp.close()
        except IOError:
            raise restricted.RestrictedError('Processing View %s' % filename,
                                             '', 'Unable to find the file')
    else:
        text = filename.read()

    # check whether it extends a layout
    while 1:
        match = re_extend.search(text)
        if not match:
            break
        t = os.path.join(path, eval(match.group('name'), context))
        try:
            fp = open(t, 'rb')
            parent = fp.read()
            fp.close()
        except IOError:
            raise restricted.RestrictedError('Processing View %s' % filename,
                  text, '', 'Unable to open parent view file: ' + t)
        (a, b) = (match.start(), match.end())
        text = text[0:a] + replace(re_include_nameless, parent,
                                   lambda x: text[b:])

    # ## check whether it includes subtemplates

    while 1:
        match = re_include.search(text)
        if not match:
            break
        t = os.path.join(path, eval(match.group('name'), context))
        try:
            fp = open(t, 'rb')
            child = fp.read()
            fp.close()
        except IOError:
            raise restricted.RestrictedError('Processing View %s' % filename,
                  text, '', 'Unable to open included view file: ' + t)
        text = replace(re_include, text, lambda x: child, 1)

    # ## now convert to a python expression

    return parse(text)

def render(content='hello world',stream=None,filename=None,path=None,context={}):
    """
    >>> render()
    'hello world'
    >>> render(content='abc')
    'abc'
    >>> render(content='abc\\'')
    "abc'"
    >>> render(content='a"\\'bc')
    'a"\\'bc'
    >>> render(content='a\\nbc')
    'a\\nbc'
    >>> render(content='a"bcd"e')
    'a"bcd"e'
    >>> render(content="'''a\\nc'''")
    "'''a\\nc'''"
    >>> render(content="'''a\\'c'''")
    "'''a\'c'''"
    """
    import globals  ### here to avoid circular imports
    if not content and not stream and not filename:
        raise SyntaxError, "Must specify a stream or filename or content"
    if not stream:
        if filename:
            stream = open(filename,'rb')
        if content:
            stream = cStringIO.StringIO(content)
    context['response'] = globals.Response()
    exec(parse_template(stream,path=path)) in context
    return context['response'].body.getvalue()

if __name__ == '__main__':
    print render(content='{{for i in range(a):}}{{=i}}<br />{{pass}}', context=dict(a=5))
    import doctest
    doctest.testmod()

