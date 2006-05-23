# Copyright 2004-2005 Canonical Ltd.  All rights reserved.

"""Customized widgets used in Launchpad."""

__metaclass__ = type

__all__ = ['TitleWidget', 'SummaryWidget', 'DescriptionWidget',
           'ShipItRecipientDisplaynameWidget', 'ShipItOrganizationWidget',
           'ShipItCityWidget', 'ShipItProvinceWidget',
           'ShipItAddressline1Widget', 'ShipItAddressline2Widget',
           'ShipItPhoneWidget', 'ShipItReasonWidget']

from zope.interface import implements

from zope.schema.interfaces import IText
from zope.app.form.browser import TextAreaWidget, TextWidget

class TitleWidget(TextWidget):
    """A launchpad title widget; a little wider than a normal Textline."""
    implements(IText)
    displayWidth = 44


class SummaryWidget(TextAreaWidget):
    """A widget to capture a summary."""
    implements(IText)
    width = 44
    height = 5


class DescriptionWidget(TextAreaWidget):
    """A widget to capture a description."""
    implements(IText)
    width = 44
    height = 10


class ShipItRecipientDisplaynameWidget(TextWidget):
    """See IShipItRecipientDisplayname"""
    displayWidth = displayMaxWidth = 20


class ShipItOrganizationWidget(TextWidget):
    """See IShipItOrganization"""
    displayWidth = displayMaxWidth = 30


class ShipItCityWidget(TextWidget):
    """See IShipItCity"""
    displayWidth = displayMaxWidth = 30


class ShipItProvinceWidget(TextWidget):
    """See IShipItProvince"""
    displayWidth = displayMaxWidth = 30


class ShipItAddressline1Widget(TextWidget):
    """See IShipItAddressline1"""
    displayWidth = displayMaxWidth = 30


class ShipItAddressline2Widget(TextWidget):
    """See IShipItAddressline2"""
    displayWidth = displayMaxWidth = 30


class ShipItPhoneWidget(TextWidget):
    """See IShipItPhone"""
    displayWidth = displayMaxWidth = 16


class ShipItReasonWidget(TextAreaWidget):
    """See IShipItReason"""
    width = 40
    height = 4
