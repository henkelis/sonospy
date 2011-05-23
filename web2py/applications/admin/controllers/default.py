# coding: utf8 

from gluon.admin import *
from glob import glob
import shutil

def index():
    """ Index handler """

    send = request.vars.send
    if not send:
        send = URL(r=request, f='site')

    if session.authorized:
        redirect(send)
    elif request.vars.password:
        if verify_password(request.vars.password):
            session.authorized = True

            if CHECK_VERSION:
                session.check_version = True
            else:
                session.check_version = False

            session.last_time = t0
            if isinstance(send, list):  # ## why does this happen?
                send = str(send[0])

            redirect(send)
        else:
            response.flash = T('invalid password')

    # f == file
    apps = [f for f in os.listdir(apath(r=request)) if f.find('.') < 0]

    return dict(apps=apps, send=send)


def check_version():
    """ Checks if web2py is up to date """

    session.forget()
    session._unlock(response)

    new_version, version_number = check_new_version(request.env.web2py_version,
                                    WEB2PY_VERSION_URL)
    
    if new_version == -1:
        return A(T('Unable to check for upgrades'), _href=WEB2PY_URL)
    elif new_version == True:
        return A(T('A new version of web2py is available: %s'
                                            % version_number), _href=WEB2PY_URL)
    else:
        return A(T('web2py is up to date'), _href=WEB2PY_URL)


def logout():
    """ Logout handler """

    session.authorized = None
    redirect(URL(r=request, f='index'))


def change_password():
    if session.pam_user:
        session.flash = T('PAM authenticated user, cannot change password here')
        redirect(URL(r=request,f='site'))
    form=SQLFORM.factory(Field('current_admin_password','password'),
                         Field('new_admin_password','password',requires=IS_STRONG()),
                         Field('new_admin_password_again','password'))
    if form.accepts(request.vars):
        if not verify_password(request.vars.current_admin_password):
            form.errors.current_admin_password = T('invalid password')
        elif form.vars.new_admin_password != form.vars.new_admin_password_again:
            form.errors.new_admin_password_again = T('no match')
        else:
            path = os.path.join(request.env.web2py_path,'parameters_%s.py' % request.env.server_port)
            open(path,'w').write('password="%s"' % CRYPT()(request.vars.new_admin_password)[0])
            session.flash = T('password changed')
            redirect(URL(r=request,f='site'))
    return dict(form=form)

def site():
    """ Site handler """

    myversion = request.env.web2py_version

    # Shortcut to make the elif statements more legible
    file_or_appurl = 'file' in request.vars or 'appurl' in request.vars

    if request.vars.filename and not 'file' in request.vars:
        # create a new application
        appname = cleanpath(request.vars.filename).replace('.', '_')
        if app_create(appname, request):
            session.flash = T('new application "%s" created', appname)
            redirect(URL(r=request,f='design',args=appname))
        else:
            session.flash = \
                T('unable to create application "%s"', request.vars.filename)
        redirect(URL(r=request))
        
    elif file_or_appurl and not request.vars.filename:
        # can't do anything without an app name
        msg = 'you must specify a name for the uploaded application'
        response.flash = T(msg)

    elif file_or_appurl and request.vars.filename:
        # fetch an application via URL or file upload
        if request.vars.appurl is not '':
            try:
                f = urllib.urlopen(request.vars.appurl)
            except Exception, e:
                session.flash = DIV(T('Unable to download app because:'),PRE(str(e)))
                redirect(URL(r=request))
            fname = request.vars.appurl
        elif request.vars.file is not '':
            f = request.vars.file.file
            fname = request.vars.file.filename

        appname = cleanpath(request.vars.filename).replace('.', '_')
        installed = app_install(appname, f, request, fname,
                                overwrite=request.vars.overwrite_check)
        if installed:
            msg = 'application %(appname)s installed with md5sum: %(digest)s'
            session.flash = T(msg, dict(appname=appname,
                                        digest=md5_hash(installed)))
        elif request.vars.overwrite_check:
            msg = 'unable to install application "%(appname)s"'
            session.flash = T(msg, dict(appname=request.vars.filename))

        else:
            msg = 'unable to install application "%(appname)s"'
            session.flash = T(msg, dict(appname=request.vars.filename))

        redirect(URL(r=request))

    regex = re.compile('^\w+$')
    apps = sorted([(f.upper(), f) for f in os.listdir(apath(r=request)) \
                       if regex.match(f)])
    apps = [item[1] for item in apps]

    return dict(app=None, apps=apps, myversion=myversion)


