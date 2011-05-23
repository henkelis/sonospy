# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Device-side device class used for implementing and deploying UPnP devices.
"""

from os import path, mkdir

from brisa.core import log, config, webserver, network

from brisa.upnp.ssdp import SSDPServer
from brisa.upnp.base_device import BaseDevice
from brisa.upnp.device.xml_gen import DeviceXMLBuilder


class Device(BaseDevice):
    """ Class that represents a device.

    When used with default settings, usage should be minimized to
    instantiation, start() and stop().

    The special setting is a create_webserver keyword that can be passed during
    construction. If False, it disables the automatic creation of the internal
    webserver for serving device files, so, the user should create his own
    webserver and set Device.webserver to it.
    """

    def __init__(self, *args, **kwargs):
        """ Constructor for the Device class.

        @param device_type: device type as described on the device reference
        @param friendly_name: a friendly name

        Optional parameters follow below:

        @param udn: uuid for the device. If not specified will be
                    automatically generated.
        @param parent: parent device
        @param manufacturer: manufacturer
        @param manufacturer_url: manufacturer url
        @param model_description: model description
        @param model_name: model name
        @param model_number: model number
        @param model_url: model url
        @param serial_number: serial number
        @param upc: upc
        @param presentation_url: presentation url
        @param create_webserver: see class description for more information.
                                 Default value is True and you should normally
                                 don't pass anything
        @param force_listen_url: forces the webserver to listen on a specific
                                 address. If it's not possible to listen on
                                 that address, another random one will be
                                 generated and used automatically.

        @type device_type: string
        @type friendly_name: string
        @type udn: string
        @type parent: Device
        @type manufacturer: string
        @type manufacturer_url: string
        @type model_description: string
        @type model_name: string
        @type model_number: string
        @type model_url: string
        @type serial_number: string
        @type upc: string
        @type presentation_url: string
        @type create_webserver: bool
        @type force_listen_url: url to use for webserver
        """
        create_webserver = kwargs.pop('create_webserver', True)
        force_listen_url = kwargs.pop('force_listen_url', '')
        udp_listener = kwargs.pop('udp_listener', '')
        BaseDevice.__init__(self, *args, **kwargs)
        self._generate_xml()
        self.SSDP = SSDPServer(self.friendly_name, self.xml_filename, udp_listener=udp_listener)
        self.webserver = None
        if create_webserver:
            self._create_webserver(force_listen_url)

    def add_service(self, service):
        """ Adds a service to the device.
        """
        assert self.location, 'service does not have a location attribute yet'\
                              '. It must have a location set before adding '\
                              'services. If you passed create_webserver=Fal'\
                              'se, you must create the webserver in your '\
                              'own fashion and set self.location to the '\
                              'listening URL before adding services. This '\
                              'problem may also occur if you pass an '\
                              'invalid force_listen_url parameter.'
        service.url_base = self.location
        BaseDevice.add_service(self, service)

    def _create_webserver(self, force_listen_url=''):
        if force_listen_url:
            p = network.parse_url(force_listen_url)
            self.webserver = webserver.WebServer(host=p.hostname, port=p.port)
        else:
            self.webserver = webserver.WebServer()

        self.location = self.webserver.get_listen_url()

    def _generate_xml(self):
        self.xml_filename = '%s-root-device.xml' % self.friendly_name
        self.xml_filename = self.xml_filename.replace(' ', '')
        self._xml_filepath = path.join(config.manager.brisa_home, 'tmp_xml')
        if not path.exists(self._xml_filepath):
            mkdir(self._xml_filepath)
        self._xml_filepath = path.join(self._xml_filepath, self.xml_filename)

    def _publish(self):
        assert self.webserver is not None, 'Device was told not to create '\
                                           'webserver (with False on the '\
                                           'create_webserver parameter) and'\
                                           'device.webserver was not set'\
                                           'manually as it should.'
        log.info('Publishing device %s' % self.friendly_name)
        DeviceXMLBuilder(self).generate_to_file(self._xml_filepath)
        self.webserver.add_static_file(webserver.StaticFile(self.xml_filename,
                                                            self._xml_filepath))

        log.info('Publishing device\'s services')
        for v in self.services.values():
            v.publish(self.webserver)

    def start(self):
        """ Starts the device.
        """
        log.info('Starting device %s' % self.friendly_name)
        log.info('Starting device\'s services')
        for k, v in self.services.items():
            try:
                log.info('Starting service %s' % k)
                v.start()
            except Exception, e:
                log.error('Error starting service %s: %s' % (k, e))
        self._publish()
        self.SSDP.register_device(self)
        self.webserver.start()
        self.SSDP.start()
        log.info('Finished starting device %s' % self.friendly_name)

    def stop(self):
        """ Stops the device.
        """
        self.SSDP.stop()
        self.webserver.stop()

    def is_running(self):
        return self.webserver.is_running() and \
               self.SSDP.is_running()

    def destroy(self):
        if self.is_running():
            self.stop()
        self._cleanup()

    def _cleanup(self):
        self.SSDP = None
        self.webserver = None
