#!/bin/python
# -*- coding: utf-8 -*-

"""
This file is part of web2py Web Framework (Copyrighted, 2007-2010).
Developed by Massimo Di Pierro <mdipierro@cs.depaul.edu>.
License: GPL v2
"""

from contenttype import contenttype
from storage import Storage, Settings, Messages
from validators import *
from html import *
from sqlhtml import *
from http import *
from utils import web2py_uuid

import base64
import cPickle
import datetime
from email import *
import logging
import sys
import os
import re
import time
import smtplib
import urllib
import urllib2
import Cookie

import serializers
import contrib.simplejson as simplejson
from sql import Field

__all__ = ['Mail', 'Auth', 'Recaptcha', 'Crud', 'Service', 'fetch', 'geocode']

DEFAULT = lambda: None


def validators(*a):
    b = []
    for item in a:
        if isinstance(item, (list, tuple)):
            b = b + list(item)
        else:
            b.append(item)
    return b


class Mail(object):
    """
    Class for configuring and sending emails with alternative text / html
    body, multiple attachments and encryption support

    Works with SMTP and Google App Engine.
    """

    class Attachment(MIMEBase.MIMEBase):
        """
        Email attachment

        Arguments::

            payload: path to file or file-like object with read() method
            filename: name of the attachment stored in message; if set to
                      None, it will be fetched from payload path; file-like
                      object payload must have explicit filename specified
            content_id: id of the attachment; automatically contained within
                        < and >
            content_type: content type of the attachment; if set to None,
                          it will be fetched from filename using gluon.contenttype
                          module
            encoding: encoding of all strings passed to this function (except
                      attachment body)

        Content ID is used to identify attachments within the html body;
        in example, attached image with content ID 'photo' may be used in
        html message as a source of img tag <img src="cid:photo" />.

        Examples::

            #Create attachment from text file:
            attachment = Mail.Attachment('/path/to/file.txt')

            Content-Type: text/plain
            MIME-Version: 1.0
            Content-Disposition: attachment; filename="file.txt"
            Content-Transfer-Encoding: base64

            SOMEBASE64CONTENT=

            #Create attachment from image file with custom filename and cid:
            attachment = Mail.Attachment('/path/to/file.png',
                                             filename='photo.png',
                                             content_id='photo')

            Content-Type: image/png
            MIME-Version: 1.0
            Content-Disposition: attachment; filename="photo.png"
            Content-Id: <photo>
            Content-Transfer-Encoding: base64

            SOMEOTHERBASE64CONTENT=
        """

        def __init__(
            self,
            payload,
            filename=None,
            content_id=None,
            content_type=None,
            encoding='utf-8'):
            if isinstance(payload, str):
                if filename == None:
                    filename = os.path.basename(payload)
                handle = open(payload, 'rb')
                payload = handle.read()
                handle.close()
            else:
                if filename == None:
                    raise Exception('Missing attachment name')
                payload = payload.read()
            filename = filename.encode(encoding)
            if content_type == None:
                content_type = contenttype(filename)
            MIMEBase.MIMEBase.__init__(self, *content_type.split('/', 1))
            self.set_payload(payload)
            self['Content-Disposition'] = 'attachment; filename="%s"' % filename
            if content_id != None:
                self['Content-Id'] = '<%s>' % content_id.encode(encoding)
            Encoders.encode_base64(self)

    def __init__(self, server=None, sender=None, login=None, tls=True):
        """
        Main Mail object

        Arguments::

            server: SMTP server address in address:port notation
            sender: sender email address
            login: sender login name and password in login:password notation
                   or None if no authentication is required
            tls: enables/disables encryption (True by default)

        In Google App Engine use::

            server='gae'

        For sake of backward compatibility all fields are optional and default
        to None, however, to be able to send emails at least server and sender
        must be specified. They are available under following fields:

            self.settings.server
            self.settings.sender
            self.settings.login

        Examples::

            #Create Mail object with authentication data for remote server:
            mail = Mail('example.com:25', 'me@example.com', 'me:password')
        """

        self.settings = Settings()
        self.settings.server = server
        self.settings.sender = sender
        self.settings.login = login
        self.settings.tls = tls
        self.result = {}
        self.error = None

    def send(
        self,
        to,
        subject='None',
        message='None',
        attachments=None,
        cc=None,
        bcc=None,
        reply_to=None,
        encoding='utf-8'
        ):
        """
        Sends an email using data specified in constructor

        Arguments::

            to: list or tuple of receiver addresses; will also accept single
                object
            subject: subject of the email
            message: email body text; depends on type of passed object:
                     if 2-list or 2-tuple is passed: first element will be
                     source of plain text while second of html text;
                     otherwise: object will be the only source of plain text
                     and html source will be set to None;
                     If text or html source is:
                     None: content part will be ignored,
                     string: content part will be set to it,
                     file-like object: content part will be fetched from
                                       it using it's read() method
            attachments: list or tuple of Mail.Attachment objects; will also
                         accept single object
            cc: list or tuple of carbon copy receiver addresses; will also
                accept single object
            bcc: list or tuple of blind carbon copy receiver addresses; will
                also accept single object
            reply_to: address to which reply should be composed
            encoding: encoding of all strings passed to this method (including
                      message bodies)

        Examples::

            #Send plain text message to single address:
            mail.send('you@example.com',
                      'Message subject',
                      'Plain text body of the message')

            #Send text and html message to three addresses (two in cc):
            mail.send('you@example.com',
                      'Message subject',
                      ('Plain text body', <html>html body</html>),
                      cc=['other1@example.com', 'other2@example.com'])

            #Send html only message with image attachment available from
            the message by 'photo' content id:
            mail.send('you@example.com',
                      'Message subject',
                      (None, '<html><img src="cid:photo" /></html>'),
                      Mail.Attachment('/path/to/photo.jpg'
                                      content_id='photo'))

            #Send email with two attachments and no body text
            mail.send('you@example.com,
                      'Message subject',
                      None,
                      [Mail.Attachment('/path/to/fist.file'),
                       Mail.Attachment('/path/to/second.file')])

        Returns True on success, False on failure.

        Before return, method updates two object's fields:
        self.result: return value of smtplib.SMTP.sendmail() or GAE's
                     mail.send_mail() method
        self.error: Exception message or None if above was successful
        """

        if not isinstance(self.settings.server, str):
            raise Exception('Server address not specified')
        if not isinstance(self.settings.sender, str):
            raise Exception('Sender address not specified')
        if isinstance(to, str):
            to = [to]
        else:
            to = list(to)
        if len(to) == 0:
            raise Exception('Target receiver address not specified')
        payload = MIMEMultipart.MIMEMultipart('related')
        payload['To'] = ', '.join(to).decode(encoding).encode('utf-8')
        if reply_to != None:
            payload['Reply-To'] = reply_to.decode(encoding).encode('utf-8')
        payload['Subject'] = subject.decode(encoding).encode('utf-8')
        if cc != None:
            if not isinstance(cc, (list, tuple)):
                cc = [cc]
            payload['Cc'] = ', '.join(cc).decode(encoding).encode('utf-8')
            to.extend(cc)
        if bcc != None:
            if not isinstance(bcc, (list, tuple)):
                bcc = [bcc]
            payload['Bcc'] = ', '.join(bcc).decode(encoding).encode('utf-8')
            to.extend(bcc)
        if message == None:
            text = html = None
        elif isinstance(message, (list, tuple)):
            text, html = message
        else:
            text = message
            html = None
        if text != None or html != None:
            attachment = MIMEMultipart.MIMEMultipart('alternative')
            if text != None:
                if isinstance(text, str):
                    text = text.decode(encoding).encode('utf-8')
                else:
                    text = text.read().decode(encoding).encode('utf-8')
                attachment.attach(MIMEText.MIMEText(text))
            if html != None:
                if isinstance(html, str):
                    html = html.decode(encoding).encode('utf-8')
                else:
                    html = html.read().decode(encoding).encode('utf-8')
                attachment.attach(MIMEText.MIMEText(html, 'html'))
            payload.attach(attachment)
        if attachments == None:
            pass
        elif isinstance(attachments, (list, tuple)):
            for attachment in attachments:
                payload.attach(attachment)
        else:
            payload.attach(attachments)
        result = {}
        try:
            if self.settings.server == 'gae':
                from google.appengine.api import mail
                result = mail.send_mail(sender=self.settings.sender, to=to,
                                        subject=subject, body=text)
            else:
                server = smtplib.SMTP(*self.settings.server.split(':'))
                if self.settings.login != None:
                    if self.settings.tls:
                        server.ehlo()
                        server.starttls()
                        server.ehlo()
                    server.login(*self.settings.login.split(':'))
                result = server.sendmail(self.settings.sender, to, payload.as_string())
                server.quit()
        except Exception, e:
            logging.warn('Mail.send failure:%s' % e)
            self.result = result
            self.error = e
            return False
        self.result = result
        self.error = None
        return True


class Recaptcha(DIV):

    API_SSL_SERVER = 'https://api-secure.recaptcha.net'
    API_SERVER = 'http://api.recaptcha.net'
    VERIFY_SERVER = 'api-verify.recaptcha.net'

    def __init__(
        self,
        request,
        public_key='',
        private_key='',
        use_ssl=False,
        error=None,
        error_message='invalid',
        ):
        self.remote_addr = request.env.remote_addr
        self.public_key = public_key
        self.private_key = private_key
        self.use_ssl = use_ssl
        self.error = error
        self.errors = Storage()
        self.error_message = error_message
        self.components = []
        self.attributes = {}
        self.label = 'Verify:'
        self.comment = ''

    def _validate(self):

        # for local testing:

        recaptcha_challenge_field = \
            self.request_vars.recaptcha_challenge_field
        recaptcha_response_field = \
            self.request_vars.recaptcha_response_field
        private_key = self.private_key
        remoteip = self.remote_addr
        if not (recaptcha_response_field and recaptcha_challenge_field
                 and len(recaptcha_response_field)
                 and len(recaptcha_challenge_field)):
            self.errors['captcha'] = self.error_message
            return False
        params = urllib.urlencode({
            'privatekey': private_key,
            'remoteip': remoteip,
            'challenge': recaptcha_challenge_field,
            'response': recaptcha_response_field,
            })
        request = urllib2.Request(
            url='http://%s/verify' % self.VERIFY_SERVER,
            data=params,
            headers={'Content-type': 'application/x-www-form-urlencoded',
                        'User-agent': 'reCAPTCHA Python'})
        httpresp = urllib2.urlopen(request)
        return_values = httpresp.read().splitlines()
        httpresp.close()
        return_code = return_values[0]
        if return_code == 'true':
            del self.request_vars.recaptcha_challenge_field
            del self.request_vars.recaptcha_response_field
            self.request_vars.captcha = ''
            return True
        self.errors['captcha'] = self.error_message
        return False

    def xml(self):
        public_key = self.public_key
        use_ssl = (self.use_ssl, )
        error_param = ''
        if self.error:
            error_param = '&error=%s' % self.error
        if use_ssl:
            server = self.API_SSL_SERVER
        else:
            server = self.API_SERVER
        captcha = DIV(SCRIPT(_type="text/javascript",
                             _src="%s/challenge?k=%s%s" % (server,public_key,error_param)),
                      TAG.noscript(IFRAME(_src="%s/noscript?k=%s%s" % (server,public_key,error_param),
                                           _height="300",_width="500",_frameborder="0"), BR(),
                                   INPUT(_type='hidden', _name='recaptcha_response_field', 
                                         _value='manual_challenge')), _id='recaptcha')
        if not self.errors.captcha:
            return XML(captcha).xml()
        else:
            captcha.append(DIV(self.errors['captcha'], _class='error'))
            return XML(captcha).xml()


