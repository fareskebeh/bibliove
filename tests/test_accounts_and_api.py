import io
import unittest
from datetime import datetime, timedelta
from hashlib import sha256
from unittest.mock import patch, MagicMock

import pymupdf

from tests import support
from tests.support import app, db, reset_database, make_user, login, csrf_token


def key_for(user_id, raw, name="unit"):
    from keymanager.models import ApiKey
    with app.app_context():
        key = ApiKey(key_hash=sha256(raw.encode()).hexdigest(), name=name, user_id=user_id)
        db.session.add(key)
        db.session.commit()
        return key.id


def small_pdf():
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "unit test")
    return doc.tobytes()


class ExtractGate(unittest.TestCase):
    def setUp(self):
        reset_database()

    def test_exhausted_free_is_refused_before_queueing(self):
        from keymanager.models import ApiUsage
        user_id = make_user(master_quota=50)
        key_for(user_id, "raw-free")
        fake_queue = MagicMock()
        with patch("core.controllers.ocr_queue", fake_queue):
            r = app.test_client().post("/extract", data={"pdf": (io.BytesIO(small_pdf()), "a.pdf")},
                                       headers={"Authorization": "Bearer raw-free"}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 429)
        self.assertFalse(fake_queue.enqueue.called)
        with app.app_context():
            self.assertEqual(ApiUsage.query.count(), 0)

    def test_free_with_allowance_is_queued(self):
        user_id = make_user(master_quota=10)
        key_for(user_id, "raw-ok")
        fake_queue = MagicMock(); fake_queue.enqueue.return_value = MagicMock(id="job")
        with patch("core.controllers.ocr_queue", fake_queue):
            r = app.test_client().post("/extract", data={"pdf": (io.BytesIO(small_pdf()), "a.pdf")},
                                       headers={"Authorization": "Bearer raw-ok"}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(fake_queue.enqueue.called)

    def test_oversized_upload_is_rejected(self):
        app.config["MAX_CONTENT_LENGTH"] = 1024
        try:
            r = app.test_client().post("/extract", data={"pdf": (io.BytesIO(b"x" * 4096), "big.pdf")},
                                       headers={"Authorization": "Bearer nope"}, content_type="multipart/form-data")
            self.assertEqual(r.status_code, 413)
        finally:
            app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


class KeyLimits(unittest.TestCase):
    def setUp(self):
        reset_database()

    def _create(self, plan_id, existing):
        user_id = make_user(email=f"k{plan_id}{existing}@test.dev", plan_id=plan_id)
        for i in range(existing):
            key_for(user_id, f"{plan_id}-{existing}-{i}", name=f"k{i}")
        client = app.test_client()
        login(client, f"k{plan_id}{existing}@test.dev")
        token = csrf_token(client)
        return client.post("/keys/create", data={"csrf_token": token}).status_code

    def test_free_one_key_then_refused(self):
        self.assertEqual(self._create(1, 1), 402)

    def test_starter_allows_third_key(self):
        self.assertEqual(self._create(2, 2), 200)

    def test_starter_refused_at_limit(self):
        self.assertEqual(self._create(2, 3), 402)


class AccountDeletion(unittest.TestCase):
    PW = "Correct-horse-1"

    def setUp(self):
        reset_database()

    def _delete(self, password, confirmation, with_csrf=True):
        user_id = make_user(email="gone@test.dev", password=self.PW)
        key_for(user_id, "raw-gone")
        client = app.test_client()
        login(client, "gone@test.dev")
        data = {"password": password, "confirmation": confirmation}
        if with_csrf:
            data["csrf_token"] = csrf_token(client, "/settings")
        with patch("payments.billing.stripe.StripeClient"):
            client.post("/account/delete", data=data)
        from auth.models import User
        with app.app_context():
            return User.query.filter_by(email="gone@test.dev").count()

    def test_wrong_password_keeps_account(self):
        self.assertEqual(self._delete("nope", "delete my account"), 1)

    def test_wrong_confirmation_keeps_account(self):
        self.assertEqual(self._delete(self.PW, "delete"), 1)

    def test_missing_csrf_keeps_account(self):
        self.assertEqual(self._delete(self.PW, "delete my account", with_csrf=False), 1)

    def test_deletion_then_cooldown_blocks_registration(self):
        self.assertEqual(self._delete(self.PW, "delete my account"), 0)
        from auth.models import User
        client = app.test_client()
        token = csrf_token(client, "/register")
        with patch("auth.controllers.resend.Emails.send", return_value={}):
            r = client.post("/register", data={"email": "gone@test.dev", "password": "x", "csrf_token": token})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.headers["Location"], "/register")
        with app.app_context():
            self.assertEqual(User.query.filter_by(email="gone@test.dev").count(), 0)

    def test_cooldown_expires(self):
        self._delete(self.PW, "delete my account")
        from auth.models import DeletedAccount
        from auth.accounts import email_fingerprint
        with app.app_context():
            record = db.session.get(DeletedAccount, email_fingerprint("gone@test.dev"))
            record.deleted_at = datetime.now() - timedelta(days=31)
            db.session.commit()
        client = app.test_client()
        token = csrf_token(client, "/register")
        with patch("auth.controllers.resend.Emails.send", return_value={}):
            r = client.post("/register", data={"email": "gone@test.dev", "password": "x", "csrf_token": token})
        self.assertEqual(r.headers["Location"], "/verify")


class Security(unittest.TestCase):
    def setUp(self):
        reset_database()

    def test_count_route_is_gone(self):
        self.assertEqual(app.test_client().get("/count/1").status_code, 404)

    def test_login_post_without_token_is_rejected(self):
        r = app.test_client().post("/login", data={"email": "x@y.z", "password": "bad"})
        self.assertEqual(r.status_code, 302)

    def test_keys_create_requires_post_and_token(self):
        user_id = make_user(email="sec@test.dev")
        client = app.test_client()
        login(client, "sec@test.dev")
        self.assertEqual(client.get("/keys/create").status_code, 405)
        self.assertEqual(client.post("/keys/create").status_code, 400)

    def test_webhook_rejects_bad_signature(self):
        r = app.test_client().post("/webhook", data=b"{}", headers={"Stripe-Signature": "t=1,v1=bad"})
        self.assertEqual(r.status_code, 400)

    def test_rate_limit_response_is_json_for_api_and_html_for_pages(self):
        from app import ratelimit_handler
        with app.test_request_context("/status/abc"):
            response, status = ratelimit_handler(Exception())
        self.assertEqual(status, 429)
        self.assertTrue(response.is_json)
        with app.test_request_context("/login"):
            response, status = ratelimit_handler(Exception())
        self.assertEqual(status, 429)
        self.assertFalse(getattr(response, 'is_json', False))
        self.assertTrue(isinstance(response, str))


class Pricing(unittest.TestCase):
    def setUp(self):
        reset_database()

    def test_anonymous_sees_get_started(self):
        html = app.test_client().get("/pricing").get_data(as_text=True)
        self.assertTrue("/register?plan=starter" in html)


if __name__ == "__main__":
    unittest.main()
