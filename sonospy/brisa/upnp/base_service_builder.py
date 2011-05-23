# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Builder module for services.
"""

from xml.etree import cElementTree as ElementTree

from brisa.core import log

from brisa.upnp.base_action import BaseArgument, BaseAction
from brisa.upnp.base_service import BaseStateVariable


class BaseServiceBuilder(object):

    def __init__(self, service, fd):
#        print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>BaseServiceBuilder.__init__"
#        print service
        self.service = service
        self.fd = fd
        self._actions = {}
        self._variables = {}

    def build(self):
        """ Builds a service given a file descriptor containing the SCPD XML.

        @return: True if service build succeeded, otherwise False.
        @rtype: bool
        """
        if not self._parse_description(self.fd):
            return False
        self._build_service()
        return True

    def _parse_description(self, fd):
        """ Parses the actions and state variables of a service given a file
        descriptor containing the SCPD XML. File descriptor must be open.

        @param fd: file descriptor
        @type fd: file

        @return: True if service parser succeeded, otherwise False.
        @rtype: bool
        """
#        print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
#        print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>BaseServiceBuilder._parse_description"
        try:
            data = fd.read()
#            print "data: " + str(data)
            data = data[data.find("<"):data.rfind(">")+1]
            tree = ElementTree.XML(data)
#            print "tree: " + str(tree)
            if tree:
                self._parse_actions(tree)
                self._parse_variables(tree)
#                print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>BaseServiceBuilder._parse_description success"
                return True
        except Exception, e:
            log.debug('Could not build service SCPD XML. %s' % str(e))

        return False

    def _parse_actions(self, tree):
        """ Parses actions from a fetched tree.

        @param tree: tree containing the actions
        @type tree: ElementTree
        """
        
#        print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>BaseServiceBuilder._parse_actions"
#        print tree
        
        ns = "urn:schemas-upnp-org:service-1-0"
        for node in tree.findall('.//{%s}action' % ns):
            name = node.findtext('{%s}name' % ns)
            args = []
            for arg in node.findall('.//{%s}argument' % ns):
                arg_direction = arg.findtext('{%s}direction' % ns)
                arg_state_var = arg.findtext('{%s}relatedStateVariable' % ns)
                arg_name = arg.findtext('{%s}name' % ns)
                args.append((arg_name, arg_direction, arg_state_var))
            self._actions[name] = args
            log.debug('#### base_service_builder._parse_actions: %s %s' , str(name), str(args))
#        print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>BaseServiceBuilder._parse_actions complete"

    def _parse_variables(self, tree):
        """ Parses variables from a fetched tree.

        @param tree: tree containing the actions
        @type tree: ElementTree
        """
#        print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>BaseServiceBuilder._parse_variables"
        ns = "urn:schemas-upnp-org:service-1-0"
        for node in tree.findall('.//{%s}stateVariable' % ns):
            # Avoid breaking when sendEvents is not specified.
            send_events = node.attrib.get('sendEvents', 'no')
            # Avoid breaking when multicast is not specified.
            multicast = node.attrib.get('multicast', 'no')

            name = node.findtext('{%s}name' % ns)
            data_type = node.findtext('{%s}dataType' % ns)
            values = [a.text for a in node.findall('.//{%s}allowedValue' % ns)]
            self._variables[name] = (send_events, multicast, data_type, values)
#        print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>BaseServiceBuilder._parse_variables complete"

    def _build_service(self):
        """ Builds a service.
        """
#        print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>BaseServiceBuilder._build_service"
        for name in self._variables.iterkeys():
            send_events, multicast, data_type, values = self._variables[name]
            send_events = True if send_events == 'yes' else False
            multicast = True if multicast == 'yes' else False
            
            self.service.add_state_variable(self.\
                        _create_state_var(name, send_events,
                                       multicast, data_type, values))
        for action_name, action_args in self._actions.iteritems():
            args = []
            for arg_name, arg_direction, arg_state_var in action_args:
                args.append(self._create_argument(arg_name,
                    arg_direction,
                    self.service._state_variables[arg_state_var]))
            self.service._actions[action_name] = self.\
                _create_action(action_name, args)
#            print "AAAAAAAAAAAAAAAAAAAAA"
#            print self.service
#            print action_name
#            print self.service._actions[action_name]
#            print "AAAAAAAAAAAAAAAAAAAAA"
#        print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>BaseServiceBuilder._build_service success"

    def _create_argument(self, arg_name, arg_direction, arg_state_var):
        """ Factory method that creates an action argument.

        @return: The argument object.
        @rtype: BaseArgument
        """
        return BaseArgument(arg_name, arg_direction, arg_state_var)

    def _create_action(self, name, args):
        """ Factory method that creates a service action.

        @return: The action object.
        @rtype: BaseAction
        """
        return BaseAction(self.service, name, args)

    def _create_state_var(self, name, send_events, multicast,
                          data_type, values):
        """ Factory method that creates a service state variable.

        @return: The state variable object.
        @rtype: BaseStateVariable
        """
        return BaseStateVariable(self.service,
                    name, send_events, multicast, data_type, values)
