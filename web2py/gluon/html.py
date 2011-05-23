#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This file is part of web2py Web Framework (Copyrighted, 2007-2010).
Developed by Massimo Di Pierro <mdipierro@cs.depaul.edu>.
License: GPL v2
"""

import cgi
import os
import re
import copy
import types
import urllib
import base64
import sanitizer
import rewrite

from storage import Storage
from validators import *
from highlight import highlight
from utils import web2py_uuid

regex_crlf = re.compile('\r|\n')

__all__ = [
    'A',
    'B',
    'BEAUTIFY',
    'BODY',
    'BR',
    'CENTER',
    'CODE',
    'DIV',
    'EM',
    'EMBED',
    'FIELDSET',
    'FORM',
    'H1',
    'H2',
    'H3',
    'H4',
    'H5',
    'H6',
    'HEAD',
    'HR',
    'HTML',
    'I',
    'IFRAME',
    'IMG',
    'INPUT',
    'LABEL',
    'LEGEND',
    'LI',
    'LINK',
    'OL',
    'UL',
    'MENU',
    'META',
    'OBJECT',
    'ON',
    'OPTION',
    'P',
    'PRE',
    'SCRIPT',
    'SELECT',
    'SPAN',
    'STYLE',
    'TABLE',
    'TAG',
    'TD',
    'TEXTAREA',
    'TH',
    'THEAD',
    'TBODY',
    'TFOOT',
    'TITLE',
    'TR',
    'TT',
    'URL',
    'XHTML',
    'XML',
    'xmlescape',
    'embed64',
    ]


def xmlescape(data, quote = False):
    """
    returns an escaped string of the provided data

    :param data: the data to be escaped
    :param quote: optional (default False)
    """

    # first try the xml function
    try:
        return data.xml()
    except AttributeError:
        pass
    except TypeError:
        pass

    # otherwise, make it a string
    if not isinstance(data, (str, unicode)):
        data = str(data)
    elif isinstance(data, unicode):
        data = data.encode('utf8', 'xmlcharrefreplace')

    # ... and do the escaping
    data = cgi.escape(data, quote)
    return data


def URL(
    a=None,
    c=None,
    f=None,
    r=None,
    args=[],
    vars={},
    anchor='',
    extension=None,
    ):
    """
    generate a relative URL

    example::

        >>> URL(a='a', c='c', f='f', args=['x', 'y', 'z'],
        ...     vars={'p':1, 'q':2}, anchor='1')
        '/a/c/f/x/y/z#1?q=2&p=1'

    generates a url \"/a/c/f\" corresponding to application a, controller c
    and function f. If r=request is passed, a, c, f are set, respectively,
    to r.application, r.controller, r.function.

    The more typical usage is:

    URL(r=request, f='index') that generates a url for the index function
    within the present application and controller.

    :param a: application (default to current if r is given)
    :param c: controller (default to current if r is given)
    :param f: function (default to current if r is given)
    :param r: request (optional)
    :param args: any arguments (optional)
    :param vars: any variables (optional)
    :param anchor: anchorname, without # (optional)

    :raises SyntaxError: when no application, controller or function is
        available
    :raises SyntaxError: when a CRLF is found in the generated url
    """

    application = controller = function = None
    if r:
        application = r.application
        controller = r.controller
        function = r.function
    if a:
        application = a
    if c:
        controller = c
    if f:
        if isinstance(f, str):
            function = f
        else:
            function = f.__name__

    if not (application and controller and function):
        raise SyntaxError, 'not enough information to build the url'

    other = ''
    if args != [] and not isinstance(args, (list, tuple)):
        args = [args]
    if args:
        other = urllib.quote('/' + '/'.join([str(x) for x in args]))
    if extension:
        function += '.'+extension
    if anchor:
        other += '#' + urllib.quote(str(anchor))
    if vars:
        other += '?%s' % urllib.urlencode(vars)

    url = '/%s/%s/%s%s' % (application, controller, function, other)

    if regex_crlf.search(url):
        raise SyntaxError, 'CRLF Injection Detected'
    return rewrite.filter_out(url)


ON = True


class XmlComponent(object):
    """
    Abstract root for all Html components
    """

    # TODO: move some DIV methods to here

    def xml(self):
        raise NotImplementedError


class XML(XmlComponent):
    """
    use it to wrap a string that contains XML/HTML so that it will not be
    escaped by the template

    example:

    >>> XML('<h1>Hello</h1>').xml()
    '<h1>Hello</h1>'
    """

    def __init__(
        self,
        text,
        sanitize = False,
        permitted_tags = [
            'a',
            'b',
            'blockquote',
            'br/',
            'i',
            'li',
            'ol',
            'ul',
            'p',
            'cite',
            'code',
            'pre',
            'img/',
            ],
        allowed_attributes = {
            'a': ['href', 'title'],
            'img': ['src', 'alt'],
            'blockquote': ['type']
            },
        ):
        """
        :param text: the XML text
        :param sanitize: sanitize text using the permitted tags and allowed
            attributes (default False)
        :param permitted_tags: list of permitted tags (default: simple list of
            tags)
        :param allowed_attributes: dictionary of allowed attributed (default
            for A, IMG and BlockQuote).
            The key is the tag; the value is a list of allowed attributes.
        """

        if sanitize:
            text = sanitizer.sanitize(text, permitted_tags,
                    allowed_attributes)
        if isinstance(text, unicode):
            text = text.encode('utf8', 'xmlcharrefreplace')
        elif not isinstance(text, str):
            text = str(text)
        self.text = text

    def xml(self):
        return self.text

    def __str__(self):
        return self.xml()


class DIV(XmlComponent):
    """
    HTML helper, for easy generating and manipulating a DOM structure.
    Little or no validation is done.

    Behaves like a dictionary regarding updating of attributes.
    Behaves like a list regarding inserting/appending components.

    example::

        >>> DIV('hello', 'world', _style='color:red;').xml()
        '<div style=\"color:red;\">helloworld</div>'

    all other HTML helpers are derived from DIV.

    _something=\"value\" attributes are transparently translated into
    something=\"value\" HTML attributes
    """

    # name of the tag, subclasses should update this
    # tags ending with a '/' denote classes that cannot
    # contain components
    tag = 'div'

    def __init__(self, *components, **attributes):
        """
        :param *components: any components that should be nested in this element
        :param **attributes: any attributes you want to give to this element

        :raises SyntaxError: when a stand alone tag receives components
        """

        if self.tag[-1:] == '/' and components:
            raise SyntaxError, '<%s> tags cannot have components'\
                 % self.tag
        if len(components) == 1 and isinstance(components[0], (list,
                tuple)):
            self.components = list(components[0])
        else:
            self.components = list(components)                    
        self.attributes = attributes
        self._fixup()        
        # converts special attributes in components attributes
        self._postprocessing()
        self.parent = None
        for c in self.components:
            self._setnode(c)

    def update(self, **kargs):
        """
        dictionary like updating of the tag attributes
        """

        for (key, value) in kargs.items():
            self[key] = value
        return self

    def append(self, value):
        """
        list style appending of components
        """
        self._setnode(value)
        return self.components.append(value)

    def insert(self, i, value):
        """
        list style inserting of components
        """
        self._setnode(value)
        return self.components.insert(i, value)

    def __getitem__(self, i):
        """
        gets attribute with name 'i' or component #i.
        If attribute 'i' is not found returns None

        :param i: index
           if i is a string: the name of the attribute
           otherwise references to number of the component
        """

        if isinstance(i, str):
            try:
                return self.attributes[i]
            except KeyError:
                return None
        else:
            return self.components[i]

    def __setitem__(self, i, value):
        """
        sets attribute with name 'i' or component #i.

        :param i: index
           if i is a string: the name of the attribute
           otherwise references to number of the component
        :param value: the new value
        """
        self._setnode(value)
        if isinstance(i, str):
            self.attributes[i] = value
        else:            
            self.components[i] = value

    def __delitem__(self, i):
        """
        deletes attribute with name 'i' or component #i.

        :param i: index
           if i is a string: the name of the attribute
           otherwise references to number of the component
        """

        if isinstance(i, str):
            del self.attributes[i]
        else:
            del self.components[i]

    def __len__(self):
        """
        returns the number of included components
        """
        return len(self.components)

    def __nonzero__(self):
        """
        always return True
        """
        return True

    def _fixup(self):
        """
        Handling of provided components.

        Nothing to fixup yet. May be overridden by subclasses,
        eg for wrapping some components in another component or blocking them.
        """
        return

    def _wrap_components(self, allowed_parents, wrap_parent = None,
        wrap_lambda = None):
        """
        helper for _fixup. Checks if a component is in allowed_parents,
        otherwise wraps it in wrap_parent

        :param allowed_parents: (tuple) classes that the component should be an
            instance of
        :param wrap_parent: the class to wrap the component in, if needed
        :param wrap_lambda: lambda to use for wrapping, if needed

        """
        components = []
        for c in self.components:
            if isinstance(c, allowed_parents):
                components.append(c)
            else:
                if wrap_lambda:
                    components.append(wrap_lambda(c))
                else:
                    components.append(wrap_parent(c))
        self.components = components

    def _postprocessing(self):
        """
        Handling of attributes (normally the ones not prefixed with '_').

        Nothing to postprocess yet. May be overridden by subclasses
        """
        return

    def _traverse(self, status):
        # TODO: docstring
        newstatus = status
        for c in self.components:
            if hasattr(c, '_traverse') and callable(c._traverse):
                c.vars = self.vars
                c.request_vars = self.request_vars
                c.errors = self.errors
                c.latest = self.latest
                c.session = self.session
                c.formname = self.formname
                newstatus = c._traverse(status) and newstatus

        # for input, textarea, select, option
        # deal with 'value' and 'validation'

        name = self['_name']
        if newstatus:
            newstatus = self._validate()
            self._postprocessing()
        elif 'old_value' in self.attributes:
            self['value'] = self['old_value']
            self._postprocessing()
        elif name and name in self.vars:
            self['value'] = self.vars[name]
            self._postprocessing()
        if name:
            self.latest[name] = self['value']
        return newstatus

    def _validate(self):
        """
        nothing to validate yet. May be overridden by subclasses
        """
        return True
    
    def _setnode(self,value):
        if isinstance(value,DIV):
            value.parent = self

    def _xml(self):
        """
        helper for xml generation. Returns separately:
        - the component attributes
        - the generated xml of the inner components

        Component attributes start with an underscore ('_') and
        do not have a False or None value. The underscore is removed
        and the name will be in lower case.
        A value of True is replaced with the attribute name.

        :returns: tuple: (attributes, components)
        """

        # get the attributes for this component
        # (they start with '_', others may have special meanings)
        fa = ''
        for key in sorted(self.attributes):
            value = self[key]
            if key[:1] != '_':
                continue
            name = key[1:].lower()
            if value is True:
                value = name
            elif value is False or value is None:
                continue
            fa += ' %s="%s"' % (name, xmlescape(value, True))

        # get the xml for the inner components
        co = ''.join([xmlescape(component) for component in
                     self.components])

        return (fa, co)

    def xml(self):
        """
        generates the xml for this component.
        """

        (fa, co) = self._xml()

        if not self.tag:
            return co

        if self.tag[-1:] == '/':
            # <tag [attributes] />
            return '<%s%s />' % (self.tag[:-1], fa)

        # else: <tag [attributes]>  inner components xml </tag>
        return '<%s%s>%s</%s>' % (self.tag, fa, co, self.tag)

    def __str__(self):
        """
        str(COMPONENT) returns equals COMPONENT.xml()
        """

        return self.xml()

    def elements(self, *args, **kargs):
        """
        find all component that match the supplied attribute dictionary,
        or None if nothing could be found

        All components of the components are searched.
        """
        # make a copy of the components
        components = [self]
        matches = []
        first_only = False
        if kargs.has_key("first_only"):
            first_only = kargs["first_only"]
            del kargs["first_only"]
        # loop the copy
        for c in components:
            try:
                # if the component has components, add it to the list
                # so it can be part of the processing
                components += copy.copy(c.components)
                # check if the component has an attribute with the same
                # value as provided
                check = True
                tag = getattr(c,'tag').replace("/","")
                if args and tag not in args:
                        check = False
                for (key, value) in kargs.items():
                    if c[key] != value:
                            check = False
                # if found, return the component
                if check:
                    matches.append(c)
                    if first_only: break
            except:
                pass
        return matches

    def element(self, *args, **kargs):
        """
        find the first component that matches the supplied attribute dictionary,
        or None if nothing could be found

        Also the components of the components are searched.
        """
        kargs['first_only'] = True
        elements = self.elements(*args, **kargs)
        if not elements:
            # we found nothing
            return None
        return elements[0]
    
    def siblings(self,*args,**kargs):
        """
        find all sibling components that match the supplied argument list 
        and attribute dictionary, or None if nothing could be found
        """
        sibs = [s for s in self.parent.components if not s == self]
        matches = []
        first_only = False
        if kargs.has_key("first_only"):
            first_only = kargs["first_only"]
            del kargs["first_only"]
        for c in sibs:
            try:
                check = True
                tag = getattr(c,'tag').replace("/","")
                if args and tag not in args:
                        check = False
                for (key, value) in kargs.items():
                    if c[key] != value:
                            check = False
                if check:
                    matches.append(c)
                    if first_only: break
            except:
                pass
        return matches            
            
    def sibling(self,*args,**kargs):
        """
        find the first sibling component that match the supplied argument list 
        and attribute dictionary, or None if nothing could be found
        """
        kargs['first_only'] = True
        sibs = self.siblings(*args, **kargs)
        if not sibs:
            return None
        return sibs[0]

class __TAG__(XmlComponent):

    """
    TAG factory example::

        >>> print TAG.first(TAG.second('test'), _key = 3)
        <first key=\"3\"><second>test</second></first>

    """

    def __getitem__(self, name):
        return self.__getattr__(name)

    def __getattr__(self, name):
        if name[-1:] == '_':
            name = name[:-1] + '/'

        class __tag__(DIV):

            tag = name


        return lambda *a, **b: __tag__(*a, **b)


TAG = __TAG__()


class HTML(DIV):
    """
    There are four predefined document type definitions.
    They can be specified in the 'doctype' parameter:

    -'strict' enables strict doctype
    -'transitional' enables transitional doctype (default)
    -'frameset' enables frameset doctype
    -'html5' enables HTML 5 doctype
    -any other string will be treated as user's own doctype

    'lang' parameter specifies the language of the document.
    Defaults to 'en'.

    See also :class:`DIV`
    """

    tag = 'html'

    strict = '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">\n'
    transitional = '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">\n'
    frameset = '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Frameset//EN" "http://www.w3.org/TR/html4/frameset.dtd">\n'
    html5 = '<!DOCTYPE HTML>\n'

    def xml(self):
        lang = self['lang']
        if not lang:
            lang = 'en'
        self.attributes['_lang'] = lang
        doctype = self['doctype']
        if doctype:
            if doctype == 'strict':
                doctype = self.strict
            elif doctype == 'transitional':
                doctype = self.transitional
            elif doctype == 'frameset':
                doctype = self.frameset
            elif doctype == 'html5':
                doctype = self.html5
            else:
                doctype = '%s\n' % doctype
        else:
            doctype = self.transitional
        (fa, co) = self._xml()
        return '%s<%s%s>%s</%s>' % (doctype, self.tag, fa, co, self.tag)

class XHTML(DIV):
    """
    This is XHTML version of the HTML helper.

    There are three predefined document type definitions.
    They can be specified in the 'doctype' parameter:

    -'strict' enables strict doctype
    -'transitional' enables transitional doctype (default)
    -'frameset' enables frameset doctype
    -any other string will be treated as user's own doctype

    'lang' parameter specifies the language of the document and the xml document.
    Defaults to 'en'.

    'xmlns' parameter specifies the xml namespace.
    Defaults to 'http://www.w3.org/1999/xhtml'.

    See also :class:`DIV`
    """

    tag = 'html'

    strict = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">\n'
    transitional = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">\n'
    frameset = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Frameset//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-frameset.dtd">\n'
    xmlns = 'http://www.w3.org/1999/xhtml'

    def xml(self):
        xmlns = self['xmlns']
        if xmlns:
            self.attributes['_xmlns'] = xmlns
        else:
            self.attributes['_xmlns'] = self.xmlns
        lang = self['lang']
        if not lang:
            lang = 'en'
        self.attributes['_lang'] = lang
        self.attributes['_xml:lang'] = lang
        doctype = self['doctype']
        if doctype:
            if doctype == 'strict':
                doctype = self.strict
            elif doctype == 'transitional':
                doctype = self.transitional
            elif doctype == 'frameset':
                doctype = self.frameset
            else:
                doctype = '%s\n' % doctype
        else:
            doctype = self.transitional
        (fa, co) = self._xml()
        return '%s<%s%s>%s</%s>' % (doctype, self.tag, fa, co, self.tag)


class HEAD(DIV):

    tag = 'head'

class TITLE(DIV):

    tag = 'title'


class META(DIV):

    tag = 'meta/'


class LINK(DIV):

    tag = 'link/'


class SCRIPT(DIV):

    tag = 'script'

    def xml(self):
        (fa, co) = self._xml()
        # no escaping of subcomponents
        co = '\n'.join([str(component) for component in
                       self.components])
        if co:
            #<script [attributes]><!--//--><![CDATA[//><!--
            #script body
            #//--><!]]></script>
            #return '<%s%s><!--//--><![CDATA[//><!--\n%s\n//--><!]]></%s>' % (self.tag, fa, co, self.tag)
            return '<%s%s><!--\n%s\n//--></%s>' % (self.tag, fa, co, self.tag)
        else:
            return DIV.xml(self)


class STYLE(DIV):

    tag = 'style'

    def xml(self):
        (fa, co) = self._xml()
        # no escaping of subcomponents
        co = '\n'.join([str(component) for component in
                       self.components])
        if co:
            #<style [attributes]><!--/*--><![CDATA[/*><!--*/
            #style body
            #/*]]>*/--></style>
            return '<%s%s><!--/*--><![CDATA[/*><!--*/\n%s\n/*]]>*/--></%s>' % (self.tag, fa, co, self.tag)
        else:
            return DIV.xml(self)


class IMG(DIV):

    tag = 'img/'


class SPAN(DIV):

    tag = 'span'


class BODY(DIV):

    tag = 'body'


class H1(DIV):

    tag = 'h1'


class H2(DIV):

    tag = 'h2'


class H3(DIV):

    tag = 'h3'


class H4(DIV):

    tag = 'h4'


class H5(DIV):

    tag = 'h5'


class H6(DIV):

    tag = 'h6'


class P(DIV):
    """
    Will replace ``\\n`` by ``<br />`` if the `cr2br` attribute is provided.

    see also :class:`DIV`
    """

    tag = 'p'

    def xml(self):
        text = DIV.xml(self)
        if self['cr2br']:
            text = text.replace('\n', '<br />')
        return text


class B(DIV):

    tag = 'b'


class BR(DIV):

    tag = 'br/'


class HR(DIV):

    tag = 'hr/'


class A(DIV):

    tag = 'a'


class EM(DIV):

    tag = 'em'


class EMBED(DIV):

    tag = 'embed/'


class TT(DIV):

    tag = 'tt'


class PRE(DIV):

    tag = 'pre'


class CENTER(DIV):

    tag = 'center'


class CODE(DIV):

    """
    displays code in HTML with syntax highlighting.

    :param attributes: optional attributes:

        - language: indicates the language, otherwise PYTHON is assumed
        - link: can provide a link
        - styles: for styles

    Example::

        {{=CODE(\"print 'hello world'\", language='python', link=None,
            counter=1, styles={})}}


    supported languages are \"python\", \"html_plain\", \"c\", \"cpp\",
    \"web2py\", \"html\".
    The \"html\" language interprets {{ and }} tags as \"web2py\" code,
    \"html_plain\" doesn't.

    if a link='/examples/global/vars/' is provided web2py keywords are linked to
    the online docs.

    the counter is used for line numbering, counter can be None or a prompt
    string.
    """

    def xml(self):
        language = self['language'] or 'PYTHON'
        link = self['link']
        counter = self.attributes.get('counter', 1)
        styles = self['styles'] or {}
        return highlight(
            ''.join(self.components),
            language=language,
            link=link,
            counter=counter,
            styles=styles,
            attributes=self.attributes,
            )


class LABEL(DIV):

    tag = 'label'


class LI(DIV):

    tag = 'li'


class UL(DIV):
    """
    UL Component.

    If subcomponents are not LI-components they will be wrapped in a LI

    see also :class:`DIV`
    """

    tag = 'ul'

    def _fixup(self):
        self._wrap_components(LI, LI)


class OL(UL):

    tag = 'ol'


class TD(DIV):

    tag = 'td'


class TH(DIV):

    tag = 'th'


class TR(DIV):
    """
    TR Component.

    If subcomponents are not TD/TH-components they will be wrapped in a TD

    see also :class:`DIV`
    """

    tag = 'tr'

    def _fixup(self):
        self._wrap_components((TD, TH), TD)


class THEAD(DIV):

    tag = 'thead'


class TBODY(DIV):

    tag = 'tbody'


class TFOOT(DIV):

    tag = 'tfoot'


class TABLE(DIV):
    """
    TABLE Component.

    If subcomponents are not TR/TBODY/THEAD/TFOOT-components
    they will be wrapped in a TR

    see also :class:`DIV`
    """

    tag = 'table'

    def _fixup(self):
        self._wrap_components((TR, TBODY, THEAD, TFOOT), TR)

class I(DIV):

    tag = 'i'

class IFRAME(DIV):

    tag = 'iframe'


class INPUT(DIV):

    """
        INPUT Component

        examples::

            >>> INPUT(_type='text', _name='name', value='Max').xml()
            '<input name=\"name\" type=\"text\" value=\"Max\" />'

            >>> INPUT(_type='checkbox', _name='checkbox', value='on').xml()
            '<input checked=\"checked\" name=\"checkbox\" type=\"checkbox\" value=\"on\" />'

            >>> INPUT(_type='radio', _name='radio', _value='yes', value='yes').xml()
            '<input checked=\"checked\" name=\"radio\" type=\"radio\" value=\"yes\" />'

            >>> INPUT(_type='radio', _name='radio', _value='no', value='yes').xml()
            '<input name=\"radio\" type=\"radio\" value=\"no\" />'

        the input helper takes two special attributes value= and requires=.

        :param value: used to pass the initial value for the input field.
            value differs from _value because it works for checkboxes, radio,
            textarea and select/option too.

            - for a checkbox value should be '' or 'on'.
            - for a radio or select/option value should be the _value
                of the checked/selected item.

        :param requires: should be None, or a validator or a list of validators
            for the value of the field.
        """

    tag = 'input/'

    def _validate(self):

        # # this only changes value, not _value

        name = self['_name']
        if name == None or name == '':
            return True
        name = str(name)

        if self['_type'] != 'checkbox':
            self['old_value'] = self['value'] or self['_value'] or ''
            value = self.request_vars.get(name, '')
            self['value'] = value
        else:
            self['old_value'] = self['value'] or False
            value = self.request_vars.get(name)
            if isinstance(value, (tuple, list)):
                self['value'] = self['_value'] in value
            else:
                self['value'] = self['_value'] == value
        requires = self['requires']
        if requires:
            if not isinstance(requires, (list, tuple)):
                requires = [requires]
            for validator in requires:
                (value, errors) = validator(value)
                if errors != None:
                    self.vars[name] = value
                    self.errors[name] = errors
                    break
        if not name in self.errors:
            self.vars[name] = value
            return True
        return False

    def _postprocessing(self):
        t = self['_type']
        if not t:
            t = self['_type'] = 'text'
        t = t.lower()
        if t == 'checkbox':
            if not self['_value']:
                self['_value'] = 'on'
            if self['value']:
                self['_checked'] = 'checked'
            else:
                self['_checked'] = None
        elif t == 'radio':
            if str(self['value']) == str(self['_value']):
                self['_checked'] = 'checked'
            else:
                self['_checked'] = None
        elif t == 'text':
            if self['value'] != None:
                self['_value'] = self['value']
            else:
                self['value'] = self['_value']

    def xml(self):
        name = self.attributes.get('_name', None)        
        if name and hasattr(self, 'errors') \
                and self.errors.get(name, None) \
                and self['hideerror'] != True:
            return DIV.xml(self) + DIV(self.errors[name], _class='error',
                errors=None, _id='%s__error' % name).xml()
        else:
            return DIV.xml(self)


class TEXTAREA(INPUT):

    """
    example::

        TEXTAREA(_name='sometext', value='blah '*100, requires=IS_NOT_EMPTY())

    'blah blah blah ...' will be the content of the textarea field.
    """

    tag = 'textarea'

    def _postprocessing(self):
        if not '_rows' in self.attributes:
            self['_rows'] = 10
        if not '_cols' in self.attributes:
            self['_cols'] = 40
        if self['value'] != None:
            self.components = [self['value']]
        elif self.components:
            self['value'] = self.components[0]


class OPTION(DIV):

    tag = 'option'

    def _fixup(self):
        if not '_value' in self.attributes:
            self.attributes['_value'] = str(self.components[0])


class OBJECT(DIV):

    tag = 'object'


class SELECT(INPUT):

    """
    example::

        >>> SELECT('yes', 'no', _name='selector', value='yes',
        ...    requires=IS_IN_SET(['yes', 'no'])).xml()
        '<select name=\"selector\"><option selected=\"selected\" value=\"yes\">yes</option><option value=\"no\">no</option></select>'

    """

    tag = 'select'

    def _fixup(self):
        components = []
        for c in self.components:
            if isinstance(c, OPTION):
                components.append(c)
            else:
                components.append(OPTION(c, _value=str(c)))
        self.components = components

    def _postprocessing(self):
        if self['value'] != None:
            if not self['_multiple']:
                for c in self.components:
                    if self['value'] and str(c['_value'])\
                         == str(self['value']):
                        c['_selected'] = 'selected'
                    else:
                        c['_selected'] = None
            else:
                values = re.compile('[\w\-:]+').findall(str(self['value']))
                for c in self.components:
                    if self['value'] and str(c['_value']) in values:
                        c['_selected'] = 'selected'
                    else:
                        c['_selected'] = None


class FIELDSET(DIV):

    tag = 'fieldset'


class LEGEND(DIV):

    tag = 'legend'


class FORM(DIV):

    """
    example::

        >>> form=FORM(INPUT(_name=\"test\", requires=IS_NOT_EMPTY()))
        >>> form.xml()
        '<form action=\"\" enctype=\"multipart/form-data\" method=\"post\"><input name=\"test\" type=\"text\" /></form>'

    a FORM is container for INPUT, TEXTAREA, SELECT and other helpers

    form has one important method::

        form.accepts(request.vars, session)

    if form is accepted (and all validators pass) form.vars contains the
    accepted vars, otherwise form.errors contains the errors.
    in case of errors the form is modified to present the errors to the user.
    """

    tag = 'form'

    def __init__(self, *components, **attributes):
        if self.tag[-1:] == '/' and components:
            raise SyntaxError, '<%s> tags cannot have components' % self.tag
        if len(components) == 1 and isinstance(components[0], (list,
                tuple)):
            self.components = list(components[0])
        else:
            self.components = list(components)
        self.attributes = attributes
        self._fixup()
        # converts special attributes in components attributes
        self._postprocessing()
        self.vars = Storage()
        self.errors = Storage()
        self.latest = Storage()

    def accepts(
        self,
        vars,
        session=None,
        formname='default',
        keepvalues=False,
        onvalidation=None,
        ):
        self.errors.clear()
        self.request_vars = Storage()
        self.request_vars.update(vars)
        self.session = session
        self.formname = formname
        self.keepvalues = keepvalues

        # if this tag is a form and we are in accepting mode (status=True)
        # check formname and formkey

        status = True
        if self.session and self.session.get('_formkey[%s]'
                 % self.formname, None) != self.request_vars._formkey:
            status = False
        if self.formname != self.request_vars._formname:
            status = False
        status = self._traverse(status)
        if status and onvalidation:
            onvalidation(self)
        if self.errors:
            status = False
        if session != None:
            self.formkey = session['_formkey[%s]' % formname] = web2py_uuid()
        if status and not keepvalues:
            self._traverse(False)
        return status

    def _postprocessing(self):
        if not '_action' in self.attributes:
            self['_action'] = ''
        if not '_method' in self.attributes:
            self['_method'] = 'post'
        if not '_enctype' in self.attributes:
            self['_enctype'] = 'multipart/form-data'

    def hidden_fields(self):
        c = []
        if 'hidden' in self.attributes:
            for (key, value) in self.attributes.get('hidden',
                    {}).items():
                c.append(INPUT(_type='hidden', _name=key, _value=value))
        if hasattr(self, 'formkey') and self.formkey:
            c.append(INPUT(_type='hidden', _name='_formkey',
                     _value=self.formkey))
        if hasattr(self, 'formname') and self.formname:
            c.append(INPUT(_type='hidden', _name='_formname',
                     _value=self.formname))
        return DIV(c, _class="hidden")

    def xml(self):
        newform = FORM(*self.components, **self.attributes)
        hidden_fields = self.hidden_fields()
        if hidden_fields.components:
            newform.append(hidden_fields)
        return DIV.xml(newform)


class BEAUTIFY(DIV):

    """
    example::

        >>> BEAUTIFY(['a', 'b', {'hello': 'world'}]).xml()
        '<div><table><tr><td><div>a</div></td></tr><tr><td><div>b</div></td></tr><tr><td><div><table><tr><td style="font-weight:bold;"><div>hello</div></td><td valign="top">:</td><td><div>world</div></td></tr></table></div></td></tr></table></div>'

    turns any list, dictionary, etc into decent looking html.
    Two special attributes are 
    :sorted: a function that takes the dict and returned sorted keys
    :keyfilter: a funciton that takes a key and returns its representation
                or None if the key is to be skipped. By default key[:1]=='_' is skipped.
    """

    tag = 'div'

    @staticmethod
    def no_underscore(key):
        if key[:1]=='_':
            return None
        return key

    def __init__(self, component, **attributes):
        self.components = [component]
        self.attributes = attributes
        sorter = attributes.get('sorted',sorted)
        keyfilter = attributes.get('keyfilter',BEAUTIFY.no_underscore)
        components = []
        attributes = copy.copy(self.attributes)
        level = attributes['level'] = attributes.get('level',6) - 1
        if '_class' in attributes:
            attributes['_class'] += 'i'
        if level == 0:
            return
        for c in self.components:            
            if hasattr(c,'xml') and callable(c.xml):
                components.append(c)
                continue
            elif hasattr(c,'keys') and callable(c.keys):
                rows = []
                try:                    
                    keys = (sorter and sorter(c)) or c
                    for key in keys:
                        if isinstance(key,(str,unicode)) and keyfilter:
                            filtered_key = keyfilter(key)
                        else:
                            filtered_key = str(key)
                        if filtered_key == None:
                            continue
                        value = c[key]
                        if type(value) == types.LambdaType:
                            continue
                        rows.append(TR(TD(filtered_key, _style='font-weight:bold;'), 
                                       TD(':',_valign='top'),
                                       TD(BEAUTIFY(value, **attributes))))
                    components.append(TABLE(*rows, **attributes))
                    continue
                except:
                    pass
            if isinstance(c, str):
                components.append(str(c))
            elif isinstance(c, unicode):
                components.append(c.encode('utf8'))
            elif isinstance(c, (list, tuple)):
                items = [TR(TD(BEAUTIFY(item, **attributes)))
                         for item in c]
                components.append(TABLE(*items, **attributes))
            elif isinstance(c, cgi.FieldStorage):
                components.append('FieldStorage object')
            else:
                components.append(repr(c))
        self.components = components


class MENU(DIV):
    """
    Used to build menus

    Optional arguments
      _class: defaults to 'web2py-menu web2py-menu-vertical'
      ul_class: defaults to 'web2py-menu-vertical'
      li_class: defaults to 'web2py-menu-expand'

    Example:
        menu = MENU([['name', False, URL(...), [submenu]], ...])
        {{=menu}}
    """

    tag = 'ul'

    def __init__(self, data, **args):
        self.data = data
        self.attributes = args
        if not '_class' in self.attributes:
            self['_class'] = 'web2py-menu web2py-menu-vertical'
        if not 'ul_class' in self.attributes:
            self['ul_class'] = 'web2py-menu-vertical'
        if not 'li_class' in self.attributes:
            self['li_class'] = 'web2py-menu-expand'
        if not 'li_active' in self.attributes:
            self['li_active'] = 'web2py-menu-active'

    def serialize(self, data, level=0):
        if level == 0:
            ul = UL(**self.attributes)
        else:
            ul = UL(_class=self['ul_class'])
        for item in data:
            (name, active, link) = item[:3]
            if link:
                li = LI(A(name, _href=link))
            else:
                li = LI(A(name, _href='#null'))
            if len(item) > 3 and item[3]:
                li['_class'] = self['li_class']
                li.append(self.serialize(item[3], level+1))
            if active:
                if li['_class']:
                    li['_class'] = li['_class']+' '+self['li_active']
                else:
                    li['_class'] = self['li_active']
            ul.append(li)
        return ul

    def xml(self):
        return self.serialize(self.data, 0).xml()


def embed64(
    filename = None,
    file = None,
    data = None,
    extension = 'image/gif',
    ):
    """
    helper to encode the provided (binary) data into base64.

    :param filename: if provided, opens and reads this file in 'rb' mode
    :param file: if provided, reads this file
    :param data: if provided, uses the provided data
    """

    if filename and os.path.exists(file):
        fp = open(filename, 'rb')
        data = fp.read()
        fp.close()
    data = base64.b64encode(data)
    return 'data:%s;base64,%s' % (extension, data)


def test():
    """
    Example:

    >>> from validators import *
    >>> print DIV(A('click me', _href=URL(a='a', c='b', f='c')), BR(), HR(), DIV(SPAN(\"World\"), _class='unknown')).xml()
    <div><a href=\"/a/b/c\">click me</a><br /><hr /><div class=\"unknown\"><span>World</span></div></div>
    >>> print DIV(UL(\"doc\",\"cat\",\"mouse\")).xml()
    <div><ul><li>doc</li><li>cat</li><li>mouse</li></ul></div>
    >>> print DIV(UL(\"doc\", LI(\"cat\", _class='feline'), 18)).xml()
    <div><ul><li>doc</li><li class=\"feline\">cat</li><li>18</li></ul></div>
    >>> print TABLE(['a', 'b', 'c'], TR('d', 'e', 'f'), TR(TD(1), TD(2), TD(3))).xml()
    <table><tr><td>a</td><td>b</td><td>c</td></tr><tr><td>d</td><td>e</td><td>f</td></tr><tr><td>1</td><td>2</td><td>3</td></tr></table>
    >>> form=FORM(INPUT(_type='text', _name='myvar', requires=IS_EXPR('int(value)<10')))
    >>> print form.xml()
    <form action=\"\" enctype=\"multipart/form-data\" method=\"post\"><input name=\"myvar\" type=\"text\" /></form>
    >>> print form.accepts({'myvar':'34'}, formname=None)
    False
    >>> print form.xml()
    <form action="" enctype="multipart/form-data" method="post"><input name="myvar" type="text" value="34" /><div class="error" id="myvar__error">invalid expression</div></form>
    >>> print form.accepts({'myvar':'4'}, formname=None, keepvalues=True)
    True
    >>> print form.xml()
    <form action=\"\" enctype=\"multipart/form-data\" method=\"post\"><input name=\"myvar\" type=\"text\" value=\"4\" /></form>
    >>> form=FORM(SELECT('cat', 'dog', _name='myvar'))
    >>> print form.accepts({'myvar':'dog'}, formname=None, keepvalues=True)
    True
    >>> print form.xml()
    <form action=\"\" enctype=\"multipart/form-data\" method=\"post\"><select name=\"myvar\"><option value=\"cat\">cat</option><option selected=\"selected\" value=\"dog\">dog</option></select></form>
    >>> form=FORM(INPUT(_type='text', _name='myvar', requires=IS_MATCH('^\w+$', 'only alphanumeric!')))
    >>> print form.accepts({'myvar':'as df'}, formname=None)
    False
    >>> print form.xml()
    <form action=\"\" enctype=\"multipart/form-data\" method=\"post\"><input name=\"myvar\" type=\"text\" value=\"as df\" /><div class=\"error\" id=\"myvar__error\">only alphanumeric!</div></form>
    >>> session={}
    >>> form=FORM(INPUT(value=\"Hello World\", _name=\"var\", requires=IS_MATCH('^\w+$')))
    >>> if form.accepts({}, session,formname=None): print 'passed'
    >>> if form.accepts({'var':'test ', '_formkey': session['_formkey[None]']}, session, formname=None): print 'passed'
    """

    pass


if __name__ == '__main__':
    import doctest
    doctest.testmod()
