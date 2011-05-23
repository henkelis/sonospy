### this works on linux only

try:
    import fcntl
    import subprocess
    import signal
    import os
except:
    session.flash='sorry, only on Unix systems'
    redirect(URL(request.application,'default','site'))

forever=10**8

def kill():
    p = cache.ram('gae_upload',lambda:None,forever)
    if not p or p.poll()!=None:
        return 'oops'
    os.kill(p.pid, signal.SIGKILL)
    cache.ram('gae_upload',lambda:None,-1)

def deploy():
    if not os.path.exists(GAE_APPCFG):
        redirect(URL(request.application,'default','site'))
    regex = re.compile('^\w+$')
    apps = sorted([(file.upper(), file) for file in \
                       os.listdir(apath(r=request)) if regex.match(file)])
    options = [OPTION(item[1]) for item in apps]
    form = FORM(TABLE(TR('Applications to deploy',
                         SELECT(_name='applications',_multiple='multiple',
                                _id='applications',*options)),
                      TR('GAE Email:',
                         INPUT(_name='email',requires=IS_EMAIL())),
                      TR('GAE Password:',
                         INPUT(_name='password',_type='password',
                               requires=IS_NOT_EMPTY())),
                      TR('',INPUT(_type='submit',value='deploy'))))
    cmd = output = errors= "" 
    if form.accepts(request.vars,session):
        try:
            kill()
        except:
            pass
        ignore_apps = [item[1] for item in apps \
                           if not item[1] in request.vars.applications]
        regex = re.compile('\(applications/\(.*')
        yaml = apath('../app.yaml', r=request)
        data=open(yaml,'r').read()
        data = regex.sub('(applications/(%s)/.*)|' % '|'.join(ignore_apps),data)
        open(yaml,'w').write(data)

        path = request.env.web2py_path
        cmd = '%s --email=%s --passin update %s' % \
            (GAE_APPCFG, form.vars.email, path)
        p = cache.ram('gae_upload',
                      lambda s=subprocess,c=cmd:s.Popen(c, shell=True,
                                                        stdin=s.PIPE,
                                                        stdout=s.PIPE,
                                                        stderr=s.PIPE, close_fds=True),-1)
        p.stdin.write(form.vars.password)
        fcntl.fcntl(p.stdout.fileno(), fcntl.F_SETFL, os.O_NONBLOCK) 
        fcntl.fcntl(p.stderr.fileno(), fcntl.F_SETFL, os.O_NONBLOCK) 
    return dict(form=form,command=cmd)

def callback():
    p = cache.ram('gae_upload',lambda:None,forever)
    if not p or p.poll()!=None:
        return '<done/>'
    try:
        output = p.stdout.read()
    except:
        output=''
    try:
        errors = p.stderr.read()        
    except:
        errors=''
    return (output+errors).replace('\n','<br/>')
