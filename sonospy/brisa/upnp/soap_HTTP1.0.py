# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>
#
# Copyright 2001 - Cayce Ullman <http://pywebsvcs.sourceforge.net>
# Copyright 2001 - Brian Matthews <http://pywebsvcs.sourceforge.net>
# Copyright 2001-2003 - Pfizer <http://pywebsvcs.sourceforge.net>
# Copyright 2007-2008 - Frank Scholz <coherence@beebits.net>

""" Parses and builds SOAP calls transparently.
"""

import log

import httplib
import exceptions

from xml.etree import ElementTree

from brisa.core.network import parse_xml, parse_url

from xml.dom import minidom
from xml.dom.minidom import parseString


# SOAP constants


NS_SOAP_ENV = "{http://schemas.xmlsoap.org/soap/envelope/}"
NS_SOAP_ENC = "{http://schemas.xmlsoap.org/soap/encoding/}"
NS_XSI = "{http://www.w3.org/1999/XMLSchema-instance}"
NS_XSD = "{http://www.w3.org/1999/XMLSchema}"

SOAP_ENCODING = "http://schemas.xmlsoap.org/soap/encoding/"

UPNPERRORS = {401: 'Invalid Action',
              402: 'Invalid Args',
              501: 'Action Failed',
              600: 'Argument Value Invalid',
              601: 'Argument Value Out of Range',
              602: 'Optional Action Not Implemented',
              603: 'Out Of Memory',
              604: 'Human Intervention Required',
              605: 'String Argument Too Long',
              606: 'Action Not Authorized',
              607: 'Signature Failure',
              608: 'Signature Missing',
              609: 'Not Encrypted',
              610: 'Invalid Sequence',
              611: 'Invalid Control URL',
              612: 'No Such Session',
              720: 'Cannot process the request', }


def build_soap_error(status, description='without words'):
    """ Builds an UPnP SOAP error message.

    @param status: error code
    @param description: error default description

    @type status: integer
    @type description: string

    @return: soap call representing the error
    @rtype: string
    """
    root = ElementTree.Element('s:Fault')
    ElementTree.SubElement(root, 'faultcode').text = 's:Client'
    ElementTree.SubElement(root, 'faultstring').text = 'UPnPError'
    e = ElementTree.SubElement(root, 'detail')
    e = ElementTree.SubElement(e, 'UPnPError')
    e.attrib['xmlns'] = 'urn:schemas-upnp-org:control-1-0'
    ElementTree.SubElement(e, 'errorCode').text = str(status)
    ElementTree.SubElement(e, 'errorDescription').text = UPNPERRORS.get(status,
                                                                   description)
    return build_soap_call(None, root, encoding=None)


def build_soap_call(method, arguments, encoding=SOAP_ENCODING,
                    envelope_attrib=None, typed=None):
    """ Builds a soap call.

    @param method: method for the soap call. If set to None, the method element
    will be omitted and arguments will be added directly to the body (error
    message)
    @param arguments: arguments for the call
    @param encoding: encoding for the call
    @param envelope_attrib: envelope attribute
    @param typed: True if typed

    @type method: string or None
    @type arguments: dict or ElementTree.Element
    @type encoding: string
    @type envelope_attrib: list
    @type typed: boolean or None

    @return: soap call
    @rtype: string
    """
    envelope = ElementTree.Element("s:Envelope")
    if envelope_attrib:
        for n in envelope_attrib:
            envelope.attrib.update({n[0]: n[1]})
    else:
        envelope.attrib.update({'s:encodingStyle':
                                "http://schemas.xmlsoap.org/soap/encoding/"})
        envelope.attrib.update({'xmlns:s':
                                "http://schemas.xmlsoap.org/soap/envelope/"})

    body = ElementTree.SubElement(envelope, "s:Body")

    if method:
        re = ElementTree.SubElement(body, method)
        if encoding:
            re.set("%sencodingStyle" % NS_SOAP_ENV, encoding)
    else:
        re = body

    # append the arguments
    if isinstance(arguments, dict):
        type_map = {str: 'xsd:string',
                    unicode: 'xsd:string',
                    int: 'xsd:int',
                    long: 'xsd:int',
                    float: 'xsd:float',
                    bool: 'xsd:boolean'}

        for arg_name, arg_val in arguments.iteritems():
            arg_type = type_map[type(arg_val)]
            if arg_type == 'xsd:string' and type(arg_val) == unicode:
                arg_val = arg_val.encode('utf-8')
            if arg_type == 'xsd:int' or arg_type == 'xsd:float':
                arg_val = str(arg_val)
            if arg_type == 'xsd:boolean':
                arg_val = '1' if arg_val else '0'

            e = ElementTree.SubElement(re, arg_name)
            if typed and arg_type:
                if not isinstance(type, ElementTree.QName):
                    arg_type = ElementTree.QName(
                                "http://www.w3.org/1999/XMLSchema", arg_type)
                e.set('%stype' % NS_XSI, arg_type)
            e.text = arg_val
    else:
        re.append(arguments)

    preamble = """<?xml version="1.0" encoding="utf-8"?>"""
    return '%s%s' % (preamble, ElementTree.tostring(envelope, 'utf-8'))


