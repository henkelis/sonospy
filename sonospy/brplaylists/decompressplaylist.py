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
    
    parser.add_option("-p", "--playlistfile", action="append", type="string", dest="plfile")

    (options, args) = parser.parse_args()

    print "Options: %s" % options
    print "Args: %s" % args

    if not options.plfile:
        print "You must specify a playlist file with the -p option"
        exit(1)

    # read input file
    playlistfile = options.plfile[0]
    compressed_playlist = None
    try:
        binf = open(playlistfile, 'rb')
        compressed_playlist = binf.read()
        binf.close()
        print 'Read %s' % playlistfile
    except IOError:
        print 'error reading %s file' % playlistfile
        print 'Stopping.'
        exit(1)
    if compressed_playlist:
        playlist = Decompressor().decompress(compressed_playlist, use_unicode = False)
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
            print 'error writing split txt file'

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
    