class Auth(object):
    """
    Class for authentication, authorization, role based access control.

    Includes:

    - registration and profile
    - login and logout
    - username and password retrieval
    - event logging
    - role creation and assignment
    - user defined group/role based permission

    Authentication Example::

        from contrib.utils import *
        mail=Mail()
        mail.settings.server='smtp.gmail.com:587'
        mail.settings.sender='you@somewhere.com'
        mail.settings.login='username:password'
        auth=Auth(globals(), db)
        auth.settings.mailer=mail
        # auth.settings....=...
        auth.define_tables()
        def authentication():
            return dict(form=auth())

    exposes:

    - http://.../{application}/{controller}/authentication/login
    - http://.../{application}/{controller}/authentication/logout
    - http://.../{application}/{controller}/authentication/register
    - http://.../{application}/{controller}/authentication/verify_email
    - http://.../{application}/{controller}/authentication/retrieve_username
    - http://.../{application}/{controller}/authentication/retrieve_password
    - http://.../{application}/{controller}/authentication/reset_password
    - http://.../{application}/{controller}/authentication/profile
    - http://.../{application}/{controller}/authentication/change_password

    On registration a group with role=new_user.id is created
    and user is given membership of this group.

    You can create a group with::

        group_id=auth.add_group('Manager', 'can access the manage action')
        auth.add_permission(group_id, 'access to manage')

    Here \"access to manage\" is just a user defined string.
    You can give access to a user::

        auth.add_membership(group_id, user_id)

    If user id is omitted, the logged in user is assumed

    Then you can decorate any action::

        @auth.requires_permission('access to manage')
        def manage():
            return dict()

    You can restrict a permission to a specific table::

        auth.add_permission(group_id, 'edit', db.sometable)
        @auth.requires_permission('edit', db.sometable)

    Or to a specific record::

        auth.add_permission(group_id, 'edit', db.sometable, 45)
        @auth.requires_permission('edit', db.sometable, 45)

    If authorization is not granted calls::

        auth.settings.on_failed_authorization

    Other options::

        auth.settings.mailer=None
        auth.settings.expiration=3600 # seconds

        ...

        ### these are messages that can be customized
        ...
    """


    def url(self, f=None, args=[], vars={}):
        return self.environment.URL(r=self.environment.request,
                                    c=self.settings.controller,
                                    f=f, args=args, vars=vars)

    def __init__(self, environment, db=None, controller='default'):
        """
        auth=Auth(globals(), db)

        - globals() has to be the web2py environment including
          request, response, session
        - db has to be the database where to create tables for authentication

        """

        self.environment = Storage(environment)
        self.db = db
        request = self.environment.request
        session = self.environment.session
        auth = session.auth
        if auth and auth.last_visit and auth.last_visit\
             + datetime.timedelta(days=0, seconds=auth.expiration)\
             > request.now:
            self.user = auth.user
            self.user_id = self.user.id
            auth.last_visit = request.now
        else:
            self.user = None
            self.user_id = None
            session.auth = None
        self.settings = Settings()

        # ## what happens after login?

        # ## what happens after registration?

        self.settings.actions_disabled = []
        self.settings.reset_password_requires_verification = False
        self.settings.registration_requires_verification = False
        self.settings.registration_requires_approval = False
        self.settings.alternate_requires_registration = False
        self.settings.create_user_groups = True

        self.settings.controller = controller
        self.settings.login_url = self.url('user', args='login')
        self.settings.logged_url = self.url('user', args='profile')
        self.settings.download_url = self.url('download')
        self.settings.mailer = None
        self.settings.login_captcha = None
        self.settings.register_captcha = None
        self.settings.captcha = None
        self.settings.expiration = 3600         # one day
        self.settings.long_expiration = 3600*30 # one month
        self.settings.remember_me_form = True
        self.settings.allow_basic_login = False

        self.settings.on_failed_authorization = self.url('user',
                                                         args='not_authorized')

        # ## table names to be used

        self.settings.password_field = 'password'
        self.settings.table_user_name = 'auth_user'
        self.settings.table_group_name = 'auth_group'
        self.settings.table_membership_name = 'auth_membership'
        self.settings.table_permission_name = 'auth_permission'
        self.settings.table_event_name = 'auth_event'

        # ## if none, they will be created

        self.settings.table_user = None
        self.settings.table_group = None
        self.settings.table_membership = None
        self.settings.table_permission = None
        self.settings.table_event = None

        # ##

        self.settings.showid = False

        # ## these should be functions or lambdas

        self.settings.login_next = self.url('index')
        self.settings.login_onvalidation = None
        self.settings.login_onaccept = None
        self.settings.login_methods = [self]
        self.settings.login_form = self
        self.settings.login_email_validate = True

        self.settings.logout_next = self.url('index')

        self.settings.register_next = self.url('index')
        self.settings.register_onvalidation = None
        self.settings.register_onaccept = None

        self.settings.verify_email_next = self.url('user', args='login')
        self.settings.verify_email_onaccept = None

        self.settings.profile_next = self.url('index')
        self.settings.retrieve_username_next = self.url('index')
        self.settings.retrieve_password_next = self.url('index')
        self.settings.request_reset_password_next = self.url('user', args='login')
        self.settings.reset_password_next = self.url('user', args='login')
        self.settings.change_password_next = self.url('index')

        self.settings.hmac_key = None


        # ## these are messages that can be customized
        self.messages = Messages(None)
        self.messages.submit_button = 'Submit'
        self.messages.verify_password = 'Verify Password'
        self.messages.delete_label = 'Check to delete:'
        self.messages.function_disabled = 'Function disabled'
        self.messages.access_denied = 'Insufficient privileges'
        self.messages.registration_verifying = 'Registration needs verification'
        self.messages.registration_pending = 'Registration is pending approval'
        self.messages.login_disabled = 'Login disabled by administrator'
        self.messages.logged_in = 'Logged in'
        self.messages.email_sent = 'Email sent'
        self.messages.unable_to_send_email = 'Unable to send email'
        self.messages.email_verified = 'Email verified'
        self.messages.logged_out = 'Logged out'
        self.messages.registration_successful = 'Registration successful'
        self.messages.invalid_email = 'Invalid email'
        self.messages.unable_send_email = 'Unable to send email'
        self.messages.invalid_login = 'Invalid login'
        self.messages.invalid_user = 'Invalid user'
        self.messages.invalid_password = 'Invalid password'
        self.messages.is_empty = "Cannot be empty"
        self.messages.mismatched_password = "Password fields don't match"
        self.messages.verify_email = \
            'Click on the link http://...verify_email/%(key)s to verify your email'
        self.messages.verify_email_subject = 'Email verification'
        self.messages.username_sent = 'Your username was emailed to you'
        self.messages.new_password_sent = 'A new password was emailed to you'
        self.messages.password_changed = 'Password changed'
        self.messages.retrieve_username = 'Your username is: %(username)s'
        self.messages.retrieve_username_subject = 'Username retrieve'
        self.messages.retrieve_password = 'Your password is: %(password)s'
        self.messages.retrieve_password_subject = 'Password retrieve'
        self.messages.reset_password = \
            'Click on the link http://...reset_password/%(key)s to reset your password'
        self.messages.reset_password_subject = 'Password reset'
        self.messages.invalid_reset_password = 'Invalid reset password'
        self.messages.profile_updated = 'Profile updated'
        self.messages.new_password = 'New password'
        self.messages.old_password = 'Old password'
        self.messages.group_description = \
            'Group uniquely assigned to user %(id)s'

        self.messages.register_log = 'User %(id)s Registered'
        self.messages.login_log = 'User %(id)s Logged-in'
        self.messages.logout_log = 'User %(id)s Logged-out'
        self.messages.profile_log = 'User %(id)s Profile updated'
        self.messages.verify_email_log = 'User %(id)s Verification email sent'
        self.messages.retrieve_username_log = 'User %(id)s Username retrieved'
        self.messages.retrieve_password_log = 'User %(id)s Password retrieved'
        self.messages.reset_password_log = 'User %(id)s Password reset'
        self.messages.change_password_log = 'User %(id)s Password changed'
        self.messages.add_group_log = 'Group %(group_id)s created'
        self.messages.del_group_log = 'Group %(group_id)s deleted'
        self.messages.add_membership_log = None
        self.messages.del_membership_log = None
        self.messages.has_membership_log = None
        self.messages.add_permission_log = None
        self.messages.del_permission_log = None
        self.messages.has_permission_log = None

        self.messages.label_first_name = 'First name'
        self.messages.label_last_name = 'Last name'
        self.messages.label_email = 'E-mail'
        self.messages.label_password = 'Password'
        self.messages.label_registration_key = 'Registration key'
        self.messages.label_reset_password_key = 'Reset Password key'
        self.messages.label_role = 'Role'
        self.messages.label_description = 'Description'
        self.messages.label_user_id = 'User ID'
        self.messages.label_group_id = 'Group ID'
        self.messages.label_name = 'Name'
        self.messages.label_table_name = 'Table name'
        self.messages.label_record_id = 'Record ID'
        self.messages.label_time_stamp = 'Timestamp'
        self.messages.label_client_ip = 'Client IP'
        self.messages.label_origin = 'Origin'
        self.messages.label_remember_me = "Remember me (for 30 days)"
        self.messages['T'] = self.environment.T
        self.messages.lock_keys = True

        # for "remember me" option
        response = self.environment.response
        if auth  and  auth.remember: #when user wants to be logged in for longer
            #import time
            #t = time.strftime(
            #    "%a, %d-%b-%Y %H:%M:%S %Z",
            #    time.gmtime(time.time() + auth.expiration) # one month longer
            #)
            # sets for appropriate cookie an appropriate expiration time
            response.cookies[response.session_id_name]["expires"] = auth.expiration

    def _HTTP(self, *a, **b):
        """
        only used in lambda: self._HTTP(404)
        """

        raise HTTP(*a, **b)

    def __call__(self):
        """
        usage:

        def authentication(): return dict(form=auth())
        """

        request = self.environment.request
        args = request.args
        if not args:
            redirect(self.url(args='login'))
        elif args[0] in self.settings.actions_disabled:
            raise HTTP(404)
        if args[0] == 'login':
            return self.login()
        elif args[0] == 'logout':
            return self.logout()
        elif args[0] == 'register':
            return self.register()
        elif args[0] == 'verify_email':
            return self.verify_email()
        elif args[0] == 'retrieve_username':
            return self.retrieve_username()
        elif args[0] == 'retrieve_password':
            return self.retrieve_password()
        elif args[0] == 'reset_password':
            return self.reset_password()
        elif args[0] == 'request_reset_password':
            return self.request_reset_password()
        elif args[0] == 'change_password':
            return self.change_password()
        elif args[0] == 'profile':
            return self.profile()
        elif args[0] == 'groups':
            return self.groups()
        elif args[0] == 'impersonate':
            return self.impersonate()
        elif args[0] == 'not_authorized':
            return self.not_authorized()
        else:
            raise HTTP(404)

    def __get_migrate(self, tablename, migrate=True):

        if type(migrate).__name__ == 'str':
            return (migrate + tablename + '.table')
        elif migrate == False:
            return False
        else:
            return True

    def define_tables(self, migrate=True):
        """
        to be called unless tables are defined manually

        usages::

            # defines all needed tables and table files
            # 'myprefix_auth_user.table', ...
            auth.define_tables(migrate='myprefix_')

            # defines all needed tables without migration/table files
            auth.define_tables(migrate=False)

        """

        db = self.db
        if not self.settings.table_user_name in db.tables:
            passfield = self.settings.password_field            
            table = db.define_table(
                self.settings.table_user_name,
                Field('first_name', length=128, default='',
                        label=self.messages.label_first_name),
                Field('last_name', length=128, default='',
                        label=self.messages.label_last_name),
                # Field('username', length=128, default=''),
                Field('email', length=512, default='',
                        label=self.messages.label_email),
                Field(passfield, 'password', length=512,
                         readable=False, label=self.messages.label_password),
                Field('registration_key', length=512,
                        writable=False, readable=False, default='',
                        label=self.messages.label_registration_key),
                Field('reset_password_key', length=512,
                        writable=False, readable=False, default='',
                        label=self.messages.label_reset_password_key),
                migrate=\
                    self.__get_migrate(self.settings.table_user_name, migrate),
                format='%(first_name)s %(last_name)s (%(id)s)')
            table.first_name.requires = \
                IS_NOT_EMPTY(error_message=self.messages.is_empty)
            table.last_name.requires = \
                IS_NOT_EMPTY(error_message=self.messages.is_empty)
            table[passfield].requires = [CRYPT(key=self.settings.hmac_key)]
            table.email.requires = \
                [IS_EMAIL(error_message=self.messages.invalid_email),
                 IS_NOT_IN_DB(db, '%s.email' % self.settings.table_user_name)]
            table.registration_key.default = ''
        self.settings.table_user = db[self.settings.table_user_name]
        if not self.settings.table_group_name in db.tables:
            table = db.define_table(
                self.settings.table_group_name,
                Field('role', length=512, default='',
                        label=self.messages.label_role),
                Field('description', 'text',
                        label=self.messages.label_description),
                migrate=self.__get_migrate(
                    self.settings.table_group_name, migrate),
                format = '%(role)s (%(id)s)')
            table.role.requires = IS_NOT_IN_DB(db, '%s.role'
                 % self.settings.table_group_name)
        self.settings.table_group = db[self.settings.table_group_name]
        if not self.settings.table_membership_name in db.tables:
            table = db.define_table(
                self.settings.table_membership_name,
                Field('user_id', self.settings.table_user,
                        label=self.messages.label_user_id),
                Field('group_id', self.settings.table_group,
                        label=self.messages.label_group_id),
                migrate=self.__get_migrate(
                    self.settings.table_membership_name, migrate))
            table.user_id.requires = IS_IN_DB(db, '%s.id' %
                    self.settings.table_user_name,
                    '%(first_name)s %(last_name)s (%(id)s)')
            table.group_id.requires = IS_IN_DB(db, '%s.id' %
                    self.settings.table_group_name,
                    '%(role)s (%(id)s)')
        self.settings.table_membership = db[self.settings.table_membership_name]
        if not self.settings.table_permission_name in db.tables:
            table = db.define_table(
                self.settings.table_permission_name,
                Field('group_id', self.settings.table_group,
                        label=self.messages.label_group_id),
                Field('name', default='default', length=512,
                        label=self.messages.label_name),
                Field('table_name', length=512,
                        label=self.messages.label_table_name),
                Field('record_id', 'integer',
                        label=self.messages.label_record_id),
                migrate=self.__get_migrate(
                    self.settings.table_permission_name, migrate))
            table.group_id.requires = IS_IN_DB(db, '%s.id' %
                    self.settings.table_group_name,
                    '%(role)s (%(id)s)')
            table.name.requires = IS_NOT_EMPTY(error_message=self.messages.is_empty)
            table.table_name.requires = IS_IN_SET(self.db.tables)
            table.record_id.requires = IS_INT_IN_RANGE(0, 10 ** 9)
        self.settings.table_permission = db[self.settings.table_permission_name]
        if not self.settings.table_event_name in db.tables:
            table  = db.define_table(
                self.settings.table_event_name,
                Field('time_stamp', 'datetime',
                        default=self.environment.request.now,
                        label=self.messages.label_time_stamp),
                Field('client_ip',
                        default=self.environment.request.client,
                        label=self.messages.label_client_ip),
                Field('user_id', self.settings.table_user, default=None,
                        label=self.messages.label_user_id),
                Field('origin', default='auth', length=512,
                        label=self.messages.label_origin),
                Field('description', 'text', default='',
                        label=self.messages.label_description),
                migrate=self.__get_migrate(
                    self.settings.table_event_name, migrate))
            table.user_id.requires = IS_IN_DB(db, '%s.id' %
                    self.settings.table_user_name,
                    '%(first_name)s %(last_name)s (%(id)s)')
            table.origin.requires = IS_NOT_EMPTY(error_message=self.messages.is_empty)
            table.description.requires = IS_NOT_EMPTY(error_message=self.messages.is_empty)
        self.settings.table_event = db[self.settings.table_event_name]

    def log_event(self, description, origin='auth'):
        """
        usage::

            auth.log_event(description='this happened', origin='auth')
        """

        if self.is_logged_in():
            user_id = self.user.id
        else:
            user_id = None  # user unknown
        self.settings.table_event.insert(description=description,
                                         origin=origin, user_id=user_id)

    def get_or_create_user(self, keys):
        """
        Used for alternate login methods:
            If the user exists already then password is updated.
            If the user doesn't yet exist, then they are created.
        """
        if 'username' in keys:
            username = 'username'
        elif 'email' in keys:
            username = 'email'
        else:
            raise SyntaxError, "user must have username or email"
        table_user = self.settings.table_user
        passfield = self.settings.password_field
        user = self.db(table_user[username] == keys[username]).select().first()
        if user:
            if passfield in keys and keys[passfield]:
                user.update_record(**{passfield: keys[passfield],
                                      'registration_key': ''})
        else:
            d = {username: keys[username],
               'first_name': keys.get('first_name', keys[username]),
               'last_name': keys.get('last_name', ''),
               'registration_key': ''}
            keys = dict([(k, v) for (k, v) in keys.items() \
                           if k in table_user.fields])
            d.update(keys)
            user_id = table_user.insert(**d)
            if self.settings.create_user_groups:
                group_id = self.add_group("user_%s" % user_id)
                self.add_membership(group_id, user_id)
            user = table_user[user_id]
        return user

    def basic(self):
        if not self.settings.allow_basic_login:
            return False
        basic = self.environment.request.env.http_authorization
        if not basic or not basic[:6].lower() == 'basic ':
            return False
        (username, password) = base64.b64decode(basic[6:]).split(':')
        return self.login_bare(username, password)

    def login_bare(self, username, password):
        """
        logins user
        """

        request = self.environment.request
        session = self.environment.session
        table_user = self.settings.table_user
        if 'username' in table_user.fields:
            userfield = 'username'
        else:
            userfield = 'email'
        passfield = self.settings.password_field
        user = self.db(table_user[userfield] == username).select().first()
        password = table_user[passfield].validate(password)[0]
        if user:
            if not user.registration_key and user[passfield] == password:
                user = Storage(table_user._filter_fields(user, id=True))
                session.auth = Storage(user=user, last_visit=request.now,
                                       expiration=self.settings.expiration)
                self.user = user
                return user
        return False

    def login(
        self,
        next=DEFAULT,
        onvalidation=DEFAULT,
        onaccept=DEFAULT,
        log=DEFAULT,
        ):
        """
        returns a login form

        .. method:: Auth.login([next=DEFAULT [, onvalidation=DEFAULT
            [, onaccept=DEFAULT [, log=DEFAULT]]]])

        """

        table_user = self.settings.table_user
        if 'username' in table_user.fields:
            username = 'username'
        else:
            username = 'email'
        if 'username' in table_user.fields or not self.settings.login_email_validate:
            tmpvalidator = IS_NOT_EMPTY(error_message=self.messages.is_empty)
        else:
            tmpvalidator = IS_EMAIL(error_message=self.messages.invalid_email)
        old_requires = table_user[username].requires
        table_user[username].requires = tmpvalidator
        request = self.environment.request
        response = self.environment.response
        session = self.environment.session
        passfield = self.settings.password_field
        if next == DEFAULT:
            next = request.get_vars._next \
                or request.post_vars._next \
                or self.settings.login_next
        if onvalidation == DEFAULT:
            onvalidation = self.settings.login_onvalidation
        if onaccept == DEFAULT:
            onaccept = self.settings.login_onaccept
        if log == DEFAULT:
            log = self.messages.login_log

        user = None # default

        # do we use our own login form, or from a central source?
        if self.settings.login_form == self:
            form = SQLFORM(
                table_user,
                fields=[username, passfield],
                hidden=dict(_next=next),
                showid=self.settings.showid,
                submit_button=self.messages.submit_button,
                delete_label=self.messages.delete_label,
                )

            if self.settings.remember_me_form:
                ## adds a new input checkbox "remember me for longer"
                form[0].insert(-1, TR(
                    "",
                    TD(
                        INPUT(_type='checkbox',
                            _class='checkbox',
                            _id="auth_user_remember",
                            _name="remember",
                        ),
                        LABEL(
                            self.messages.label_remember_me,
                            _for="auth_user_remember",
                        ),
                    ),
                    ""
                ))
 
            captcha = self.settings.login_captcha or self.settings.captcha
            if captcha:
                form[0].insert(-1, TR(LABEL(captcha.label), 
                                      captcha,captcha.comment,
                                      _id = 'capctha__row'))
            accepted_form = False
            if form.accepts(request.post_vars, session,
                            formname='login', dbio=False,
                            onvalidation=onvalidation):
                accepted_form = True
                # check for username in db
                user = self.db(table_user[username] == form.vars[username]).select().first()
                if user:
                    # user in db, check if registration pending or disabled
                    temp_user = user
                    if temp_user.registration_key == 'pending':
                        response.flash = self.messages.registration_pending
                        return form
                    elif temp_user.registration_key == 'disabled':
                        response.flash = self.messages.login_disabled
                        return form
                    elif temp_user.registration_key.strip():
                        response.flash = \
                            self.messages.registration_verifying
                        return form
                    # try alternate logins 1st as these have the current version of the password
                    user = None
                    for login_method in self.settings.login_methods:
                        if login_method != self and \
                                login_method(request.vars[username],
                                             request.vars[passfield]):
                            if not self in self.settings.login_methods:
                                # do not store password in db
                                form.vars[passfield] = None
                            user = self.get_or_create_user(form.vars)
                            break
                    if not user:
                        # alternates have failed, maybe because service inaccessible
                        if self.settings.login_methods[0] == self:
                            # try logging in locally using cached credentials
                            if temp_user[passfield] == form.vars.get(passfield, ''):
                                # success
                                user = temp_user
                else:
                    # user not in db
                    if not self.settings.alternate_requires_registration:
                        # we're allowed to auto-register users from external systems
                        for login_method in self.settings.login_methods:
                            if login_method != self and \
                                    login_method(request.vars[username],
                                                 request.vars[passfield]):
                                if not self in self.settings.login_methods:
                                    # do not store password in db
                                    form.vars[passfield] = None
                                user = self.get_or_create_user(form.vars)
                                break
                if not user:
                    # invalid login
                    session.flash = self.messages.invalid_login
                    redirect(self.url(args=request.args))
        else:
            # use a central authentication server
            cas = self.settings.login_form
            cas_user = cas.get_user()
            if cas_user:
                cas_user[passfield] = None
                user = self.get_or_create_user(cas_user)
            else:
                # we need to pass through login again before going on
                next = URL(r=request) + '?_next=' + next
                redirect(cas.login_url(next))

        # process authenticated users
        if user:
            user = Storage(table_user._filter_fields(user, id=True))

            if request.vars.has_key("remember"):
                # user wants to be logged in for longer
                session.auth = Storage(
                    user = user,
                    last_visit = request.now,
                    expiration = self.settings.long_expiration,
                    remember = True,
                )
            else:
                # user doesn't want to be logged in for longer
                session.auth = Storage(
                    user = user,
                    last_visit = request.now,
                    expiration = self.settings.expiration,
                    remember =  False,
                )

            self.user = user
            session.flash = self.messages.logged_in
        if log and self.user:
            self.log_event(log % self.user)

        # how to continue
        if self.settings.login_form == self:
            if accepted_form:
                if onaccept:
                    onaccept(form)
                if isinstance(next, (list, tuple)):
                    # fix issue with 2.6
                    next = next[0]
                if next and not next[0] == '/' and next[:4] != 'http':
                    next = self.url(next.replace('[id]', str(form.vars.id)))
                redirect(next)
            table_user[username].requires = old_requires
            return form
        else:
            redirect(next)

    def logout(self, next=DEFAULT, onlogout=DEFAULT, log=DEFAULT):
        """
        logout and redirects to login

        .. method:: Auth.logout ([next=DEFAULT[, onlogout=DEFAULT[,
            log=DEFAULT]]])

        """

        if next == DEFAULT:
            next = self.settings.logout_next
        if onlogout == DEFAULT:
            onlogout = self.settings.logout_onlogout
        if onlogout:
            onlogout(self.user)
        if log == DEFAULT:
            log = self.messages.logout_log
        if log and self.user:
            self.log_event(log % self.user)

        if self.settings.login_form != self:
            cas = self.settings.login_form
            cas_user = cas.get_user()
            if cas_user:
                next = cas.logout_url(next)

        self.environment.session.auth = None
        self.environment.session.flash = self.messages.logged_out
        if next:
            redirect(next)

    def register(
        self,
        next=DEFAULT,
        onvalidation=DEFAULT,
        onaccept=DEFAULT,
        log=DEFAULT,
        ):
        """
        returns a registration form

        .. method:: Auth.register([next=DEFAULT [, onvalidation=DEFAULT
            [, onaccept=DEFAULT [, log=DEFAULT]]]])

        """

        table_user = self.settings.table_user
        request = self.environment.request
        response = self.environment.response
        session = self.environment.session
        if self.is_logged_in():
            redirect(self.settings.logged_url)
        if next == DEFAULT:
            next = request.get_vars._next \
                or request.post_vars._next \
                or self.settings.register_next
        if onvalidation == DEFAULT:
            onvalidation = self.settings.register_onvalidation
        if onaccept == DEFAULT:
            onaccept = self.settings.register_onaccept
        if log == DEFAULT:
            log = self.messages.register_log

        passfield = self.settings.password_field
        form = SQLFORM(table_user,
                       hidden=dict(_next=next),
                       showid=self.settings.showid,
                       submit_button=self.messages.submit_button,
                       delete_label=self.messages.delete_label)
        for i, row in enumerate(form[0].components):
            item = row[1][0]
            if isinstance(item, INPUT) and item['_name'] == passfield:
                form[0].insert(i+1, TR(
                        LABEL(self.messages.verify_password + ':'),
                        INPUT(_name="password_two",
                              _type="password",
                              requires=IS_EXPR('value==%s' % \
                               repr(request.vars.get(passfield, None)),
                        error_message=self.messages.mismatched_password)),
                '', _class='%s_%s__row' % (table_user, 'password_two')))
        captcha = self.settings.register_captcha or self.settings.captcha
        if captcha:
            form[0].insert(-1, TR(LABEL(captcha.label),
                                  captcha,captcha.comment,
                                  _id = 'capctha__row'))

        table_user.registration_key.default = key = web2py_uuid()
        if form.accepts(request.post_vars, session, formname='register',
                        onvalidation=onvalidation):
            description = self.messages.group_description % form.vars
            if self.settings.create_user_groups:
                group_id = self.add_group("user_%s" % form.vars.id, description)
                self.add_membership(group_id, form.vars.id)
            if self.settings.registration_requires_verification:
                if not self.settings.mailer or \
                   not self.settings.mailer.send(to=form.vars.email,
                        subject=self.messages.verify_email_subject,
                        message=self.messages.verify_email
                         % dict(key=key)):
                    self.db.rollback()
                    response.flash = self.messages.unable_send_email
                    return form
                session.flash = self.messages.email_sent
            elif self.settings.registration_requires_approval:
                user[form.vars.id] = dict(registration_key='pending')
                session.flash = self.messages.registration_pending
            else:
                table_user[form.vars.id] = dict(registration_key='')
                session.flash = self.messages.registration_successful
                table_user = self.settings.table_user
                if 'username' in table_user.fields:
                    username = 'username'
                else:
                    username = 'email'
                user = self.db(table_user[username] == form.vars[username]).select().first()
                user = Storage(table_user._filter_fields(user, id=True))
                session.auth = Storage(user=user, last_visit=request.now,
                                   expiration=self.settings.expiration)
                self.user = user
                session.flash = self.messages.logged_in
            if log:
                self.log_event(log % form.vars)
            if onaccept:
                onaccept(form)
            if not next:
                next = self.url(args = request.args)
            elif isinstance(next, (list, tuple)): ### fix issue with 2.6
                next = next[0]
            elif next and not next[0] == '/' and next[:4] != 'http':
                next = self.url(next.replace('[id]', str(form.vars.id)))
            redirect(next)
        return form

    def is_logged_in(self):
        """
        checks if the user is logged in and returns True/False.
        if so user is in auth.user as well as in session.auth.user
        """

        if self.environment.session.auth:
            return True
        return False

    def verify_email(
        self,
        next=DEFAULT,
        onaccept=DEFAULT,
        log=DEFAULT,
        ):
        """
        action user to verify the registration email, XXXXXXXXXXXXXXXX

        .. method:: Auth.verify_email([next=DEFAULT [, onvalidation=DEFAULT
            [, onaccept=DEFAULT [, log=DEFAULT]]]])

        """

        key = self.environment.request.args[-1]
        table_user = self.settings.table_user
        user = self.db(table_user.registration_key == key).select().first()
        if not user:
            raise HTTP(404)
        if self.settings.registration_requires_approval:
            user.update_record(registration_key = 'pending')
            self.environment.session.flash = self.messages.registration_pending
        else:
            user.update_record(registration_key = '')
            self.environment.session.flash = self.messages.email_verified
        if log == DEFAULT:
            log = self.messages.verify_email_log
        if next == DEFAULT:
            next = self.settings.verify_email_next
        if onaccept == DEFAULT:
            onaccept = self.settings.verify_email_onaccept
        if log:
            self.log_event(log % user)
        if onaccept:
            onaccept(user)
        redirect(next)

    def retrieve_username(
        self,
        next=DEFAULT,
        onvalidation=DEFAULT,
        onaccept=DEFAULT,
        log=DEFAULT,
        ):
        """
        returns a form to retrieve the user username
        (only if there is a username field)

        .. method:: Auth.retrieve_username([next=DEFAULT
            [, onvalidation=DEFAULT [, onaccept=DEFAULT [, log=DEFAULT]]]])

        """

        table_user = self.settings.table_user
        if not 'username' in table_user.fields:
            raise HTTP(404)
        request = self.environment.request
        response = self.environment.response
        session = self.environment.session

        if not self.settings.mailer:
            response.flash = self.messages.function_disabled
            return ''
        if next == DEFAULT:
            next = request.get_vars._next \
                or request.post_vars._next \
                or self.settings.retrieve_username_next
        if onvalidation == DEFAULT:
            onvalidation = self.settings.retrieve_username_onvalidation
        if onaccept == DEFAULT:
            onaccept = self.settings.retrieve_username_onaccept
        if log == DEFAULT:
            log = self.messages.retrieve_username_log
        old_requires = table_user.email.requires
        table_user.email.requires = [IS_IN_DB(self.db, table_user.email,
            error_message=self.messages.invalid_email)]
        form = SQLFORM(table_user,
                       fields=['email'],
                       hidden=dict(_next=next),
                       showid=self.settings.showid,
                       submit_button=self.messages.submit_button,
                       delete_label=self.messages.delete_label)
        if form.accepts(request.post_vars, session,
                        formname='retrieve_username', dbio=False,
                        onvalidation=onvalidation):
            user = self.db(table_user.email == form.vars.email).select().first()
            if not user:
                self.environment.session.flash = \
                    self.messages.invalid_email
                redirect(self.url(args=request.args))
            username = user.username
            self.settings.mailer.send(to=form.vars.email,
                    subject=self.messages.retrieve_username_subject,
                    message=self.messages.retrieve_username
                     % dict(username=username))
            session.flash = self.messages.email_sent
            if log:
                self.log_event(log % user)
            if onaccept:
                onaccept(form)
            if not next:
                next = self.url(args = request.args)
            elif isinstance(next, (list, tuple)): ### fix issue with 2.6
                next = next[0]
            elif next and not next[0] == '/' and next[:4] != 'http':
                next = self.url(next.replace('[id]', str(form.vars.id)))
            redirect(next)
        table_user.email.requires = old_requires
        return form

    def random_password(self):
        import string
        import random
        password = ''
        specials=r'!#$*'
        for i in range(0,3):
            password += random.choice(string.lowercase)
            password += random.choice(string.uppercase)
            password += random.choice(string.digits)
            password += random.choice(specials)
        return ''.join(random.sample(password,len(password)))

    def reset_password_deprecated(
        self,
        next=DEFAULT,
        onvalidation=DEFAULT,
        onaccept=DEFAULT,
        log=DEFAULT,
        ):
        """
        returns a form to reset the user password (deprecated)

        .. method:: Auth.reset_password_deprecated([next=DEFAULT
            [, onvalidation=DEFAULT [, onaccept=DEFAULT [, log=DEFAULT]]]])

        """

        table_user = self.settings.table_user
        request = self.environment.request
        response = self.environment.response
        session = self.environment.session
        if not self.settings.mailer:
            response.flash = self.messages.function_disabled
            return ''
        if next == DEFAULT:
            next = request.get_vars._next \
                or request.post_vars._next \
                or self.settings.retrieve_password_next
        if onvalidation == DEFAULT:
            onvalidation = self.settings.retrieve_password_onvalidation
        if onaccept == DEFAULT:
            onaccept = self.settings.retrieve_password_onaccept
        if log == DEFAULT:
            log = self.messages.retrieve_password_log
        old_requires = table_user.email.requires
        table_user.email.requires = [IS_IN_DB(self.db, table_user.email,
            error_message=self.messages.invalid_email)]
        form = SQLFORM(table_user,
                       fields=['email'],
                       hidden=dict(_next=next),
                       showid=self.settings.showid,
                       submit_button=self.messages.submit_button,
                       delete_label=self.messages.delete_label)
        if form.accepts(request.post_vars, session,
                        formname='retrieve_password', dbio=False,
                        onvalidation=onvalidation):
            user = self.db(table_user.email == form.vars.email).select().first()
            if not user:
                self.environment.session.flash = \
                    self.messages.invalid_email
                redirect(self.url(args=request.args))
            elif user.registration_key in ['pending', 'disabled']:
                self.environment.session.flash = \
                    self.messages.registration_pending
                redirect(self.url(args=request.args))
            password = self.random_password()
            passfield = self.settings.password_field
            d = {passfield: table_user[passfield].validate(password)[0],
                 'registration_key': ''}
            user.update_record(**d)
            if self.settings.mailer and \
               self.settings.mailer.send(to=form.vars.email,
                        subject=self.messages.retrieve_password_subject,
                        message=self.messages.retrieve_password \
                        % dict(password=password)):
                session.flash = self.messages.email_sent
            else:
                session.flash = self.messages.unable_to_send_email
            if log:
                self.log_event(log % user)
            if onaccept:
                onaccept(form)
            if not next:
                next = self.url(args = request.args)
            elif isinstance(next, (list, tuple)): ### fix issue with 2.6
                next = next[0]
            elif next and not next[0] == '/' and next[:4] != 'http':
                next = self.url(next.replace('[id]', str(form.vars.id)))
            redirect(next)
        table_user.email.requires = old_requires
        return form

    def reset_password(
        self,
        next=DEFAULT,
        onvalidation=DEFAULT,
        onaccept=DEFAULT,
        log=DEFAULT,
        ):
        """
        returns a form to reset the user password

        .. method:: Auth.reset_password([next=DEFAULT
            [, onvalidation=DEFAULT [, onaccept=DEFAULT [, log=DEFAULT]]]])

        """

        table_user = self.settings.table_user
        request = self.environment.request
        response = self.environment.response
        session = self.environment.session

        if next == DEFAULT:
            next = request.get_vars._next \
                or request.post_vars._next \
                or self.settings.reset_password_next

        try:
            key = request.vars.key or request.args[-1]
            t0 = int(key.split('-')[0])
            if time.time()-t0 > 60*60*24: raise Exception
            user = self.db(table_user.reset_password_key == key).select().first()
            if not user: raise Exception
        except Exception, e:
            session.flash = self.messages.invalid_reset_password
            redirect(next)
        passfield = self.settings.password_field
        form = form_factory(
            Field('new_password', 'password',
                  label=self.messages.new_password,
                  requires=self.settings.table_user[passfield].requires),
            Field('new_password2', 'password',
                  label=self.messages.verify_password,
                  requires=[IS_EXPR('value==%s' % repr(request.vars.new_password),
                                    self.messages.mismatched_password)]))
        if form.accepts(request.post_vars,session):
            user.update_record(password=form.vars.new_password,reset_password_key='')
            session.flash = self.messages.password_changed
            redirect(next)
        return form

    def request_reset_password(
        self,
        next=DEFAULT,
        onvalidation=DEFAULT,
        onaccept=DEFAULT,
        log=DEFAULT,
        ):
        """
        returns a form to reset the user password

        .. method:: Auth.reset_password([next=DEFAULT
            [, onvalidation=DEFAULT [, onaccept=DEFAULT [, log=DEFAULT]]]])

        """

        table_user = self.settings.table_user
        request = self.environment.request
        response = self.environment.response
        session = self.environment.session

        if next == DEFAULT:
            next = request.get_vars._next \
                or request.post_vars._next \
                or self.settings.request_reset_password_next

        if not self.settings.mailer:
            response.flash = self.messages.function_disabled
            return ''
        if onvalidation == DEFAULT:
            onvalidation = self.settings.reset_password_onvalidation
        if onaccept == DEFAULT:
            onaccept = self.settings.reset_password_onaccept
        if log == DEFAULT:
            log = self.messages.reset_password_log
        old_requires = table_user.email.requires
        table_user.email.requires = [IS_IN_DB(self.db, table_user.email,
                                            error_message=self.messages.invalid_email)]
        form = SQLFORM(table_user,
                       fields=['email'],
                       hidden=dict(_next=next),
                       showid=self.settings.showid,
                       submit_button=self.messages.submit_button,
                       delete_label=self.messages.delete_label)
        if form.accepts(request.post_vars, session,
                        formname='reset_password', dbio=False,
                        onvalidation=onvalidation):
            user = self.db(table_user.email == form.vars.email).select().first()
            if not user:
                session.flash = self.messages.invalid_email
                redirect(self.url(args=request.args))
            elif user.registration_key in ['pending', 'disabled']:
                session.flash = self.messages.registration_pending
                redirect(self.url(args=request.args))
            reset_password_key = str(int(time.time()))+'-' + web2py_uuid()

            if self.settings.mailer.send(to=form.vars.email,
                                         subject=self.messages.reset_password_subject,
                                         message=self.messages.reset_password % \
                                             dict(key=reset_password_key)):
                session.flash = self.messages.email_sent
                user.update_record(reset_password_key=reset_password_key)
            else:
                session.flash = self.messages.unable_to_send_email
            if log:
                self.log_event(log % user)
            if onaccept:
                onaccept(form)
            if not next:
                next = self.url(args = request.args)
            elif isinstance(next, (list, tuple)): ### fix issue with 2.6
                next = next[0]
            elif next and not next[0] == '/' and next[:4] != 'http':
                next = self.url(next.replace('[id]', str(form.vars.id)))
            redirect(next)
        old_requires = table_user.email.requires
        return form

    def retrieve_password(
        self,
        next=DEFAULT,
        onvalidation=DEFAULT,
        onaccept=DEFAULT,
        log=DEFAULT,
        ):
        if self.settings.reset_password_requires_verification:
            return self.request_reset_password(next,onvalidation,onaccept,log)
        else:
            return self.reset_password_deprecated(next,onvalidation,onaccept,log)

    def change_password(
        self,
        next=DEFAULT,
        onvalidation=DEFAULT,
        onaccept=DEFAULT,
        log=DEFAULT,
        ):
        """
        returns a form that lets the user change password

        .. method:: Auth.change_password([next=DEFAULT[, onvalidation=DEFAULT[,
            onaccept=DEFAULT[, log=DEFAULT]]]])
        """

        if not self.is_logged_in():
            redirect(self.settings.login_url)
        db = self.db
        table_user = self.settings.table_user
        usern = self.settings.table_user_name
        s = db(table_user.email == self.user.email)

        request = self.environment.request
        session = self.environment.session
        if next == DEFAULT:
            next = request.get_vars._next \
                or request.post_vars._next \
                or self.settings.change_password_next
        if onvalidation == DEFAULT:
            onvalidation = self.settings.change_password_onvalidation
        if onaccept == DEFAULT:
            onaccept = self.settings.change_password_onaccept
        if log == DEFAULT:
            log = self.messages.change_password_log
        passfield = self.settings.password_field
        form = form_factory(Field(
            'old_password',
            'password',
            label=self.messages.old_password,
            requires=validators(
                     table_user[passfield].requires,
                     IS_IN_DB(s, '%s.%s' % (usern, passfield),
                              error_message=self.messages.invalid_password))),
            Field('new_password', 'password',
            label=self.messages.new_password,
            requires=table_user[passfield].requires),
            Field('new_password2', 'password',
            label=self.messages.verify_password,
            requires=[IS_EXPR('value==%s' % repr(request.vars.new_password),
                              self.messages.mismatched_password)]))
        if form.accepts(request.post_vars, session,
                        formname='change_password',
                        onvalidation=onvalidation):
            d = {passfield: form.vars.new_password}
            s.update(**d)
            session.flash = self.messages.password_changed
            if log:
                self.log_event(log % self.user)
            if onaccept:
                onaccept(form)
            if not next:
                next = self.url(args=request.args)
            elif isinstance(next, (list, tuple)): ### fix issue with 2.6
                next = next[0]
            elif next and not next[0] == '/' and next[:4] != 'http':
                next = self.url(next.replace('[id]', str(form.vars.id)))
            redirect(next)
        return form

    def profile(
        self,
        next=DEFAULT,
        onvalidation=DEFAULT,
        onaccept=DEFAULT,
        log=DEFAULT,
        ):
        """
        returns a form that lets the user change his/her profile

        .. method:: Auth.profile([next=DEFAULT [, onvalidation=DEFAULT
            [, onaccept=DEFAULT [, log=DEFAULT]]]])

        """

        if not self.is_logged_in():
            redirect(self.settings.login_url)
        passfield = self.settings.password_field
        self.settings.table_user[passfield].writable = False
        request = self.environment.request
        session = self.environment.session
        if next == DEFAULT:
            next = request.get_vars._next \
                or request.post_vars._next \
                or self.settings.profile_next
        if onvalidation == DEFAULT:
            onvalidation = self.settings.profile_onvalidation
        if onaccept == DEFAULT:
            onaccept = self.settings.profile_onaccept
        if log == DEFAULT:
            log = self.messages.profile_log
        form = SQLFORM(
            self.settings.table_user,
            self.user.id,
            hidden=dict(_next=next),
            showid=self.settings.showid,
            submit_button=self.messages.submit_button,
            delete_label=self.messages.delete_label,
            upload=self.settings.download_url
            )
        if form.accepts(request.post_vars, session,
                        formname='profile',
                        onvalidation=onvalidation):
            self.user.update(form.vars)
            session.flash = self.messages.profile_updated
            if log:
                self.log_event(log % self.user)
            if onaccept:
                onaccept(form)
            if not next:
                next = self.url(args=request.args)
            elif isinstance(next, (list, tuple)): ### fix issue with 2.6
                next = next[0]
            elif next and not next[0] == '/' and next[:4] != 'http':
                next = self.url(next.replace('[id]', str(form.vars.id)))
            redirect(next)
        return form

    def is_impersonating(self):
        return self.environment.session.auth.impersonator

    def impersonate(self, user_id=DEFAULT):
        """
        usage: http://..../impersonate/[user_id]
        or:    http://..../impersonate/0 to restore impersonator

        requires impersonator is logged in and
        has_permission('impersonate', 'auth_user', user_id)
        """
        request = self.environment.request
        session = self.environment.session
        auth = session.auth
        if not self.is_logged_in():
            raise HTTP(401, "Not Authorized")
        if user_id == DEFAULT and self.environment.request.args:
            user_id = self.environment.request.args[1]
        if user_id and user_id != self.user.id and user_id != '0':
            if not self.has_permission('impersonate',
                                       self.settings.table_user_name,
                                       user_id):
                raise HTTP(403, "Forbidden")
            user = self.settings.table_user[request.args[1]]
            if not user:
                raise HTTP(401, "Not Authorized")
            auth.impersonator = cPickle.dumps(session)
            auth.user.update(
                self.settings.table_user._filter_fields(user, True))
            self.user = auth.user
            if self.settings.login_onaccept:
                form = Storage(dict(vars=self.user))
                self.settings.login_onaccept(form)
        elif user_id in [None, 0, '0'] and self.is_impersonating():
            session.clear()
            session.update(cPickle.loads(auth.impersonator))
            self.user = session.auth.user
        return self.user

    def groups(self):
        """
        displays the groups and their roles for the logged in user
        """

        if not self.is_logged_in():
            redirect(self.settings.login_url)
        memberships = self.db(self.settings.table_membership.user_id
                               == self.user.id).select()
        table = TABLE()
        for membership in memberships:
            groups = self.db(self.settings.table_group.id
                              == membership.group_id).select()
            if groups:
                group = groups[0]
                table.append(TR(H3(group.role, '(%s)' % group.id)))
                table.append(TR(P(group.description)))
        if not memberships:
            return None
        return table

    def not_authorized(self):
        """
        you can change the view for this page to make it look as you like
        """

        return 'ACCESS DENIED'

    def requires(self, condition):
        """
        decorator that prevents access to action if not logged in
        """

        def decorator(action):

            def f(*a, **b):
                if not self.basic() and not self.is_logged_in():
                    request = self.environment.request
                    next = URL(r=request,args=request.args,
                               vars=request.get_vars)
                    redirect(self.settings.login_url + \
                                 '?_next='+urllib.quote(next))
                if not condition:
                    self.environment.session.flash = \
                        self.messages.access_denied
                    next = self.settings.on_failed_authorization
                    redirect(next)
                return action(*a, **b)
            f.__doc__ = action.__doc__
            return f

        return decorator

    def requires_login(self):
        """
        decorator that prevents access to action if not logged in
        """

        def decorator(action):

            def f(*a, **b):

                if not self.basic() and not self.is_logged_in():
                    request = self.environment.request
                    next = URL(r=request,args=request.args,
                               vars=request.get_vars)
                    redirect(self.settings.login_url + \
                                 '?_next='+urllib.quote(next))
                return action(*a, **b)
            f.__doc__ = action.__doc__
            return f

        return decorator

    def requires_membership(self, role):
        """
        decorator that prevents access to action if not logged in or
        if user logged in is not a member of group_id.
        If role is provided instead of group_id then the 
        group_id is calculated.
        """

        def decorator(action):
            group_id = self.id_group(role)

            def f(*a, **b):
                if not self.basic() and not self.is_logged_in():
                    request = self.environment.request
                    next = URL(r=request,args=request.args,
                               vars=request.get_vars)
                    redirect(self.settings.login_url + \
                                 '?_next='+urllib.quote(next))
                if not self.has_membership(group_id):
                    self.environment.session.flash = \
                        self.messages.access_denied
                    next = self.settings.on_failed_authorization
                    redirect(next)
                return action(*a, **b)
            f.__doc__ = action.__doc__
            return f

        return decorator

    def requires_permission(
        self,
        name,
        table_name='',
        record_id=0,
        ):
        """
        decorator that prevents access to action if not logged in or
        if user logged in is not a member of any group (role) that
        has 'name' access to 'table_name', 'record_id'.
        """

        def decorator(action):

            def f(*a, **b):
                if not self.basic() and not self.is_logged_in():
                    request = self.environment.request
                    next = URL(r=request,args=request.args,
                               vars=request.get_vars)
                    redirect(self.settings.login_url + 
                             '?_next='+urllib.quote(next))
                if not self.has_permission(name, table_name, record_id):
                    self.environment.session.flash = \
                        self.messages.access_denied
                    next = self.settings.on_failed_authorization
                    redirect(next)
                return action(*a, **b)
            f.__doc__ = action.__doc__
            return f

        return decorator

    def add_group(self, role, description=''):
        """
        creates a group associated to a role
        """

        group_id = self.settings.table_group.insert(role=role,
                description=description)
        log = self.messages.add_group_log
        if log:
            self.log_event(log % dict(group_id=group_id, role=role))
        return group_id

    def del_group(self, group_id):
        """
        deletes a group
        """

        self.db(self.settings.table_group.id == group_id).delete()
        self.db(self.settings.table_membership.group_id
                 == group_id).delete()
        self.db(self.settings.table_permission.group_id
                 == group_id).delete()
        log = self.messages.del_group_log
        if log:
            self.log_event(log % dict(group_id=group_id))

    def id_group(self, role):
        """
        returns the group_id of the group specified by the role
        """
        rows = self.db(self.settings.table_group.role == role).select()
        if not rows:
            return None
        return rows[0].id

    def user_group(self, user_id = None):
        """
        returns the group_id of the group uniquely associated to this user
        i.e. role=user:[user_id]
        """
        if not user_id and self.user:
            user_id = self.user.id
        role = 'user_%s' % user_id
        return self.id_group(role)

    def has_membership(self, group_id, user_id=None):
        """
        checks if user is member of group_id
        """

        if not user_id and self.user:
            user_id = self.user.id
        membership = self.settings.table_membership
        if self.db((membership.user_id == user_id)
                    & (membership.group_id == group_id)).select():
            r = True
        else:
            r = False
        log = self.messages.has_membership_log
        if log:
            self.log_event(log % dict(user_id=user_id,
                                      group_id=group_id, check=r))
        return r

    def add_membership(self, group_id, user_id=None):
        """
        gives user_id membership of group_id
        if group_id==None than user_id is that of current logged in user
        """

        if not user_id and self.user:
            user_id = self.user.id
        membership = self.settings.table_membership
        id = membership.insert(group_id=group_id, user_id=user_id)
        log = self.messages.add_membership_log
        if log:
            self.log_event(log % dict(user_id=user_id,
                                      group_id=group_id))
        return id

    def del_membership(self, group_id, user_id=None):
        """
        revokes membership from group_id to user_id
        if group_id==None than user_id is that of current logged in user
        """

        if not user_id and self.user:
            user_id = self.user.id
        membership = self.settings.table_membership
        log = self.messages.del_membership_log
        if log:
            self.log_event(log % dict(user_id=user_id,
                                      group_id=group_id))
        return self.db(membership.user_id
                       == user_id)(membership.group_id
                                   == group_id).delete()

    def has_permission(
        self,
        name='any',
        table_name='',
        record_id=0,
        user_id=None,
        ):
        """
        checks if user_id or current logged in user is member of a group
        that has 'name' permission on 'table_name' and 'record_id'
        """

        if not user_id and self.user:
            user_id = self.user.id
        membership = self.settings.table_membership
        rows = self.db(membership.user_id
                        == user_id).select(membership.group_id)
        groups = set([row.group_id for row in rows])
        permission = self.settings.table_permission
        rows = self.db(permission.name == name)(permission.table_name
                 == str(table_name))(permission.record_id
                 == record_id).select(permission.group_id)
        groups_required = set([row.group_id for row in rows])
        if record_id:
            rows = self.db(permission.name
                            == name)(permission.table_name
                     == str(table_name))(permission.record_id
                     == 0).select(permission.group_id)
            groups_required = groups_required.union(set([row.group_id
                    for row in rows]))
        if groups.intersection(groups_required):
            r = True
        else:
            r = False
        log = self.messages.has_permission_log
        if log:
            self.log_event(log % dict(user_id=user_id, name=name,
                           table_name=table_name, record_id=record_id))
        return r

    def add_permission(
        self,
        group_id,
        name='any',
        table_name='',
        record_id=0,
        ):
        """
        gives group_id 'name' access to 'table_name' and 'record_id'
        """

        permission = self.settings.table_permission
        if group_id == 0:
            group_id = self.user_group()
        id = permission.insert(group_id=group_id, name=name,
                               table_name=str(table_name),
                               record_id=long(record_id))
        log = self.messages.add_permission_log
        if log:
            self.log_event(log % dict(permission_id, group_id=group_id,
                           name=name, table_name=table_name,
                           record_id=record_id))
        return id

    def del_permission(
        self,
        group_id,
        name='any',
        table_name='',
        record_id=0,
        ):
        """
        revokes group_id 'name' access to 'table_name' and 'record_id'
        """

        permission = self.settings.table_permission
        log = self.messages.del_permission_log
        if log:
            self.log_event(log % dict(group_id=group_id, name=name,
                           table_name=table_name, record_id=record_id))
        return self.db(permission.group_id == group_id)(permission.name
                 == name)(permission.table_name
                           == str(table_name))(permission.record_id
                 == long(record_id)).delete()

    def accessible_query(self, name, table, user_id=None):
        """
        returns a query with all accessible records for user_id or
        the current logged in user
        this method does not work on GAE because uses JOIN and IN

        example::

           db(auth.accessible_query('read', db.mytable)).select(db.mytable.ALL)

        """
        if not user_id:
            user_id = self.user.id
        if self.has_permission(name, table, 0, user_id):
            return table.id > 0
        db = self.db
        membership = self.settings.table_membership
        permission = self.settings.table_permission
        return table.id.belongs(db(membership.user_id == user_id)\
                           (membership.group_id == permission.group_id)\
                           (permission.name == name)\
                           (permission.table_name == table)\
                           ._select(permission.record_id))