def build_soap_call_file(method, arguments, encoding=SOAP_ENCODING,
                    envelope_attrib=None, typed=None):
    """ Builds a soap call.

    @param method: method for the soap call. If set to None, the method element
    will be omitted and arguments will be added directly to the body (error
    message)
    @param arguments: arguments for the call
    @param encoding: encoding for the call
    @param envelope_attrib: envelope attribute
    @param typed: True if typed

    @type method: string or None
    @type arguments: dict or ElementTree.Element
    @type encoding: string
    @type envelope_attrib: list
    @type typed: boolean or None

    @return: soap call
    @rtype: string
    """
    
    envelope = ElementTree.Element("s:Envelope")
    if envelope_attrib:
        for n in envelope_attrib:
            envelope.attrib.update({n[0]: n[1]})
    else:
#        envelope.attrib.update({'s:encodingStyle':
#                                "http://schemas.xmlsoap.org/soap/encoding/"})
        envelope.attrib.update({'xmlns:s':
                                "http://schemas.xmlsoap.org/soap/envelope/"})

    '''
            <s:Header>
                <credentials xmlns="http://www.sonos.com/Services/1.1">
                    <deviceProvider>Sonos</deviceProvider>
                </credentials>
            </s:Header>
    '''
    header = ElementTree.SubElement(envelope, "s:Header")
    credentials = ElementTree.SubElement(header, 'credentials')
    credentials.attrib.update({'xmlns': "http://www.sonos.com/Services/1.1"})
    deviceProvider = ElementTree.SubElement(credentials, "deviceProvider")
    deviceProvider.text = 'Sonos'

    body = ElementTree.SubElement(envelope, "s:Body")

    if method:
        # RadioTime does not appear to cater for a namespace prefix on the method name
        # (note that it returns the default response for a call it can't process, so for getMetadata it returns the root metadata)

        if method.startswith('{') and method.rfind('}') > 1:
            ns, method_name = method[1:].split('}')
        else:
            ns = None
            method_name = method
        
        re = ElementTree.SubElement(body, method_name)
        if ns:
            re.attrib.update({'xmlns': ns})
        
        if encoding:
            re.set("%sencodingStyle" % NS_SOAP_ENV, encoding)
    else:
        re = body

#    print "~~~~~~~~~~~~~~~~~~~~~~~~"                        
#    print "~~~~~~~~~~~~~~~~~~~~~~~~"                        
#    print "method"
#    print method
   
#    print "~~~~~~~~~~~~~~~~~~~~~~~~"                        
#    print "~~~~~~~~~~~~~~~~~~~~~~~~"                        
#    print "arguments"
#    print arguments
    
    if isinstance(arguments, dict):
        type_map = {str: 'xsd:string',
                    unicode: 'xsd:string',
                    int: 'xsd:int',
                    long: 'xsd:int',
                    float: 'xsd:float',
                    bool: 'xsd:boolean'}

