# Copyright 2016-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Event subscribers for OCI recipe builds."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type

from zope.component import getUtility

from lp.buildmaster.enums import BuildStatus
from lp.oci.interfaces.ocirecipe import OCI_RECIPE_WEBHOOKS_FEATURE_FLAG
from lp.oci.interfaces.ocirecipebuild import IOCIRecipeBuild
from lp.oci.interfaces.ocirecipebuildjob import IOCIRegistryUploadJobSource
from lp.services.features import getFeatureFlag
from lp.services.webapp.publisher import canonical_url
from lp.services.webhooks.interfaces import IWebhookSet
from lp.services.webhooks.payload import compose_webhook_payload


def _trigger_oci_recipe_build_webhook(build, action):
    if getFeatureFlag(OCI_RECIPE_WEBHOOKS_FEATURE_FLAG):
        payload = {
            "recipe_build": canonical_url(build, force_local_path=True),
            "action": action,
            }
        payload.update(compose_webhook_payload(
            IOCIRecipeBuild, build,
            ["recipe", "status"]))
        getUtility(IWebhookSet).trigger(
            build.recipe, "oci-recipe:build:0.1", payload)


def oci_recipe_build_created(build, event):
    """Trigger events when a new OCI recipe build is created."""
    _trigger_oci_recipe_build_webhook(build, "created")


def oci_recipe_build_status_changed(build, event):
    """Trigger events when OCI recipe build statuses change."""
    if event.edited_fields is not None:
        if "status" in event.edited_fields:
            _trigger_oci_recipe_build_webhook(build, "status-changed")
    if (build.recipe.can_upload_to_registry and
            build.status == BuildStatus.FULLYBUILT):
        getUtility(IOCIRegistryUploadJobSource).create(build)