class Crud(object):

    def url(self, f=None, args=[], vars={}):
        return self.environment.URL(r=self.environment.request,
                                    c=self.settings.controller,
                                    f=f, args=args, vars=vars)

    def __init__(self, environment, db):
        self.environment = Storage(environment)
        self.db = db
        self.settings = Settings()
        self.settings.auth = None
        self.settings.logger = None

        self.settings.create_next = None
        self.settings.update_next = None
        self.settings.controller = 'default'
        self.settings.delete_next = self.url()
        self.settings.download_url = self.url('download')
        self.settings.create_onvalidation = None
        self.settings.update_onvalidation = None
        self.settings.delete_onvalidation = None
        self.settings.create_onaccept = None
        self.settings.update_onaccept = None
        self.settings.update_ondelete = None
        self.settings.delete_onaccept = None
        self.settings.update_deletable = True
        self.settings.showid = False
        self.settings.keepvalues = False
        self.settings.create_captcha = None
        self.settings.update_captcha = None
        self.settings.captcha = None
        self.settings.lock_keys = True

        self.messages = Messages(self.environment.T)
        self.messages.submit_button = 'Submit'
        self.messages.delete_label = 'Check to delete:'
        self.messages.record_created = 'Record Created'
        self.messages.record_updated = 'Record Updated'
        self.messages.record_deleted = 'Record Deleted'

        self.messages.update_log = 'Record %(id)s updated'
        self.messages.create_log = 'Record %(id)s created'
        self.messages.read_log = 'Record %(id)s read'
        self.messages.delete_log = 'Record %(id)s deleted'

        self.messages.lock_keys = True

    def __call__(self):

        args = self.environment.request.args
        if len(args) < 1:
            redirect(self.url(args='tables'))
        elif args[0] == 'tables':
            return self.tables()
        elif args[0] == 'create':
            return self.create(args(1))
        elif args[0] == 'select':
            return self.select(args(1))
        elif args[0] == 'read':
            return self.read(args(1), args(2))
        elif args[0] == 'update':
            return self.update(args(1), args(2))
        elif args[0] == 'delete':
            return self.delete(args(1), args(2))
        else:
            raise HTTP(404)

    def log_event(self, message):
        if self.settings.logger:
            self.settings.logger.log_event(message, 'crud')

    def has_permission(self, name, table, record=0):
        if not self.settings.auth:
            return True
        try:
            record_id = record.id
        except:
            record_id = record
        return self.settings.auth.has_permission(name, str(table), record_id)

    def tables(self):
        request = self.environment.request
        return TABLE(*[TR(A(name, _href=self.url(args=('select',
                     name)))) for name in self.db.tables])


    @staticmethod
    def archive(form,archive_table=None,current_record='current_record'):
        """
        If you have a table (db.mytable) that needs full revision history you can just do::
        
            form=crud.update(db.mytable,myrecord,onaccept=crud.archive)

        crud.archive will define a new table "mytable_history" and store the
        previous record in the newly created table including a reference
        to the current record.
        
        If you want to access such table you need to define it yourself in a mode::

            db.define_table('mytable_history',
                Field('current_record',db.mytable),
                db.mytable)

        Notice such table includes all fields of db.mytable plus one: current_record.
        crud.archive does not timestamp the stored record unless your original table
        has a fields like::

            db.define_table(...,
                Field('saved_on','datetime',
                     default=request.now,update=request.now,writable=False),
                Field('saved_by',auth.user,
                     default=auth.user_id,update=auth.user_id,writable=False),

        there is nothing special about these fields since they are filled before 
        the record is archived.
       
        Alterantively you can create similar fields in the 'mytable_history' table
        and they will be filled when the record is archived.

        If you want to change the achive table name and the name of the reference field
        you can do, for example::

            db.define_table('myhistory',
                Field('parent_record',db.mytable),
                mytable)   
        
        and use it as::

            form=crud.update(db.mytable,myrecord,
                             onaccept=lambda form:crud.archive(form, \
                               archive_table=db.myhistory, \
                               current_record='parent_record'))

        """
        old_record = form.record
        if not old_record:
            return None
        table = form.table
        if not archive_table:
            archive_table_name = '%s_archive' % table
            if archive_table_name in table._db:
                archive_table = table._db[archive_table_name]
            else:
                archive_table = table._db.define_table(archive_table_name,
                                                       Field(current_record,table),
                                                       table)
        new_record = {current_record:old_record.id}
        for fieldname in archive_table.fields:
            if not fieldname in ['id',current_record] and fieldname in old_record:
                new_record[fieldname]=old_record[fieldname]
        id = archive_table.insert(**new_record)
        return id

    def update(
        self,
        table,
        record,
        next=DEFAULT,
        onvalidation=DEFAULT,
        onaccept=DEFAULT,
        ondelete=DEFAULT,
        log=DEFAULT,
        message=DEFAULT,
        deletable=DEFAULT,
        ):
        """
        .. method:: Crud.update(table, record, [next=DEFAULT
            [, onvalidation=DEFAULT [, onaccept=DEFAULT [, log=DEFAULT
            [, message=DEFAULT[, deletable=DEFAULT]]]]]])

        """
        if not (isinstance(table, self.db.Table) or table in self.db.tables) \
                or (isinstance(record, str) and not str(record).isdigit()):
            raise HTTP(404)
        if not isinstance(table, self.db.Table):
            table = self.db[table]
        try:
            record_id = record.id
        except:
            record_id = record or 0
        if record_id and not self.has_permission('update', table, record_id):
            redirect(self.settings.auth.settings.on_failed_authorization)
        if not record_id \
                and not self.has_permission('create', table, record_id):
            redirect(self.settings.auth.settings.on_failed_authorization)

        request = self.environment.request
        response = self.environment.response
        session = self.environment.session
        if request.extension == 'json' and request.vars.json:
            request.vars.update(simplejson.loads(request.vars.json))
        if next == DEFAULT:
            next = request.get_vars._next \
                or request.post_vars._next \
                or self.settings.update_next
        if onvalidation == DEFAULT:
            onvalidation = self.settings.update_onvalidation
        if onaccept == DEFAULT:
            onaccept = self.settings.update_onaccept
        if ondelete == DEFAULT:
            ondelete = self.settings.update_ondelete
        if log == DEFAULT:
            log = self.messages.update_log
        if deletable == DEFAULT:
            deletable = self.settings.update_deletable
        if message == DEFAULT:
            message = self.messages.record_updated
        form = SQLFORM(
            table,
            record,
            hidden=dict(_next=next),
            showid=self.settings.showid,
            submit_button=self.messages.submit_button,
            delete_label=self.messages.delete_label,
            deletable=deletable,
            upload=self.settings.download_url,
            )
        captcha = self.settings.update_captcha or \
                  self.settings.captcha
        if record and captcha:            
            form[0].insert(-1, TR(LABEL(captcha.label), 
                                  captcha, captcha.comment,
                                  _id='captcha__row'))
        captcha = self.settings.create_captcha or \
                  self.settings.captcha
        if not record and captcha:
            form[0].insert(-1, TR(LABEL(captcha.label), 
                                  captcha, captcha.comment,
                                  _id='captcha__row'))
        if request.extension != 'html':
            (_session, _formname) = (None, None)
        else:
            (_session, _formname) = \
                (session, '%s/%s' % (table._tablename, form.record_id))
        if form.accepts(request.post_vars, _session, formname=_formname,
                        onvalidation=onvalidation,
                        keepvalues=self.settings.keepvalues):
            response.flash = message
            if log:
                self.log_event(log % form.vars)
            if request.vars.delete_this_record and ondelete:
                ondelete(form)
            if onaccept:
                onaccept(form)
            if request.extension != 'html':
                raise HTTP(200, 'RECORD CREATED/UPDATED')
            if isinstance(next, (list, tuple)): ### fix issue with 2.6
               next = next[0]
            if next: # Only redirect when explicit
                if next[0] != '/' and next[:4] != 'http':
                    next = self.url(next.replace('[id]', str(form.vars.id)))
                session.flash = response.flash
                redirect(next)
        elif request.extension != 'html':
            raise HTTP(401)
        return form

    def create(
        self,
        table,
        next=DEFAULT,
        onvalidation=DEFAULT,
        onaccept=DEFAULT,
        log=DEFAULT,
        message=DEFAULT,
        ):
        """
        .. method:: Crud.create(table, [next=DEFAULT [, onvalidation=DEFAULT
            [, onaccept=DEFAULT [, log=DEFAULT[, message=DEFAULT]]]]])
        """

        if next == DEFAULT:
            next = self.settings.create_next
        if onvalidation == DEFAULT:
            onvalidation = self.settings.create_onvalidation
        if onaccept == DEFAULT:
            onaccept = self.settings.create_onaccept
        if log == DEFAULT:
            log = self.messages.create_log
        if message == DEFAULT:
            message = self.messages.record_created
        return self.update(
            table,
            None,
            next=next,
            onvalidation=onvalidation,
            onaccept=onaccept,
            log=log,
            message=message,
            deletable=False,
            )

    def read(self, table, record):
        if not (isinstance(table, self.db.Table) or table in self.db.tables) \
                or (isinstance(record, str) and not str(record).isdigit()):
            raise HTTP(404)
        if not isinstance(table, self.db.Table):
            table = self.db[table]
        if not self.has_permission('read', table, record):
            redirect(self.settings.auth.settings.on_failed_authorization)
        form = SQLFORM(
            table,
            record,
            readonly=True,
            comments=False,
            upload=self.settings.download_url,
            showid=self.settings.showid,
            )
        if self.environment.request.extension != 'html':
            return table._filter_fields(form.record, id=True)
        return form

    def delete(
        self,
        table,
        record_id,
        next=DEFAULT,
        message=DEFAULT,
        ):
        """
        .. method:: Crud.delete(table, record_id, [next=DEFAULT
            [, message=DEFAULT]])
        """
        if not (isinstance(table, self.db.Table) or table in self.db.tables) \
                or not str(record_id).isdigit():
            raise HTTP(404)
        if not isinstance(table, self.db.Table):
            table = self.db[table]
        if not self.has_permission('delete', table, record_id):
            redirect(self.settings.auth.settings.on_failed_authorization)
        request = self.environment.request
        session = self.environment.session
        if next == DEFAULT:
            next = request.get_vars._next \
                or request.post_vars._next \
                or self.settings.delete_next
        if message == DEFAULT:
            message = self.messages.record_deleted
        record = table[record_id]
        if record:
            if self.settings.delete_onvalidation:
                self.settings.delete_onvalidation(record)
            del table[record_id]
            if self.settings.delete_onaccept:
                self.settings.delete_onaccept(record)
            session.flash = message
        redirect(next)

    def select(
        self,
        table,
        query=None,
        fields=None,
        orderby=None,
        limitby=None,
        headers={},
        **attr
        ):
        request = self.environment.request
        if not (isinstance(table, self.db.Table) or table in self.db.tables):
            raise HTTP(404)
        if not self.has_permission('select', table):
            redirect(self.settings.auth.settings.on_failed_authorization)
        #if record_id and not self.has_permission('select', table):
        #    redirect(self.settings.auth.settings.on_failed_authorization)
        if not isinstance(table, self.db.Table):
            table = self.db[table]
        if not query:
            query = table.id > 0
        if not fields:
            fields = [table.ALL]
        rows = self.db(query).select(*fields, **dict(orderby=orderby,
            limitby=limitby))
        if not rows:
            return None # Nicer than an empty table.
        if not 'linkto' in attr:
            attr['linkto'] = self.url(args='read')
        if not 'upload' in attr:
            attr['upload'] = self.url('download')
        if request.extension != 'html':
            return rows.as_list()
        return SQLTABLE(rows, headers=headers, **attr)


