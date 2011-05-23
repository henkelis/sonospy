# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2009, Brisa team <brisa-develop@garage.maemo.org>

""" Control point side device implementation.

If you're using the control point high level API with no modifications on the
global flags (located on module brisa), then you shouldn't need to create this
class manually.

The framework default response to a device arrival is to build it and its
services automatically and forward it to your control point on the
"new_device_event" subscribed callback. This callback will receive the device
already ready for all actions.

Service objects contained by a device should be retrieved using the method
Device.get_service_by_type or accessing the Device.services dictionary directly.
"""

import uuid
import brisa

from brisa.core import log
from brisa.core.network import url_fetch
from brisa.upnp.base_device import BaseDevice, BaseDeviceIcon
from brisa.upnp.control_point.device_builder import DeviceAssembler
from brisa.upnp.upnp_defaults import UPnPDefaults


class Device(BaseDevice):
    """ Represents an UPnP device.

    Consult http://upnp.org/standardizeddcps/basic.asp as a basic reference.
    """

    def add_device(self, device):
        if not BaseDevice.add_device(self, device):
            # Could not add device
            return False
        if brisa.__skip_soap_service__:
            return

        # Auto generate soap service
        self._generate_soap_services_for_device(device)

    def generate_soap_services(self):
        """ Generates soap services for services and devices contained this
        device.
        """
        # Set SOAPService to each device service
        self._generate_soap_services_for_device(self)

        # Set SOAPService to each embedded child device
        for child_device in self.devices.values():
            self._generate_soap_services_for_device(child_device)

    def _generate_soap_services_for_device(self, device):
        """ Generates soap services for a single device

        @param device: device to generate soap services from
        @type device: Device
        """
        for k, service in device.services.items():
            service.generate_soap_service()

    @classmethod
    def get_from_location(cls, location):
        return DeviceAssembler(cls(), location).mount_device()

    @classmethod
    def get_from_location_async(cls, location, callback, cargo):
        DeviceAssembler(cls(), location).mount_device_async(callback, cargo)

    @classmethod
    def get_from_file(cls, location, filename):
        return DeviceAssembler(cls(), location, filename).mount_device()

    @classmethod
    def get_from_file_async(cls, location, filename, callback, cargo):
        DeviceAssembler(cls(), location, filename).mount_device_async(callback,
                                                                      cargo)
