#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import zlib

import os
from optparse import OptionParser
import re
import urllib
from socket import *
    
def main():

    usage = "usage: %prog [options] arg"
    parser = OptionParser(usage)
    
    parser.add_option("-z", "--zoneplayer", action="append", type="string", dest="zpip")
    parser.add_option("-u", "--uriplaylistfile", action="append", type="string", dest="urifile")

    (options, args) = parser.parse_args()

    print "Options: %s" % options
    print "Args: %s" % args

    if not options.zpip:
        print "You must specify a Zoneplayer IP address with the -z option"
        exit(1)

    if not options.urifile:
        print "You must specify a served playlist file URI with the -u option"
        exit(1)

    ip_address = options.zpip[0]
    uri = options.urifile[0]
    port = '1400'
    hostName = "%s:%s" % (ip_address, port)

    soapret = sendSOAP(hostName,
                       'urn:schemas-upnp-org:service:DeviceProperties:1',
                       '/DeviceProperties/Control',
                       'ImportSetting',
                       {
                        'SettingID': '2',
                        'SettingURI': '%s' % uri,
                       })
    print soapret

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
                   '<s:Header><credentials xmlns="http://www.sonos.com/Services/1.1"><deviceId>00-0E-58-30-D2-F0:8</deviceId><deviceProvider>Sonos</deviceProvider></credentials></s:Header>'\
                   '<s:Body>'\
                   '<ns0:%s>%s</ns0:%s>'\
                   '</s:Body>'\
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
        
        #Send data and go into receive loop
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
    
