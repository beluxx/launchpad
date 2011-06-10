# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Translations-specific testing infrastructure for Windmill."""

__metaclass__ = type
__all__ = [
    'TranslationsWindmillLayer',
    'TranslationsYUITestLayer',
    ]


from canonical.testing.layers import (
    BaseWindmillLayer,
    BaseYUITestLayer,
    )


class TranslationsWindmillLayer(BaseWindmillLayer):
    """Layer for Translations Windmill tests."""

    @classmethod
    def setUp(cls):
        cls.facet = 'translations'
        cls.base_url = cls.appserver_root_url(cls.facet)
        super(TranslationsWindmillLayer, cls).setUp()


class TranslationsYUITestLayer(BaseYUITestLayer):
    """Layer for Code YUI tests."""

    @classmethod
    def setUp(cls):
        cls.base_url = cls.appserver_root_url()
        super(TranslationsYUITestLayer, cls).setUp()
