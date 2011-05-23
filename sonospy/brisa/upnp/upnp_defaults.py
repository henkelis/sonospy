# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" UPnP constants defined on the 1.0 specification.
"""


class UPnPDefaults(object):
    """ UPnP constants defined on the 1.0 specification.
    """
    SERVICE_ID_PREFIX = "urn:upnp-org:serviceId:"
    SERVICE_ID_MS_PREFIX = "urn:microsoft.com:serviceId:"
    SERVICE_SCHEMA_VERSION = "service-1-0"
    SCHEMA_VERSION = "device-1-0"
    SCHEMA_VERSION_MAJOR = "1"
    SCHEMA_VERSION_MINOR = "0"
    NAME_SPACE_XML_SCHEMA = '%s%s' % ("urn:schemas-upnp-org:", SCHEMA_VERSION)
    SSDP_PORT = 1900
    SSDP_ADDR = '239.255.255.250'
    MULTICAST_EVENT_PORT = 7900
    MULTICAST_EVENT_ADDR = '239.255.255.246'
    MSEARCH_DEFAULT_SEARCH_TIME = 600.0
    MSEARCH_DEFAULT_SEARCH_TYPE = 'ssdp:all'


type_map = {str: 'xsd:string',
            unicode: 'xsd:string',
            int: 'xsd:int',
            long: 'xsd:int',
            float: 'xsd:float',
            bool: 'xsd:boolean'}

""" Map a variable to an upnp representation for a type.

@param value: variable value

@return: the value
@rtype: string
"""
def map_upnp_value(value):
    if value == None:
        return None
    
    var_type = type_map[type(value)]
    if var_type == 'xsd:string':
        var_val = value
        if type(value) == unicode:
            var_val = var_val.encode('utf-8')
    elif var_type == 'xsd:int' or var_type == 'xsd:float':
        var_val = str(value)
    elif var_type == 'xsd:boolean':
        var_val = '1' if value else '0'
    else:
        raise ValueError, "Unknown value type"
    
    return var_val

""" Map a variable to an upnp type.

@param value: variable value

@return: the type
@rtype: string
"""
def map_upnp_type(value):
    return type_map[type(value)]
