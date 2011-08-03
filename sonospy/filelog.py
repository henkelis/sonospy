import codecs
import sys
import os

G_QUIET = False
G_VERBOSE = False
WARNING_FILE = 'logs/scanwarnings.txt'
wfile = codecs.open(WARNING_FILE,'a','utf-8')
ERROR_FILE = 'logs/scanerrors.txt'
efile = codecs.open(ERROR_FILE,'a','utf-8')
LOG_FILE = 'logs/scanlog.txt'
lfile = codecs.open(LOG_FILE,'a','utf-8')
VERBOSE_LOG_FILE = 'logs/scanlogverbose.txt'
vfile = codecs.open(VERBOSE_LOG_FILE,'a','utf-8')

enc = sys.getfilesystemencoding()

def clear_log_files():
    os.unlink(WARNING_FILE)
    os.unlink(ERROR_FILE)
    os.unlink(LOG_FILE)
    os.unlink(VERBOSE_LOG_FILE)

def write_warning(warningstring):
    if G_VERBOSE:
        print warningstring.encode(enc, 'replace')
    wfile.write('%s\n' % warningstring)

def write_error(errorstring):
    if not G_QUIET:
        print errorstring.encode(enc, 'replace')
    efile.write('%s\n' % errorstring)
    write_verbose_log(errorstring)

def write_log(logstring):
    if not G_QUIET:
        print logstring.encode(enc, 'replace')
    lfile.write('%s\n' % logstring)
    write_verbose_log(logstring)

def write_verbose_log(logstring):
    if G_VERBOSE:
        vfile.write('%s\n' % logstring)


