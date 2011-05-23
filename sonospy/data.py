import os
from brisa.core import webserver
from brisa.core import log
from xml.sax.saxutils import unescape

unescape_entities = {
                   '%20'   : " ",
                   '%21'   : "!",
                   '%22'   : '"',
                   '%23'   : "#",
                   '%24'   : "$",
#                   '%25'   : "%",
                   '%26'   : "&",
                   '%27'   : "'",
                   '%28'   : "(",
                   '%29'   : ")",
                   '%2A'   : "*",
                   '%2B'   : "+",
                   '%2C'   : ",",
                   '%2D'   : "-",
                   '%2E'   : ".",
                   '%2F'   : "/",
                   '%3A'   : ":",
                   '%3B'   : ";",
                   '%3C'   : "<",
                   '%3D'   : "=",
                   '%3E'   : ">",
                   '%3F'   : "?",
                   '%40'   : "@",
                   '%5B'   : "[",
                   '%5C'   : "\\",
                   '%5D'   : "]",
                   '%5E'   : "^",
                   '%5F'   : "_",
                   '%7B'   : "{",
                   '%7C'   : "|",
                   '%7D'   : "}",
                   '%7E'   : "~",
                  }

class ListDataController(webserver.CustomResource):

    def __init__(self, data, name):
        self.data = data
        webserver.CustomResource.__init__(self, name)

    def render(self, uri, request, response):
        response.status = 200
        response.body = make_utf8(self.data)
        return response.body

class GetDataController(webserver.CustomResource):

    def __init__(self, data, name, getter):
        self.data = data
        self.getter = getter
        webserver.CustomResource.__init__(self, name)

    def render(self, uri, request, response):
#        print "GetDataController"
#        print "request.query: " + str(request.query)
#        print "data: " + str(self.data)
        query = unescape(request.query, unescape_entities)
        self.data = self.getter(query)
        response.body = make_utf8(self.data)
        response.status = 200
        return response.body

class PlayController(webserver.CustomResource):

    def __init__(self, name, setter):
        self.setter = setter
        webserver.CustomResource.__init__(self, name)

    def render(self, uri, request, response):
#        print "request.query: " + str(request.query)
        query = unescape(request.query, unescape_entities)
        ret = self.setter(query)
        response.status = 200
        response.body = make_utf8(ret)
        return response.body

class GetDeviceController(webserver.CustomResource):

    def __init__(self, data, name):
        self.data = data
        webserver.CustomResource.__init__(self, name)

    def render(self, uri, request, response):
        response.status = 200
        response.body = make_utf8(self.data)
        return response.body

class SetRendererController(webserver.CustomResource):

    def __init__(self, data, name, setter):
        self.data = data
        self.setter = setter
        webserver.CustomResource.__init__(self, name)

    def render(self, uri, request, response):
#        print "request.query: " + str(request.query)
        query = unescape(request.query, unescape_entities)
        self.data = self.setter(query)
        response.status = 200
        response.body = make_utf8(self.data)
        return response.body

class PollRendererController(webserver.CustomResource):

    def __init__(self, data, name, getter):
        self.data = data
        self.getter = getter
        webserver.CustomResource.__init__(self, name)

    def render(self, uri, request, response):
#        print "request.query: " + str(request.query)
        query = unescape(request.query, unescape_entities)
        self.data = self.getter(query)
        response.body = make_utf8(self.data)
        response.status = 200
        return response.body

class ActionRendererController(webserver.CustomResource):

    def __init__(self, data, name, setter):
        self.data = data
        self.setter = setter
        webserver.CustomResource.__init__(self, name)

    def render(self, uri, request, response):
#        print "request.query: " + str(request.query)
        query = unescape(request.query, unescape_entities)
        self.data = self.setter(query)
        response.status = 200
        response.body = make_utf8(self.data)
        return response.body

class PollServerController(webserver.CustomResource):

    def __init__(self, data, name, getter):
        self.data = data
        self.getter = getter
        webserver.CustomResource.__init__(self, name)

    def render(self, uri, request, response):
#        print "request.query: " + str(request.query)
        query = unescape(request.query, unescape_entities)
        self.data = self.getter(query)
        response.body = make_utf8(self.data)
        response.status = 200
        return response.body

class PollQueueController(webserver.CustomResource):

    def __init__(self, data, name, getter):
        self.data = data
        self.getter = getter
        webserver.CustomResource.__init__(self, name)

    def render(self, uri, request, response):
#        print "request.query: " + str(request.query)
        query = unescape(request.query, unescape_entities)
        self.data = self.getter(query)
        response.body = make_utf8(self.data)
        response.status = 200
        return response.body

def make_utf8(list):
    dt = []
    for e in list:
        if isinstance(e, str):
            # already in UTF-8
            dt.append(e)
        else:
            # unicode - convert to UTF-8
            dt.append(e.encode('utf-8'))
    return dt
