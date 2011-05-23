import sys
import cStringIO

FE=10**9

def index():
    app = request.args[0]
    reset()
    return dict(app=app)

def __shell(app, response):
    import code, thread
    from gluon.shell import env
    (shell, lock) = (code.InteractiveInterpreter(), thread.allocate_lock())
    shell.locals = env(app,True)
    response._custom_commit = lambda: None
    response._custom_rollback = lambda: None
    return (shell, lock)

def unlock():
    app = request.args[0]
    (shell, lock) = cache.ram('shell/'+app,lambda a=app,r=response:__shell(a,r),FE)
    if request.vars.rollback:
        shell.runsource("SQLDB.close_all_instances(SQLDB.rollback)")
    else:
        shell.runsource("SQLDB.close_all_instances(SQLDB.commit)")
    redirect(URL(r=request,c='default',f='design',args=app))

def callback():    
    app = request.args[0]
    command = request.vars.statement
    escape = command[:1]!='!'
    if not escape:
        command = command[1:]
    if command == '%reset':
        reset()
        return '*** reset ***'
    elif command[0] == '%':
        try:
            command=session.shell_history[int(command[1:])]
        except ValueError:
            return ''
    session.shell_history.append(command)
    (shell, lock) = cache.ram('shell/'+app,lambda a=app,r=response:__shell(a,r),FE)
    try:
        lock.acquire()
        (oldstdout, oldstderr) = (sys.stdout, sys.stderr)
        sys.stdout = sys.stderr = cStringIO.StringIO()
        shell.runsource(command)
    finally:
        output = sys.stdout.getvalue()
        lock.release()
        (sys.stdout, sys.stderr) = (oldstdout, oldstderr)
    k = len(session.shell_history) - 1
    output = PRE(output)
    return TABLE(TR('In[%i]:'%k,PRE(command)),TR('Out[%i]:'%k,output))

def reset():
    app = request.args[0]
    session.shell_history=[]
    cache.ram('shell/'+app,lambda a=app,r=response:__shell(a,r),0)
    return 'done'