def pack():
    if len(request.args) == 1:
        fname = 'web2py.app.%s.w2p' % request.args[0]
        filename = app_pack(request.args[0], request)
    else:
        fname = 'web2py.app.%s.compiled.w2p' % request.args[0]
        filename = app_pack_compiled(request.args[0], request)

    if filename:
        response.headers['Content-Type'] = 'application/w2p'
        disposition = 'attachment; filename=%s' % fname
        response.headers['Content-Disposition'] = disposition
        return open(filename, 'rb').read()
    else:
        session.flash = T('internal error')
        redirect(URL(r=request, f='site'))

def pack_plugin():
    if len(request.args) == 2:
        fname = 'web2py.plugin.%s.w2p' % request.args[1]
        filename = plugin_pack(request.args[0], request.args[1], request)
    if filename:
        response.headers['Content-Type'] = 'application/w2p'
        disposition = 'attachment; filename=%s' % fname
        response.headers['Content-Disposition'] = disposition
        return open(filename, 'rb').read()
    else:
        session.flash = T('internal error')
        redirect(URL(r=request, f='plugin',args=request.args))

def upgrade_web2py():
    if 'upgrade' in request.vars:
        (success, error) = upgrade(request)
        if success:
            session.flash = T('web2py upgraded, plase restart it')
        else:
            session.flash = T('unable to upgrade because "%s"', error)
        redirect(URL(r=request, f='site'))
    elif 'noupgrade' in request.vars:
        redirect(URL(r=request, f='site'))
    return dict()

def uninstall():
    app = request.args[0]

    if 'delete' in request.vars:
        deleted = app_uninstall(app, request)
        if deleted:
            session.flash = T('application "%s" uninstalled', app)
        else:
            session.flash = T('unable to uninstall "%s"', app)
        redirect(URL(r=request, f='site'))
    elif 'nodelete' in request.vars:
        redirect(URL(r=request, f='site'))
    return dict(app=app)


def cleanup():
    clean = app_cleanup(request.args[0], request)
    if not clean:
        session.flash = T("some files could not be removed")
    else:
        session.flash = T('cache, errors and sessions cleaned')

    redirect(URL(r=request, f='site'))


def compile_app():
    c = app_compile(request.args[0], request)
    if c:
        session.flash = T('application compiled')
    else:
        import traceback
        tb = traceback.format_exc()
        session.flash = DIV(T('Cannot compile: there are errors in your app:',CODE(tb)))    
    redirect(URL(r=request, f='site'))


def remove_compiled_app():
    """ Remove the compiled application """
    remove_compiled_application(apath(request.args[0], r=request))
    session.flash = T('compiled application removed')
    redirect(URL(r=request, f='site'))

    
def delete():
    """ Object delete handler """

    filename = '/'.join(request.args)
    sender = request.vars.sender

    if isinstance(sender, list):  # ## fix a problem with Vista
        sender = sender[0]

    if 'nodelete' in request.vars:
        redirect(URL(r=request, f=sender))
    elif 'delete' in request.vars:
        try:
            os.unlink(apath(filename, r=request))
            session.flash = T('file "%(filename)s" deleted',
                              dict(filename=filename))
        except Exception:
            session.flash = T('unable to delete file "%(filename)s"',
                              dict(filename=filename))
        redirect(URL(r=request, f=sender))
    return dict(filename=filename, sender=sender)
        
def peek():
    """ Visualize object code """

    filename = '/'.join(request.args)

    try:
        data = open(apath(filename, r=request), 'r').read().replace('\r','')
    except IOError:
        session.flash = T('file does not exist')
        redirect(URL(r=request, f='site'))

    extension = filename[filename.rfind('.') + 1:].lower()

    return dict(app=request.args[0],
                filename=filename,
                data=data,
                extension=extension)


