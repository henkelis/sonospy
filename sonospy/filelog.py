import codecs
import sys
import os

_WARNING_FILE = 'logs/scanwarnings.txt'
_ERROR_FILE = 'logs/scanerrors.txt'
_LOG_FILE = 'logs/scanlog.txt'
_VERBOSE_LOG_FILE = 'logs/scanlogverbose.txt'

enc = sys.getfilesystemencoding()

class filelog(object):

    def __init__(self):
        self.wfile = None
        self.efile = None
        self.lfile = None
        self.vfile = None

    def set_log_type(self, quiet, verbose):
        self.quiet = quiet
        self.verbose = verbose

    def clear_log_files(self):
        try: os.unlink(_WARNING_FILE)
        except: pass
        try: os.unlink(_ERROR_FILE)
        except: pass
        try: os.unlink(_LOG_FILE)
        except: pass
        try: os.unlink(_VERBOSE_LOG_FILE)
        except: pass

    def open_log_files(self):
        self.wfile = codecs.open(_WARNING_FILE,'a','utf-8')
        self.efile = codecs.open(_ERROR_FILE,'a','utf-8')
        self.lfile = codecs.open(_LOG_FILE,'a','utf-8')
        self.vfile = codecs.open(_VERBOSE_LOG_FILE,'a','utf-8')

    def close_log_files(self):
        self.wfile.close()
        self.efile.close()
        self.lfile.close()
        self.vfile.close()

    def write_warning(self, warningstring):
        if self.verbose:
            print warningstring.encode(enc, 'replace')
        self.wfile.write('%s\n' % warningstring)

    def write_error(self, errorstring):
        if not self.quiet:
            print errorstring.encode(enc, 'replace')
        self.efile.write('%s\n' % errorstring)
        self.write_verbose_log(errorstring)

    def write_log(self, logstring):
        if not self.quiet:
            print logstring.encode(enc, 'replace')
        self.lfile.write('%s\n' % logstring)
        self.write_verbose_log(logstring)

    def write_verbose_log(self, logstring):
        if self.verbose:
            self.vfile.write('%s\n' % logstring)

_fl = filelog()
set_log_type = _fl.set_log_type
clear_log_files = _fl.clear_log_files
open_log_files = _fl.open_log_files
close_log_files = _fl.close_log_files
write_warning = _fl.write_warning
write_error = _fl.write_error
write_log = _fl.write_log
write_verbose_log = _fl.write_verbose_log

