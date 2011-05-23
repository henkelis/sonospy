# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php or see LICENSE file.
# Copyright 2007-2008 Brisa Team <brisa-develop@garage.maemo.org>

""" Facilities for python properties generation.
"""


def gen_property_with_default(name, fget=None, fset=None, doc=""):
    """ Generates a property of a name either with a default fget or a default
    fset.

    @param name: property name
    @param fget: default fget
    @param fset: default fset
    @param doc: documentation for the property

    @type name: string
    @type fget: callable or None
    @type fset: callable or None
    @type doc: string
    """
    if fget == None and fset == None:
        raise NotImplementedError("fget or fset must be not null")

    internal_name = '%s%s' % ("_prop_", name)

    def getter(self):
        if not internal_name in dir(self):
            setattr(self, internal_name, "")
        return getattr(self, internal_name)

    def setter(self, value):
        return setattr(self, internal_name, value)

    if fget is None:
        return property(getter, fset, doc=doc)

    return property(fget, setter, doc=doc)


def gen_property_of_type(name, _type, doc=""):
    """ Generates a type-forced property associated with a name. Provides type
    checking on the setter (coherence between value to be set and the type
    specified).

    @param name: property name
    @param _type: force type
    @param doc: documentation for the property

    @type name: string
    @type _type: type
    @type doc: string
    """
    internal_name = '%s%s' % ("_prop_", name)

    def getter(self):
        return getattr(self, internal_name)

    def setter(self, value):
        if isinstance(value, _type):
            return setattr(self, internal_name, value)
        else:
            raise TypeError(("invalid type '%s' for property %s:"
                             "%s is required.") %
                            (type(value).__name__, name, type(_type).__name__))

    return property(getter, setter, doc=doc)
