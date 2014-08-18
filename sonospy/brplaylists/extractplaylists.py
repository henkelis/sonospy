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
    parser.add_option("-p", "--playlistfile", action="append", type="string", dest="plfile")

    (options, args) = parser.parse_args()

    print "Options: %s" % options
    print "Args: %s" % args

    if not options.zpip:
        print "You must specify a Zoneplayer IP address with the -z option"
        exit(1)

    if not options.plfile:
        print "You must specify a playlist file with the -p option"
        exit(1)

    ip_address = options.zpip[0]
    port = '1400'
    hostName = "%s:%s" % (ip_address, port)
    
    action = '/getrs?id=2'
    extraheaders = {
                    'x-rincon-content-format':'1',
                   }
    head, ret = sendGET(hostName, action, extraheaders)
    print head
    playlistfile = options.plfile[0]
    if ret:
        playlist = Decompressor().decompress(ret, use_unicode = False)
        try:
            binf = open(playlistfile, 'wb')
            binf.write(ret)
            binf.close()
        except IOError:
            print 'error writing bin file'
        try:
            txtf = open('%s.txt' % playlistfile, 'w')
            txtf.write(playlist)
            txtf.close()
        except IOError:
            print 'error writing txt file'
        try:
            playlist = playlist.replace('><SavedQueue', '>\n<SavedQueue')
            playlist = playlist.replace('></SavedQueue', '>\n</SavedQueue')
            playlist = playlist.replace('><Track', '>\n<Track')
            txtf = open('%s.split.txt' % playlistfile, 'w')
            txtf.write(playlist)
            txtf.close()
        except IOError:
            print 'error writing txt file'

def sendGET(hostName, action, extraheaders):

        #Check if a port number was specified in the host name; default is port 80
        if ':' in hostName:
                hostNameArray = hostName.split(':')
                host = hostNameArray[0]
                try:
                        port = int(hostNameArray[1])
                except:
                        print 'Invalid port specified for host connection: ',hostName[1]
                        return False, False
        else:
                host = hostName
                port = 80

        # create request
        request = 'GET %s HTTP/1.1\r\n' % action

        #Specify the headers to send with the request
        headers = {
                    'Host':hostName,
                  }
        headers.update(extraheaders)

        #Generate the final payload
        for head,value in headers.iteritems():
                request += '%s: %s\r\n' % (head,value)
        request += '\r\n%s' % ''

        print request
        
        #Send data and go into receive loop
        response = ''
        try:
                    sock = socket(AF_INET,SOCK_STREAM)
                    sock.connect((host,port))
                    sock.send(request)
                    while True:
                        data = sock.recv(8192)
                        if not data:
                                break
                        else:
                                response += data
                    sock.close()

                    (header,body) = response.split('\r\n\r\n',1)
                    return header, body

        except Exception, e:
                    print 'Caught socket exception:',e
                    sock.close()
                    return False, False
        except KeyboardInterrupt:
                    sock.close()
                    return False, False

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

class Decompressor():

    def decompress(self, data, use_unicode = True):
        try:
            if use_unicode:
                decompressed = unicode(zlib.decompress(data), 'utf-8')
            else:
                decompressed = str(zlib.decompress(data))
        except zlib.error:
            print 'Decompressor: caught zlib.error exception'
            decompressed = None

        return decompressed


if __name__ == "__main__":
    main()
    
