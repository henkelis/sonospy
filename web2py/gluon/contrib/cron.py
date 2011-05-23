#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Created by Attila Csipa <web2py@csipa.in.rs>
Modified by Massimo Di Pierro <mdipierro@cs.depaul.edu>
"""

import sys
import os
import threading
import logging
import time
import sched
import re
import datetime
import traceback
import platform
import gluon.portalocker as portalocker
import cPickle
from subprocess import Popen, PIPE, call

# crontype can be 'soft', 'hard', 'external', None
crontype = 'soft'

class extcron(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
        self.setDaemon(False)
        self.path = apppath(dict(web2py_path=os.getcwd()))

    def run(self):
        logging.debug('External cron invocation')
        crondance(self.path, 'ext')

class hardcron(threading.Thread):

    def __init__(self):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self.path = apppath(dict(web2py_path=os.getcwd()))
        self.startup = True
        self.launch()
        self.startup = False

    def launch(self):
        crondance(self.path, 'hard', startup = self.startup)

    def run(self):
        s = sched.scheduler(time.time, time.sleep)
        logging.info('Hard cron daemon started')
        while True:
            now = time.time()
            s.enter(60 - now % 60, 1, self.launch, ())
            s.run()

class softcron(threading.Thread):

    def __init__(self, env):
        threading.Thread.__init__(self)
        self.env = env
        self.cronmaster = 0
        self.softwindow = 120
        self.path = apppath(self.env)
        self.cronmaster = crondance(self.path, 'soft', startup = True)

    def run(self):
        if crontype != 'soft':
            return
        now = time.time()
        # our own thread did a cron check less than a minute ago, don't even
        # bother checking the file
        if self.cronmaster and 60 > now - self.cronmaster:
            logging.debug("Don't bother with cron.master, it's only %s s old"
                           % (now - self.cronmaster))
            return

        logging.debug('Cronmaster stamp: %s, Now: %s'
                      % (self.cronmaster, now))
        if 60 <= now - self.cronmaster:  # new minute, do the cron dance
            self.cronmaster = crondance(self.path, 'soft')    

class Token:
    def __init__(self,path):
        self.path = os.path.join(path, 'cron.master')
        if not os.path.exists(self.path):
            open(self.path,'wb').close()
        self.master = None
        self.now = time.time()

    def acquire(self,startup=False):
        """
        returns the time when the lock is acquired or 
        None if cron already runing
        
        lock is implemnted by writing a pickle (start, stop) in cron.master
        start is time when cron job starts and stop is time when cron completed
        stop == 0 if job started but did not yet complete
        if a cron job started within less than 60 secods, acquire returns None
        if a cron job started before 60 seconds and did not stop, 
        a warning is issue "Stale cron.master detected"
        """
        if portalocker.LOCK_EX == None:
            logging.warning('WEB2PY CRON: Disabled because no file locking')
            return None
        self.master = open(self.path,'rb+')        
        try:
            ret = None
            portalocker.lock(self.master,portalocker.LOCK_EX)
            try:
                (start, stop) =  cPickle.load(self.master)
            except:
                (start, stop) = (0, 1)
            if startup or self.now - start >= 60:
                ret = self.now
                if not stop:
                    # this happens if previous cron job longer than 1 minute
                    logging.warning('WEB2PY CRON: Stale cron.master detected')
                logging.debug('WEB2PY CRON: Acquiring lock')
                self.master.seek(0)
                cPickle.dump((self.now,0),self.master)
        finally:
            portalocker.unlock(self.master)
        if not ret:
            # do this so no need to release
            self.master.close()
        return ret

    def release(self):
        """
        this function writes into cron.msater the time when cron job 
        was completed
        """
        if not self.master.closed:
            portalocker.lock(self.master,portalocker.LOCK_EX)        
            logging.debug('WEB2PY CRON: Releasing cron lock')
            self.master.seek(0)
            (start, stop) =  cPickle.load(self.master)
            if start == self.now: # if this is my lock
                self.master.seek(0)
                cPickle.dump((self.now,time.time()),self.master)
            portalocker.unlock(self.master)
            self.master.close()


def apppath(env=None):
    if 'web2py_path' in env:
        web2py_path = env['web2py_path']
    else:
        web2py_path = os.path.split(env['SCRIPT_FILENAME'])[0]
    return os.path.join(web2py_path, 'applications')


def rangetolist(s, period='min'):
    retval = []
    if s.startswith('*'):
        if period == 'min':
            s = s.replace('*', '0-59', 1)
        elif period == 'hr':
            s = s.replace('*', '0-23', 1)
        elif period == 'dom':
            s = s.replace('*', '1-31', 1)
        elif period == 'mon':
            s = s.replace('*', '1-12', 1)
        elif period == 'dow':
            s = s.replace('*', '0-6', 1)
    m = re.compile(r'(\d+)-(\d+)/(\d+)')
    match = m.match(s)
    if match:
        for i in range(int(match.group(1)), int(match.group(2)) + 1):
            if i % int(match.group(3)) == 0:
                retval.append(i)
    return retval


def parsecronline(line):
    task = {}
    if line.startswith('@reboot'):
        line=line.replace('@reboot', '-1 * * * *')
    elif line.startswith('@yearly'):
        line=line.replace('@yearly', '0 0 1 1 *')
    elif line.startswith('@annually'):
        line=line.replace('@annually', '0 0 1 1 *')
    elif line.startswith('@monthly'):
        line=line.replace('@monthly', '0 0 1 * *')
    elif line.startswith('@weekly'):
        line=line.replace('@weekly', '0 0 * * 0')
    elif line.startswith('@daily'):
        line=line.replace('@daily', '0 0 * * *')
    elif line.startswith('@midnight'):
        line=line.replace('@midnight', '0 0 * * *')
    elif line.startswith('@hourly'):
        line=line.replace('@hourly', '0 * * * *')
    params = line.strip().split(None, 6)
    if len(params) < 7:
        return None
    for (s, id) in zip(params[:5], ['min', 'hr', 'dom', 'mon', 'dow']):
        if not s in [None, '*']:
            task[id] = []
            vals = s.split(',')
            for val in vals:
                if val.find('/') > -1:
                    task[id] += rangetolist(val, id)
                elif val.isdigit() or val=='-1':
                    task[id].append(int(val))
    task['user'] = params[5]
    task['cmd'] = params[6]
    return task


class cronlauncher(threading.Thread):

    def __init__(self, cmd, shell=True):
        threading.Thread.__init__(self)
        if platform.system() == 'Windows':
            shell = False
        elif isinstance(cmd,list):
            cmd = ' '.join(cmd)
        self.cmd = cmd
        self.shell = shell

    def run(self):
        proc = Popen(self.cmd,
                     stdin=PIPE,
                     stdout=PIPE,
                     stderr=PIPE,
                     shell=self.shell)
        (stdoutdata,stderrdata) = proc.communicate()
        if proc.returncode != 0:
            logging.warning(
                'WEB2PY CRON Call returned code %s:\n%s' % \
                    (proc.returncode, stdoutdata+stderrdata))
        else:
            logging.debug('WEB2PY CRON Call retruned success:\n%s' \
                              % stdoutdata)

def crondance(apppath, ctype='soft',startup=False):
    cron_path = os.path.join(apppath,'admin','cron')
    token = Token(cron_path)
    cronmaster = token.acquire(startup=startup)
    if not cronmaster:
        return
    now_s = time.localtime()
    checks=(('min',now_s.tm_min),
            ('hr',now_s.tm_hour),
            ('mon',now_s.tm_mon),
            ('dom',now_s.tm_mday),
            ('dow',now_s.tm_wday))
    
    apps = [x for x in os.listdir(apppath)
            if os.path.isdir(os.path.join(apppath, x))]
        
    for app in apps:
        apath = os.path.join(apppath,app)
        cronpath = os.path.join(apath, 'cron')
        crontab = os.path.join(cronpath, 'crontab')
        if not os.path.exists(crontab):
            continue
        try:
            f = open(crontab, 'rt')
            cronlines = f.readlines()
            lines = [x for x in cronlines if x.strip() and x[0]!='#']
            tasks = [parsecronline(cline) for cline in lines]
        except Exception, e:
            logging.error('WEB2PY CRON: crontab read error %s' % e)
            continue

        for task in tasks:
            commands = [sys.executable]
            if os.path.exists('web2py.py'):
                commands.append('web2py.py')
            citems = [(k in task and not v in task[k]) for k,v in checks]
            task_min= task.get('min',[])
            if not task:
                continue
            elif not startup and task_min == [-1]:
                continue
            elif task_min != [-1] and reduce(lambda a,b: a or b, citems):
                continue
            logging.info('WEB2PY CRON (%s): %s executing %s in %s at %s' \
                             % (ctype, app, task.get('cmd'),
                                os.getcwd(), datetime.datetime.now()))
            action, command, models = False, task['cmd'], ''
            if command.startswith('**'):
                (action,models,command) = (True,'',command[2:])
            elif command.startswith('*'):
                (action,models,command) = (True,'-M',command[1:])
            else:
                action=False
            if action and command.endswith('.py'):
                commands.extend(('-P',
                                 '-N',models,
                                 '-S',app,
                                 '-a','"<recycle>"',
                                 '-R',command))
                shell = True
            elif action:
                commands.extend(('-P',
                                 '-N',models,
                                 '-S',app+'/'+command,
                                 '-a','"<recycle>"'))
                shell = True
            else:
                commands = command
                shell = False
            try:
                print time.ctime()+' '+ctype+' CRON RUNNING %s' % commands
                cronlauncher(commands, shell=shell).start()
            except Exception, e:
                logging.warning(
                    'WEB2PY CRON: Execution error for %s: %s' \
                        % (task.get('cmd'), e))
    token.release()
