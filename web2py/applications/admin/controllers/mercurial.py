
from mercurial import cmdutil


_hgignore_content = """\
syntax: glob
*~
*.pyc
*.pyo
*.bak
cache/*
databases/*
sessions/*
errors/*
"""

def commit():

    app = request.args[0]
    path = apath(app, r=request)

    uio = ui.ui()
    uio.quiet = True
    if not os.environ.get('HGUSER') and not uio.config("ui", "username"):
        os.environ['HGUSER'] = 'web2py@localhost'
    try:
        r = hg.repository(ui=uio, path=path)
    except:
        r = hg.repository(ui=uio, path=path, create=True)
    hgignore = os.path.join(path, '.hgignore')
    if not os.path.exists(hgignore):
        open(hgignore, 'w').write(_hgignore_content)
    form = FORM('Comment:',INPUT(_name='comment',requires=IS_NOT_EMPTY()),
                INPUT(_type='submit',_value='Commit'))
    if form.accepts(request.vars,session):
        oldid = r[r.lookup('.')]
        cmdutil.addremove(r)
        r.commit(text=form.vars.comment)
        if r[r.lookup('.')] == oldid:
            response.flash = 'no changes' 
    files = r[r.lookup('.')].files()
    return dict(form=form,files=TABLE(*[TR(file) for file in files]),repo=r)
