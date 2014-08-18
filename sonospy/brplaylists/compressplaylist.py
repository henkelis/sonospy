#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import zlib
ZLIB_WBIT = 12
ZLIB_MEMLEVEL = 5

from optparse import OptionParser

def main():

    print 'Compress playlist'

    usage = "usage: %prog [options] arg"
    parser = OptionParser(usage)
    
    parser.add_option("-i", "--inputplaylistfile", action="append", type="string", dest="plin")
    parser.add_option("-o", "--outputplaylistfile", action="append", type="string", dest="plout")

    (options, args) = parser.parse_args()

    print "Options: %s" % options
    print "Args: %s" % args

    if not options.plin:
        print "You must specify an input playlist file with the -i option"
        exit(1)
    if not options.plout:
        print "You must specify an output playlist file with the -o option"
        exit(1)

    inplaylistfile = options.plin[0]
    outplaylistfile = options.plout[0]

    playlist = ''
    try:
        txtf = open(inplaylistfile, 'r')
        playlist = txtf.read()
        playlist = unicode(playlist, 'utf-8')
        txtf.close()
    except IOError:
        print 'error reading input %s file' % inplaylistfile

    compressor = Compressor()
    compressed_playlist = compressor.compress(playlist)

    try:
        binf = open(outplaylistfile, 'wb')
        binf.write(compressed_playlist)
        binf.close()
    except IOError:
        print 'error writing output %s file' % outplaylistfile
    
class Compressor():
    compressor = None

    def __init__(self):
        print 'Compress: init'
        self.compressor = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, ZLIB_WBIT, ZLIB_MEMLEVEL, zlib.Z_DEFAULT_STRATEGY)

    def __del__(self):
        self.compressor = None

    def compress(self, data):
        print 'Compress: compress data'
        compressed_data = None
        if self.compressor:
            compressed_data = self.compressor.compress(data.encode('utf-8'))
            compressed_data += self.compressor.flush()
        return compressed_data

if __name__ == "__main__":
    main()
    