urllib2.install_opener(urllib2.build_opener(urllib2.HTTPCookieProcessor()))

def fetch(url, data=None, headers={},
          cookie=Cookie.SimpleCookie(), 
          user_agent='Mozilla/5.0'):
    data = data if data is None else urllib.urlencode(data)
    if user_agent: headers['User-agent'] = user_agent
    headers['Cookie'] = ' '.join(['%s=%s;'%(c.key,c.value) for c in cookie.values()])
    try:
        from google.appengine.api import urlfetch
    except ImportError:
        req = urllib2.Request(url, data, headers)
        html = urllib2.urlopen(req).read()
    else:
        method = urlfetch.GET if data is None else urlfetch.POST
        while url is not None:
            response = urlfetch.fetch(url=url, payload=data,
                                      method=method, headers=headers,
                                      allow_truncated=False,follow_redirects=False,
                                      deadline=10)
            # next request will be a get, so no need to send the data again
            data = None 
            method = urlfetch.GET
            # load cookies from the response
            cookie.load(response.headers.get('set-cookie', '')) 
            url = response.headers.get('location')
        html = response.content
    return html 

regex_geocode = \
    re.compile('\<coordinates\>(?P<la>[^,]*),(?P<lo>[^,]*).*?\</coordinates\>')


def geocode(address):
    try:
        a = urllib.quote(address)
        txt = fetch('http://maps.google.com/maps/geo?q=%s&output=xml'
                     % a)
        item = regex_geocode.search(txt)
        (la, lo) = (float(item.group('la')), float(item.group('lo')))
        return (la, lo)
    except:
        return (0.0, 0.0)