#        if method == '{http://www.sonos.com/Services/1.1}getMetadata':
#            order = ['id', 'index', 'count', 'recursive']
#        else:
#            order = arguments.keys()
#        for arg_name in order:
        for arg_name, arg_val in arguments.iteritems():
        
            if arg_name in arguments:
        
                arg_val = arguments[arg_name]

                arg_type = type_map[type(arg_val)]
                if arg_type == 'xsd:string' and type(arg_val) == unicode:
                    arg_val = arg_val.encode('utf-8')
                if arg_type == 'xsd:int' or arg_type == 'xsd:float':
                    arg_val = str(arg_val)
                if arg_type == 'xsd:boolean':
                    arg_val = '1' if arg_val else '0'

                e = ElementTree.SubElement(re, arg_name)
                if typed and arg_type:
                    if not isinstance(type, ElementTree.QName):
                        arg_type = ElementTree.QName(
                                    "http://www.w3.org/1999/XMLSchema", arg_type)
                    e.set('%stype' % NS_XSI, arg_type)
                e.text = arg_val

    else:
        re.append(arguments)

#    preamble = """<?xml version="1.0" encoding="utf-8"?>"""
    preamble = ""
#TODO: CHANGE THIS BACK?
    
    return '%s%s' % (preamble, ElementTree.tostring(envelope, 'utf-8'))


def __decode_result(element):
    """ Decodes the result out of an Element. Returns the text, if possible.

    @param element: element to decode the result
    @type element Element

    @return: text of the result
    @rtype: string
    """
#    print "element"
#    print element
    type = element.get('{http://www.w3.org/1999/XMLSchema-instance}type')
#    print "type"
#    print type
    if type is not None:
        try:
            prefix, local = type.split(":")
            if prefix == 'xsd':
                type = local
        except ValueError:
            pass
            
#    print "element.text: " + str(element.text)
#    print "element.attrib: " + str(element.attrib)
    c = element.getchildren()
#    print "element.children: " + str(c)
#    if c:
#        print c[0]
    
    if type == "integer" or type == "int":
        return int(element.text)
    if type == "float" or type == "double":
        return float(element.text)
    if type == "boolean":
        return element.text == "true"

    return element.text or ""


def __decode_result_file(element):
    """ Decodes the result out of an Element. Returns the text, if possible.

    @param element: element to decode the result
    @type element Element

    @return: text of the result
    @rtype: string
    """
#    print "element"
#    print element
    type = element.get('{http://www.w3.org/1999/XMLSchema-instance}type')
#    print "type"
#    print type
    if type is not None:
        try:
            prefix, local = type.split(":")
            if prefix == 'xsd':
                type = local
        except ValueError:
            pass
            
#    print "element.text: " + str(element.text)
#    print "element.attrib: " + str(element.attrib)
    c = element.getchildren()
#    print "element.children: " + str(c)
    if c:

#        args = []

        result = ElementTree.Element("Result")

        kwargs = {}
        for child in c:

#            print "child: " + str(child)
#            print "child.tag: " + str(child.tag)
#            print "child.text: " + str(child.text)
#            print "child.attrib: " + str(child.attrib)
            if child.text == None:
                
                entry = ElementTree.SubElement(result, child.tag)
                entry.text = ElementTree.tostring(child)
            
#                kwargs[child.tag] = child
            else:
                kwargs[child.tag] = child.text
#            args.append(kwargs[child.tag])

        kwargs["Result"] = result

#        log.debug('#### result--->\n%s', minidom.parseString(result).toprettyxml())

#        log.debug('#### result--->\n%s', result.dump())

        return kwargs

    if type == "integer" or type == "int":
        return int(element.text)
    if type == "float" or type == "double":
        return float(element.text)
    if type == "boolean":
        return element.text == "true"

    return element.text or ""


def parse_soap_call(data):
    """ Parses a soap call and returns a 4-tuple.

    @param data: raw soap XML call data
    @type data: string

    @return: 4-tuple (method_name, args, kwargs, namespace)
    @rtype: tuple
    """
    tree = parse_xml(data)
    body = tree.find('{http://schemas.xmlsoap.org/soap/envelope/}Body')
    method = body.getchildren()[0]
    
    method_name = method.tag
    ns = None

    if method_name.startswith('{') and method_name.rfind('}') > 1:
        ns, method_name = method_name[1:].split('}')

#    print "ns, method"
#    print ns
#    print method

    args = []
    kwargs = {}
    for child in method.getchildren():

