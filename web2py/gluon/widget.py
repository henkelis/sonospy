#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This file is part of web2py Web Framework (Copyrighted, 2007-2010).
Developed by Massimo Di Pierro <mdipierro@cs.depaul.edu>.
License: GPL v2

The widget is called from web2py.
"""

import sys
import cStringIO
import time
import thread
import re
import os
import stat
import socket
import signal
import math
import logging

from optparse import *
from textwrap import dedent

import contrib.cron

from main import HttpServer
from fileutils import w2p_pack
from shell import run, test

try:
    import Tkinter, tkMessageBox
    import contrib.taskbar_widget
    from winservice import web2py_windows_service_handler
except:
    pass

try:
    BaseException
except NameError:
    BaseException = Exception

ProgramName = 'web2py Enterprise Web Framework'
ProgramAuthor = 'Created by Massimo Di Pierro, Copyright 2007-2010'
versioninfo = open('VERSION', 'r')
ProgramVersion = versioninfo.read().strip()
versioninfo.close()

ProgramInfo = '''%s
                 %s
                 %s''' % (ProgramName, ProgramAuthor, ProgramVersion)

if not sys.version[:3] in ['2.4', '2.5', '2.6']:
    msg = 'Warning: web2py requires Python 2.4, 2.5 (recommended), or 2.6 but you are running:\n%s'
    msg = msg % sys.version
    sys.stderr.write(msg)


class IO(object):
    """   """

    def __init__(self):
        """   """

        self.buffer = cStringIO.StringIO()

    def write(self, data):
        """   """

        sys.__stdout__.write(data)
        if hasattr(self, 'callback'):
            self.callback(data)
        else:
            self.buffer.write(data)


def try_start_browser(url):
    """ Try to start the default browser """

    try:
        import webbrowser
        webbrowser.open(url)
    except:
        print 'warning: unable to detect your browser'


def start_browser(ip, port):
    """ Starts the default browser """

    print 'please visit:'
    print '\thttp://%s:%s' % (ip, port)
    print 'starting browser...in 5 seconds'
    time.sleep(5)
    try_start_browser('http://%s:%s' % (ip, port))


def presentation(root):
    """ Draw the splash screen """

    root.withdraw()

    dx = root.winfo_screenwidth()
    dy = root.winfo_screenheight()

    dialog = Tkinter.Toplevel(root)
    dialog.geometry('%ix%i+%i+%i' % (500, 300, dx / 2 - 200, dy / 2 - 150))

    dialog.overrideredirect(1)
    dialog.focus_force()

    canvas = Tkinter.Canvas(dialog,
                            background='white',
                            width=500,
                            height=300)
    canvas.pack()
    root.update()

    for counter in xrange(5):
        if counter is 0:
            canvas.create_text(250,
                               50,
                               text='Welcome to ...',
                               font=('Helvetica', 12),
                               anchor=Tkinter.CENTER,
                               fill='#195866')
        elif counter is 1:
            canvas.create_text(250,
                               130,
                               text=ProgramName,
                               font=('Helvetica', 18),
                               anchor=Tkinter.CENTER,
                               fill='#FF5C1F')
        elif counter is 2:
            canvas.create_text(250,
                               170,
                               text=ProgramAuthor,
                               font=('Helvetica', 12),
                               anchor=Tkinter.CENTER,
                               fill='#195866')
        elif counter is 3:
            canvas.create_text(250,
                               250,
                               text=ProgramVersion,
                               font=('Helvetica', 12),
                               anchor=Tkinter.CENTER,
                               fill='#195866')
        else:
            dialog.destroy()
            return

        root.update()
        time.sleep(1.5)
    return root


class web2pyDialog(object):
    """ Main window dialog """

    def __init__(self, root, options):
        """ web2pyDialog constructor  """

        root.title('web2py server')
        self.root = Tkinter.Toplevel(root)
        self.options = options
        self.menu = Tkinter.Menu(self.root)
        servermenu = Tkinter.Menu(self.menu, tearoff=0)
        httplog = os.path.join(os.getcwd(), 'httpserver.log')

        # Building the Menu
        item = lambda: try_start_browser(httplog)
        servermenu.add_command(label='View httpserver.log',
                               command=item)

        servermenu.add_command(label='Quit (pid:%i)' % os.getpid(),
                               command=self.quit)

        self.menu.add_cascade(label='Server', menu=servermenu)

        self.pagesmenu = Tkinter.Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label='Pages', menu=self.pagesmenu)

        helpmenu = Tkinter.Menu(self.menu, tearoff=0)

        # Home Page
        item = lambda: try_start_browser('http://www.web2py.com')
        helpmenu.add_command(label='Home Page',
                             command=item)

        # About
        item = lambda: tkMessageBox.showinfo('About web2py', ProgramInfo)
        helpmenu.add_command(label='About',
                             command=item)

        self.menu.add_cascade(label='Info', menu=helpmenu)

        self.root.config(menu=self.menu)

        if options.taskbar:
            self.root.protocol('WM_DELETE_WINDOW',
                               lambda: self.quit(True))
        else:
            self.root.protocol('WM_DELETE_WINDOW', self.quit)

        sticky = Tkinter.NW

        # Password
        Tkinter.Label(self.root,
                      text='Choose a password:',
                      justify=Tkinter.LEFT).grid(row=0,
                                                 column=0,
                                                 sticky=sticky)

        self.password = Tkinter.Entry(self.root, show='*')
        self.password.grid(row=0, column=1, sticky=sticky)

        # IP
        Tkinter.Label(self.root,
                      text='Running from host:',
                      justify=Tkinter.LEFT).grid(row=1,
                                                 column=0,
                                                 sticky=sticky)
        self.ip = Tkinter.Entry(self.root)
        self.ip.insert(Tkinter.END, self.options.ip)
        self.ip.grid(row=1, column=1, sticky=sticky)

        # Port
        Tkinter.Label(self.root,
                      text='Running from port:',
                      justify=Tkinter.LEFT).grid(row=2,
                                                 column=0,
                                                 sticky=sticky)

        self.port_number = Tkinter.Entry(self.root)
        self.port_number.insert(Tkinter.END, self.options.port)
        self.port_number.grid(row=2, column=1, sticky=sticky)

        # Prepare the canvas
        self.canvas = Tkinter.Canvas(self.root,
                                     width=300,
                                     height=100,
                                     bg='black')
        self.canvas.grid(row=3, column=0, columnspan=2)
        self.canvas.after(1000, self.update_canvas)

        # Prepare the frame
        frame = Tkinter.Frame(self.root)
        frame.grid(row=4, column=0, columnspan=2)

        # Start button
        self.button_start = Tkinter.Button(frame,
                                           text='start server',
                                           command=self.start)

        self.button_start.grid(row=0, column=0)

        # Stop button
        self.button_stop = Tkinter.Button(frame,
                                          text='stop server',
                                          command=self.stop)

        self.button_stop.grid(row=0, column=1)
        self.button_stop.configure(state='disabled')

        if options.taskbar:
            self.tb = contrib.taskbar_widget.TaskBarIcon()
            self.checkTaskBar()

            if options.password != '<ask>':
                self.password.insert(0, options.password)
                self.start()
                self.root.withdraw()
        else:
            self.tb = None

    def checkTaskBar(self):
        """ Check taskbar status """

        if self.tb.status:
            if self.tb.status[0] == self.tb.EnumStatus.QUIT:
                self.quit()
            elif self.tb.status[0] == self.tb.EnumStatus.TOGGLE:
                if self.root.state() == 'withdrawn':
                    self.root.deiconify()
                else:
                    self.root.withdraw()
            elif self.tb.status[0] == self.tb.EnumStatus.STOP:
                self.stop()
            elif self.tb.status[0] == self.tb.EnumStatus.START:
                self.start()
            elif self.tb.status[0] == self.tb.EnumStatus.RESTART:
                self.stop()
                self.start()
            del self.tb.status[0]

        self.root.after(1000, self.checkTaskBar)

    def update(self, text):
        """ Update app text """

        try:
            self.text.configure(state='normal')
            self.text.insert('end', text)
            self.text.configure(state='disabled')
        except:
            pass  # ## this should only happen in case app is destroyed

    def connect_pages(self):
        """ Connect pages """

        for arq in os.listdir('applications/'):
            if os.path.exists('applications/%s/__init__.py' % arq):
                url = self.url + '/' + arq
                start_browser = lambda u = url: try_start_browser(u)
                self.pagesmenu.add_command(label=url,
                                           command=start_browser)

    def quit(self, justHide=False):
        """ Finish the program execution """

        if justHide:
            self.root.withdraw()
        else:
            try:
                self.server.stop()
            except:
                pass

            try:
                self.tb.Destroy()
            except:
                pass

            self.root.destroy()
            sys.exit()

    def error(self, message):
        """ Show error message """

        tkMessageBox.showerror('web2py start server', message)

    def start(self):
        """ Start web2py server """

        password = self.password.get()

        if not password:
            self.error('no password, no web admin interface')

        ip = self.ip.get()

        regexp = '\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'
        if ip and not re.compile(regexp).match(ip):
            return self.error('invalid host ip address')

        try:
            port = int(self.port_number.get())
        except:
            return self.error('invalid port number')

        self.url = 'http://%s:%s' % (ip, port)
        self.connect_pages()
        self.button_start.configure(state='disabled')

        try:
            options = self.options
            req_queue_size = options.request_queue_size

            self.server = HttpServer(
                ip,
                port,
                password,
                pid_filename=options.pid_filename,
                log_filename=options.log_filename,
                profiler_filename=options.profiler_filename,
                ssl_certificate=options.ssl_certificate,
                ssl_private_key=options.ssl_private_key,
                numthreads=options.numthreads,
                server_name=options.server_name,
                request_queue_size=req_queue_size,
                timeout=options.timeout,
                shutdown_timeout=options.shutdown_timeout,
                path=options.folder)

            thread.start_new_thread(self.server.start, ())
        except Exception, e:
            self.button_start.configure(state='normal')
            return self.error(str(e))

        self.button_stop.configure(state='normal')

        if not options.taskbar:
            thread.start_new_thread(start_browser, (ip, port))

        self.password.configure(state='readonly')
        self.ip.configure(state='readonly')
        self.port_number.configure(state='readonly')

        if self.tb:
            self.tb.SetServerRunning()

    def stop(self):
        """ Stop web2py server """

        self.button_start.configure(state='normal')
        self.button_stop.configure(state='disabled')
        self.password.configure(state='normal')
        self.ip.configure(state='normal')
        self.port_number.configure(state='normal')
        self.server.stop()

        if self.tb:
            self.tb.SetServerStopped()

    def update_canvas(self):
        """ Update canvas """

        try:
            t1 = os.stat('httpserver.log')[stat.ST_SIZE]
        except:
            self.canvas.after(1000, self.update_canvas)
            return

        try:
            fp = open('httpserver.log', 'r')
            fp.seek(self.t0)
            data = fp.read(t1 - self.t0)
            fp.close()
            value = self.p0[1:] + [10 + 90.0 / math.sqrt(1 + data.count('\n'))]
            self.p0 = value

            for i in xrange(len(self.p0) - 1):
                c = self.canvas.coords(self.q0[i])
                self.canvas.coords(self.q0[i],
                                   (c[0],
                                    self.p0[i],
                                    c[2],
                                    self.p0[i + 1]))
            self.t0 = t1
        except BaseException:
            self.t0 = time.time()
            self.t0 = t1
            self.p0 = [100] * 300
            self.q0 = [self.canvas.create_line(i, 100, i + 1, 100,
                       fill='green') for i in xrange(len(self.p0) - 1)]

        self.canvas.after(1000, self.update_canvas)


def console():
    """ Defines the behavior of the console web2py execution """

    usage = "python web2py.py"

    description = """\
    web2py Web Framework startup script.
    ATTENTION: unless a password is specified (-a 'passwd') web2py will
    attempt to run a GUI. In this case command line options are ignored."""

    description = dedent(description)

    parser = OptionParser(usage, None, Option, ProgramVersion)

    parser.description = description

    parser.add_option('-i',
                      '--ip',
                      default='127.0.0.1',
                      dest='ip',
                      help='ip address of the server (127.0.0.1)')

    parser.add_option('-p',
                      '--port',
                      default='8000',
                      dest='port',
                      type='int',
                      help='port of server (8000)')

    msg = 'password to be used for administration'
    msg += ' (use -a "<recycle>" to reuse the last password))'
    parser.add_option('-a',
                      '--password',
                      default='<ask>',
                      dest='password',
                      help=msg)

    parser.add_option('-c',
                      '--ssl_certificate',
                      default='',
                      dest='ssl_certificate',
                      help='file that contains ssl certificate')

    parser.add_option('-k',
                      '--ssl_private_key',
                      default='',
                      dest='ssl_private_key',
                      help='file that contains ssl private key')

    parser.add_option('-d',
                      '--pid_filename',
                      default='httpserver.pid',
                      dest='pid_filename',
                      help='file to store the pid of the server')

    parser.add_option('-l',
                      '--log_filename',
                      default='httpserver.log',
                      dest='log_filename',
                      help='file to log connections')

    parser.add_option('-n',
                      '--numthreads',
                      default='10',
                      type='int',
                      dest='numthreads',
                      help='number of threads')

    parser.add_option('-s',
                      '--server_name',
                      default=socket.gethostname(),
                      dest='server_name',
                      help='server name for the web server')

    msg = 'max number of queued requests when server unavailable'
    parser.add_option('-q',
                      '--request_queue_size',
                      default='5',
                      type='int',
                      dest='request_queue_size',
                      help=msg)

    parser.add_option('-o',
                      '--timeout',
                      default='10',
                      type='int',
                      dest='timeout',
                      help='timeout for individual request (10 seconds)')

    parser.add_option('-z',
                      '--shutdown_timeout',
                      default='5',
                      type='int',
                      dest='shutdown_timeout',
                      help='timeout on shutdown of server (5 seconds)')
    parser.add_option('-f',
                      '--folder',
                      default=os.getcwd(),
                      dest='folder',
                      help='folder from which to run web2py')

    parser.add_option('-v',
                      '--verbose',
                      action='store_true',
                      dest='verbose',
                      default=False,
                      help='increase --test verbosity')

    parser.add_option('-Q',
                      '--quiet',
                      action='store_true',
                      dest='quiet',
                      default=False,
                      help='disable all output')

    msg = 'set debug output level (0-100, 0 means all, 100 means none;'
    msg += ' default is 30)'
    parser.add_option('-D',
                      '--debug',
                      dest='debuglevel',
                      default=30,
                      type='int',
                      help=msg)

    msg = 'run web2py in interactive shell or IPython (if installed) with'
    msg += ' specified appname'
    parser.add_option('-S',
                      '--shell',
                      dest='shell',
                      metavar='APPNAME',
                      help=msg)

    msg = 'only use plain python shell; should be used with --shell option'
    parser.add_option('-P',
                      '--plain',
                      action='store_true',
                      default=False,
                      dest='plain',
                      help=msg)

    msg = 'auto import model files; default is False; should be used'
    msg += ' with --shell option'
    parser.add_option('-M',
                      '--import_models',
                      action='store_true',
                      default=False,
                      dest='import_models',
                      help=msg)

    msg = 'run PYTHON_FILE in web2py environment;'
    msg += ' should be used with --shell option'
    parser.add_option('-R',
                      '--run',
                      dest='run',
                      metavar='PYTHON_FILE',
                      default='',
                      help=msg)

    msg = 'run doctests in web2py environment; ' +\
        'TEST_PATH like a/c/f (c,f optional)'
    parser.add_option('-T',
                      '--test',
                      dest='test',
                      metavar='TEST_PATH',
                      default=None,
                      help=msg)

    parser.add_option('-W',
                      '--winservice',
                      dest='winservice',
                      default='',
                      help='-W install|start|stop as Windows service')

    msg = 'trigger a cron run manually; usually invoked from a system crontab'
    parser.add_option('-C',
                      '--cron',
                      action='store_true',
                      dest='extcron',
                      default=False,
                      help=msg)

    parser.add_option('-N',
                      '--no-cron',
                      action='store_true',
                      dest='nocron',
                      default=False,
                      help='do not start cron automatically')

    parser.add_option('-L',
                      '--config',
                      dest='config',
                      default='',
                      help='config file')

    parser.add_option('-F',
                      '--profiler',
                      dest='profiler_filename',
                      default=None,
                      help='profiler filename')

    parser.add_option('-t',
                      '--taskbar',
                      action='store_true',
                      dest='taskbar',
                      default=False,
                      help='use web2py gui and run in taskbar (system tray)')

    parser.add_option('',
                      '--nogui',
                      action='store_true',
                      default=False,
                      dest='nogui',
                      help='text-only, no GUI')

    parser.add_option('-A',
                      '--args',
                      action='store',
                      dest='args',
                      default='',
                      help='should be followed by a list of arguments to be passed to script, to be used with -S, -A must be the last option')

    if '-A' in sys.argv: k = sys.argv.index('-A')
    elif '--args' in sys.argv: k = sys.argv.index('--args')
    else: k=len(sys.argv)
    sys.argv, other_args = sys.argv[:k], sys.argv[k+1:]
    (options, args) = parser.parse_args()
    options.args = [options.run] + other_args

    if options.quiet:
        capture = cStringIO.StringIO()
        sys.stdout = capture
        logging.getLogger().setLevel(logging.CRITICAL + 1)
    else:
        logging.getLogger().setLevel(options.debuglevel)

    if options.config[-3:] == '.py':
        options.config = options.config[:-3]

    if not os.path.exists('applications'):
        os.mkdir('applications')

    if not os.path.exists('deposit'):
        os.mkdir('deposit')

    if not os.path.exists('site-packages'):
        os.mkdir('site-packages')

    sys.path.append(os.path.join(os.getcwd(),'site-packages'))

    # If we have the applications package or if we should upgrade
    if not os.path.exists('applications/__init__.py'):
        fp = open('applications/__init__.py', 'w')
        fp.write('')
        fp.close()

    if not os.path.exists('welcome.w2p') or os.path.exists('NEWINSTALL'):
        w2p_pack('welcome.w2p','applications/welcome')
        os.unlink('NEWINSTALL')

    return (options, args)


def start(cron = True):
    """ Start server  """

    # ## get command line arguments

    (options, args) = console()

    print ProgramName
    print ProgramAuthor
    print ProgramVersion

    from sql import drivers
    print 'Database drivers available: %s' % ', '.join(drivers)

    # ## Starts cron daemon

    if not options.shell and cron and not options.nocron:
        print 'Starting cron...'
        contrib.cron.crontype = 'hard'
        cron = contrib.cron.hardcron()
        cron.start()

    # ## if -W install/start/stop web2py as service

    if options.winservice:
        if os.name == 'nt':
            web2py_windows_service_handler(['', options.winservice],
                    options.config)
        else:
            print 'Error: Windows services not supported on this platform'
            sys.exit(1)
        return

    # ## if -T run doctests

    if options.test:
        test(options.test, verbose=options.verbose)
        return

    # ## if -S start interactive shell

    if options.shell:
        sys.args = options.args
        run(options.shell, plain=options.plain,
            import_models=options.import_models, startfile=options.run)
        return

    # ## if -L load options from options.config file

    if options.config:
        try:
            options = __import__(options.config, [], [], '')
        except Exception:
            try:
                # Jython doesn't like the extra stuff
                options = __import__(options.config)
            except Exception:
                print 'Cannot import config file [%s]' % options.config
                sys.exit(1)

    # ## if -C start cron run
    # ## if -N disable cron in this *process*
    # ##     - note, startup tasks WILL be run regardless !

    if options.extcron or options.nocron:
        contrib.cron.crontype = 'External'
        if options.extcron:
            cron = contrib.cron.extcron()
            cron.start()
            cron.join()
            return

    # ## if no password provided and havetk start Tk interface
    # ## or start interface if we want to put in taskbar (system tray)

    try:
        options.taskbar
    except:
        options.taskbar = False

    if options.taskbar and os.name != 'nt':
        print 'Error: taskbar not supported on this platform'
        sys.exit(1)

    root = None

    if not options.nogui:
        try:
            import tkMessageBox
            import Tkinter
            havetk = True
        except ImportError:
            logging.warn('GUI not available because Tk library is not installed')
            havetk = False

        if options.password == '<ask>' and havetk or options.taskbar and havetk:
            try:
                root = Tkinter.Tk()
            except:
                pass

    if root:
        root.focus_force()
        if not options.quiet:
            presentation(root)
        master = web2pyDialog(root, options)
        signal.signal(signal.SIGTERM, lambda a, b: master.quit())

        try:
            root.mainloop()
        except:
            master.quit()

        sys.exit()

    # ## if no tk and no password, ask for a password

    if not root and options.password == '<ask>':
        options.password = raw_input('choose a password:')

    if not options.password:
        print 'no password, no admin interface'

    # ## start server

    (ip, port) = (options.ip, int(options.port))

    print 'please visit:'
    print '\thttp://%s:%s' % (ip, port)
    print 'use "kill -SIGTERM %i" to shutdown the web2py server' % os.getpid()

    server = HttpServer(ip=ip,
                        port=port,
                        password=options.password,
                        pid_filename=options.pid_filename,
                        log_filename=options.log_filename,
                        profiler_filename=options.profiler_filename,
                        ssl_certificate=options.ssl_certificate,
                        ssl_private_key=options.ssl_private_key,
                        numthreads=options.numthreads,
                        server_name=options.server_name,
                        request_queue_size=options.request_queue_size,
                        timeout=options.timeout,
                        shutdown_timeout=options.shutdown_timeout,
                        path=options.folder)

    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()
        #os.kill(os.getpid(),signal.SIGKILL)
