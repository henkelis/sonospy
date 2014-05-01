#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import sys
fenc = sys.getfilesystemencoding()
import os
import ConfigParser
import StringIO
import codecs
from optparse import OptionParser
import subprocess
import re
import urllib
from socket import *
if os.name != 'nt':
    import fcntl
from struct import pack
    
from brisa.core import log
from brisa.core.log import modcheck

def get_ip_address(ifname):
    try:
        s = socket(AF_INET, SOCK_DGRAM)
        ip = inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915, pack('256s', str(ifname[:15])))[20:24])
        return ip
    except:
        return gethostbyname(gethostname())

def get_active_ifaces():
    if os.name == 'nt':
        return [gethostbyname(gethostname())]
    else:
        try:
            rd = open('/proc/net/route').readlines()
        except (IOError, OSError):
            return [gethostbyname(gethostname())]
        net = [line.split('\t')[0:2] for line in rd]
        return [v[0] for v in net if v[1] == '00000000']    

active_ifaces = get_active_ifaces()
print "Active interfaces: %s" % active_ifaces
ip_address = get_ip_address(active_ifaces[0])
print "IP address: %s" % ip_address

def main():

    usage = "usage: %prog [options] arg"
    parser = OptionParser(usage)
    
    parser.add_option("-d", "--debug", action="store_true", dest="debug")
    
    parser.add_option("-i", "--invalidate", action="store_true", dest="invalidate", default=False)

    parser.add_option("-p", "--proxy", action="store_true", dest="proxy", default=False)

    parser.add_option("-s", "--smapi", action="store_true", dest="smapi", default=False)

    (options, args) = parser.parse_args()

    print "Options: %s" % options
    print "Args: %s" % args

    if options.debug:
        modcheck['all'] = True

    config = ConfigParser.ConfigParser()
    config.optionxform = str
    ini = ''
    f = codecs.open('pycpoint.ini', encoding=fenc)
    for line in f:
        ini += line
    config.readfp(StringIO.StringIO(ini))

    # get ports to use
    smapi_port = 50104
    wmp_internal_port = 10244
    try:
        smapi_port = int(config.get('INI', 'smapi_port'))
    except ConfigParser.NoOptionError:
        pass
    try:        
        wmp_internal_port = int(config.get('INI', 'wmp_internal_port'))
    except ConfigParser.NoOptionError:
        pass
    print "smapi_port: %s" % smapi_port
    print "wmp_internal_port: %s" % wmp_internal_port

    proxies = getrunning('proxy')
    services = getrunning('service')
    if not proxies and not services:
        print "\npycpoint is not running"
        exit(1)
    print "Proxies: %s" % proxies
    print "Services: %s" % services
    addresses = getproxyaddresses(proxies, wmp_internal_port)

    proxy_addresses = []
    service_addresses = []
    for r in range(0, len(proxies)):
        proxy_addresses += [(proxies[r], wmp_internal_port + r)]
    for r in range(0, len(services)):
        service_addresses += [(services[r], smapi_port + r)]
    print "Available proxy addresses: %s" % proxy_addresses
    print "Available service addresses: %s" % service_addresses

    if args:
        new_proxy_addresses = []
        for (proxy, port) in proxy_addresses:
            if proxy in args:
                new_proxy_addresses.append((proxy, port))
        proxy_addresses = new_proxy_addresses
        print "Selected proxy addresses: %s" % proxy_addresses
        new_service_addresses = []
        for (service, port) in service_addresses:
            if service in args:
                new_service_addresses.append((service, port))
        service_addresses = new_service_addresses
        print "Selected service addresses: %s" % service_addresses

    invalidate = '%i' % options.invalidate

    if not (options.proxy or options.smapi):
        print "\nnothing to do"

    if options.proxy:
        for (proxy, port) in proxy_addresses:
            print '**** proxy %s:' % proxy
            hostName = "%s:%s" % (ip_address, port)
            soapret = sendSOAP(hostName,
                               'urn:schemas-upnp-org:service:ContentDirectory:1',
                               '/ContentDirectory/control',
                               'ReloadIni',
                               {'Invalidate': invalidate})
            print soapret

    if options.smapi:
        for (service, port) in service_addresses:
            print '**** service %s:' % service
            hostName = "%s:%s" % (ip_address, port)
            soapret = sendSOAP(hostName,
                               'http://www.sonos.com/Services/1.1',
                               '/smapi/control',
                               'reloadIni',
                               {})
            print soapret
            if options.invalidate:
                soapret = sendSOAP(hostName,
                                   'http://www.sonos.com/Services/1.1',
                                   '/smapi/control',
                                   'invalidateCD',
                                   {})
                print soapret

    
