# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Device description XML generator.
"""

from xml.etree.cElementTree import ElementTree, Element, SubElement

from brisa.upnp.upnp_defaults import UPnPDefaults


class DeviceXMLBuilder(object):

    def __init__(self, device):
        self.device = device
        self.url_base = device.location

    def get_element(self):
        # <root>
        elt = Element('root', xmlns = 'urn:schemas-upnp-org:' +
                           UPnPDefaults.SCHEMA_VERSION)
        # <specVersion>
        spec_version_element = SubElement(elt, 'specVersion')
        element = SubElement(spec_version_element, 'major')
        element.text = UPnPDefaults.SCHEMA_VERSION_MAJOR
        element = SubElement(spec_version_element, 'minor')
        element.text = UPnPDefaults.SCHEMA_VERSION_MINOR

        # <urlBase>
#        if self.url_base != None:
#            element = SubElement(elt, 'URLBase')
#            element.text = self.url_base

        # <device>
        elt.append(DeviceXMLGenerator(self.device).generate())
        return elt

    def generate_to_file(self, filepath):
        ElementTree(self.get_element()).write(filepath)
        ElementTree(self.get_element()).write("device.xml")

    def generate(self):
        ElementTree(self.get_element())


class DeviceXMLGenerator(object):

    def __init__(self, device):
        self.device = device

    def generate(self):
        self.device_element = Element("device")
        self._create_device()
        self._create_icon_list()
        self._create_service_list()
        self._create_embedded_devices()
        return self.device_element

    def _create_device(self):
        
        element = SubElement(self.device_element, "deviceType")
        element.text = self.device.device_type

        element = SubElement(self.device_element, "friendlyName")
        element.text = self.device.friendly_name

        element = SubElement(self.device_element, "manufacturer")
        element.text = self.device.manufacturer

        element = SubElement(self.device_element, "manufacturerURL")
        element.text = self.device.manufacturer_url

        element = SubElement(self.device_element, "modelDescription")
        element.text = self.device.model_description

        element = SubElement(self.device_element, "modelName")
        element.text = self.device.model_name

        element = SubElement(self.device_element, "modelURL")
        element.text = self.device.model_url

        element = SubElement(self.device_element, "modelNumber")
        element.text = self.device.model_number

        element = SubElement(self.device_element, "serialNumber")
        element.text = self.device.serial_number

        element = SubElement(self.device_element, "UDN")
        element.text = self.device.udn

#        element = SubElement(self.device_element, "UPC")
#        element.text = self.device.upc

        element = SubElement(self.device_element, "presentationURL")
        element.text = self.device.presentation_url

        element = SubElement(self.device_element, 'dlna:X_DLNADOC')
        element.attrib['xmlns:dlna'] = 'urn:schemas-dlna-org:device-1-0'
        element.text = 'DMS-1.00'

#        element = SubElement(self.device_element, 'dlna:X_DLNADOC')
#        element.attrib['xmlns:dlna'] = 'urn:schemas-dlna-org:device-1-0'
#        element.text = 'DMS-1.50'

#        element = SubElement(self.device_element, 'dlna:X_DLNADOC')
#        element.attrib['xmlns:dlna'] = 'urn:schemas-dlna-org:device-1-0'
#        element.text = 'M-DMS-1.50'

#        element = SubElement(self.device_element, 'dlna:X_DLNACAP')
#        element.attrib['xmlns:dlna'] = 'urn:schemas-dlna-org:device-1-0'
#        element.text = 'av-upload,image-upload,audio-upload'

    def _create_icon_list(self):
        #<device><iconList>
        device_icons = self.device.icons
        if len(device_icons) > 0:
            icon_list_element = SubElement(self.device_element, "iconList")
            for device_icon in device_icons:
                icon_element = SubElement(icon_list_element, "icon")
                element = SubElement(icon_element, "mimetype")
                element.text = device_icon.get_mimetype()

                element = SubElement(icon_element, "width")
                element.text = device_icon.get_width()

                element = SubElement(icon_element, "height")
                element.text = device_icon.get_height()

                element = SubElement(icon_element, "depth")
                element.text = device_icon.get_depth()

                element = SubElement(icon_element, "url")
                element.text = device_icon.get_url()

    def _create_service_list(self):
        device_services = self.device.services
        if len(device_services) > 0:
            service_list_element = SubElement(self.device_element,
                                              "serviceList")
            for k, device_service in device_services.items():
                service_element = SubElement(service_list_element, "service")
                element = SubElement(service_element, "serviceType")
                element.text = device_service.service_type

                element = SubElement(service_element, "serviceId")
                element.text = device_service.id

                element = SubElement(service_element, "SCPDURL")
                element.text = device_service.scpd_url

                element = SubElement(service_element, "controlURL")
                element.text = device_service.control_url

                element = SubElement(service_element, "eventSubURL")
                element.text = device_service.event_sub_url

                element = SubElement(service_element, "presentationURL")
                element.text = device_service.presentation_url

    def _create_embedded_devices(self):
        if self.device.is_root_device():
            embedded_devices = self.device.devices

            if len(embedded_devices) > 0:
                device_list_element = SubElement(self.device_element,
                                                 "deviceList")
                for embedded_device in embedded_devices:
                    embedded_device_description = DeviceXMLGenerator(
                                                            embedded_device)
                    device_list_element.append(embedded_device_description.
                                               create_description())


class ServiceXMLBuilder(object):

    def __init__(self, service):
        self.service = service

    def get_element(self):
        # <root>
        elt = Element('scpd', xmlns = 'urn:schemas-upnp-org:' +
                           UPnPDefaults.SERVICE_SCHEMA_VERSION)
        # <specVersion>
        spec_version_element = SubElement(elt, 'specVersion')
        element = SubElement(spec_version_element, 'major')
        element.text = UPnPDefaults.SCHEMA_VERSION_MAJOR
        element = SubElement(spec_version_element, 'minor')
        element.text = UPnPDefaults.SCHEMA_VERSION_MINOR

        # <actionList> and <serviceStateTable>
        action_list_element, service_state_table_element = ServiceXMLGenerator(self.service).generate()
        elt.append(action_list_element)
        elt.append(service_state_table_element)
        return elt

    def generate_to_file(self, filepath):
        ElementTree(self.get_element()).write(filepath)

    def generate(self):
        ElementTree(self.get_element())


class ServiceXMLGenerator(object):

    def __init__(self, service):
        self.service = service

    def generate(self):
        self.action_list_element = Element("actionList")
        if self.service.get_actions():
            self._create_actions(self.service.get_actions())
        self.service_state_table_element = Element("serviceStateTable")
        self._create_variables(self.service.get_variables())
        return self.action_list_element, self.service_state_table_element

    def _create_actions(self, actions):
        for action_name, action in actions.iteritems():
            action_element = SubElement(self.action_list_element, "action")

            element = SubElement(action_element, "name")
            element.text = action.name
            
            # <argumentList>
            argument_list_element = SubElement(action_element, "argumentList")
            if action.arguments:
                self._create_arguments(argument_list_element, action.arguments)

    def _create_arguments(self, argument_list_element, arguments):
        for arg in arguments:
            arg_element = SubElement(argument_list_element, "argument")

            element = SubElement(arg_element, "name")
            element.text = arg.name

            element = SubElement(arg_element, "direction")
            element.text = arg.direction

            element = SubElement(arg_element, "relatedStateVariable")
            element.text = arg.state_var.name

    def _create_variables(self, state_variables):
        for var_name, var in state_variables.iteritems():
            var_element = SubElement(self.service_state_table_element, "stateVariable")
            if var.send_events:
                var_element.attrib['sendEvents'] = 'yes'
            else:
                var_element.attrib['sendEvents'] = 'no'

            element = SubElement(var_element, "name")
            element.text = var.name

            element = SubElement(var_element, "dataType")
            element.text = var.data_type

            element = SubElement(var_element, "defaultValue")
            element.text = var.get_value()
            
            # <allowedValueList>
            allowed_value_list_element = SubElement(var_element, "allowedValueList")
            
            for allowed_value in var.allowed_values:
                element = SubElement(allowed_value_list_element, "allowedValue")
                element.text = allowed_value
