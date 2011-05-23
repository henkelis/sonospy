# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

"""
BRisa configuration API consists of access methods (sets and gets) to the
configuration.

When initialized (imported), the configuration reads data from the
configuration persistence and stores it on a so called "state". By default,
gets/sets do not apply directly on the persistence, but on the state. For
example, setting a parameter value with a set_parameter() applies by default
on the state.

The state can be save()'d - stored on the persistence - or update()'d - updated
with latest persistence values.

There's an override that can be made in order to make sets/gets apply directly
on the persistence. This can be achieved by setting direct_access to True. One
can use directly config.manager.set_direct_access(True) or just set it
directly with config.manager.direct_access = True.

Basically, holding a state is useful for avoiding overhead during runtime (some
configurations never change during runtime and those that change are very out
numbered). Also, for those configurations that needs monitoring, setting
them and getting them is obviously faster when accessing the state.

Note that some methods of config.* are just links to methods of
config.manager (like config.get_parameter and config.manager.get_parameter).

Special variables
=================
- brisa_home: BRisa's home folder for the user running brisa
- version: BRisa version
- __interface__: network interface. Can be modified directly during
                 runtime for modifying other modules behavior
- shared_url: may be used as a global variable for sharing url between
              web servers
"""

import sys
import os
import shutil
import cPickle
import platform

from brisa import version as brisa_version


brisa_home = os.path.join(os.path.expanduser('~'), ".brisa")


def get_platform_name():
    """ Returns the platform name for this machine. May return 'win32',
    'unix', 'java', 'mac' or '' (in case it wasn't possible to resolve
    the name).

    """
    if platform.mac_ver()[0]:
        return 'mac'
    if platform.win32_ver()[0]:
        return 'windows'
    if any(platform.dist()):
        return 'unix'
    if platform.java_ver()[0] or platform.java_ver()[1]:
        return 'java'

    return ''


class ConfigurationManager(object):
    """ Class that provides an easy way of managing configurations.

    Configuration is organized in sections, which may contain parameters.
    Each section has a name and a parameter has a name and a value.

    Concerning storage, the configuration can be saved on a sqlite database.
    Also, there's a feature called "direct access" that enables direct
    operations on the database. For example, a get_parameter() call would
    retrieve the value of a parameter directly from the database, if the
    feature is enabled.

    When disabled, all methods apply to (what we call) the "state". The state
    initially contains the same information that is on the database, but if
    the "direct access" feature is disabled, all get()'s and set()'s apply
    to the state. This means you can have a "runtime configuration" and a
    "static configuration".

    By default, the "direct access" feature is disabled. To enable it, just
    call set_direct_access(True).

    The state can be saved on the persistence by explicitly calling manager.\
    save(). It can also update its values by explicitly calling update().
    """

    def __init__(self, config_path='', default_config={}):
        """ Constructor for the ConfigurationManager class.

        @param config_path: path of the database to work on. If not supplied
                            will work on a memory database.
        @param default_config: default sections and parameters. Keys are
                               section names and values are dicts where
                               keys,value pairs represent a parameter
                               name and value, respectivelly.

        @type config_path: string
        @type default_config: dict
        """
        self._state = {}
        self._state_diffs = {}
        self._default_config = default_config
        self._config_path = config_path
        self.direct_access = False

    def set_direct_access(self, access=False):
        """ Sets the direct access option of the ConfigurationManager. When
        True, direct access makes all get and set methods work directly on the
        database, not on the current state.

        Another short description is: direct access disables the
        ConfigurationManager state feature.

        @param access: The direct access option of the ConfigurationManager

        @type access: boolean
        """
        self.direct_access = access

    def get_direct_access(self):
        """ Returns False if the ConfigurationManager is currently working on
        the runtime state. Otherwise, it will return True, which means it's
        working directly on the persistence.

        @return: The current status of the ConfigurationManager
        @rtype: boolean
        """
        return self.direct_access

    def update(self):
        """ Updates the current state of the manager according to persistence
        data.
        """
        self._state = cPickle.load(open(self._config_path, 'rb'))

    def save(self):
        """ Stores the state of the manager on the persistence.
        """
        cPickle.dump(self._state, open(self._config_path, 'wb'),
                     cPickle.HIGHEST_PROTOCOL)

    def get_parameter(self, section='', parameter=''):
        """ Retrieves the value associated with the parameter in the section
        given.

        @param section: section to find the parameter
        @param parameter: parameter to return the value

        @type section: string
        @type parameter: string

        @return: the value for the given parameter
        @rtype: string
        """
        if self.get_direct_access():
            self.update()

        if section in self._state:
            return self._state[section].get(parameter, '')

        return ''

    def get_parameter_bool(self, section='', parameter=''):
        """ Retrieves the bool associated with the parameter in the section
        given. Returns True in case of 'on', 'yes', '1' or 'True' (False if
        not on this list).

        @param section: section to find the parameter
        @param parameter: parameter to return the value

        @type section: string
        @type parameter: string

        @return: the existence or not of the parameter
        @rtype: boolean
        """
        value = self.get_parameter(section, parameter)

        if value in ['on', 'yes', '1', 'True', True]:
            return True

        return False

    def get_parameter_as_list(self, section='', parameter='', token=':'):
        """ Retrieves the list associated with the parameter in the section
        given.

        @param section: section to find the parameter
        @param parameter: parameter where is located the list
        @param token: split token for the list

        @type section: string
        @type parameter: string
        @type token: string

        @return: list associated with the parameter
        @rtype: []
        """
        value = self.get_parameter(section, parameter)

        if value:
            return value.split(token)

        return []

    def set_parameter(self, section, parameter, par_value=None):
        """ Sets a parameter's value in the given section. If the parameter
        does not exist, it gets created.

        @param section: section to set the parameter
        @param parameter: parameter to set the value
        @param par_value: value to be set

        @type section: string
        @type parameter: string
        @type par_value: string
        """
        if section not in self._state:
            self._state[section] = {}

        if par_value == None and parameter in self._state[section]:
            self._state[section].pop(parameter)
        else:
            self._state[section][parameter] = par_value

        if self.get_direct_access():
            self.save()

    def rem_section(self, section):
        """ Removes a section given the name.

        @param section: section name to be removed
        @type section: string
        """
        if section in self._state:
            self._state.pop(section)
        else:
            raise ValueError('section %s does not exist' % section)

        if self.get_direct_access():
            self.save()

    def contains(self, section, parameter):
        """ Returns wether the given section exists and contains the given
        parameter.

        @param section: section name
        @param parameter: parameter to check if present

        @type section: string
        @type parameter: string

        @return: Exitance of the parameter on the given section.
        @rtype: boolean
        """
        if self.get_parameter(section, parameter):
            return True
        return False

    def items(self, section):
        """ Returns all the items of the given section.

        @param section: string

        @type section: string

        @return: all the items of the given section
        @rtype: dictionary
        """
        if self.get_direct_access():
            self.update()

        return self._state.get(section, {})

    def get_section_names(self):
        """ Returns the names of all sections.

        @return: name of all sections
        @rtype: list
        """
        if self.get_direct_access():
            self.update()

        return self._state.keys()


