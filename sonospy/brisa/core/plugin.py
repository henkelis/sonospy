# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Defines a interface for plugins. These plugins can be managed by the
PluginManager.
"""

class PluginInterface(object):
    """ The base class to all plugins. For writing plugins inherit from this
    class and set the appropriate values for your plugin:

        - name: friendly name for your plugin. All objects inside your plugin
          will be named in the form name:id.

        - usage: can be on or off. This value is automatically set when your
          plugin has an entry on the configuration file. When set to 'off', the
          plugin manager will not instantiate the plugin.

        - has_browse_filter: can be True or False. If your plugin implements
          the browse() function in a way that it uses the slicing/sorting
          (filters) parameters, has_browse_filter should be set to True. If
          not, it should be False (which means that the filter will be applied
          by the plugin manager - your plugin returns browse result).
    """
    name = 'plugin_stub'
    usage = False
    watch = False
    has_browse_filter = False

    def __init__(self, *args, **kwargs):
        """ Initializes the base plugin. If overwritten, remember to set
        plugin_manager to PluginManagerSingleton.
        """
        self.plugin_manager = None

    def execute(self):
        """ Loads the plugin media information into the database.
        """
        self.load()

    def load(self):
        """ Forces subclasses to implement the load method.
        """
        raise NotImplementedError("%s: load method not implemented" %
                                  self.name)

    def publish(self, webserver):
        """ Publishes the plugin resources on the service's webserver. Optional.
        """
        pass

    def unload(self):
        """ Unloads the plugin media information from memory.
        """
        raise NotImplementedError("%s: unload method not implemented" %
                                  self.name)

    def browse(self, str_object_id, browse_flag, filter, starting_index,
                requested_count, sort_criteria):
        """ Browse implementation for the plugin. See Plugin documentation for
        information about the has_browse_filter flag.

        @param str_object_id: object to be browsed
        @param browse_flag: UPnP flag
        @param filter: filter parameter
        @param starting_index: The starting intex of the browser
        @param requested_count: Requested number of entries under the object
        @param sort_criteria: sorting criteria

        @type str_object_id: string
        @type browse_flag: string
        @type filter: string
        @type starting_index: ui4
        @type requested_count: ui4
        @type sort_criteria: string

        @return: the results of the browsing action
        @rtype: string
        """
        raise NotImplementedError("browse not implemented for plugin %s" %
                                  self.name)

    def search(self, str_object_id, browse_flag, filter, starting_index,
                requested_count, sort_criteria):
        """ Search implementation for the plugin.

        @param str_object_id: object to be searched
        @param browse_flag: UPnP flag
        @param filter: filter parameter
        @param starting_index: The starting intex of the browser
        @param requested_count: Requested number of entries under the object
        @param sort_criteria: sorting criteria

        @type str_object_id: string
        @type browse_flag: string
        @type filter: string
        @type starting_index: ui4
        @type requested_count: ui4
        @type sort_criteria: string

        @return: the results of the searching action
        @rtype: string
        """
        raise NotImplementedError("search not implemented for plugin %s" %
                                  self.name)