def test():
    """ Execute controller tests """

    app = request.args[0]

    if len(request.args) > 1:
        file = request.args[1]
    else:
        file = '.*\.py'

    controllers = listdir(apath('%s/controllers/' % app, r=request), file + '$')

    return dict(app=app, controllers=controllers)

def keepalive():
    return ''

def edit():
    """ File edit handler """
    # Load json only if it is ajax edited...

    filename = '/'.join(request.args)

    # Try to discover the file type
    if filename[-3:] == '.py':
        filetype = 'python'
    elif filename[-5:] == '.html':
        filetype = 'html'
    elif filename[-4:] == '.css':
        filetype = 'css'
    elif filename[-3:] == '.js':
        filetype = 'js'
    else:
        filetype = 'text'

    # ## check if file is not there

    path = apath(filename, r=request)

    if request.vars.revert and os.path.exists(path + '.bak'):
        try:
            data = open(path + '.bak', 'r').read()
            data1 = open(path, 'r').read()
        except IOError:
            session.flash = T('Invalid action')
            if 'from_ajax' in request.vars:
                 return response.json({'error': T('Invalid action')})
            else:
                redirect(URL(r=request, f='site'))

        open(path, 'w').write(data)
        file_hash = md5_hash(data)
        saved_on = time.ctime(os.stat(path)[stat.ST_MTIME])
        open(path + '.bak', 'w').write(data1)
        response.flash = T('file "%s" of %s restored', (filename, saved_on))
    else:
        try:
            data = open(path, 'r').read()
        except IOError:
            session.flash = T('Invalid action')
            if 'from_ajax' in request.vars:
                return response.json({'error': T('Invalid action')})
            else:
                redirect(URL(r=request, f='site'))

        file_hash = md5_hash(data)
        saved_on = time.ctime(os.stat(path)[stat.ST_MTIME])

        if request.vars.file_hash and request.vars.file_hash != file_hash:
            session.flash = T('file changed on disk')
            data = request.vars.data.replace('\r\n', '\n').strip() + '\n'
            open(path + '.1', 'w').write(data)
            if 'from_ajax' in request.vars:
                return response.json({'error': T('file changed on disk'), 'redirect': URL(r=request, f='resolve', args=request.args)})
            else:
                redirect(URL(r=request, f='resolve', args=request.args))
        elif request.vars.data:
            open(path + '.bak', 'w').write(data)
            data = request.vars.data.replace('\r\n', '\n').strip() + '\n'
            open(path, 'w').write(data)
            file_hash = md5_hash(data)
            saved_on = time.ctime(os.stat(path)[stat.ST_MTIME])
            response.flash = T('file saved on %s', saved_on)

    data_or_revert = (request.vars.data or request.vars.revert)

    if data_or_revert and request.args[1] == 'modules':
        # Lets try to reload the modules
        try:
            mopath = '.'.join(request.args[2:])[:-3]
            exec 'import applications.%s.modules.%s' % (request.args[0], mopath)
            reload(sys.modules['applications.%s.modules.%s'
                    % (request.args[0], mopath)])
        except Exception, e:
            response.flash = DIV(T('failed to reload module because:'),PRE(str(e)))

    edit_controller = None
    editviewlinks = None
    view_link = None
    if filetype == 'html' and request.args >= 3:
        cfilename = os.path.join(request.args[0], 'controllers',
                                 request.args[2] + '.py')
        if os.path.exists(apath(cfilename, r=request)):
            edit_controller = URL(r=request, f='edit', args=[cfilename])
            view = request.args[3].replace('.html','')
            view_link = A(T('view'),_href=URL(request.args[0],request.args[2],view))
    elif filetype == 'python' and request.args[1] == 'controllers':
        ## it's a controller file.
        ## Create links to all of the associated view files.
        app = request.args[0]
        viewname = os.path.splitext(request.args[2])[0]
        viewpath = os.path.join(app,'views',viewname)
        aviewpath = apath(viewpath, r=request)
        viewlist = []
        if os.path.exists(aviewpath):
            if os.path.isdir(aviewpath):
                viewlist = glob(os.path.join(aviewpath,'*.html'))
        elif os.path.exists(aviewpath+'.html'):
            viewlist.append(aviewpath+'.html')
        if len(viewlist):
            editviewlinks = []
            for v in viewlist:
                vf = os.path.split(v)[-1]
                vargs = "/".join([viewpath.replace(os.sep,"/"),vf])
                editviewlinks.append(A(T(vf.split(".")[0]),\
                    _href=URL(r=request,f='edit',args=[vargs])))

    if len(request.args) > 2 and request.args[1] == 'controllers':
        controller = (request.args[2])[:-3]
        functions = regex_expose.findall(data)
    else:
        (controller, functions) = (None, None)

    if 'from_ajax' in request.vars:
        return response.json({'file_hash': file_hash, 'saved_on': saved_on, 'functions':functions, 'controller': controller, 'application': request.args[0] })
    else:

        editarea_preferences = {}
        editarea_preferences['FONT_SIZE'] = '10'
        editarea_preferences['FULL_SCREEN'] = 'false'
        editarea_preferences['ALLOW_TOGGLE'] = 'true'
        editarea_preferences['REPLACE_TAB_BY_SPACES'] = '4'
        editarea_preferences['DISPLAY'] = 'onload'
        for key in editarea_preferences:
            if globals().has_key(key):
                editarea_preferences[key]=globals()[key]
        return dict(app=request.args[0],
                    filename=filename,
                    filetype=filetype,
                    data=data,
                    edit_controller=edit_controller,
                    file_hash=file_hash,
                    saved_on=saved_on,
                    controller=controller,
                    functions=functions,
                    view_link=view_link,
                    editarea_preferences=editarea_preferences,
                    editviewlinks=editviewlinks)