#        print "child"
#        print child
#        print child.tag
        kwargs[child.tag] = __decode_result(child)
        args.append(kwargs[child.tag])

    return method_name, args, kwargs, ns


def parse_soap_call_file(data):
    """ Parses a soap call and returns a 4-tuple.

    @param data: raw soap XML call data
    @type data: string

    @return: 4-tuple (method_name, args, kwargs, namespace)
    @rtype: tuple
    """
    tree = parse_xml(data)
    body = tree.find('{http://schemas.xmlsoap.org/soap/envelope/}Body')
    method = body.getchildren()[0]
    
    method_name = method.tag
    ns = None

    if method_name.startswith('{') and method_name.rfind('}') > 1:
        ns, method_name = method_name[1:].split('}')

#    print "ns, method"
#    print ns
#    print method

    args = []
    kwargs = {}
    for child in method.getchildren():

#        print "child"
#        print child
#        print child.tag
#        kwargs[child.tag] = __decode_result_file(child)
        res = __decode_result_file(child)
#        args.append(kwargs[child.tag])

#    return method_name, args, kwargs, ns
    return method_name, args, res, ns


def parse_soap_fault(data):
    """ Parses a soap call and returns a 4-tuple.

    @param data: raw soap XML call data
    @type data: string

    @return: 4-tuple (method_name, args, kwargs, namespace)
    @rtype: tuple
    """
    tree = parse_xml(data)
    body = tree.find('{http://schemas.xmlsoap.org/soap/envelope/}Body')
    method = body.getchildren()[0]
    
    method_name = method.tag
    ns = None

    if method_name.startswith('{') and method_name.rfind('}') > 1:
        ns, method_name = method_name[1:].split('}')

    args = []
    kwargs = {}
    for child in method.getchildren():

        kwargs[child.tag] = __decode_result(child)

        if child.tag == 'detail':
            UPnPError = child.find('{urn:schemas-upnp-org:control-1-0}UPnPError')
            errorCode = UPnPError.find('{urn:schemas-upnp-org:control-1-0}errorCode')
            errorCodeText = errorCode.text
            errorCode = int(errorCodeText)
            errorDescription = UPNPERRORS.get(errorCode, '')
            kwargs[child.tag] = errorCodeText + " - " + errorDescription
            
        args.append(kwargs[child.tag])

    return method_name, args, kwargs, ns


class SOAPProxy(object):
    """ Proxy for making remote SOAP calls Based on twisted.web.soap.Proxy
    and SOAPpy.
    """

    def __init__(self, url, namespace=None):
        """ Constructor for the SOAPProxy class.

        @param url: remote SOAP server
        @param namespace: calls namespace

        @type url: string
        @type namespace: tuple
        """
        self.url = url
        self.namespace = namespace

    def call_remote(self, soapmethod, **kwargs):
        """ Performs a remote SOAP call.

        @param soapmethod: method to be called
        @param kwargs: args to be passed, can be named.

        @type soapmethod: string
        @type kwargs: dictionary

        @return: the result text of the soap call.
        @rtype: string
        """
        ns = self.namespace
        soapaction = '%s#%s' % (ns[1], soapmethod)
        payload = build_soap_call('{%s}%s' % (ns[1], soapmethod),
                                  kwargs, encoding=None)

        log.debug('#### SOAPProxy #########################################')
        log.debug('#### SOAP BEFORE START #################################')
        log.debug('#### SOAP self.url     : %s' % str(self.url))
        log.debug('#### SOAP payload      : %s' % str(payload))
        log.debug('#### SOAP ns           : %s' % str(ns))
        log.debug('#### SOAP soapaction   : %s' % str(soapaction))
        log.debug('#### SOAP BEFORE END ###################################')

        result = HTTPTransport().call(self.url, payload, ns,
                                      soapaction=soapaction, encoding='utf-8')
                                      
        log.debug('#### SOAP AFTER START ##################################')

        newdata = result.replace("&amp;","&")
        newdata = newdata.replace("&amp;","&")
        newdata = newdata.replace("&amp;","&")
        newdata = newdata.replace("&amp;","&")
        newdata = newdata.replace("&amp;","&")
        newdata = newdata.replace("&quot;","\"")
        newdata = newdata.replace("&lt;","<")
        newdata = newdata.replace("&gt;",">")
