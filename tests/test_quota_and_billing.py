import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from tests import support
from tests.support import app, db, reset_database
from auth.quota import last_reset_point, apply_quota_reset
from payments.billing import billable_pages


class QuotaMath(unittest.TestCase):
    def test_free_resets_on_creation_day(self):
        created = datetime(2026, 8, 21, 22, 52)
        self.assertEqual(last_reset_point(created, datetime(2026, 11, 10, 9, 0)), datetime(2026, 10, 21, 22, 52))
        self.assertEqual(last_reset_point(created, datetime(2026, 1, 15)), datetime(2025, 12, 21, 22, 52))

    def test_month_end_clamp(self):
        created = datetime(2026, 1, 31, 8, 0)
        self.assertEqual(last_reset_point(created, datetime(2026, 3, 1, 9, 0)), datetime(2026, 2, 28, 8, 0))

    def test_reset_happens_once_per_period(self):
        user = SimpleNamespace(date_created=datetime(2026, 8, 21), quota_reset_at=datetime(2026, 9, 21), master_quota=30)
        self.assertTrue(apply_quota_reset(user, True, datetime(2026, 11, 10)))
        self.assertEqual(user.master_quota, 0)
        self.assertFalse(apply_quota_reset(user, True, datetime(2026, 11, 10)))

    def test_paid_counter_does_not_use_creation_day(self):
        user = SimpleNamespace(date_created=datetime(2026, 8, 21), quota_reset_at=datetime(2026, 11, 1), master_quota=40)
        self.assertFalse(apply_quota_reset(user, False, datetime(2026, 11, 10)))
        self.assertEqual(user.master_quota, 40)

    def test_billable_pages(self):
        self.assertEqual(billable_pages(500, 480, 510), 10)
        self.assertEqual(billable_pages(500, 600, 630), 30)
        self.assertEqual(billable_pages(500, 100, 130), 0)


class OverageLedger(unittest.TestCase):
    def setUp(self):
        reset_database()
        self.user_id = support.make_user(plan_id=2, master_quota=490)
        from core import tasks
        self.tasks = tasks
        self.session = tasks.Session()

    def tearDown(self):
        self.session.close()

    def _plan(self):
        from payments.models import Plan
        return self.session.get(Plan, 2)

    def _user(self):
        from auth.models import User
        user = self.session.get(User, self.user_id)
        user.stripe_customer_id = "cus_unit"
        self.session.commit()
        return user

    def test_failure_then_success_sends_once(self):
        import stripe
        from payments.models import OverageReport
        user = self._user()
        with patch.object(self.tasks, "report_overage", side_effect=stripe.StripeError("timeout")):
            self.tasks.report_pending_overage(self.session, user, self._plan(), 490, 30)
        row = self.session.query(OverageReport).one()
        self.assertIsNone(row.sent_at)
        sent_ids = []
        with patch.object(self.tasks, "report_overage", side_effect=lambda *a: sent_ids.append(a[3])):
            self.tasks.report_pending_overage(self.session, user, self._plan(), 520, 0)
        self.assertIn(row.id, sent_ids)
        self.assertIsNotNone(self.session.get(OverageReport, row.id).sent_at)

    def test_already_exists_counts_as_sent(self):
        import stripe
        from payments.models import OverageReport
        user = self._user()
        error = stripe.InvalidRequestError("An event already exists with identifier x", None)
        with patch.object(self.tasks, "report_overage", side_effect=error):
            self.tasks.report_pending_overage(self.session, user, self._plan(), 490, 30)
        self.assertIsNotNone(self.session.query(OverageReport).one().sent_at)

    def test_old_unsent_reports_expire(self):
        from datetime import timedelta
        from payments.models import OverageReport
        import stripe
        user = self._user()
        self.session.add(OverageReport(id="old-report", user_id=self.user_id, pages=5,
                                       created_at=datetime.now() - timedelta(days=31), attempts=0))
        self.session.commit()
        with patch.object(self.tasks, "report_overage", side_effect=stripe.StripeError("down")):
            self.tasks.report_pending_overage(self.session, user, self._plan(), 0, 0)
        self.assertTrue(self.session.get(OverageReport, "old-report").expired)


class DashboardOverage(unittest.TestCase):
    def setUp(self):
        reset_database()

    def test_counter_shows_pages_over_allowance(self):
        user_id = support.make_user(email="paid@test.dev", plan_id=2, master_quota=520)
        from auth.models import User
        with app.app_context():
            User.query.get(user_id).quota_reset_at = datetime.now()
            db.session.commit()
        client = app.test_client()
        support.login(client, "paid@test.dev")
        html = client.get("/dashboard").get_data(as_text=True)
        self.assertTrue("20 <span" in html, "overage page count missing")
        self.assertTrue("$0.100" in html, "overage amount missing")


if __name__ == "__main__":
    unittest.main()