def resolve():
    """  """

    filename = '/'.join(request.args)

    if filename[-3:] == '.py':
        filetype = 'python'

    elif filename[-5:] == '.html':
        filetype = 'html'

    elif filename[-4:] == '.css':
        filetype = 'css'

    elif filename[-3:] == '.js':
        filetype = 'js'
    else:
        filetype = 'text'

    # ## check if file is not there

    path = apath(filename, r=request)
    a = open(path, 'r').readlines()

    try:
        b = open(path + '.1', 'r').readlines()
    except IOError:
        session.flash = 'Other file, no longer there'
        redirect(URL(r=request, f='edit', args=request.args))

    d = difflib.ndiff(a, b)

    def leading(line):
        """  """

        # TODO: we really need to comment this
        z = ''
        for (k, c) in enumerate(line):
            if c == ' ':
                z += '&nbsp;'
            elif c == ' \t':
                z += '&nbsp;'
            elif k == 0 and c == '?':
                pass
            else:
                break

        return XML(z)

    def getclass(item):
        """ Determine item class """

        if item[0] == ' ':
            return 'normal'
        if item[0] == '+':
            return 'plus'
        if item[0] == '-':
            return 'minus'

    if request.vars:
        c = ''.join([item[2:] for (i, item) in enumerate(d) if item[0] \
                     == ' ' or 'line%i' % i in request.vars])
        open(path, 'w').write(c)
        session.flash = 'files merged'
        redirect(URL(r=request, f='edit', args=request.args))
    else:
        # Making the short circuit compatible with <= python2.4
        gen_data = lambda index,item: not item[:1] in ['+','-'] and "" \
                   or INPUT(_type='checkbox',
                            _name='line%i' % index,
                            value=item[0] == '+')

        diff = TABLE(*[TR(TD(gen_data(i,item)),
                          TD(item[0]),
                          TD(leading(item[2:]),
                          TT(item[2:].rstrip())), _class=getclass(item))
                       for (i, item) in enumerate(d) if item[0] != '?'])

    return dict(diff=diff, filename=filename)


