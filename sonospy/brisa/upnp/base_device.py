# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2009 Brisa Team <brisa-develop@garage.maemo.org>

""" Basic device classes.
"""

__all__ = ('BaseDevice', 'BaseDeviceIcon')

import uuid


from brisa.core import log


class BaseDevice(object):
    """ Represents an UPnP device.

    Consult http://upnp.org/standardizeddcps/basic.asp as a basic reference.
    """

    def __init__(self, device_type='', friendly_name='', location='', udn=None,
                 parent=None, manufacturer='', manufacturer_url='',
                 model_description='', model_name='', model_number='',
                 model_url='', serial_number='', upc='', presentation_url=''):
        """ Constructor for the Device class.

        @param device_type: device type as described on the device reference
        @param friendly_name: a friendly name
        @param location: network location
        @param udn: uuid
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

        @type device_type: string
        @type friendly_name: string
        @type location: string
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

        @note: basic device reference:
        http://upnp.org/standardizeddcps/basic.asp
        """
        self.device_type = device_type
        self.friendly_name = friendly_name
        self.location = location
        self.udn = udn
        self.parent = parent
        self.manufacturer = manufacturer
        self.manufacturer_url = manufacturer_url
        self.model_description = model_description
        self.model_name = model_name
        self.model_number = model_number
        self.model_url = model_url
        self.serial_number = serial_number
        self.upc = upc
        self.presentation_url = presentation_url
        self.services = {}
        self.devices = {}
        self.icons = []
        self.soap_service = None
        self.is_root = True

        if not udn:
            self.udn = 'uuid:%s' % uuid.uuid4()

    def del_service_by_id(self, id):
        """ Removes service that matches the given id.

        @param id: service id
        @type id: string
        """
        for k, service in self.services.items():
            if service.id == id:
                del self.services[k]
                break

    def add_device(self, device):
        """ Adds a device embedded inside this device.

        @param device: device to be added
        @type device: Device
        """
        if device in self.devices.values():
            log.debug('Device %s already contained by %s' % (device, self))
            return False
        if device.friendly_name not in self.devices:
            self.devices[device.friendly_name] = device
        else:
            d = 0
            name = None
            while not name:
                name = '%s%d' % (device.friendly_name, d)
                if name not in [d.friendly_name for d in self.devices if \
                                device.friendly_name in d.friendly_name]:
                    break
                else:
                    d += 1
                    name = None
                    continue
            self.devices[name] = device
        return True

    def del_device(self, device):
        if device in self.devices.values():
            for k, v in self.devices.items():
                if v == device:
                    del self.devices[k]
                    break

    def add_service(self, service):
        """ Adds a service to the device.
        """
        if service.service_type not in self.services:
            self.services[service.service_type] = service

    def get_service_by_type(self, service_type):
        """ Returns a service given its type.
        """
        return self.services.get(service_type, None)

    def del_service(self, service):
        """ Removes a service, if present on the device.
        """
        if service.service_type in self.services:
            del self.services[service.service_type]

    def is_root_device(self):
        """ Returns True if this device is a root device (it contains embedded
        devices).
        """
        return True if self.devices or self.is_root else False


class BaseDeviceIcon(object):
    """ Represents an icon of a device.
    """

    def __init__(self, mimetype, width, height, depth, url):
        """ Constructor for the DeviceIcon class.

        @param mimetype: mimetype for the icon
        @param width: icon width
        @param height: icon height
        @param depth: icon depth
        @param url: icon url

        @type mimetype: string
        @type width: string
        @type height: string
        @type depth: string
        @type url: string
        """
        self.mimetype = mimetype
        self.width = width
        self.height = height
        self.depth = depth
        self.url = url

    def get_mimetype(self):
        """ Returns icon's mimetype.

        @rtype: string
        """
        return self.mimetype

    def get_width(self):
        """ Returns icon's width.

        @rtype: string
        """
        return  self.width

    def get_height(self):
        """ Returns icon's height.

        @rtype: string
        """
        return self.height

    def get_depth(self):
        """ Returns icon's depth.

        @rtype: string
        """
        return self.depth

    def get_url(self):
        """ Returns icon's url.

        @rtype: string
        """
        return self.url