def universal_caller(f, *a, **b):
    c = f.func_code.co_argcount
    n = f.func_code.co_varnames[:c]
    b = dict([(k, v) for k, v in b.items() if k in n])
    if len(b) == c:
        return f(**b)
    elif len(a) >= c:
        return f(*a[:c])
    raise HTTP(404, "Object does not exist")


class Service:

    def __init__(self, environment):
        self.environment = environment
        self.run_procedures = {}
        self.csv_procedures = {}
        self.xml_procedures = {}
        self.rss_procedures = {}
        self.json_procedures = {}
        self.jsonrpc_procedures = {}
        self.xmlrpc_procedures = {}
        self.amfrpc_procedures = {}
        self.amfrpc3_procedures = {}

    def run(self, f):
        """
        example::

            service = Service(globals())
            @service.run
            def myfunction(a, b):
                return a + b
            def call():
                return service()

        Then call it with::

            wget http://..../app/default/call/run/myfunction?a=3&b=4

        """
        self.run_procedures[f.__name__] = f
        return f

    def csv(self, f):
        """
        example::

            service = Service(globals())
            @service.csv
            def myfunction(a, b):
                return a + b
            def call():
                return service()

        Then call it with::

            wget http://..../app/default/call/csv/myfunction?a=3&b=4

        """
        self.run_procedures[f.__name__] = f
        return f

    def xml(self, f):
        """
        example::

            service = Service(globals())
            @service.xml
            def myfunction(a, b):
                return a + b
            def call():
                return service()

        Then call it with::

            wget http://..../app/default/call/xml/myfunction?a=3&b=4

        """
        self.run_procedures[f.__name__] = f
        return f

    def rss(self, f):
        """
        example::

            service = Service(globals())
            @service.rss
            def myfunction():
                return dict(title=..., link=..., description=...,
                    created_on=..., entries=[dict(title=..., link=...,
                        description=..., created_on=...])
            def call():
                return service()

        Then call it with::

            wget http://..../app/default/call/rss/myfunction

        """
        self.rss_procedures[f.__name__] = f
        return f

    def json(self, f):
        """
        example::

            service = Service(globals())
            @service.json
            def myfunction(a, b):
                return [{a: b}]
            def call():
                return service()

        Then call it with::

            wget http://..../app/default/call/json/myfunc?a=hello&b=world

        """
        self.json_procedures[f.__name__] = f
        return f

    def jsonrpc(self, f):
        """
        example::

            service = Service(globals())
            @service.jsonrpc
            def myfunction(a, b):
                return a + b
            def call():
                return service()

        Then call it with::

            wget http://..../app/default/call/jsonrpc/myfunc?a=hello&b=world

        """
        self.jsonrpc_procedures[f.__name__] = f
        return f

    def xmlrpc(self, f):
        """
        example::

            service = Service(globals())
            @service.xmlrpc
            def myfunction(a, b):
                return a + b
            def call():
                return service()

        The call it with::

            wget http://..../app/default/call/xmlrpc/myfunction?a=hello&b=world

        """
        self.xmlrpc_procedures[f.__name__] = f
        return f

    def amfrpc(self, f):
        """
        example::

            service = Service(globals())
            @service.amfrpc
            def myfunction(a, b):
                return a + b
            def call():
                return service()

        The call it with::

            wget http://..../app/default/call/amfrpc/myfunction?a=hello&b=world

        """
        self.amfrpc_procedures[f.__name__] = f
        return f

    def amfrpc3(self, domain='default'):
        """
        example::

            service = Service(globals())
            @service.amfrpc3('domain')
            def myfunction(a, b):
                return a + b
            def call():
                return service()

        The call it with::

            wget http://..../app/default/call/amfrpc3/myfunction?a=hello&b=world

        """
        if not isinstance(domain, str):
            raise SyntaxError, "AMF3 requires a domain for function"

        def _amfrpc3(f):
            if domain:
                self.amfrpc3_procedures[domain+'.'+f.__name__] = f
            else:
                self.amfrpc3_procedures[f.__name__] = f
            return f
        return _amfrpc3

    def serve_run(self, args=None):
        request = self.environment['request']
        if not args:
            args = request.args
        if args and args[0] in self.run_procedures:
            return universal_caller(self.run_procedures[args[0]],
                                    *args[1:], **dict(request.vars))
        self.error()

    def serve_csv(self, args=None):
        request = self.environment['request']
        response = self.environment['response']
        response.headers['Content-Type'] = 'text/x-csv'
        if not args:
            args = request.args

        def none_exception(value):
            if isinstance(value, unicode):
                return value.encode('utf8')
            if hasattr(value, 'isoformat'):
                return value.isoformat()[:19].replace('T', ' ')
            if value == None:
                return '<NULL>'
            return value
        if args and args[0] in self.run_procedures:
            r = universal_caller(self.run_procedures[args[0]],
                                 *args[1:], **dict(request.vars))
            s = cStringIO.StringIO()
            if hasattr(r, 'export_to_csv_file'):
                r.export_to_csv_file(s)
            elif r and isinstance(r[0], (dict, Storage)):
                import csv
                writer = csv.writer(s)
                writer.writerow(r[0].keys())
                for line in r:
                    writer.writerow([none_exception(v) \
                                     for v in line.values()])
            else:
                import csv
                writer = csv.writer(s)
                for line in r:
                    writer.writerow(line)
            return s.getvalue()
        self.error()

    def serve_xml(self, args=None):
        request = self.environment['request']
        response = self.environment['response']
        response.headers['Content-Type'] = 'text/xml'
        if not args:
            args = request.args
        if args and args[0] in self.run_procedures:
            s = universal_caller(self.run_procedures[args[0]],
                                 *args[1:], **dict(request.vars))
            if hasattr(s, 'as_list'):
                s = s.as_list()
            return serializers.xml(s)
        self.error()

    def serve_rss(self, args=None):
        request = self.environment['request']
        response = self.environment['response']
        if not args:
            args = request.args
        if args and args[0] in self.rss_procedures:
            feed = universal_caller(self.rss_procedures[args[0]],
                                    *args[1:], **dict(request.vars))
        else:
            self.error()
        response.headers['Content-Type'] = 'application/rss+xml'
        return serializers.rss(feed)

    def serve_json(self, args=None):
        request = self.environment['request']
        response = self.environment['response']
        response.headers['Content-Type'] = 'text/x-json'
        if not args:
            args = request.args
        d = dict(request.vars)
        if args and args[0] in self.json_procedures:
            s = universal_caller(self.json_procedures[args[0]],*args[1:],**d)
            if hasattr(s, 'as_list'):
                s = s.as_list()
            return response.json(s)
        self.error()

    def serve_jsonrpc(self):
        import contrib.simplejson as simplejson
        def return_response(id, result):
            return simplejson.dumps({'version': '1.1',
                'id': id, 'result': result, 'error': None})

        def return_error(id, code, message):
            return simplejson.dumps({'id': id,
                                     'version': '1.1',
                                     'error': {'name': 'JSONRPCError',
                                        'code': code, 'message': message}
                                     })

        request = self.environment['request']
        methods = self.jsonrpc_procedures
        data = simplejson.loads(request.body.read())
        id, method, params = data["id"], data["method"], data["params"]
        if not method in methods:
            return return_error(id, 100, 'method "%s" does not exist' % method)
        try:
            s = methods[method](*params)
            if hasattr(s, 'as_list'):
                s = s.as_list()
            return return_response(id, s)
        except BaseException:
            etype, eval, etb = sys.exc_info()
            return return_error(id, 100, '%s: %s' % (etype.__name__, eval))
        except:
            etype, eval, etb = sys.exc_info()
            return return_error(id, 100, 'Exception %s: %s' % (etype, eval))

    def serve_xmlrpc(self):
        request = self.environment['request']
        response = self.environment['response']
        services = self.xmlrpc_procedures.values()
        return response.xmlrpc(request, services)

    def serve_amfrpc(self, version=0):
        try:
            import pyamf
            import pyamf.remoting.gateway
        except:
            return "pyamf not installed or not in Python sys.path"
        request = self.environment['request']
        response = self.environment['response']
        if version == 3:
            services = self.amfrpc3_procedures
            base_gateway = pyamf.remoting.gateway.BaseGateway(services)
            pyamf_request = pyamf.remoting.decode(request.body)
        else:
            services = self.amfrpc_procedures
            base_gateway = pyamf.remoting.gateway.BaseGateway(services)
            context = pyamf.get_context(pyamf.AMF0)
            pyamf_request = pyamf.remoting.decode(request.body, context)
        pyamf_response = pyamf.remoting.Envelope(pyamf_request.amfVersion,
                                                 pyamf_request.clientType)
        for name, message in pyamf_request:
            pyamf_response[name] = base_gateway.getProcessor(message)(message)
        response.headers['Content-Type'] = pyamf.remoting.CONTENT_TYPE
        if version==3:
            return pyamf.remoting.encode(pyamf_response).getvalue()
        else:
            return pyamf.remoting.encode(pyamf_response, context).getvalue()

    def __call__(self):
        """
        register services with:
        service = Service(globals())
        @service.run
        @service.rss
        @service.json
        @service.jsonrpc
        @service.xmlrpc
        @service.jsonrpc
        @service.amfrpc
        @service.amfrpc3('domain')

        expose services with

        def call(): return service()

        call services with
        http://..../app/default/call/run?[parameters]
        http://..../app/default/call/rss?[parameters]
        http://..../app/default/call/json?[parameters]
        http://..../app/default/call/jsonrpc
        http://..../app/default/call/xmlrpc
        http://..../app/default/call/amfrpc
        http://..../app/default/call/amfrpc3
        """

        request = self.environment['request']
        if len(request.args) < 1:
            raise HTTP(400, "Bad request")
        arg0 = request.args(0)
        if arg0 == 'run':
            return self.serve_run(request.args[1:])
        elif arg0 == 'rss':
            return self.serve_rss(request.args[1:])
        elif arg0 == 'csv':
            return self.serve_csv(request.args[1:])
        elif arg0 == 'xml':
            return self.serve_xml(request.args[1:])
        elif arg0 == 'json':
            return self.serve_json(request.args[1:])
        elif arg0 == 'jsonrpc':
            return self.serve_jsonrpc()
        elif arg0 == 'xmlrpc':
            return self.serve_xmlrpc()
        elif arg0 == 'amfrpc':
            return self.serve_amfrpc()
        elif arg0 == 'amfrpc3':
            return self.serve_amfrpc(3)
        else:
            self.error()

    def error(self):
        raise HTTP(404, "Object does not exist")