def edit_language():
    """ Edit language file """

    filename = '/'.join(request.args)

    from gluon.languages import read_dict, write_dict
    strings = read_dict(apath(filename, r=request))
    keys = sorted(strings.keys())
    rows = []
    rows.append(H2(T('Original/Translation')))

    for key in keys:
        name = md5_hash(key)
        if len(key) <= 40:
            elem = INPUT(_type='text', _name=name,value=strings[key],_size=70)
        else:
            elem = TEXTAREA(_name=name, value=strings[key], _cols=70, _rows=5)

        # Making the short circuit compatible with <= python2.4
        k = (strings[key] != key) and key or B(key)

        rows.append(P(k, BR(), elem, TAG.BUTTON(T('delete'),
                            _onclick='return delkey("%s")' % name), _id=name))

    rows.append(INPUT(_type='submit', _value=T('update')))
    form = FORM(*rows)
    if form.accepts(request.vars, keepvalues=True):
        strs = dict()
        for key in keys:
            name = md5_hash(key)
            if form.vars[name]==chr(127): continue
            strs[key] = form.vars[name]
        write_dict(apath(filename, r=request), strs)
        session.flash = T('file saved on %(time)s', dict(time=time.ctime()))
        redirect(URL(r=request,args=request.args))
    return dict(app=request.args[0], filename=filename, form=form)


def htmledit():
    """ Html file edit handler """

    filename = '/'.join(request.args)

    # ## check if file is not there
    data = open(apath(filename, r=request), 'r').read()
    try:
        data = request.vars.data.replace('\r\n', '\n')
        open(apath(filename, r=request), 'w').write(data)
        response.flash = T('file saved on %(time)s',
                           dict(time=time.ctime()))
    except Exception:
        pass

    return dict(app=request.args[0], filename=filename, data=data)


def about():
    """ Read about info """

    app = request.args[0]

    # ## check if file is not there
    about = open(apath('%s/ABOUT' % app, r=request), 'r').read()
    license = open(apath('%s/LICENSE' % app, r=request), 'r').read()

    return dict(app=app, about=WIKI(about), license=WIKI(license))


def design():
    """ Application design handler """

    app = request.args[0]

    if not response.flash and app == request.application:
        msg = T('ATTENTION: you cannot edit the running application!')
        response.flash = msg

    if request.vars.pluginfile!=None:
        filename=os.path.basename(request.vars.pluginfile.filename)
        if plugin_install(app, request.vars.pluginfile.file,
                          request, filename):
            session.flash = T('new plugin installed')
            redirect(URL(r=request,f='design',args=app))
        else:
            session.flash = \
                T('unable to create application "%s"', request.vars.filename)
        redirect(URL(r=request))


    # If we have only pyc files it means that 
    # we cannot design
    if os.path.exists(apath('%s/compiled' % app, r=request)):
        session.flash = \
            T('application is compiled and cannot be designed')
        redirect(URL(r=request, f='site'))

    # Get all models
    models = listdir(apath('%s/models/' % app, r=request), '.*\.py$')
    models=[x.replace('\\','/') for x in models]
    defines = {}
    for m in models:
        data = open(apath('%s/models/%s' % (app, m), r=request), 'r').read()
        defines[m] = regex_tables.findall(data)
        defines[m].sort()

    # Get all controllers
    controllers = sorted(listdir(apath('%s/controllers/' % app, r=request), '.*\.py$'))
    controllers = [x.replace('\\','/') for x in controllers]
    functions = {}
    for c in controllers:
        data = open(apath('%s/controllers/%s' % (app, c), r=request), 'r').read()
        items = regex_expose.findall(data)
        functions[c] = items
    
    # Get all views
    views = sorted(listdir(apath('%s/views/' % app, r=request), '[\w/\-]+\.\w+$'))
    views = [x.replace('\\','/') for x in views]
    extend = {}
    include = {}
    for c in views:
        data = open(apath('%s/views/%s' % (app, c), r=request), 'r').read()
        items = regex_extend.findall(data)

        if items:
            extend[c] = items[0][1]

        items = regex_include.findall(data)
        include[c] = [i[1] for i in items]
    
    # Get all modules
    modules = listdir(apath('%s/modules/' % app, r=request), '.*\.py$')
    modules = modules=[x.replace('\\','/') for x in modules]
    modules.sort()
    
    # Get all static files
    statics = listdir(apath('%s/static/' % app, r=request), '[^\.#].*')
    statics = [x.replace('\\','/') for x in statics]
    statics.sort()
    
    # Get all languages
    languages = listdir(apath('%s/languages/' % app, r=request), '[\w-]*\.py')

    #Get crontab
    cronfolder = apath('%s/cron' % app, r=request)
    if not os.path.exists(cronfolder): os.mkdir(cronfolder)
    crontab = apath('%s/cron/crontab' % app, r=request)
    if not os.path.exists(crontab): open(crontab,'w').write('#crontab')

    plugins=[]
    def filter_plugins(items,plugins):
        plugins+=[item[7:].split('/')[0].split('.')[0] for item in items if item.startswith('plugin_')]
        plugins[:]=list(set(plugins))
        plugins.sort()
        return [item for item in items if not item.startswith('plugin_')]
    
    return dict(app=app,
                models=filter_plugins(models,plugins),
                defines=defines,
                controllers=filter_plugins(controllers,plugins),
                functions=functions,
                views=filter_plugins(views,plugins),
                modules=filter_plugins(modules,plugins),
                extend=extend,
                include=include,
                statics=filter_plugins(statics,plugins),
                languages=languages,
                crontab=crontab,
                plugins=plugins)