# BRisa Default configuration
# keys, values = sections, dict of parameters
_default_config = {'brisa':
                        {'owner': 'brisa',
                         'version': '0.10.0',
                         'encoding': 'utf-8',
                         'logging': 'INFO',
                         'logging.field_type': 'entry',
                         'logging_output': 'file',
                         'logging_output.field_type': 'entry',
                         'listen_interface': 'eth0'}}


class _BRisaConfigurationManager(ConfigurationManager):
    """ Custom ConfigurationManager adapted to provide auto-upgrade with
    configurations merging for BRisa.
    """
    _merge_configurations = False
    brisa_version = brisa_version
    brisa_home = brisa_home

    def __init__(self):
        """ Constructor for the _BRisaConfigurationManager class. """
        ConfigurationManager.__init__(self, os.path.join(brisa_home,
                                                   'configurations.pickle'),
                                                       _default_config)
        self._check_config_file()

        if self._merge_configurations:
            self._merge_configs()

        self.update()

    def _merge_configs(self):
        """ Merges an old configuration with the default one.
        """
        # Check version
        section = self.items('brisa')

        if not section:
            self.set_direct_access(False)
            return

        if 'version' not in section:
            return

        version = section['version']

        if not version:
            return

        if version.value == self.brisa_version:
            return

        self.set_direct_access(True)

        for section in self.get_section_names():
            s = self.items(section)

            # If section retrieved successfully
            if s:
                for k, v in s:
                    if k in self._default_config[section]:
                        self._default_config[section][k] = v

        self.set_direct_access(False)

        # Rename configuration.db to configuration.db.old
        old_config_path = '%s%s' % (self._config_path, '.old')
        os.rename(self._config_path, old_config_path)

        # Initialize the database based on self._default_config
        self._initialize_database()

    def _check_config_file(self):
        """ If brisa home does not exist for the user or it exists and does not
        contain a configuration file, a default configuration is used.

        If there's already one configuration, then it gets merged with the
        default.
        """
        if os.path.exists(brisa_home):
            # Home exists
            if os.path.isfile(self._config_path):
                # There's an old config file
                self._merge_configurations = True
            else:
                # There's no old config file, just create the default
                self._merge_configurations = False
                self._initialize_database()
        else:
            # Home does not exist
            os.mkdir(brisa_home)
            os.chmod(brisa_home, 0777)
            self._merge_configurations = False
            self._initialize_database()
            os.chmod(self._config_path, 0666)

    def _initialize_database(self):
        """ Creates an initial database for BRisa. This database contains base
        sections and parameters with default values. Creating this through code
        is better than manually because it is better maintainable and the
        creation is automatic.
        """
        self._state = self._default_config
        self.save()


# Manager for BRisa
manager = _BRisaConfigurationManager()

shared_url = ""
get_parameter_bool = manager.get_parameter_bool
get_parameter = manager.get_parameter
get_parameter_as_list = manager.get_parameter_as_list
set_parameter = manager.set_parameter
contains = manager.contains
__interface__ = get_parameter('connection', 'listenif')
platform_name = get_platform_name()
