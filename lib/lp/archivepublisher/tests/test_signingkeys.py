# Copyright 2010-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import mock

from lp.archivepublisher.enums import SigningKeyType
from lp.archivepublisher.model.signingkeys import SigningKey
from lp.services.database.interfaces import IMasterStore
from lp.services.signing.tests.test_proxy import SigningServiceResponseFactory
from lp.testing import TestCaseWithFactory
from lp.testing.layers import DatabaseFunctionalLayer


class TestSigningServiceSigningKey(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self, *args, **kwargs):
        super(TestSigningServiceSigningKey, self).setUp(*args, **kwargs)
        self.signing_service = SigningServiceResponseFactory()

    def test_save_signing_key(self):
        archive = self.factory.makeArchive()
        s = SigningKey(
            SigningKeyType.UEFI, archive, u"a fingerprint", u"a public_key",
            description=u"This is my key!")
        store = IMasterStore(SigningKey)
        store.add(s)
        store.commit()

        resultset = store.find(SigningKey)
        self.assertEqual(1, resultset.count())
        db_key = resultset.one()
        self.assertEqual(SigningKeyType.UEFI, db_key.key_type)
        self.assertEqual(archive, db_key.archive)
        self.assertEqual("a fingerprint", db_key.fingerprint)
        self.assertEqual("a public_key", db_key.public_key)
        self.assertEqual("This is my key!", db_key.description)

    @mock.patch("lp.services.signing.proxy.requests")
    def test_generate_signing_key_saves_correctly(self, mock_requests):
        self.signing_service.patch(mock_requests)

        archive = self.factory.makeArchive()
        distro_series = archive.distribution.series[0]

        key = SigningKey.generate(
            SigningKeyType.UEFI, archive, distro_series, u"this is my key")
        self.assertIsInstance(key, SigningKey)

        store = IMasterStore(SigningKey)
        store.invalidate()

        rs = store.find(SigningKey)
        self.assertEqual(1, rs.count())
        db_key = rs.one()

        self.assertEqual(SigningKeyType.UEFI, db_key.key_type)
        self.assertEqual(
            self.signing_service.generated_fingerprint, db_key.fingerprint)
        self.assertEqual(
            self.signing_service.generated_public_key, db_key.public_key)
        self.assertEqual(archive, db_key.archive)
        self.assertEqual(distro_series, db_key.distro_series)
        self.assertEqual("this is my key", db_key.description)

    @mock.patch("lp.services.signing.proxy.requests")
    def test_sign_some_data(self, mock_requests):
        self.signing_service.patch(mock_requests)

        archive = self.factory.makeArchive()

        s = SigningKey(
            SigningKeyType.UEFI, archive, u"a fingerprint", u"a public_key",
            description=u"This is my key!")
        signed = s.sign("ATTACHED", "secure message", "message_name")

        # Checks if the returned value is actually the returning value from
        # HTTP POST /sign call to lp-signing service
        api_resp = self.signing_service.get_latest_json_response(
            "POST", "/sign")
        self.assertIsNotNone(api_resp, "The API was never called")
        self.assertEqual(api_resp['signed-message'], signed)