def delete_plugin():
    """ Object delete handler """

    app=request.args(0)
    plugin = request.args(1)
    plugin_name='plugin_'+plugin
    if 'nodelete' in request.vars:
        redirect(URL(r=request,f='design',args=app))
    elif 'delete' in request.vars:
        try:
            for folder in ['models','views','controllers','static','modules']:
                path=os.path.join(apath(app,r=request),folder)
                for item in os.listdir(path):
                    if item.startswith(plugin_name): 
                        filename=os.path.join(path,item)
                        if os.path.isdir(filename):
                            shutil.rmtree(filename)
                        else:                            
                            os.unlink(filename)
            session.flash = T('plugin "%(plugin)s" deleted',
                              dict(plugin=plugin))
        except Exception:
            session.flash = T('unable to delete file plugin "%(plugin)s"',
                              dict(plugin=plugin))
        redirect(URL(r=request,f='design',args=request.args(0)))
    return dict(plugin=plugin)

def plugin():
    """ Application design handler """

    app = request.args(0)
    plugin = request.args(1)

    if not response.flash and app == request.application:
        msg = T('ATTENTION: you cannot edit the running application!')
        response.flash = msg

    # If we have only pyc files it means that 
    # we cannot design
    if os.path.exists(apath('%s/compiled' % app, r=request)):
        session.flash = \
            T('application is compiled and cannot be designed')
        redirect(URL(r=request, f='site'))

    # Get all models
    models = listdir(apath('%s/models/' % app, r=request), '.*\.py$')
    models=[x.replace('\\','/') for x in models]
    defines = {}
    for m in models:
        data = open(apath('%s/models/%s' % (app, m), r=request), 'r').read()
        defines[m] = regex_tables.findall(data)
        defines[m].sort()

    # Get all controllers
    controllers = sorted(listdir(apath('%s/controllers/' % app, r=request), '.*\.py$'))
    controllers = [x.replace('\\','/') for x in controllers]
    functions = {}
    for c in controllers:
        data = open(apath('%s/controllers/%s' % (app, c), r=request), 'r').read()
        items = regex_expose.findall(data)
        functions[c] = items
    
    # Get all views
    views = sorted(listdir(apath('%s/views/' % app, r=request), '[\w/\-]+\.\w+$'))
    views = [x.replace('\\','/') for x in views]
    extend = {}
    include = {}
    for c in views:
        data = open(apath('%s/views/%s' % (app, c), r=request), 'r').read()
        items = regex_extend.findall(data)

        if items:
            extend[c] = items[0][1]

        items = regex_include.findall(data)
        include[c] = [i[1] for i in items]
    
    # Get all modules
    modules = listdir(apath('%s/modules/' % app, r=request), '.*\.py$')
    modules = modules=[x.replace('\\','/') for x in modules]
    modules.sort()
    
    # Get all static files
    statics = listdir(apath('%s/static/' % app, r=request), '[^\.#].*')
    statics = [x.replace('\\','/') for x in statics]
    statics.sort()
    
    # Get all languages
    languages = listdir(apath('%s/languages/' % app, r=request), '[\w-]*\.py')

    #Get crontab
    crontab = apath('%s/cron/crontab' % app, r=request)
    if not os.path.exists(crontab): open(crontab,'w').write('#crontab')
    

    def filter_plugins(items):
        regex=re.compile('^plugin_'+plugin+'(/.*|\..*)?$')
        return [item for item in items if regex.match(item)]
    
    return dict(app=app,
                models=filter_plugins(models),
                defines=defines,
                controllers=filter_plugins(controllers),
                functions=functions,
                views=filter_plugins(views),
                modules=filter_plugins(modules),
                extend=extend,
                include=include,
                statics=filter_plugins(statics),
                languages=languages,
                crontab=crontab)


