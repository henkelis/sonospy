# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008, Brisa Team <brisa-develop@garage.maemo.org>

""" Basic action classes.
"""

__all__ = ('BaseAction', 'BaseArgument')

class BaseAction(object):
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
        self.service = service
        self.name = name
        self.arguments = arguments

    def __call__(self, **kwargs):
        pass

    def cleanup(self):
        self.service = None


class BaseArgument(object):
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
        self.name = arg_name
        self.direction = arg_direction
        self.state_var = arg_state_var
