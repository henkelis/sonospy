"""
This file is part of web2py Web Framework (Copyrighted, 2007-2010).
Developed by Massimo Di Pierro <mdipierro@cs.depaul.edu>.
License: GPL v2

Utility functions for the Admin application
===========================================
"""
import os
import zipfile
import urllib
from utils import web2py_uuid
from shutil import rmtree, copyfile
from fileutils import *
from restricted import RestrictedError


def apath(path='', r=None):
    """
    Builds a path inside an application folder

    Parameters
    ----------
    path:
        path within the application folder
    r:
        the global request object

    """

    opath = up(r.folder)
    while path[:3] == '../':
        (opath, path) = (up(opath), path[3:])
    return os.path.join(opath, path).replace('\\', '/')


def app_pack(app, request):
    """
    Builds a w2p package for the application

    Parameters
    ----------
    app:
        application name
    request:
        the global request object

    Returns
    -------
    filename:
        filename of the w2p file or None on error
    """
    try:
        app_cleanup(app, request)
        filename = apath('../deposit/%s.w2p' % app, request)
        w2p_pack(filename, apath(app, request))
        return filename
    except Exception:
        return False


def app_pack_compiled(app, request):
    """
    Builds a w2p bytecode-compiled package for the application

    Parameters
    ----------
    app:
        application name
    request:
        the global request object

    Returns
    -------
    filename:
        filename of the w2p file or None on error
    """

    try:
        filename = apath('../deposit/%s.w2p' % app, request)
        w2p_pack(filename, apath(app, request), compiled=True)
        return filename
    except Exception:
        return None


def app_cleanup(app, request):
    """
    Removes session, cache and error files

    Parameters
    ----------
    app:
        application name
    request:
        the global request object
    """
    r = True

    # Remove error files
    files = listdir(apath('%s/errors/' % app, request), '^\d.*$', 0)
    for f in files:
        try:
            os.unlink(f)
        except:
            r = False

    # Remove session files
    files = listdir(apath('%s/sessions/' % app, request), '^\d.*$', 0)
    for f in files:
        try:
            os.unlink(f)
        except:
            r = False

    # Remove cache files
    files = listdir(apath('%s/cache/' % app, request), '^cache.*$', 0)
    for file in files:
        try:
            os.unlink(file)
        except:
            r = False

    return r


def app_compile(app, request):
    """
    Compiles the application

    Parameters
    ----------
    app:
        application name
    request:
        the global request object
    """
    from compileapp import compile_application, remove_compiled_application
    folder = apath(app, request)
    try:
        compile_application(folder)
        return True
    except (Exception, RestrictedError):
        remove_compiled_application(folder)
        return False

def app_create(app, request):
    """
    Create a copy of welcome.w2p (scaffolding) app

    Parameters
    ----------
    app:
        application name
    request:
        the global request object

    """
    did_mkdir = False
    try:
        path = apath(app, request)
        os.mkdir(path)
        did_mkdir = True
        w2p_unpack('welcome.w2p', path)
        db = os.path.join(path,'models/db.py')
        if os.path.exists(db):
            fp = open(db,'r')
            data = fp.read()
            fp.close()
            data = data.replace('<your secret key>','sha512:'+web2py_uuid())
            fp = open(db,'w')
            fp.write(data)
            fp.close()
        return True
    except:
        if did_mkdir:
            rmtree(path)
        return False


def app_install(app, fobj, request, filename, overwrite=None):
    """
    Installs an application:

    - Identifies file type by filename
    - Writes `fobj` contents to the `../deposit/` folder
    - Calls `w2p_unpack()` to do the job.

    Parameters
    ----------
    app:
        new application name
    fobj:
        file object containing the application to be installed
    request:
        the global request object
    filename:
        original filename of the `fobj`, required to determine extension

    Returns
    -------
    upname:
        name of the file where app is temporarily stored or `None` on failure
    """
    did_mkdir = False
    if filename[-4:] == '.w2p':
        extension = 'w2p'
    elif filename[-7:] == '.tar.gz':
        extension = 'tar.gz'
    else:
        extension = 'tar'
    upname = apath('../deposit/%s.%s' % (app, extension), request)

    try:
        upfile = open(upname, 'wb')
        upfile.write(fobj.read())
        upfile.close()
        path = apath(app, request)
        if not overwrite:
            os.mkdir(path)
            did_mkdir = True
        w2p_unpack(upname, path)
        if extension != 'tar':
            os.unlink(upname)
        fix_newlines(path)
        return upname
    except Exception:
        if did_mkdir:
            rmtree(path)
        return False