def create_file():
    """ Create files handler """

    try:
        path = apath(request.vars.location, r=request)
        filename = re.sub('[^\w./-]+', '_', request.vars.filename)

        if path[-11:] == '/languages/':
            # Handle language files
            if len(filename) == 0:
                raise SyntaxError
            if not filename[-3:] == '.py':
                filename += '.py'
            app = path.split('/')[-3]
            path=os.path.join(apath(app, r=request),'languages',filename)
            if not os.path.exists(path):
                open(path,'w').write('')
            findT(apath(app, r=request), filename[:-3])
            session.flash = T('language file "%(filename)s" created/updated',
                              dict(filename=filename))
            redirect(request.vars.sender)

        elif path[-8:] == '/models/':
            # Handle python models
            if not filename[-3:] == '.py':
                filename += '.py'

            if len(filename) == 3:
                raise SyntaxError

            fn = re.sub('\W', '', filename[:-3].lower())
            text = '# coding: utf8\n# %s\n%s=DAL("sqlite://%s.db")'
            text = text % (T('try something like'), fn, fn)

        elif path[-13:] == '/controllers/':
            # Handle python controlers
            if not filename[-3:] == '.py':
                filename += '.py'

            if len(filename) == 3:
                raise SyntaxError

            text = '# coding: utf8\n# %s\ndef index(): return dict(message="hello from %s")'
            text = text % (T('try something like'), filename)

        elif path[-7:] == '/views/':
            if request.vars.plugin and not filename.startswith('plugin_%s/' % request.vars.plugin):
                filename = 'plugin_%s/%s' % (request.vars.plugin, filename)
            # Handle template (html) views
            if filename.find('.')<0:
                filename += '.html'
            
            if len(filename) == 5:
                raise SyntaxError

            msg = T('This is the %(filename)s template',
                    dict(filename=filename))
            text = dedent("""
                   {{extend 'layout.html'}}
                   <h1>%s</h1>
                   {{=BEAUTIFY(response._vars)}}""" % msg)

        elif path[-9:] == '/modules/':
            if request.vars.plugin and not filename.startswith('plugin_%s/' % request.vars.plugin):
                filename = 'plugin_%s/%s' % (request.vars.plugin, filename)
            # Handle python module files
            if not filename[-3:] == '.py':
                filename += '.py'

            if len(filename) == 3:
                raise SyntaxError

            text = dedent("""
                   #!/usr/bin/env python 
                   # coding: utf8 
                   from gluon.html import *
                   from gluon.http import *
                   from gluon.validators import *
                   from gluon.sqlhtml import *
                   # request, response, session, cache, T, db(s) 
                   # must be passed and cannot be imported!""")

        elif path[-8:] == '/static/':
            if request.vars.plugin and not filename.startswith('plugin_%s/' % request.vars.plugin):
                filename = 'plugin_%s/%s' % (request.vars.plugin, filename)
            text = ''
        else:
            redirect(request.vars.sender)

        full_filename = os.path.join(path, filename)
        dirpath = os.path.dirname(full_filename)

        if not os.path.exists(dirpath):
            os.makedirs(dirpath)

        if os.path.exists(full_filename):
            raise SyntaxError

        open(full_filename, 'w').write(text)
        session.flash = T('file "%(filename)s" created',
                          dict(filename=full_filename[len(path):]))
        redirect(URL(r=request, f='edit',
                 args=[os.path.join(request.vars.location, filename)]))
    except Exception, e:
        if not isinstance(e,HTTP):
            session.flash = T('cannot create file')

    redirect(request.vars.sender)