#        newdata = newdata.replace("&","&amp;")

        print newdata
#        log.debug('#### soap result--->\n%s', minidom.parseString(newdata).toprettyxml())
        log.debug('#### soap result--->\n%s', minidom.parseString(result).toprettyxml())
        log.debug('#### SOAP AFTER END ####################################')

#        _, _, res, _ = parse_soap_call(result)
        a, b, res, d = parse_soap_call(result)

        if a == 'Fault':
            a, b, res, d = parse_soap_fault(result)

        return res


class SOAPProxyFile(object):
    """ Proxy for making remote SOAP calls Based on twisted.web.soap.Proxy
    and SOAPpy.
    """

    def __init__(self, url, namespace=None):
        """ Constructor for the SOAPProxy class.

        @param url: remote SOAP server
        @param namespace: calls namespace

        @type url: string
        @type namespace: tuple
        """
        self.url = url
        self.namespace = namespace

    def call_remote(self, soapmethod, **kwargs):
        """ Performs a remote SOAP call.

        @param soapmethod: method to be called
        @param kwargs: args to be passed, can be named.

        @type soapmethod: string
        @type kwargs: dictionary

        @return: the result text of the soap call.
        @rtype: string
        """
        

        ns = self.namespace
        soapaction = '%s#%s' % (ns[1], soapmethod)
        payload = build_soap_call_file('{%s}%s' % (ns[1], soapmethod), kwargs, encoding=None)

        log.debug('#### SOAPProxyFile #####################################')
        log.debug('#### SOAP BEFORE START #################################')
        log.debug('#### SOAP self.url     : %s' % str(self.url))
        log.debug('#### SOAP payload      : %s' % str(payload))
        log.debug('#### SOAP ns           : %s' % str(ns))
        log.debug('#### SOAP soapaction   : %s' % str(soapaction))
        log.debug('#### SOAP BEFORE END ###################################')

        result = HTTPTransportFile().call(self.url, payload, ns,
                                      soapaction=soapaction, encoding='utf-8')
                                      
        log.debug('#### SOAP AFTER START ##################################')

        newdata = result.replace("&amp;","&")
        newdata = newdata.replace("&amp;","&")
        newdata = newdata.replace("&amp;","&")
        newdata = newdata.replace("&quot;","\"")
        newdata = newdata.replace("&lt;","<")
        newdata = newdata.replace("&gt;",">")
        newdata = newdata.replace("&","&amp;")

        log.debug('#### soap result--->\n%s', minidom.parseString(newdata).toprettyxml())
        log.debug('#### SOAP AFTER END ####################################')

#        _, _, res, _ = parse_soap_call_file(result)
        a, b, res, d = parse_soap_call_file(result)

        log.debug('#### soap a--->\n%s', a)
        log.debug('#### soap b--->\n%s', b)
        log.debug('#### soap res--->\n%s', res)
        log.debug('#### soap d--->\n%s', d)



        if a == 'Fault':
            a, b, res, d = parse_soap_fault(result)

        return res