def completion(callback):
    def _completion(f):
        def __completion(*a,**b):
            d = None
            try:
                d = f(*a,**b)
                return d
            finally:
                callback(d)
        return __completion
    return _completion

def prettydate(d,T=lambda x:x):
    try:
        dt = datetime.now() - d
    except:
        return ''
    if dt.days >= 2*365:
        return T('%d years ago') % int(dt.days / 365)
    elif dt.days >= 365:
        return T('1 year ago')
    elif dt.days >= 60:
        return T('%d months ago') % int(dt.days / 30)
    elif dt.days > 21:
        return T('1 month ago')
    elif dt.days >= 14:
        return T('%d weeks ago') % int(dt.days / 7)
    elif dt.days >= 7:
        return T('1 week ago')
    elif dt.days > 1:
        return T('%d days ago') % dt.days
    elif dt.days == 1:
        return T('1 day ago')
    elif dt.seconds >= 2*60*60:
        return T('%d hours ago') % int(dt.seconds / 3600)
    elif dt.seconds >= 60*60:
        return T('1 hour ago')
    elif dt.seconds >= 2*60:
        return T('%d minutes ago') % int(dt.seconds / 60)
    elif dt.seconds >= 60:
        return T('1 minute ago')
    elif dt.seconds > 1:
        return T('%d seconds ago') % dt.seconds
    elif dt.seconds == 1:
        return T('1 second ago')
    else:
        return T('now')
