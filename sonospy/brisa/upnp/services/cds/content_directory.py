# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2005, Tim Potter <tpot@samba.org>
# Copyright 2006 John-Mark Gurney <gurney_j@resnet.uoregon.edu>
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Content Directory service implementation.

Common usage is to just add a ContentDirectory class instance to a device.
"""

import os.path

from brisa.core import log, plugin_manager
from brisa.upnp.device import Service
from brisa.upnp.didl.didl_lite import Element
from brisa.upnp.services.xmls import xml_path


log = log.getLogger('services.cds')

service_name = 'ContentDirectory'
service_type = 'urn:schemas-upnp-org:service:ContentDirectory:1'
scpd_xml_path = os.path.join(xml_path, 'content-directory-scpd.xml')


def compare_objects(a, b):
    """ Compares two DIDL objects by their title for proper sorting.

    @param a: A DIDL object to be compared with.
    @param b: A DIDL object to compare with.

    @type a: DIDL
    @type b: DIDL

    @return: The comparation result.
    @rtype: boolean
    """
    if a.title.lower().startswith("all "):
        return -1

    if b.title.lower().startswith("all "):
        return 1

    return cmp(a.title.lower(), b.title.lower())


class ContentDirectory(Service):
    """ Content Directory service implementation (version 1.0).
    """

    def __init__(self, plugins_folder, plugins_module_str):
        Service.__init__(self, service_name, service_type, '', scpd_xml_path)
        self.plugin_manager = plugin_manager.PluginManager(plugins_folder,
                                                           plugins_module_str)
        self.updateID = 0

    def start(self):
        """ Starts the ContentDirectory by loading the plugins.
        """
        self.plugin_manager.load_plugins()

    def stop(self):
        """ Stops the ContentDirectory servie by unloading the plugins.
        """
        self.plugin_manager.unload_plugins()

    def publish(self, webserver):
        Service.publish(self, webserver)
        self.plugin_manager.publish_plugins(webserver)

    def soap_GetSearchCapabilities(self, *args, **kwargs):
        """ Returns the search capabilities supported by the device.

        @param args: list of arguments for the GetSearchCapabilities UPnP\
        function
        @param kwargs: dict of arguments for the GetSearchCapabilities UPnP\
        function

        @type args: list
        @type kwargs: dict

        @return: the search capabilities supported by the device
        @rtype: dict
        """
        log.debug('Action on ContentDirectory: GetSearchCapabilities()')
        # While the search method is not properly implemented, the server does
        # not support search.
        return {'SearchCaps': ''}

    def soap_GetSortCapabilities(self, *args, **kwargs):
        """ Returns the CSV list of meta-data tags that can be used in
        sortCriteria.

        @param args: list of arguments for the GetSortCapabilities UPnP\
        function
        @param kwargs: dict of arguments for the GetSortCapabilities UPnP\
        function

        @type args: list
        @type kwargs: dict

        @return: CSV list of meta-data
        @rtype: dict
        """
        log.debug('Action on ContentDirectory: GetSortCapabilities()')
        return {'SortCaps': 'dc:title'}

    def soap_GetSystemUpdateID(self, *args, **kwargs):
        """ Returns the current value of state variable SystemUpdateID.

        @param args: list of arguments for the GetSystemUpdateID UPnP\
        function
        @param kwargs: dict of arguments for the GetSystemUPdateID UPnP\
        function

        @type args: list
        @type kwargs: dict

        @return: current value of SystemUpdateID
        @rtype: dict
        """
        log.debug('Action on ContentDirectory: GetSystemUpdateID()')
        return {'Id': self.updateID}

    def soap_Browse(self, *args, **kwargs):
        """ Implements the Browse action for the ContentDirectory.

        @param args: list of arguments for the Browse UPnP\
        function
        @param kwargs: dict of arguments for the Browse UPnP\
        function

        @type args: list
        @type kwargs: dict

        @return: the results of the browsing
        @rtype: dict
        """
        log.debug('Action on ContentDirectory: Browse%s', args)
        # Formats the parameters for the real soap browse
        args = (kwargs['ObjectID'], kwargs['BrowseFlag'], kwargs['Filter'],
                kwargs['StartingIndex'], kwargs['RequestedCount'],
                kwargs['SortCriteria'])
        l = {}
        l['query'] = 'Browse(ObjectID=%s, BrowseFlags=%s, Filter=%s, ' \
            'StartingIndex=%s RequestedCount=%s SortCriteria=%s)' % \
            tuple(map(repr, args))
        try:
            ret = self._soap_Browse(*args)
        except Exception, e:
            log.error('Action Browse on ContentDirectory: %s', e.message)

        l['response'] = ret

        return ret

    def _soap_Browse(self, *args):
        """ Real implementation of the soap browse.

        @param args: list of arguments
        @type args: list

        @return: the results of browsing
        @rtype: dict
        """
        (object_id, browse_flag, filter, starting_index, requested_count,
         sort_criteria) = args
        try:
            starting_index = int(starting_index)
            requested_count = int(requested_count)
            last_index = None
            plugin = self.plugin_manager.root_plugin

            if browse_flag == 'BrowseDirectChildren' and \
            requested_count != 0:
                last_index = requested_count + starting_index

            if ':' in object_id:
                namespace = object_id.split(':')[0]
                plugin = self.plugin_manager.plugins_instances[namespace]

                if not plugin:
                    log.error('Could not get plugin associated with this'\
                              'browse action on id %s' % object_id)

            elements = plugin.browse(object_id, browse_flag, filter,
                                     starting_index, requested_count,
                                     sort_criteria)

            elements.sort(cmp=compare_objects)
            didl = Element()
            total = 0

            if plugin.has_browse_filter:
                for item in elements:
                    didl.add_item(item)
                    total = total + 1
            else:
                for item in elements[starting_index: last_index]:
                    didl.add_item(item)
                    total = total + 1

            didl_xml = didl.to_string()
            soap_result = {'Result': didl_xml,
                           'TotalMatches': len(elements),
                           'NumberReturned': total,
                           'UpdateID': self.updateID}
        except Exception, e:
            soap_result = {'Result': '',
                           'TotalMatches': 0,
                           'NumberReturned': 0,
                           'UpdateID': self.updateID}
            log.error('ContentDirectory.Browse internal problem: %s', e)

        return soap_result

    def soap_Search(self, *args, **kwargs):
        """ Search for objects that match some search criteria.

        @param args: list of arguments for the Search UPnP function
        @param kwargs: dict of arguments for the Search UPnP function

        @type args: list
        @type kwargs: dict

        TODO: forward the search to the respective plugin.
        TODO: implement the search.
        """
        return {'Result': '',
                'NumberReturned': 0,
                'TotalMatches': 0,
                'UpdateID': self.updateID}