def upload_file():
    """ File uploading handler """

    try:
        path = apath(request.vars.location, r=request)

        if request.vars.filename:
            filename = re.sub('[^\w\./]+', '_', request.vars.filename)
        else:
            filename = os.path.split(request.vars.file.filename)[-1]

        if path[-8:] == '/models/' and not filename[-3:] == '.py':
            filename += '.py'

        if path[-9:] == '/modules/' and not filename[-3:] == '.py':
            filename += '.py'

        if path[-13:] == '/controllers/' and not filename[-3:] == '.py':
            filename += '.py'

        if path[-7:] == '/views/' and not filename[-5:] == '.html':
            filename += '.html'

        if path[-11:] == '/languages/' and not filename[-3:] == '.py':
            filename += '.py'

        filename = os.path.join(path, filename)
        dirpath = os.path.dirname(filename)

        if not os.path.exists(dirpath):
            os.makedirs(dirpath)

        open(filename, 'wb').write(request.vars.file.file.read())
        session.flash = T('file "%(filename)s" uploaded',
                          dict(filename=filename[len(path):]))
    except Exception:
        session.flash = T('cannot upload file "%(filename)s"',
                          dict(filename[len(path):]))

    redirect(request.vars.sender)


def errors():
    """ Error handler """

    app = request.args[0]

    for item in request.vars:
        if item[:7] == 'delete_':
            os.unlink(apath('%s/errors/%s' % (app, item[7:]), r=request))

    func = lambda p: os.stat(apath('%s/errors/%s' % (app, p), r=request)).st_mtime
    tickets = sorted(listdir(apath('%s/errors/' % app, r=request), '^\w.*'),
                     key=func,
                     reverse=True)

    return dict(app=app, tickets=tickets)


def make_link(path):
    """ Create a link from a path """
    tryFile = path.replace('\\', '/')

    if os.path.isabs(tryFile) and os.path.isfile(tryFile):
        (folder, filename) = os.path.split(tryFile)
        (base, ext) = os.path.splitext(filename)
        app = request.args[0]
        
        editable = {'controllers': '.py', 'models': '.py', 'views': '.html'}
        for key in editable.keys():
            check_extension = folder.endswith("%s/%s" % (app,key))
            if ext.lower() == editable[key] and check_extension:
                return A('"' + tryFile + '"',
                         _href=URL(r=request,
                         f='edit/%s/%s/%s' % (app, key, filename))).xml()
    return ''


def make_links(traceback):
    """ Make links using the given traceback """

    lwords = traceback.split('"')

    # Making the short circuit compatible with <= python2.4
    result = (len(lwords) != 0) and lwords[0] or ''

    i = 1

    while i < len(lwords):
        link = make_link(lwords[i])

        if link == '':
            result += '"' + lwords[i]
        else:
            result += link

            if i + 1 < len(lwords):
                result += lwords[i + 1]
                i = i + 1

        i = i + 1

    return result


class TRACEBACK(object):
    """ Generate the traceback """

    def __init__(self, text):
        """ TRACEBACK constructor """

        self.s = make_links(CODE(text).xml())

    def xml(self):
        """ Returns the xml """

        return self.s


def ticket():
    """ Ticket handler """

    if len(request.args) != 2:
        session.flash = T('invalid ticket')
        redirect(URL(r=request, f='site'))

    app = request.args[0]
    ticket = request.args[1]
    e = RestrictedError()
    e.load(request, app, ticket)

    return dict(app=app,
                ticket=ticket,
                traceback=TRACEBACK(e.traceback),
                code=e.code,
                layer=e.layer)


def update_languages():
    """ Update avaliable languages """

    app = request.args[0]
    update_all_languages(apath(app, r=request))
    session.flash = T('Language files (static strings) updated')
    redirect(URL(r=request, f='design/' + app))

def twitter():
    session.forget()
    session._unlock(response)
    import gluon.tools
    import gluon.contrib.simplejson as sj
    try:
        page = gluon.tools.fetch('http://twitter.com/web2py?format=json')
        return sj.loads(page)['#timeline']
    except Exception, e:
        return DIV(T('Unable to download because'),PRE(str(e)))

