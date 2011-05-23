# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Control Point side action class used for implementing UPnP actions.
"""

from brisa.upnp.base_action import BaseAction, BaseArgument


class Argument(BaseArgument):
    """ Represents an action argument.
    """

    def __init__(self, arg_name, arg_direction, arg_state_var):
        """ Constructor for the Argument class.

        @param arg_name: argument name
        @param arg_direction: argument direction
        @param arg_state_var: argument related state variable

        @type arg_name: string
        @type arg_direction: string
        @type arg_state_var: string
        """
        BaseArgument.__init__(self, arg_name, arg_direction, arg_state_var)


class Action(BaseAction):
    """ Represents a service action.
    """

    def __init__(self, service, name, arguments = []):
        """ Constructor for the Action class.

        @param service: service which holds this action
        @param name: action name
        @param arguments: arguments list

        @type service: Service
        @type name: string
        @type arguments: list of Argument
        """
        BaseAction.__init__(self, service, name, arguments)

    def __call__(self, **kwargs):
        if not self.service._soap_service:
            raise RuntimeError('Service\'s soap service not created. Maybe '\
                               'generate_soap_service() was not called.')
        return self.service._soap_service.call_remote(self.name, **kwargs)
