import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bson import ObjectId

import services.orders_service as orders_service
import services.payment_service as payment_service
import services.user_service as user_service


class UC6UC8OrdersServiceBoundaryTests(unittest.TestCase):
    # when rider has fewer active bounties than the limit, accept should proceed.
    def test_uc6_accept_bounty_allows_when_below_limit(self):
        # fake collection: active count below threshold + successful update.
        collection = Mock();
        collection.count_documents.return_value = 0;
        # mock find_one_and_update to return a valid accepted bounty document
        collection.find_one_and_update.return_value = {
            "_id": "507f1f77bcf86cd799439011",
            "status": "accepted",
            "items": [],
            "total": 6.5,
        }
        # essentially, we're hardcoding database responses to simulate a rider with 0 active bounties, 
        # and a successful bounty acceptance.

        with patch("services.orders_service._get_collection", return_value=collection), patch(
            "services.orders_service.get_user_by_uid", return_value={"uid": 9, "username": "zutomayo_rider9", "student_id": "1000009"}
        ), patch("services.orders_service.MAX_ACTIVE_BOUNTIES", 1):
            out = orders_service.accept_bounty("507f1f77bcf86cd799439011", 9)

        self.assertIsNotNone(out); self.assertEqual(out["status"], "accepted")

    # once rider reaches max active bounties, accept should be blocked.
    def test_uc6_accept_bounty_rejects_when_at_limit(self):
        collection = Mock();
        collection.count_documents.return_value = 1;

        with patch("services.orders_service._get_collection", return_value=collection), patch(
            "services.orders_service.get_user_by_uid", return_value={"uid": 9, "username": "zutomayo_rider9", "student_id": "1000009"}
        ), patch("services.orders_service.MAX_ACTIVE_BOUNTIES", 1):
            out = orders_service.accept_bounty("507f1f77bcf86cd799439011", 9)

        self.assertIsNone(out); collection.find_one_and_update.assert_not_called()

    # malformed count values should degrade safely (fallback path) instead of crashing.
    def test_uc6_accept_bounty_non_int_active_count_falls_back_to_zero(self):
        collection = Mock();
        collection.count_documents.return_value = "1";
        collection.find_one_and_update.return_value = {
            "_id": "507f1f77bcf86cd799439011",
            "status": "accepted",
            "items": [],
            "total": 6.5,
        }

        with patch("services.orders_service._get_collection", return_value=collection), patch(
            "services.orders_service.get_user_by_uid", return_value={"uid": 9, "username": "zutomayo_rider9", "student_id": "1000009"}
        ), patch("services.orders_service.MAX_ACTIVE_BOUNTIES", 1):
            out = orders_service.accept_bounty("507f1f77bcf86cd799439011", 9)

        self.assertIsNotNone(out); self.assertEqual(out["status"], "accepted")

    # guard case: missing rider id should fail fast.
    def test_uc8_mark_completed_guard_missing_zutomayo_rider(self):
        with patch("services.orders_service._get_collection", return_value=Mock()): self.assertIsNone(orders_service.mark_order_completed("507f1f77bcf86cd799439011", None))

    # only delivered orders can be marked completed.
    def test_uc8_mark_completed_requires_delivered_state(self):
        collection = Mock();
        collection.find_one_and_update.return_value = None;

        with patch("services.orders_service._get_collection", return_value=collection):
            out = orders_service.mark_order_completed("507f1f77bcf86cd799439011", 88)

        self.assertIsNone(out)

    # first rollback from picked_up should be allowed.
    def test_uc8_retract_picked_up_first_time_success(self):
        collection = Mock();
        collection.find_one_and_update.return_value = {
            "_id": "507f1f77bcf86cd799439011",
            "status": "accepted",
            "items": [],
            "total": 5.0,
        }

        with patch("services.orders_service._get_collection", return_value=collection):
            out = orders_service.retract_order_picked_up("507f1f77bcf86cd799439011", 77)

        self.assertIsNotNone(out); self.assertEqual(out["status"], "accepted")

    # rollback should not be repeatable forever.
    def test_uc8_retract_picked_up_second_time_blocked(self):
        collection = Mock();
        collection.find_one_and_update.return_value = None;

        with patch("services.orders_service._get_collection", return_value=collection):
            out = orders_service.retract_order_picked_up("507f1f77bcf86cd799439011", 77)

        self.assertIsNone(out)

    # close must wait until enough time has passed after completion.
    def test_uc8_close_bounty_not_old_enough(self):
        oid = ObjectId("507f1f77bcf86cd799439011");
        collection = Mock();
        collection.find_one.return_value = {
            "_id": oid,
            "status": "completed",
            "user_id": 1,
            "assigned_rider_id": 77,
            "items": [],
            "total": 9.0,
            "completed_at": datetime.now(UTC) - timedelta(minutes=1),
        }

        with patch("services.orders_service._get_collection", return_value=collection), patch(
            "services.orders_service.record_delivery_payment"
        ) as payout_mock:
            out = orders_service.close_bounty(str(oid))

        self.assertIsNone(out); payout_mock.assert_not_called()

    # timezone-naive timestamps from BSON should still be normalized and handled.
    def test_uc8_close_bounty_handles_naive_datetime(self):
        oid = ObjectId("507f1f77bcf86cd799439011");
        # intentionally pass naive datetime to test normalization path
        naive_completed_at = (datetime.now(UTC) - timedelta(minutes=5)).replace(tzinfo=None)
        collection = Mock();
        collection.find_one.return_value = {
            "_id": oid,
            "status": "completed",
            "user_id": 1,
            "assigned_rider_id": 77,
            "items": [],
            "total": 9.0,
            "completed_at": naive_completed_at,
        }
        collection.find_one_and_update.return_value = {
            "_id": oid,
            "status": "closed",
            "user_id": 1,
            "items": [],
            "total": 9.0,
            "delivery_payment": {"payment_id": "pay-1", "status": "paid_out"},
        }

        with patch("services.orders_service._get_collection", return_value=collection), patch(
            "services.orders_service.get_user_by_uid", return_value={"uid": 77, "username": "zutomayo_r77", "student_id": "1000077"}
        ), patch(
            "services.orders_service.record_delivery_payment",
            return_value={"payment_id": "pay-1", "status": "paid_out"},
        ):
            out = orders_service.close_bounty(str(oid))

        self.assertIsNotNone(out); self.assertEqual(out["status"], "closed")

    # invalid receiving method should record pending balance instead of paid payout.
    def test_uc8_close_bounty_invalid_receiving_method_sets_pending(self):
        oid = ObjectId("507f1f77bcf86cd799439011");
        collection = Mock();
        collection.find_one.return_value = {
            "_id": oid,
            "status": "completed",
            "user_id": 1,
            "assigned_rider_id": 77,
            "items": [],
            "total": 9.0,
            "completed_at": datetime.now(UTC) - timedelta(minutes=5),
        }
        collection.find_one_and_update.return_value = {
            "_id": oid,
            "status": "closed",
            "user_id": 1,
            "items": [],
            "total": 9.0,
            "delivery_payment": {"payment_id": "pay-2", "status": "pending_balance"},
        }

        with patch("services.orders_service._get_collection", return_value=collection), patch(
            "services.orders_service.get_user_by_uid",
            return_value={"uid": 77, "username": "zutomayo_r77", "student_id": "1000077", "receiving_method_valid": False},
        ), patch("services.orders_service.record_delivery_payment") as payout_mock:
            payout_mock.return_value = {"payment_id": "pay-2", "status": "pending_balance", "reason": "invalid_receiving_method"}
            out = orders_service.close_bounty(str(oid))

        self.assertIsNotNone(out)
        self.assertEqual(out["delivery_payment"]["status"], "pending_balance")
        self.assertEqual(payout_mock.call_args.kwargs["receiving_method_valid"], False)


