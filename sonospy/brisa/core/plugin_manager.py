# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Manager for plugins that implement the plugin interface defined on the
plugin module.
"""

__all__ = ('PluginManager', )


import os

from brisa.core import log
from brisa.core.singleton import Singleton
from brisa.core.plugin import PluginInterface
from brisa.upnp.didl.didl_lite import Container


log = log.getLogger('core.PluginManager')


class RootPlugin(PluginInterface):
    """ Root plugin for all plugins. Receives the first browse which returns
    the initial folder structure.
    """
    name = "rootplugin"
    containers = {}

    def __init__(self):
        """ Constructor for the _RootPlugin class. """
        self._id = 0

    def _get_next_id(self):
        """ Method to get the next plugin id.

        @return: the next plugin id
        @rtype: integer
        """

        self._id += 1
        return self._id

    def load(self):
        """ Adds root containers for the root plugin.
        """
        self.add_container("root")

    def get_container(self, title):
        """ Method to get the container which is equal to the title parameter

        @param title: the title of the container which you want to get
        @type title: string

        @return: The container, if it's there
        @rtype: None or dict
        """
        for id, container in self.containers.items():
            if container.title == title:
                return container
        return None

    def unload(self):
        """ Unload implementation.
        """
        self.containers.clear()

    def browse(self, id, browse_flag, filter, starting_index,
                requested_count, sort_criteria):
        """ Browse implementation.

        @param id: object to be browsed
        @param browse_flag: UPnP flag
        @param filter: filter parameter
        @param starting_index: The starting intex of the browser
        @param requested_count: Requested number of entries under the object
        @param sort_criteria: sorting criteria

        @type id: string
        @type browse_flag: string
        @type filter: string
        @type starting_index: ui4
        @type requested_count: ui4
        @type sort_criteria: string

        @return: the results of the browsing action
        @rtype: string
        """
        if browse_flag == "BrowseDirectChildren":
            return self.containers[id].containers
        else:
            return [self.containers[id]]

    def search(self, id, browse_flag, filter, starting_index, requested_count,
                sort_criteria):
        """ TODO Search implementation.
        """
        return None

    def add_container(self, title, parent_id=-1, plugin=None):
        """ Adds a container to the root plugin.

        @param title: title
        @param parent_id: parent id
        @param plugin: container owner plugin

        @type title: string
        @type parent_id: string
        @type plugin: Plugin

        @return: the added container
        @rtype: MemDIDLContainer
        """
        # Object id
        object_id = 0

        if parent_id != -1:
            object_id = self._get_next_id()

        # Namespace if plugin is present
        if plugin != None:
            if object_id == None:
                raise Exception('Error adding root plugin container: you'\
                                ' must define the object_id')
            if not hasattr(plugin, 'browse') or not hasattr(plugin, "name"):
                raise NotImplementedError('The plugin must implement the'\
                                          '\'browse\' method and assign '\
                                          'an attribute \'name\'.')

            object_id = '%s:%d' % (plugin.name, object_id)

        new_container = Container(id=str(object_id),
                                  title=title,
                                  parent_id=parent_id)

        self.containers[str(object_id)] = new_container

        if parent_id != -1:
            self.containers[str(parent_id)].add_container(new_container)

        return new_container


class PluginManager(Singleton):
    """ Manages plugins.'
    """
    plugins_instances = {}
    plugins_classes = {}

    def __init__(self, plugins_folder, plugins_modules_path):
        """ Instantiates the plugin manager and recognizes the plugins.

        @param plugins_folder: the name of the plugin folder
        @param plugins_modules_path: the path to the plugin folder

        @type plugins_folder: string
        @type plugins_modules_path: string
        """
        self._find_and_import_plugins(plugins_folder, plugins_modules_path)
        self.root_plugin = RootPlugin()
        self.root_plugin.load()
        self.plugins_classes[self.root_plugin.name] = \
            self.root_plugin.__class__
        self._recognize_plugins()

    def _find_and_import_plugins(self, plugins_folder, plugins_modules_path):
        for root, dirs, files in os.walk(plugins_folder):
            if root != plugins_folder:
                break

            for dir in dirs:
                if not dir.startswith("."):
                    try:
                        module_path = '%s.%s' % (plugins_modules_path, dir)
                        __import__(module_path)
                    except Exception, e:
                        msg = 'Error while importing %s plugin. The module '\
                              'path used to load was: %s. Error: %s' % \
                              (dir, module_path, e)
                        log.error(msg)

    def publish_plugins(self, webserver):
        log.info('Publishing plugins for ContentDirectory')
        for v in self.plugins_instances.values():
            v.publish(webserver)

    def load_plugins(self):
        """ Instantiates plugins and loads them using PluginLoader.
        """
        self._instantiate_plugins()
        names = [p.name for p in self.plugins_instances.values() \
                 if p.name!='rootplugin']
        log.info('Detected plugins: %s', ', '.join(names))
        self._load_plugins()

    def unload_plugins(self):
        """ Unload all plugins.
        """
        for p in self.plugins_instances.values():
            log.info('Unloading plugin %s', p.name)
            p.unload()

    def _recognize_plugins(self):
        """ Recognizes plugins classes.
        """
        classes = PluginInterface.__subclasses__()

        plugins_class_ref = self.plugins_classes.values()
        for _class in classes:
            if _class not in plugins_class_ref:
                self.plugins_classes[_class.name] = _class

    def _instantiate_plugins(self):
        """ Instantiates all plugin classes into the plugin manager.
        """
        plugins = self.plugins_classes.values()
        for plugin in plugins:
            if plugin.usage:
                try:
                    self.plugins_instances[plugin.name] = plugin()
                except Exception, e:
                    log.error("Error while instantiating %s: %s" % \
                              (plugin.name, str(e)))

    def _load_plugin(self, plugin):
        """ Loads a plugin using PluginLoader.

        @param plugin: plugin instance to be loaded
        @type plugin: Plugin
        """
        log.info('Loading plugin %s', plugin.name)
        plugin.plugin_manager = self
        plugin.execute()

    def _load_plugins(self):
        """ Loads all plugins selected using _load_plugin() method.
        """
        try:
            plugins = self.plugins_instances.values()
            for plugin in plugins:
                self._load_plugin(plugin)
        except Exception, e:
            log.error("Error loading plugin %s: %s", plugin.name, e)
