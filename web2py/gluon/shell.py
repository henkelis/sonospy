#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This file is part of web2py Web Framework (Copyrighted, 2007-2010).
Developed by Massimo Di Pierro <mdipierro@cs.depaul.edu>,
limodou <limodou@gmail.com> and srackham <srackham@gmail.com>.
License: GPL v2

"""

import os
import sys
import code
import logging
import types
import re
import optparse
import glob

import fileutils
from compileapp import *
from restricted import RestrictedError
from globals import Request, Response, Session
from storage import Storage
from admin import w2p_unpack


def exec_environment(
    pyfile='',
    request=Request(),
    response=Response(),
    session=Session(),
    ):
    """
    .. function:: gluon.shell.exec_environment([pyfile=''[, request=Request()
        [, response=Response[, sessions=Session()]]]])

        Environment builder and module loader.


        Builds a web2py environment and optionally executes a Python
        file into the environment.
        A Storage dictionary containing the resulting environment is returned.
        The working directory must be web2py root -- this is the web2py default.

    """

    if request.folder is None:
        mo = re.match(r'(|.*/)applications/(?P<appname>[^/]+)', pyfile)
        if mo:
            appname = mo.group('appname')
            request.folder = os.path.join('applications', appname)
        else:
            request.folder = ''
    env = build_environment(request, response, session)
    if pyfile:
        pycfile = pyfile + 'c'
        if os.path.isfile(pycfile):
            exec read_pyc(pycfile) in env
        else:
            execfile(pyfile, env)
    return Storage(env)


def env(
    a,
    import_models=False,
    c=None,
    f=None,
    dir='',
    ):
    """
    Return web2py execution environment for application (a), controller (c),
    function (f).
    If import_models is True the exec all application models into the
    environment.
    """

    request = Request()
    response = Response()
    session = Session()
    request.application = a

    # Populate the dummy environment with sensible defaults.

    if not dir:
        request.folder = os.path.join('applications', a)
    else:
        request.folder = dir
    request.controller = c or 'default'
    request.function = f or 'index'
    response.view = '%s/%s.html' % (request.controller,
                                    request.function)
    request.env.path_info = '/%s/%s/%s' % (a, c, f)
    request.env.http_host = '127.0.0.1:8000'
    request.env.remote_addr = '127.0.0.1'

    # Monkey patch so credentials checks pass.

    def check_credentials(request, other_application='admin'):
        return True

    fileutils.check_credentials = check_credentials

    environment = build_environment(request, response, session)

    if import_models:
        try:
            run_models_in(environment)
        except RestrictedError, e:
            sys.stderr.write(e.traceback+'\n')
            sys.exit(1)
    return environment


def exec_pythonrc():
    pythonrc = os.environ.get('PYTHONSTARTUP')
    if pythonrc and os.path.isfile(pythonrc):
        try:
            execfile(pythonrc)
        except NameError:
            pass


def run(
    appname,
    plain=False,
    import_models=False,
    startfile=None,
    ):
    """
    Start interactive shell or run Python script (startfile) in web2py
    controller environment. appname is formatted like:

    a      web2py application name
    a/c    exec the controller c into the application environment
    """

    (a, c, f) = parse_path_info(appname)
    errmsg = 'invalid application name: %s' % appname
    if not a:
        die(errmsg)
    adir = os.path.join('applications', a)
    if not os.path.exists(adir):
        if raw_input('application %s does not exist, create (y/n)?'
                      % a).lower() in ['y', 'yes']:
            os.mkdir(adir)
            w2p_unpack('welcome.w2p', adir)
        else:
            return

    if c:
        import_models = True
    _env = env(a, c=c, import_models=import_models)
    if c:
        cfile = os.path.join('applications', a, 'controllers', c + '.py')
        if not os.path.isfile(cfile):
            die(errmsg)
        execfile(cfile, _env)

    if f:
        exec ('print %s()' % f, _env)
    elif startfile:
        exec_pythonrc()
        try:
            execfile(startfile, _env)
        except RestrictedError, e:
            print e.traceback
    else:
        if not plain:
            try:
                import IPython
                # following 2 lines fixe a problem with IPython, thanks Michael Toomim
                if '__builtins__' in _env:
                    del _env['__builtins__']
                shell = IPython.Shell.IPShell(argv=[], user_ns=_env)
                shell.mainloop()
                return
            except:
                logging.warning(
                    'import IPython error, use default python shell')
        try:
            import readline
            import rlcompleter
        except ImportError:
            pass
        else:
            readline.set_completer(rlcompleter.Completer(_env).complete)
            readline.parse_and_bind('tab:complete')
        exec_pythonrc()
        code.interact(local=_env)


def parse_path_info(path_info):
    """
    Parse path info formatted like a/c/f where c and f are optional
    and a leading / accepted.
    Return tuple (a, c, f). If invalid path_info a is set to None.
    If c or f are omitted they are set to None.
    """

    mo = re.match(r'^/?(?P<a>\w+)(/(?P<c>\w+)(/(?P<f>\w+))?)?$',
                  path_info)
    if mo:
        return (mo.group('a'), mo.group('c'), mo.group('f'))
    else:
        return (None, None, None)


def die(msg):
    print >> sys.stderr, msg
    sys.exit(1)


def test(testpath, import_models=True, verbose=False):
    """
    Run doctests in web2py environment. testpath is formatted like:

    a      tests all controllers in application a
    a/c    tests controller c in application a
    a/c/f  test function f in controller c, application a

    Where a, c and f are application, controller and function names
    respectively. If the testpath is a file name the file is tested.
    If a controller is specified models are executed by default.
    """

    import doctest
    if os.path.isfile(testpath):
        mo = re.match(r'(|.*/)applications/(?P<a>[^/]+)', testpath)
        if not mo:
            die('test file is not in application directory: %s'
                 % testpath)
        a = mo.group('a')
        c = f = None
        files = [testpath]
    else:
        (a, c, f) = parse_path_info(testpath)
        errmsg = 'invalid test path: %s' % testpath
        if not a:
            die(errmsg)
        cdir = os.path.join('applications', a, 'controllers')
        if not os.path.isdir(cdir):
            die(errmsg)
        if c:
            cfile = os.path.join(cdir, c + '.py')
            if not os.path.isfile(cfile):
                die(errmsg)
            files = [cfile]
        else:
            files = glob.glob(os.path.join(cdir, '*.py'))
    for testfile in files:
        globs = env(a, import_models)
        ignores = globs.keys()
        execfile(testfile, globs)

        def doctest_object(name, obj):
            """doctest obj and enclosed methods and classes."""

            if type(obj) in (types.FunctionType, types.TypeType,
                             types.ClassType, types.MethodType,
                             types.UnboundMethodType):

                # Reload environment before each test.

                globs = env(a, c=c, f=f, import_models=import_models)
                execfile(testfile, globs)
                doctest.run_docstring_examples(obj, globs=globs,
                        name='%s: %s' % (os.path.basename(testfile),
                        name), verbose=verbose)
                if type(obj) in (types.TypeType, types.ClassType):
                    for attr_name in dir(obj):

                        # Execute . operator so decorators are executed.

                        o = eval('%s.%s' % (name, attr_name), globs)
                        doctest_object(attr_name, o)

        for (name, obj) in globs.items():
            if name not in ignores and (f is None or f == name):
                doctest_object(name, obj)


def get_usage():
    usage = """
  %prog [options] pythonfile
"""
    return usage


def execute_from_command_line(argv=None):
    if argv is None:
        argv = sys.argv

    parser = optparse.OptionParser(usage=get_usage())

    parser.add_option('-S', '--shell', dest='shell', metavar='APPNAME',
        help='run web2py in interactive shell or IPython(if installed) ' + \
            'with specified appname')
    parser.add_option(
        '-P',
        '--plain',
        action='store_true',
        default=False,
        dest='plain',
        help='only use plain python shell, should be used with --shell option',
        )
    parser.add_option(
        '-M',
        '--import_models',
        action='store_true',
        default=False,
        dest='import_models',
        help='auto import model files, default is False, ' + \
            ' should be used with --shell option',
        )
    parser.add_option(
        '-R',
        '--run',
        dest='run',
        metavar='PYTHON_FILE',
        default='',
        help='run PYTHON_FILE in web2py environment, ' + \
            'should be used with --shell option',
        )

    (options, args) = parser.parse_args(argv[1:])

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    if len(args) > 0:
        startfile = args[0]
    else:
        startfile = ''
    run(options.shell, options.plain, startfile=startfile)


if __name__ == '__main__':
    execute_from_command_line()
