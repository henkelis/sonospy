# -*- coding: UTF-8 -*-

import ConfigParser
import StringIO
import codecs
import sys
import re

config = ConfigParser.ConfigParser()
config.optionxform = str

ini = ''
f = codecs.open('pycpoint.ini', encoding='utf-8')
for line in f:
#    print line
    ini += line

config.readfp(StringIO.StringIO(ini))

try:        
    chunk_metadata_delimiter_prefix_start = config.get('INI', 'chunk_metadata_delimiter_prefix_start')
except ConfigParser.NoSectionError:
    pass
except ConfigParser.NoOptionError:
    pass
try:        
    chunk_metadata_delimiter_prefix_end = config.get('INI', 'chunk_metadata_delimiter_prefix_end')
except ConfigParser.NoSectionError:
    pass
except ConfigParser.NoOptionError:
    pass
try:        
    chunk_metadata_delimiter_suffix_start = config.get('INI', 'chunk_metadata_delimiter_suffix_start')
except ConfigParser.NoSectionError:
    pass
except ConfigParser.NoOptionError:
    pass
try:        
    chunk_metadata_delimiter_suffix_end = config.get('INI', 'chunk_metadata_delimiter_suffix_end')
except ConfigParser.NoSectionError:
    pass
except ConfigParser.NoOptionError:
    pass

chunk_metadata_delimiter_prefix_start = unicode(chunk_metadata_delimiter_prefix_start)
chunk_metadata_delimiter_prefix_end = unicode(chunk_metadata_delimiter_prefix_end)
chunk_metadata_delimiter_suffix_start = unicode(chunk_metadata_delimiter_suffix_start)
chunk_metadata_delimiter_suffix_end = unicode(chunk_metadata_delimiter_suffix_end)


searchre_pre = '%s[^%s]*%s' % (chunk_metadata_delimiter_prefix_start, chunk_metadata_delimiter_prefix_end, chunk_metadata_delimiter_prefix_end)
multi_pre = '^(%s)* ' % searchre_pre
print searchre_pre
print multi_pre

searchre_suf = '%s[^%s]*%s' % (chunk_metadata_delimiter_suffix_start, chunk_metadata_delimiter_suffix_end, chunk_metadata_delimiter_suffix_end)
multi_suf = ' (%s)*$' % searchre_suf
print searchre_suf
print multi_suf

entry = u"ж99жжZж All Angels ж&&ж"
print entry

found = re.search(multi_pre, entry)
if found:
    print found.group(0)
    pfound = re.findall(searchre_pre, found.group(0))
    print pfound
    print len(pfound)
found = re.search(multi_suf, entry)
if found:
    print found.group(0)
    pfound = re.findall(searchre_suf, found.group(0))
    print pfound
    print len(pfound)

