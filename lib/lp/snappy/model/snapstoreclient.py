# Copyright 2016-2018 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Communication with the snap store."""

from __future__ import absolute_import, print_function, unicode_literals

__metaclass__ = type
__all__ = [
    'SnapStoreClient',
    ]

import base64
import json
try:
    from json.decoder import JSONDecodeError
except ImportError:
    JSONDecodeError = ValueError
import string
import time
from urlparse import urlsplit

from lazr.restful.utils import get_current_browser_request
from pymacaroons import Macaroon
import requests
from requests_toolbelt import MultipartEncoder
import six
from zope.component import getUtility
from zope.interface import implementer
from zope.security.proxy import removeSecurityProxy

from lp.services.config import config
from lp.services.features import getFeatureFlag
from lp.services.memcache.interfaces import IMemcacheClient
from lp.services.scripts import log
from lp.services.timeline.requesttimeline import get_request_timeline
from lp.services.timeout import urlfetch
from lp.services.webapp.url import urlappend
from lp.snappy.interfaces.snapstoreclient import (
    BadRefreshResponse,
    BadRequestPackageUploadResponse,
    BadScanStatusResponse,
    BadSearchResponse,
    ISnapStoreClient,
    NeedsRefreshResponse,
    ReleaseFailedResponse,
    ScanFailedResponse,
    UnauthorizedUploadResponse,
    UploadFailedResponse,
    UploadNotScannedYetResponse,
    )


class LibraryFileAliasWrapper:
    """A `LibraryFileAlias` wrapper usable with a `MultipartEncoder`."""

    def __init__(self, lfa):
        self.lfa = lfa
        self.position = 0

    @property
    def len(self):
        return self.lfa.content.filesize - self.position

    def read(self, length=-1):
        chunksize = None if length == -1 else length
        data = self.lfa.read(chunksize=chunksize)
        if chunksize is None:
            self.position = self.lfa.content.filesize
        else:
            self.position += length
        return data


class InvalidStoreSecretsError(Exception):
    pass


class MacaroonAuth(requests.auth.AuthBase):
    """Attaches macaroon authentication to a given Request object."""

    # The union of the base64 and URL-safe base64 alphabets.
    allowed_chars = set(string.digits + string.letters + "+/=-_")

    def __init__(self, root_macaroon_raw, unbound_discharge_macaroon_raw=None,
                 logger=log):
        self.root_macaroon_raw = root_macaroon_raw
        self.unbound_discharge_macaroon_raw = unbound_discharge_macaroon_raw
        self.logger = logger

    def _logMacaroon(self, macaroon_name, macaroon_raw):
        """Log relevant information from the authorising macaroons.

        This shouldn't be trusted for anything since we can't verify the
        macaroons here, but it's helpful when debugging.
        """
        macaroon = Macaroon.deserialize(macaroon_raw)
        for caveat in macaroon.first_party_caveats():
            try:
                _, key, value = caveat.caveat_id.split("|")
                if key == "account":
                    account = json.loads(
                        base64.b64decode(value).decode("UTF-8"))
                    if "openid" in account:
                        self.logger.debug(
                            "%s macaroon: OpenID identifier: %s" %
                            (macaroon_name, account["openid"]))
                elif key == "acl":
                    self.logger.debug(
                        "%s macaroon: permissions: %s" %
                        (macaroon_name, value))
                elif key == "channel":
                    self.logger.debug(
                        "%s macaroon: channels: %s" % (macaroon_name, value))
                elif key == "expires":
                    self.logger.debug(
                        "%s macaroon: expires: %s" % (macaroon_name, value))
                elif key == "package_id":
                    self.logger.debug(
                        "%s macaroon: snap-ids: %s" % (macaroon_name, value))
                elif key == "valid_since":
                    self.logger.debug(
                        "%s macaroon: valid since: %s" %
                        (macaroon_name, value))
            except ValueError:
                pass

    def _makeAuthParam(self, key, value):
        # Check framing.
        if not set(key).issubset(self.allowed_chars):
            raise InvalidStoreSecretsError(
                "Key contains unsafe characters: %r" % key)
        if not set(value).issubset(self.allowed_chars):
            # Don't include secrets in exception arguments.
            raise InvalidStoreSecretsError("Value contains unsafe characters")
        self._logMacaroon(key, value)
        return '%s="%s"' % (key, value)

    @property
    def discharge_macaroon_raw(self):
        root_macaroon = Macaroon.deserialize(self.root_macaroon_raw)
        unbound_discharge_macaroon = Macaroon.deserialize(
            self.unbound_discharge_macaroon_raw)
        discharge_macaroon = root_macaroon.prepare_for_request(
            unbound_discharge_macaroon)
        return discharge_macaroon.serialize()

    def __call__(self, r):
        params = []
        params.append(self._makeAuthParam("root", self.root_macaroon_raw))
        if self.unbound_discharge_macaroon_raw is not None:
            params.append(
                self._makeAuthParam("discharge", self.discharge_macaroon_raw))
        r.headers["Authorization"] = "Macaroon " + ", ".join(params)
        return r


