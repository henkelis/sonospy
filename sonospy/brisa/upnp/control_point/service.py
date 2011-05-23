# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Control Point side service implementation. Classes contained by this module
contain methods for performing actions on the service and event notification.

If you're using the control point high level API with no modifications on the
global flags (located on module brisa), then you shouldn't need to create this
class manually.

The framework default response to a device arrival is to build it and its
services automatically and forward it to your control point on the
"new_device_event" subscribed callback. This callback will receive the device
already ready for all actions.

These device's services are already built and their UPnP actions are already
methods of the service object itself. For instance, a content directory service
object would already have a Browse() method for you to call directly, passing
parameters in the keywords format (key=value) e.g. cds.Browse(ObjectId=5, ...).
Also note that the keys should be on the UPnP specified format, like the
example above we used ObjectId, as it appears on the reference.

"""

import brisa

import re

from brisa.core import log
from brisa.core.network import url_fetch, parse_url, http_call
from brisa.core.threaded_call import run_async_call
from brisa.core.threaded_call import ThreadedCall
from brisa.upnp.soap import SOAPProxy, SOAPProxyFile
from brisa.upnp.base_service import BaseService, BaseStateVariable,\
                                    format_rel_url
from brisa.upnp.control_point.action import Action, Argument
from brisa.upnp.base_service_builder import BaseServiceBuilder


class StateVariable(BaseStateVariable):

    def __init__(self, service, name, send_events, multicast, data_type, values):
        BaseStateVariable.__init__(self, service, name, send_events,
                                   multicast, data_type, values)

    def subscribe(self, callback):
        BaseStateVariable.subscribe_for_update(self, callback)


class ServiceBuilder(BaseServiceBuilder):

    def build(self):
        try:
            return BaseServiceBuilder.build(self)
        except:
            return False

    def _create_argument(self, arg_name, arg_direction, arg_state_var):
        return Argument(arg_name, arg_direction, arg_state_var.name)

    def _create_action(self, name, args):
        action = Action(self.service, name, args)
        setattr(self.service, name, action)
        return action

    def _create_state_var(self, name, send_events, multicast,
                          data_type, values):
        return StateVariable(self.service, name, send_events,
                             multicast, data_type, values)


def is_relative(url, base):
    if base == '':
        return False
    if base in url:
        return False
    return True

def is_file(url):
    if 'file:///' in url:
        return True
    return False

class Service(BaseService):

    def __init__(self, id, serv_type, url_base, scpd_url,
                 control_url='', event_url='', presentation_url='',
                 build_async=False, async_cb=None, build=False):
        """
        @param async_cb: callback in the form async_cb(success). Receives only
                         one parameter (success) that tells if the the service
                         has been successfully built or not.
        """
        BaseService.__init__(self, id, serv_type, url_base)
        self.event_sid = ''
        self.event_timeout = 0
        self.scpd_url = scpd_url
        self.control_url = control_url
        self.event_sub_url = event_url
        self.presentation_url = presentation_url
        self._auto_renew_subs = None
        self._soap_service = None

        if not brisa.__skip_soap_service__:
            if is_file(self.scpd_url):
                self.generate_soap_service('file')
            else:
                self.generate_soap_service('url')

        if brisa.__skip_service_xml__:
            return

        if build_async:
            assert async_cb != None, 'you won\'t be notified when the '\
                                           'service build finished.'
            self._build_async(async_cb)
        elif build:
            self._build_sync()

    def _build_sync(self):
        """ Builds the Service synchronously.
        """
#        print "_build_sync scpd_url: " + str(self.scpd_url)
#        print "_build_sync url_base: " + str(self.url_base)
        if is_file(self.scpd_url):
            fd = open(self.scpd_url[8:], 'r')
        else:
            if is_relative(self.scpd_url, self.url_base):
                url = '%s%s' % (self.url_base, self.scpd_url)
            else:
                url = self.scpd_url
#            print "_build_sync url: " + str(url)
            fd = url_fetch(url)
        if not fd:
            log.debug('Could not fetch SCPD URL %s' % self.scpd_url)
            raise RuntimeError('Could not build Service %s', self)
        ServiceBuilder(self, fd).build()

    def _build_async(self, cb):
        """ Builds the service asynchronously. Forwards True to the specified
        callback 'cb' if the service was successfully built (otherwise,
        forwards False).
        """
#        print "_build_async: " + str(self.scpd_url)
#        print "_build_async url_base: " + str(self.url_base)
        
        # TODO: test file processing below!
        if is_file(self.scpd_url):
#            fd = open(self.scpd_url[8:], 'r')
            run_async_call(open,
                           success_callback=self._fetch_scpd_async_done,
                           error_callback=self._fetch_scpd_async_error,
                           delay=0, file=self.scpd_url[8:], mode='r', success_callback_cargo=cb,
                           error_callback_cargo=cb)
        else:
            if is_relative(self.scpd_url, self.url_base):
                path = '%s%s' % (self.url_base, self.scpd_url)
            else:
                path = self.scpd_url
#            print "_build_async path: " + str(path)
            run_async_call(url_fetch,
                           success_callback=self._fetch_scpd_async_done,
                           error_callback=self._fetch_scpd_async_error,
                           delay=0, url=path, success_callback_cargo=cb,
                           error_callback_cargo=cb)

    def _fetch_scpd_async_done(self, fd=None, cb=None):
        """ Called when the SCPD XML was sucessfully fetched. If so, build the
        service by parsing the description.
        """
#        print '_fetch_scpd_async_done'
#        print '_fetch_scpd_async_done fd: ' + str(fd)
#        print '_fetch_scpd_async_done cb: ' + str(cb)
        if fd:
            parsed_ok = ServiceBuilder(self, fd).build()
#            print '_fetch_scpd_async_done parsed_ok: ' + str(parsed_ok)
            if cb:
                cb(parsed_ok)

    def _fetch_scpd_async_error(self, cb=None, error=None):
        """ Called when the SCPD XML wasn't successfully fetched.
        """
        log.debug('Failed to fetch SCPD for service %s' % self.id)
        if cb:
            cb(False)

    def generate_soap_service(self, soap_type='url'):
        namespace = ('u', self.service_type)
        ctrl_url = ''

#        if self.url_base in self.control_url:
        if is_relative(self.control_url, self.url_base):
            ctrl_url = '%s%s' % (self.url_base,
                                 format_rel_url(self.control_url))
        else:
            ctrl_url = self.control_url

        if soap_type == 'file':
            self._soap_service = SOAPProxyFile(ctrl_url, namespace)
        else:
            self._soap_service = SOAPProxy(ctrl_url, namespace)

    def subscribe_for_variable(self, var_name, callback):
        """ Subscribes for events on a specific variable (unicast eventing)
        with a notifier callback.

        @param var_name: variable name to subscribe on
        @param callback: callback to receive notifications

        @type var_name: string
        @type callback: callable
        """
        if var_name in self._state_variables:
            self._state_variables[var_name].subscribe(callback)

    def get_state_variable(self, var_name):
        """ Returns a state variable of the service, if exists.

        @param var_name: name of the state variable
        @type var_name: string

        @return: matching state variable or None
        @rtype: StateVariable
        """
        return self._state_variables.get(var_name, None)

    def event_subscribe(self, event_host, callback, cargo, auto_renew=True,
                        renew_callback=None):
        """ Subscribes for events.

        @param event_host: 2-tuple (host, port) with the event listener server.
        @param callback: callback
        @param cargo: callback parameters
        @param auto_renew: if True, the framework will automatically renew the
        subscription before it expires. If False, the program need to call
        event_renew method before the subscription timeout.
        @param renew_callback: renew callback. It will be used when auto_renew
                               is True

        @type event_host: tuple
        @type callback: callable
        @type auto_renew: boolean
        @type renew_callback: callable
        """
        if auto_renew:
            self._auto_renew_subs = AutoRenew(self, event_host,
                                              renew_callback, cargo)
        SubscribeRequest(self, event_host, callback, cargo)

    def event_unsubscribe(self, event_host, callback, cargo):
        """ Unsubscribes for events.

        @param event_host: 2-tuple (host, port) with the event listener server.
        @param callback: callback
        @param cargo: callback parameters

        @type event_host: tuple
        @type callback: callable
        """
        if not self.event_sid:
            # not registered
            return
        UnsubscribeRequest(self, event_host, callback, cargo)

    def event_renew(self, event_host, callback, cargo):
        """ Renew subscription for events.

        @param event_host: 2-tuple (host, port) with the event listener server.
        @param callback: callback
        @param cargo: callback parameters

        @type event_host: tuple
        @type callback: callable
        """
        if not self._auto_renew_subs:
            RenewSubscribeRequest(self, event_host, callback, cargo)

    def _on_event(self, changed_vars):
        log.debug('Receiving state variables notify')

        for name, value in changed_vars.items():

            # HACK: MS MP returns namespace with tag, but SCPD doesn't contain it
            '''
            Asset
1252079894.723467 DEBUG sonos:1341:on_device_event() device_event sid: uuid:KQYCSCBRXIQPHUNITES
1252079894.724094 DEBUG sonos:1342:on_device_event() device_event c_v: {'AuthorizationGrantedUpdateID': '0', 'AuthorizationDeniedUpdateID': '0', 'ValidationRevokedUpdateID': '0', 'ValidationSucceededUpdateID': '0'}
            MS MP
1252080093.125994 DEBUG sonos:1341:on_device_event() device_event sid: uuid:2aa6df46-c650-4f16-be4b-36a28e324a10
1252080093.126435 DEBUG sonos:1342:on_device_event() device_event c_v: {'{urn:microsoft.com:service:X_MS_MediaReceiverRegistrar:1}ValidationSucceededUpdateID': '3', '{urn:microsoft.com:service:X_MS_MediaReceiverRegistrar:1}AuthorizationGrantedUpdateID': '4', '{urn:microsoft.com:service:X_MS_MediaReceiverRegistrar:1}ValidationRevokedUpdateID': '5', '{urn:microsoft.com:service:X_MS_MediaReceiverRegistrar:1}AuthorizationDeniedUpdateID': '3'}
            '''
            name = re.sub("{.*}","",name)    

            # check before updating - Twonky at least sends a state variable (ContainerUpdateIDs) that it doesn't show in its SCPD
            if name in self._state_variables:
                self._state_variables[name].update(value)


class SubscribeRequest(object):
    """ Wrapper for an event subscription.
    """

    def __init__(self, service, event_host, callback, cargo):
        """ Constructor for the SubscribeRequest class.

        @param service: service that is subscribing
        @param event_host: 2-tuple (host, port) of the event listener server
        @param callback: callback
        @param cargo: callback parameters

        @type service: Service
        @type event_host: tuple
        @type callback: callable
        """
        log.debug("subscribe")
        self.callback = callback
        self.cargo = cargo
        self.service = service

        addr = "%s%s" % (service.url_base, service.event_sub_url)
        Paddr = parse_url(addr)

        headers = {}
#        headers["Host"] = Paddr.hostname
        headers["User-agent"] = 'BRisa UPnP Framework'
        headers["TIMEOUT"] = 'Second-1800'
        headers["NT"] = 'upnp:event'
        headers["CALLBACK"] = "<http://%s:%d/eventSub>" % event_host
        headers["HOST"] = '%s:%d' % (Paddr.hostname, Paddr.port)

        run_async_call(http_call, success_callback=self.response,
                       error_callback=self.error, delay=0,
                       method='SUBSCRIBE', url=addr,
                       headers=headers)

    def error(self, cargo, error):
        """ Callback for receiving an error.

        @param cargo: callback parameters passed at construction
        @param error: exception raised

        @type error: Exception

        @rtype: boolean
        """
        log.debug("error %s", error)
        self.service.event_sid = ""
        self.service.event_timeout = 0
        if self.callback:
            self.callback(self.cargo, "", 0)
        return True

    def response(self, http_response, cargo):
        """ Callback for receiving the HTTP response on a successful HTTP call.

        @param http_response: response object
        @param cargo: callback parameters passed at construction

        @type http_response: HTTPResponse

        @rtype: boolean
        """
        log.debug("response")

        log.debug('http_response: %s, cargo: %s, msg: %s, ver: %s, status: %s, reason: %s', http_response, cargo, http_response.msg, http_response.version, http_response.status, http_response.reason)

        compressed_headers = {}
        sid = None
        for k, v in dict(http_response.getheaders()).items():
            if not v:
                v = ""
#            compressed_headers[k.lower()] = v.lower().strip()
            compressed_headers[k.lower()] = v.strip()
            if 'sid' in compressed_headers:
                sid = compressed_headers['sid']
                timeout = 1800
                if 'timeout' in compressed_headers:
                    stimeout = compressed_headers['timeout']
                    if stimeout[0:7] == "second-":
                        try:
                            timeout = int(stimeout[7:])
                        except ValueError:
                            pass
                self.service.event_sid = sid
                self.service.event_timeout = timeout
        if self.service._auto_renew_subs and sid:
            self.service._auto_renew_subs.start_auto_renew()
        if self.callback and sid:
            self.callback(self.cargo, sid, timeout)

        return True


class UnsubscribeRequest(object):
    """ Wrapper for an event unsubscription.
    """

    def __init__(self, service, event_host, callback, cargo):
        """ Constructor for the UnsubscribeRequest class.

        @param service: service that is unsubscribing
        @param event_host: 2-tuple (host, port) of the event listener server
        @param callback: callback
        @param cargo: callback parameters

        @type service: Service
        @type event_host: tuple
        @type callback: callable
        """
        self.old_sid = service.event_sid
        service.event_sid = ""
        service.event_timeout = 0

        self.callback = callback
        self.cargo = cargo
        self.service = service

        addr = "%s%s" % (service.url_base, service.event_sub_url)
        Paddr = parse_url(addr)

        headers = {}
#        headers["Host"] = Paddr.hostname
        headers["User-agent"] = 'BRISA-CP'
        headers["HOST"] = '%s:%d' % (Paddr.hostname, Paddr.port)
        headers["SID"] = self.old_sid

        run_async_call(http_call, success_callback=self.response,
                       error_callback=self.error, delay=0,
                       method='UNSUBSCRIBE', url=addr, headers=headers)

    def error(self, cargo, error):
        """ Callback for receiving an error.

        @param cargo: callback parameters passed at construction
        @param error: exception raised

        @type error: Exception

        @rtype: boolean
        """
        if self.callback:
            self.callback(self.cargo, "")
        return True

    def response(self, data, cargo):
        """ Callback for receiving the HTTP response on a successful HTTP call.

        @param data: response object
        @param cargo: callback parameters passed at construction

        @type data: HTTPResponse

        @rtype: boolean
        """
        if self.callback:
            self.callback(self.cargo, self.old_sid)
        return True


class RenewSubscribeRequest(object):
    """ Wrapper for renew an event subscription.
    """

    def __init__(self, service, event_host, callback, cargo):
        """ Constructor for the RenewSubscribeRequest class.

        @param service: service that is renewing the subscribe
        @param event_host: 2-tuple (host, port) of the event listener server
        @param callback: callback
        @param cargo: callback parameters

        @type service: Service
        @type event_host: tuple
        @type callback: callable
        """
        log.debug("renew subscribe")

        if not service.event_sid or service.event_sid == "":
            return

        self.callback = callback
        self.cargo = cargo
        self.service = service

        addr = "%s%s" % (service.url_base, service.event_sub_url)
        Paddr = parse_url(addr)

        headers = {}
        headers["HOST"] = '%s:%d' % (Paddr.hostname, Paddr.port)
        headers["SID"] = self.service.event_sid
        headers["TIMEOUT"] = 'Second-1800'

        run_async_call(http_call, success_callback=self.response,
                       error_callback=self.error, delay=0,
                       method='SUBSCRIBE', url=addr,
                       headers=headers)

    def error(self, cargo, error):
        """ Callback for receiving an error.

        @param cargo: callback parameters passed at construction
        @param error: exception raised

        @type error: Exception

        @rtype: boolean
        """
        log.debug("error", error)
        self.service.event_sid = ""
        self.service.event_timeout = 0
        if self.callback:
            self.callback(self.cargo, "", 0)
        return True

    def response(self, http_response, cargo):
        """ Callback for receiving the HTTP response on a successful HTTP call.

        @param http_response: response object
        @param cargo: callback parameters passed at construction

        @type http_response: HTTPResponse

        @rtype: boolean
        """
        log.debug("response")
        compressed_headers = {}
        sid = None
        for k, v in dict(http_response.getheaders()).items():
            if not v:
                v = ""
#            compressed_headers[k.lower()] = v.lower().strip()
            compressed_headers[k.lower()] = v.strip()
            if 'sid' in compressed_headers:
                sid = compressed_headers['sid']
                timeout = 1800
                if 'timeout' in compressed_headers:
                    stimeout = compressed_headers['timeout']
                    if stimeout[0:7] == "second-":
                        try:
                            timeout = int(stimeout[7:])
                        except ValueError:
                            pass
                self.service.event_sid = sid
                self.service.event_timeout = timeout
        if self.callback and sid:
            self.callback(self.cargo, sid, timeout)

        return True


class AutoRenew(object):

    def __init__(self, service, event_host, callback, cargo):
        self.event_host = event_host
        self.callback = callback
        self.cargo = cargo
        self.service = service

    def start_auto_renew(self):
        self._auto_renew()

    def _auto_renew(self):
        renew_delay = int(self.service.event_timeout) - 10
        if renew_delay <= 0:
            renew_delay = int(self.service.event_timeout) - 0.5
        t_call = ThreadedCall(self._renew, delay=renew_delay)
        t_call.start()

    def _renew(self):
        RenewSubscribeRequest(self.service, self.event_host,
                              self._renew_callback, self.cargo)

    def _renew_callback(self, cargo, sid, timeout):
        if timeout != 0:
            self._auto_renew()
        if self.callback:
            self.callback(cargo, sid, timeout)