def getrunning(rtype):

    devnull = file(os.devnull, 'ab')

    if os.name == 'nt':
        p1 = subprocess.Popen(["tasklist /V", "au"],
                stdout=subprocess.PIPE,
                stderr=devnull)
        output = p1.stdout.read()
    else:    
        p1 = subprocess.Popen(["ps", "au"],
                stdout=subprocess.PIPE,
                stderr=devnull)
        p2 = subprocess.Popen(["grep", "pycpoint.py"],
                stdin=p1.stdout,
                stdout=subprocess.PIPE,
                stderr=devnull)
        p3 = subprocess.Popen(["grep", "-v", "grep"],
                stdin=p2.stdout,
                stdout=subprocess.PIPE,
                stderr=devnull)
        output = p3.stdout.read()
    
    running = []
    if not output: return running
    entries = output.split(' ')
    for entry in entries:
        if rtype == 'proxy' and entry.startswith('-wSonospy='):
            running.append(entry[10:].split(',')[0])
        elif rtype == 'service' and entry.startswith('-sSonospy='):
            running.append(entry[10:].split(',')[0])
    return running

def getproxyaddresses(proxies, port):
    port = int(port)
    addresses = []
    for proxy in proxies:
        uri = 'http://%s:%s/%s-root-device.xml' % (ip_address, port, proxy)
        try:
            datastring=urllib.urlopen(uri).read()
        except IOError:
            pass
        else:
            parts = datastring.split('<UDN>')
            udn = parts[1].split('</UDN>')[0]
            addresses.append((proxy, port, udn))
            port += 1
    return addresses

#Send SOAP request
# taken from Miranda.py
# Interactive UPNP application #
# Craig Heffner                #
# www.sourcesec.com            #
# 07/16/2008                   #

def sendSOAP(hostName, serviceType, controlURL, actionName, actionArguments):
        argList = ''
        soapResponse = ''
        soapend = re.compile('<\/.*:envelope>')

        if '://' in controlURL:
                urlArray = controlURL.split('/',3)
                if len(urlArray) < 4:
                        controlURL = '/'
                else:
                        controlURL = '/' + urlArray[3]

        soapRequest = 'POST %s HTTP/1.1\r\n' % controlURL

        #Check if a port number was specified in the host name; default is port 80
        if ':' in hostName:
                hostNameArray = hostName.split(':')
                host = hostNameArray[0]
                try:
                        port = int(hostNameArray[1])
                except:
                        print 'Invalid port specified for host connection:',hostName[1]
                        return False
        else:
                host = hostName
                port = 80

        #Create a string containing all of the SOAP action's arguments and values
        for arg, val in actionArguments.iteritems():
                argList += '<%s>%s</%s>' % (arg,val,arg)

        #Create the SOAP request
        soapBody = '<?xml version="1.0" encoding="utf-8"?>'\
                   '<s:Envelope xmlns:ns0="%s" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/" xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'\
                   '    <s:Body>'\
                   '        <ns0:%s>%s</ns0:%s>'\
                   '    </s:Body>'\
                   '</s:Envelope>'  % (serviceType, actionName, argList, actionName)

        #Specify the headers to send with the request
        headers =         {
                        'Host':hostName,
                        'Content-Length':len(soapBody),
                        'Content-Type':'text/xml',
                        'SOAPAction':'"%s#%s"' % (serviceType,actionName)
                        }

        #Generate the final payload
        for head,value in headers.iteritems():
                soapRequest += '%s: %s\r\n' % (head,value)
        soapRequest += '\r\n%s' % soapBody

        print soapRequest
        
        #Send data and go into recieve loop
        try:
                    sock = socket(AF_INET,SOCK_STREAM)
                    sock.connect((host,port))
                    sock.send(soapRequest)
                    while True:
                        data = sock.recv(8192)
                        if not data:
                                break
                        else:
                                soapResponse += data
                                if soapend.search(soapResponse.lower()) != None:
                                        break
                    sock.close()

                    (header,body) = soapResponse.split('\r\n\r\n',1)
                    if not header.upper().startswith('HTTP/1.1 200'):
                        print 'SOAP request failed with error code:',header.split('\r\n')[0].split(' ',1)[1]
                        errorMsg = extractSingleTag(body,'errorDescription')
                        if errorMsg:
                                print 'SOAP error message:',errorMsg
                        return False
                    else:
                        return body
        except Exception, e:
                    print 'Caught socket exception:',e
                    sock.close()
                    return False
        except KeyboardInterrupt:
                    sock.close()
                    return False

#Extract the contents of a single XML tag from the data
def extractSingleTag(data,tag):
	startTag = "<%s" % tag
	endTag = "</%s>" % tag

	try:
		tmp = data.split(startTag)[1]
		index = tmp.find('>')
		if index != -1:
			index += 1
			return tmp[index:].split(endTag)[0].strip()
	except:
		pass
	return None


if __name__ == "__main__":
    main()
    