class HTTPTransport(object):
    """ Wrapper class for a HTTP SOAP call. It contain the call() method that
    can perform calls and return the response payload.
    """

    def call(self, addr, data, namespace, soapaction=None, encoding=None):
        """ Builds and performs an HTTP request. Returns the response payload.

        @param addr: address to receive the request in the form
        schema://hostname:port
        @param data: data to be sent
        @param soapaction: soap action to be called
        @param encoding: encoding for the message

        @type addr: string
        @type data: string
        @type soapaction: string
        @type encoding: string

        @return: response payload
        @rtype: string
        """

        log.debug('#### HTTPTransport call - addr : %s' % str(addr))
        log.debug('#### HTTPTransport call - data : %s' % str(data))
        log.debug('#### HTTPTransport call - namespace : %s' % str(namespace))
        log.debug('#### HTTPTransport call - soapaction : %s' % str(soapaction))
        log.debug('#### HTTPTransport call - encoding : %s' % str(encoding))

        # Build a request
        addr = parse_url(addr)
        real_addr = '%s:%d' % (addr.hostname, addr.port)
        real_path = addr.path

        if addr.scheme == 'https':
            r = httplib.HTTPS(real_addr)
        else:
            r = httplib.HTTP(real_addr)

        log.debug('#### HTTPTransport call - real_addr : %s' % real_addr)
        log.debug('#### HTTPTransport call - real_path : %s' % real_path)
        log.debug('#### HTTPTransport call - addr.scheme : %s' % addr.scheme)
        log.debug('#### HTTPTransport call - addr.hostname : %s' % addr.hostname)

        r.putrequest("POST", real_path)
        r.putheader("Host", addr.hostname)
        r.putheader("User-agent", 'BRISA SERVER')
        t = 'text/xml'
        if encoding:
            t += '; charset="%s"' % encoding
        r.putheader("Content-type", t)
        r.putheader("Content-length", str(len(data)))

        # if user is not a user:passwd format
        if addr.username != None:
            val = base64.encodestring(addr.user)
            r.putheader('Authorization', 'Basic ' + val.replace('\012', ''))

        # This fixes sending either "" or "None"
        if soapaction:
            r.putheader("SOAPAction", '"%s"' % soapaction)
        else:
            r.putheader("SOAPAction", "")

        r.endheaders()

        log.debug('#### HTTP BEFORE r.send ################################')

        r.send(data)

        log.debug('#### HTTP AFTER r.send ################################')

        #read response line
        code, msg, headers = r.getreply()

        log.debug('#### HTTP AFTER START #################################')
        log.debug('#### HTTP code        : %s' % str(code))
        log.debug('#### HTTP msg         : %s' % str(msg))
        log.debug('#### HTTP headers     : %s' % str(headers))
        log.debug('#### HTTP AFTER END ###################################')

        content_type = headers.get("content-type", "text/xml")
        content_length = headers.get("Content-length")
        if content_length == None:
            data = r.getfile().read()
            message_len = len(data)
        else:
            message_len = int(content_length)
            data = r.getfile().read(message_len)

        def startswith(string, val):
            return string[0:len(val)] == val


        if code == 500 and not \
               (startswith(content_type, "text/xml") and message_len > 0):
            raise HTTPError(code, msg)

        if code not in (200, 500):
            raise HTTPError(code, msg)

        #return response payload
        return data.decode('utf-8')


class HTTPTransportFile(object):
    """ Wrapper class for a HTTP SOAP call. It contain the call() method that
    can perform calls and return the response payload.
    """

    def call(self, addr, data, namespace, soapaction=None, encoding=None):
        """ Builds and performs an HTTP request. Returns the response payload.

        @param addr: address to receive the request in the form
        schema://hostname:port
        @param data: data to be sent
        @param soapaction: soap action to be called
        @param encoding: encoding for the message

        @type addr: string
        @type data: string
        @type soapaction: string
        @type encoding: string

        @return: response payload
        @rtype: string
        """

        log.debug('#### HTTPTransport call - addr : %s' % str(addr))
        log.debug('#### HTTPTransport call - data : %s' % str(data))
        log.debug('#### HTTPTransport call - namespace : %s' % str(namespace))
        log.debug('#### HTTPTransport call - soapaction : %s' % str(soapaction))
        log.debug('#### HTTPTransport call - encoding : %s' % str(encoding))

        # Build a request
        
        '''
        addr : http://legato.radiotime.com:80
        data : <?xml version="1.0" encoding="utf-8"?><s:Envelope s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Header><credentials xmlns="http://www.sonos.com/Services/1.1"><deviceProvider>Sonos</deviceProvider></credentials></s:Header><s:Body><ns0:getMetadata xmlns:ns0="http://www.sonos.com/Services/1.1"><count>100</count><index>0</index><recursive>false</recursive><id>root</id></ns0:getMetadata></s:Body></s:Envelope>
        namespace : ('u', 'http://www.sonos.com/Services/1.1')
        soapaction : http://www.sonos.com/Services/1.1#getMetadata
        encoding : utf-8
        real_addr : legato.radiotime.com:80
        real_path : 
        addr.scheme : http
        addr.hostname : legato.radiotime.com

        POST /Radio.asmx HTTP/1.1
        CONNECTION: close
        ACCEPT-ENCODING: gzip
        HOST: legato.radiotime.com
        USER-AGENT: Linux UPnP/1.0 Sonos/11.7-19141a
        CONTENT-LENGTH: 337
        CONTENT-TYPE: text/xml; charset="utf-8"
        ACCEPT-LANGUAGE: en-US
        SOAPACTION: "http://www.sonos.com/Services/1.1#getMetadata"
        '''
        # TODO: tidy up parameters, use saved params from musicservices call, change to gzip
        addr = parse_url(addr)
        real_addr = '%s:%d' % (addr.hostname, addr.port)
        real_path = addr.path

        if addr.scheme == 'https':
            r = httplib.HTTPSConnection(real_addr)
        else:
            r = httplib.HTTPConnection(real_addr)

        log.debug('#### HTTPTransport call - real_addr : %s' % real_addr)
        log.debug('#### HTTPTransport call - real_path : %s' % real_path)
        log.debug('#### HTTPTransport call - addr.scheme : %s' % addr.scheme)
        log.debug('#### HTTPTransport call - addr.hostname : %s' % addr.hostname)

        r.putrequest("POST", real_path, skip_host=1, skip_accept_encoding=1)
        
        r.putheader("ACCEPT-ENCODING", 'gzip')
        r.putheader("CONNECTION", 'close')

        r.putheader("HOST", addr.hostname)
        r.putheader("USER-AGENT", 'Linux UPnP/1.0 Sonos/11.7-19141a')
        t = 'text/xml'
