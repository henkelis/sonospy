#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This file is part of web2py Web Framework (Copyrighted, 2007-2009).
Developed by Massimo Di Pierro <mdipierro@cs.depaul.edu>.
License: GPL v2

Thanks to Hans Donner <hans.donner@pobox.com> for CAS.
"""


class CasAuth(object):
    """
    Login will be done via a CAS, instead of web2py's  login form.
    To enable CAS login, set auth.setting.login_form to the CAS object.

    Example::

        # include in your model (eg db.py)
        # GaeGoogleAccount is an implementation of a CAS
        from gluon.contrib.login_methods.gae_google_login import \
            GaeGoogleAccount
        auth.settings.login_form=GaeGoogleAccount()

    """

    def login_url(self, next="/"):
        """
        Provides the url for a CAS login form, and is called from Auth.login()

        :param next: where to go after login
        """
        raise NotImplementedError

    def logout_url(self, next="/"):
        """
        Provides the url for a CAS logout, and is called from Auth.logout()

        :param next: where to go after logout
        """
        raise NotImplementedError

    def get_user(self):
        """
        Retrieves the user information (who is logged in?), and is called from
        Auth.login(). The information is passed to Auth.get_or_create_user

        Example::

            return dict(nickname=user.nickname(), email=user.email(),
                user_id=user.user_id(), source="google account")

        """
        raise NotImplementedError