def app_uninstall(app, request):
    """
    Uninstalls the application.

    Parameters
    ----------
    app:
        application name
    request:
        the global request object

    Returns
    -------
    `True` on success, `False` on failure
    """
    try:
        # Hey App, this is your end...
        path = apath(app, request)
        rmtree(path)
        return True
    except Exception:
        return False

def plugin_pack(app, plugin_name, request):
    """
    Builds a w2p package for the application

    Parameters
    ----------
    app:
        application name
    plugin_name:
        the name of the plugin without plugin_ prefix
    request:
        the current request app

    Returns
    -------
    filename:
        filename of the w2p file or None on error
    """
    try:
        filename = apath('../deposit/web2py.plugin.%s.w2p' % plugin_name, request)
        w2p_pack_plugin(filename, apath(app, request), plugin_name)
        return filename
    except Exception:
        return False

def plugin_install(app, fobj, request, filename):
    """
    Installs an application:

    - Identifies file type by filename
    - Writes `fobj` contents to the `../deposit/` folder
    - Calls `w2p_unpack()` to do the job.

    Parameters
    ----------
    app:
        new application name
    fobj:
        file object containing the application to be installed
    request:
        the global request object
    filename:
        original filename of the `fobj`, required to determine extension

    Returns
    -------
    upname:
        name of the file where app is temporarily stored or `None` on failure
    """

    upname = apath('../deposit/%s' % filename, request)

    try:
        upfile = open(upname, 'wb')
        upfile.write(fobj.read())
        upfile.close()
        path = apath(app, request)
        w2p_unpack_plugin(upname, path)
        fix_newlines(path)
        return upname
    except Exception:
        os.unlink(upfile)
        return False

def check_new_version(myversion, version_URL):
    """
    Compares current web2py's version with the latest stable web2py version.

    Parameters
    ----------
    myversion:
        the current version as stored in file `web2py/VERSION`
    version_URL:
        the URL that contains the version of the latest stable release

    Returns
    -------
    state:
        `True` if upgrade available, `False` if current version if up-to-date,
        -1 on error
    version:
        the most up-to-version available
    """
    try:
        from urllib import urlopen
        version = urlopen(version_URL).read()
    except Exception:
        return -1, myversion

    if version > myversion:
        return True, version
    else:
        return False, version

def unzip(filename, dir, subfolder=''):
    """
    Unzips filename into dir (.zip only, no .gz etc)    
    if subfolder!='' it unzip only files in subfolder
    """
    if not zipfile.is_zipfile(filename):
        raise RuntimeError, 'Not a valid zipfile'
    zf = zipfile.ZipFile(filename)
    if not subfolder.endswith('/'):
        subfolder = subfolder + '/'
    n = len(subfolder)
    for name in sorted(zf.namelist()):
        if not name.startswith(subfolder):
            continue
        #print name[n:]
        if name.endswith('/'):
            folder = os.path.join(dir,name[n:])
            if not os.path.exists(folder):
                os.mkdir(folder)
        else:
            outfile = open(os.path.join(dir, name[n:]), 'wb')
            outfile.write(zf.read(name))         
            outfile.close()


def upgrade(request, url = 'http://web2py.com'):
    """
    Upgrades web2py (src, osx, win) is a new version is posted.
    It detects whether src, osx or win is running and downloads the right one

    Parameters
    ----------
    request:
        the current request object, required to determine version and path
    url:
        the incomplete url where to locate the latest web2py
        actual url is url+'/examples/static/web2py_(src|osx|win).zip'

    Returns
    -------
        True on success, False on failure (network problem or old version)
    """
    web2py_version = request.env.web2py_version
    web2py_path = request.env.web2py_path
    if not web2py_path.endswith('/'):
        web2py_path = web2py_path + '/'
    (check, version) = check_new_version(web2py_version,
                                         url+'/examples/default/version')
    if not check:
        return (False, 'Already latest version')
    if os.path.exists(os.path.join(web2py_path,'web2py.exe')):
        version_type = 'win'
        destination = web2py_path
        subfolder = 'web2py/'
    elif web2py_path.endswith('/Contents/Resources/'):
        version_type = 'osx'
        destination = web2py_path[:-len('/Contents/Resources/')]
        subfolder = 'web2py/web2py.app/'
    else:
        version_type = 'src'
        destination = web2py_path
        subfolder = 'web2py/'

    full_url = url+'/examples/static/web2py_%s.zip' % version_type
    filename = os.path.join(web2py_path,
                            'web2py_%s_downloaded.zip' % version_type)
    try:
        file = open(filename,'wb')
        file.write(urllib.urlopen(full_url).read())
        file.close()
    except Exception,e:
        file.close()
        return False, e
    try:
        unzip(filename,destination,subfolder)
        return True, None
    except Exception,e:
        return False, e
        

