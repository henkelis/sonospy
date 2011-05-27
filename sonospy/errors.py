import sys, cgitb
from datetime import datetime

def catch_errors():
    sys.excepthook = my_except_hook
    
def my_except_hook(etype, evalue, etraceback):
    do_verbose_exception( (etype,evalue,etraceback) )
    
def do_verbose_exception(exc_info=None):
    if exc_info is None:
        exc_info = sys.exc_info()
        
    txt = cgitb.text(exc_info)
    
    d = datetime.now()
    p = (d.year, d.month, d.day, d.hour, d.minute, d.second)        
    filename = "errors/ErrorDump-%d%02d%02d-%02d%02d%02d.txt" % p
                
    open(filename,'w').write(txt)
    print "** EXITING on unhandled exception - See %s" % filename  
    sys.exit(1)