#        if encoding:
#            t += '; charset="%s"' % encoding
            
            
        r.putheader("CONTENT-TYPE", t)
#        r.putheader("ACCEPT-CHARSET", 'ISO-8859-1,utf-8;q=0.7,*;q=0.7')
        r.putheader("ACCEPT-LANGUAGE", 'en-US')
        r.putheader("CONTENT-LENGTH", str(len(data)))


        # if user is not a user:passwd format
        if addr.username != None:
            val = base64.encodestring(addr.user)
            r.putheader('Authorization', 'Basic ' + val.replace('\012', ''))

        # This fixes sending either "" or "None"
        if soapaction:
            r.putheader("SOAPACTION", '"%s"' % soapaction)
        else:
            r.putheader("SOAPACTION", "")

        r.endheaders()

        log.debug('#### HTTP BEFORE r.send ################################')

        r.send(data)

        log.debug('#### HTTP AFTER r.send ################################')

        #read response line
#        code, msg, headers = r.getreply()
        response = r.getresponse()
        code = response.status
        msg = response.reason
        headers = response.msg

        log.debug('#### HTTP AFTER START #################################')
        log.debug('#### HTTP code        : %s' % str(code))
        log.debug('#### HTTP msg         : %s' % str(msg))
        log.debug('#### HTTP headers     : %s' % str(headers))
        log.debug('#### HTTP AFTER END ###################################')

        content_type = headers.get("content-type", "text/xml")
        content_length = headers.get("Content-length")
        if content_length == None:
#            data = r.getfile().read()
            data = response.read()
            message_len = len(data)
        else:
            message_len = int(content_length)
#            data = r.getfile().read(message_len)
            data = response.read(message_len)

        def startswith(string, val):
            return string[0:len(val)] == val


        if code == 500 and not \
               (startswith(content_type, "text/xml") and message_len > 0):
            raise HTTPError(code, msg)

        if code not in (200, 500):
            raise HTTPError(code, msg)

        #return response payload
#        return data.decode('utf-8')

        import StringIO
        stream = StringIO.StringIO(data)
        import gzip
        gzipper = gzip.GzipFile(fileobj=stream)
        data = gzipper.read()


        return data


class HTTPError(exceptions.Exception):
    """ Represents an error of a HTTP request.
    """

    def __init__(self, code, msg):
        """ Constructor for the HTTPError class.

        @param code: error code
        @param msg: error message

        @type code: string
        @type msg: string
        """
        self.code = code
        self.msg = msg

    def __repr__(self):
        return "<HTTPError %s %s>" % (self.code, self.msg)

    def __call___(self):
        return (self.code, self.msg, )