# Hardcoded fallback.
_default_store_channels = [
    {"name": "candidate", "display_name": "Candidate"},
    {"name": "edge", "display_name": "Edge"},
    {"name": "beta", "display_name": "Beta"},
    {"name": "stable", "display_name": "Stable"},
    ]


@implementer(ISnapStoreClient)
class SnapStoreClient:
    """A client for the API provided by the snap store."""

    @staticmethod
    def _getTimeline():
        # XXX cjwatson 2016-06-29: This can be simplified once jobs have
        # timeline support.
        request = get_current_browser_request()
        if request is None:
            return None
        return get_request_timeline(request)

    @classmethod
    def _makeSnapStoreError(cls, error_class, requests_error):
        error_message = requests_error.args[0]
        if requests_error.response.content:
            try:
                response_data = requests_error.response.json()
            except JSONDecodeError:
                pass
            else:
                if "error_list" in response_data:
                    error_message = "\n".join(
                        error["message"]
                        for error in response_data["error_list"])
        detail = six.ensure_text(
            requests_error.response.content, errors="replace")
        can_retry = requests_error.response.status_code in (502, 503)
        return error_class(error_message, detail=detail, can_retry=can_retry)

    @classmethod
    def requestPackageUploadPermission(cls, snappy_series, snap_name):
        assert config.snappy.store_url is not None
        request_url = urlappend(config.snappy.store_url, "dev/api/acl/")
        request = get_current_browser_request()
        timeline_action = get_request_timeline(request).start(
            "request-snap-upload-macaroon",
            "%s/%s" % (snappy_series.name, snap_name), allow_nested=True)
        try:
            response = urlfetch(
                request_url, method="POST",
                json={
                    "packages": [
                        {"name": snap_name, "series": snappy_series.name}],
                    "permissions": ["package_upload"],
                    })
            response_data = response.json()
            if "macaroon" not in response_data:
                raise BadRequestPackageUploadResponse(response.text)
            return response_data["macaroon"]
        except requests.HTTPError as e:
            raise cls._makeSnapStoreError(BadRequestPackageUploadResponse, e)
        finally:
            timeline_action.finish()

    @classmethod
    def _uploadFile(cls, lfa, lfc):
        """Upload a single file."""
        assert config.snappy.store_upload_url is not None
        unscanned_upload_url = urlappend(
            config.snappy.store_upload_url, "unscanned-upload/")
        lfa.open()
        try:
            lfa_wrapper = LibraryFileAliasWrapper(lfa)
            encoder = MultipartEncoder(
                fields={
                    "binary": (
                        lfa.filename, lfa_wrapper, "application/octet-stream"),
                    })
            # XXX cjwatson 2016-05-09: This should add timeline information,
            # but that's currently difficult in jobs.
            try:
                response = urlfetch(
                    unscanned_upload_url, method="POST", data=encoder,
                    headers={
                        "Content-Type": encoder.content_type,
                        "Accept": "application/json",
                        })
                response_data = response.json()
                if not response_data.get("successful", False):
                    raise UploadFailedResponse(response.text)
                return {"upload_id": response_data["upload_id"]}
            except requests.HTTPError as e:
                raise cls._makeSnapStoreError(UploadFailedResponse, e)
        finally:
            lfa.close()

    @classmethod
    def _uploadApp(cls, snapbuild, upload_data):
        """Create a new store upload based on the uploaded file."""
        snap = snapbuild.snap
        assert config.snappy.store_url is not None
        assert snap.store_name is not None
        assert snapbuild.date_started is not None
        upload_url = urlappend(config.snappy.store_url, "dev/api/snap-push/")
        data = {
            "name": snap.store_name,
            "updown_id": upload_data["upload_id"],
            "series": snap.store_series.name,
            "built_at": snapbuild.date_started.isoformat(),
            "only_if_newer": True,
            }
        # XXX cjwatson 2016-05-09: This should add timeline information, but
        # that's currently difficult in jobs.
        try:
            assert snap.store_secrets is not None
            response = urlfetch(
                upload_url, method="POST", json=data,
                auth=MacaroonAuth(
                    snap.store_secrets["root"],
                    snap.store_secrets.get("discharge")))
            response_data = response.json()
            return response_data["status_details_url"]
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                if (e.response.headers.get("WWW-Authenticate") ==
                        "Macaroon needs_refresh=1"):
                    raise NeedsRefreshResponse()
                else:
                    raise cls._makeSnapStoreError(
                        UnauthorizedUploadResponse, e)
            raise cls._makeSnapStoreError(UploadFailedResponse, e)

    @classmethod
    def upload(cls, snapbuild):
        """See `ISnapStoreClient`."""
        assert snapbuild.snap.can_upload_to_store
        for _, lfa, lfc in snapbuild.getFiles():
            if not lfa.filename.endswith(".snap"):
                continue
            upload_data = cls._uploadFile(lfa, lfc)
            return cls.refreshIfNecessary(
                snapbuild.snap, cls._uploadApp, snapbuild, upload_data)

    @classmethod
    def refreshDischargeMacaroon(cls, snap):
        """See `ISnapStoreClient`."""
        assert config.launchpad.openid_provider_root is not None
        assert snap.store_secrets is not None
        refresh_url = urlappend(
            config.launchpad.openid_provider_root, "api/v2/tokens/refresh")
        data = {"discharge_macaroon": snap.store_secrets["discharge"]}
        try:
            response = urlfetch(refresh_url, method="POST", json=data)
            response_data = response.json()
            if "discharge_macaroon" not in response_data:
                raise BadRefreshResponse(response.text)
            # Set a new dict here to avoid problems with security proxies.
            new_secrets = dict(snap.store_secrets)
            new_secrets["discharge"] = response_data["discharge_macaroon"]
            snap.store_secrets = new_secrets
        except requests.HTTPError as e:
            raise cls._makeSnapStoreError(BadRefreshResponse, e)

    @classmethod
    def refreshIfNecessary(cls, snap, f, *args, **kwargs):
        """See `ISnapStoreClient`."""
        try:
            return f(*args, **kwargs)
        except NeedsRefreshResponse:
            cls.refreshDischargeMacaroon(snap)
            return f(*args, **kwargs)

    @classmethod
    def checkStatus(cls, status_url):
        """See `ISnapStoreClient`."""
        try:
            response = urlfetch(status_url)
            response_data = response.json()
            if not response_data["processed"]:
                raise UploadNotScannedYetResponse()
            elif "errors" in response_data:
                error_message = "\n".join(
                    error["message"] for error in response_data["errors"])
                error_messages = []
                for error in response_data["errors"]:
                    error_detail = {"message": error["message"]}
                    if "link" in error:
                        error_detail["link"] = error["link"]
                    error_messages.append(error_detail)
                raise ScanFailedResponse(
                    error_message, messages=error_messages)
            elif not response_data["can_release"]:
                return response_data["url"], None
            else:
                return response_data["url"], response_data["revision"]
        except requests.HTTPError as e:
            raise cls._makeSnapStoreError(BadScanStatusResponse, e)

    @classmethod
    def listChannels(cls):
        """See `ISnapStoreClient`."""
        if config.snappy.store_search_url is None:
            return _default_store_channels
        channels = None
        memcache_client = getUtility(IMemcacheClient)
        search_host = urlsplit(config.snappy.store_search_url).hostname
        memcache_key = ("%s:channels" % search_host).encode("UTF-8")
        cached_channels = memcache_client.get(memcache_key)
        if cached_channels is not None:
            try:
                channels = json.loads(cached_channels)
            except JSONDecodeError:
                log.exception(
                    "Cannot load cached channels for %s; deleting" %
                    search_host)
                memcache_client.delete(memcache_key)
        if (channels is None and
                not getFeatureFlag(u"snap.disable_channel_search")):
            path = "api/v1/channels"
            timeline = cls._getTimeline()
            if timeline is not None:
                action = timeline.start("store-search-get", "/" + path)
            channels_url = urlappend(config.snappy.store_search_url, path)
            try:
                response = urlfetch(
                    channels_url, headers={"Accept": "application/hal+json"})
            except requests.HTTPError as e:
                raise cls._makeSnapStoreError(BadSearchResponse, e)
            finally:
                if timeline is not None:
                    action.finish()
            channels = response.json().get("_embedded", {}).get(
                "clickindex:channel", [])
            expire_time = time.time() + 60 * 60 * 24
            memcache_client.set(
                memcache_key, json.dumps(channels), expire_time)
        if channels is None:
            channels = _default_store_channels
        return channels

    @classmethod
    def _release(cls, snap, revision):
        """Release a snap revision to specified channels."""
        release_url = urlappend(
            config.snappy.store_url, "dev/api/snap-release/")
        data = {
            "name": snap.store_name,
            "revision": revision,
            # The security proxy is useless and breaks JSON serialisation.
            "channels": removeSecurityProxy(snap.store_channels),
            "series": snap.store_series.name,
            }
        # XXX cjwatson 2016-06-28: This should add timeline information, but
        # that's currently difficult in jobs.
        try:
            assert snap.store_secrets is not None
            urlfetch(
                release_url, method="POST", json=data,
                auth=MacaroonAuth(
                    snap.store_secrets["root"],
                    snap.store_secrets.get("discharge")))
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                if (e.response.headers.get("WWW-Authenticate") ==
                        "Macaroon needs_refresh=1"):
                    raise NeedsRefreshResponse()
            raise cls._makeSnapStoreError(ReleaseFailedResponse, e)

    @classmethod
    def release(cls, snapbuild, revision):
        """See `ISnapStoreClient`."""
        assert config.snappy.store_url is not None
        snap = snapbuild.snap
        assert snap.store_name is not None
        assert snap.store_series is not None
        assert snap.store_channels
        cls.refreshIfNecessary(snap, cls._release, snap, revision)
