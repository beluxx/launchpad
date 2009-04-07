# Copyright 2009 Canonical Ltd.  All rights reserved.

"""Helpers to patch circular import shortcuts for the webservice.

Many of the exports for the webservice entries deliberately set various
types to `Interface` because using the real types cause circular import
problems.

The only current option is to later patch the types to the correct value.
The helper functions in this file make that easy.
"""

__metaclass__ = type

__all__ = [
    'patch_entry_return_type',
    'patch_choice_parameter_type',
    'patch_collection_return_type',
    'patch_plain_parameter_type',
    'patch_reference_property',
    ]

EXPORTED_TAG = 'lazr.webservice.exported'


def patch_entry_return_type(exported_class, method_name, return_type):
    """Update return type for a webservice method that returns entries.
    
    :param exported_class: The class containing the method.
    :param method_name: The method name that you need to patch.
    :param return_type: The new return type for the method.
    """
    exported_class[method_name].queryTaggedValue(
        EXPORTED_TAG)['return_type'].schema = return_type


def patch_collection_return_type(exported_class, method_name, return_type):
    """Update return type for a webservice method that returns a collection.

    :param exported_class: The class containing the method.
    :param method_name: The method name that you need to patch.
    :param return_type: The new return type for the method.
    """
    exported_class[method_name].queryTaggedValue(
        EXPORTED_TAG)['return_type'].value_type.schema = return_type


def patch_plain_parameter_type(exported_class, method_name, param_name,
                               param_type):
    """Update a plain parameter type for a webservice method.

    :param exported_class: The class containing the method.
    :param method_name: The method name that you need to patch.
    :param param_name: The name of the parameter that you need to patch.
    :param param_type: The new type for the parameter.
    """
    exported_class[method_name].queryTaggedValue(
        EXPORTED_TAG)['params'][param_name].schema = param_type


def patch_choice_parameter_type(exported_class, method_name, param_name,
                                choice_type):
    """Update a `Choice` parameter type for a webservice method.

    :param exported_class: The class containing the method.
    :param method_name: The method name that you need to patch.
    :param param_name: The name of the parameter that you need to patch.
    :param choice_type: The new choice type for the parameter.
    """
    exported_class[method_name].queryTaggedValue(
        EXPORTED_TAG)['params'][param_name].vocabulary = choice_type


def patch_reference_property(exported_class, property, property_type):
    """Update a `Reference` property type.

    :param exported_class: The class containing the property.
    :param property: The property whose type you want to patch.
    :param property_type: The new type for the property.
    """
    exported_class[property].schema = property_type