class UC8PaymentServiceBoundaryTests(unittest.TestCase):
    # guard case: no collection means no payout record can be created.
    def test_record_delivery_payment_guard_missing_collection(self):
        with patch("services.payment_service._get_collection", return_value=None): self.assertIsNone(payment_service.record_delivery_payment(7, 2.5, "oid-1"))

    # guard case: missing rider id should fail safely.
    def test_record_delivery_payment_guard_missing_zutomayo_rider(self):
        with patch("services.payment_service._get_collection", return_value=Mock()): self.assertIsNone(payment_service.record_delivery_payment(None, 2.5, "oid-1"))

    # invalid amount payload should be rejected.
    def test_record_delivery_payment_invalid_amount_returns_none(self):
        collection = Mock();

        with patch("services.payment_service._get_collection", return_value=collection), patch(
            "services.payment_service.get_user_by_uid", return_value={"uid": 7, "username": "zutomayo_u7", "student_id": "1000007"}
        ):
            self.assertIsNone(payment_service.record_delivery_payment(7, "bad-amount", "oid-1"))

    # happy path: valid receiving method should mark payout as paid_out.
    def test_record_delivery_payment_paid_out_success(self):
        collection = Mock();
        collection.insert_one.return_value = SimpleNamespace(inserted_id="mongo-id")

        with patch("services.payment_service._get_collection", return_value=collection), patch(
            "services.payment_service.get_user_by_uid", return_value={"uid": 7, "username": "zutomayo_u7", "student_id": "1000007"}
        ):
            out = payment_service.record_delivery_payment(7, 12.34, "oid-1", receiving_method_valid=True)

        self.assertIsNotNone(out); self.assertEqual(out["status"], "paid_out")

    # invalid receiving method should route funds to pending balance.
    def test_record_delivery_payment_pending_balance_success(self):
        collection = Mock();
        collection.insert_one.return_value = SimpleNamespace(inserted_id="mongo-id")

        with patch("services.payment_service._get_collection", return_value=collection), patch(
            "services.payment_service.get_user_by_uid", return_value={"uid": 7, "username": "zutomayo_u7", "student_id": "1000007"}
        ):
            out = payment_service.record_delivery_payment(7, 12.34, "oid-1", receiving_method_valid=False)

        self.assertIsNotNone(out); self.assertEqual(out["status"], "pending_balance")
        self.assertEqual(out["reason"], "invalid_receiving_method")


class UserServiceOutageBehaviorTests(unittest.TestCase):
    # has_registered_account intentionally fails open when DB is offline
    def test_has_registered_account_fail_open_on_no_collection(self):
        with patch("services.user_service._get_collection", return_value=None):
            self.assertTrue(user_service.has_registered_account(42))

    # create_user_account fails closed when DB is offline
    def test_create_user_account_fails_closed_on_no_collection(self):
        with patch("services.user_service._get_collection", return_value=None):
            self.assertIsNone(user_service.create_user_account(42, "acane", "1001234"))

    # invalid input should still fail even when DB exists
    def test_create_user_account_rejects_invalid_student_id(self):
        with patch("services.user_service._get_collection", return_value=Mock()):
            self.assertIsNone(user_service.create_user_account(42, "acane", "abc"))


if __name__ == "__main__":
    unittest.main()
