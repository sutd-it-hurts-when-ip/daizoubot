import os
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pymongo import MongoClient

import handlers.menu as menu_handlers
from handlers.router import router
import services.menu_service as menu_service
import services.orders_service as orders_service
import services.payment_service as payment_service
import services.user_service as user_service


class UseCaseIntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    # setup class (run once before all tests)
    # set MongoDB connection & change config to use test db to avoid polluting production data
    def setUpClass(cls):
        cls.mongo_uri = os.getenv("MONGO_URI")
        if not cls.mongo_uri:
            raise unittest.SkipTest("MONGO_URI is not set")

        # check that mongo reachable
        cls.client = MongoClient(cls.mongo_uri, serverSelectionTimeoutMS=1000)
        try:
            cls.client.admin.command("ping")
        except Exception as exc:
            raise unittest.SkipTest(f"MongoDB is not reachable: {exc}") # skip since doesn't mean test failed

        # use MONGO_TEST_DB_NAME environment var if set (it's not), else default to daizoubu_integration_test
        cls.test_db_name = os.getenv("MONGO_TEST_DB_NAME", "daizoubu_integration_test")

        # setUpClass saves original module-level config values to restore later in tearDownClass
        # setUpClass child of unittest.IsolatedAsyncioTestCase, which stores class-level attributes in cls, 
        # so we can access them in tearDownClass
        cls._menu_original_db = menu_service.MONGO_DB_NAME
        cls._orders_original_db = orders_service.MONGO_DB_NAME
        cls._users_original_db = user_service.MONGO_DB_NAME
        cls._payments_original_db = payment_service.MONGO_DB_NAME
        cls._menu_original_client = menu_service._client
        cls._orders_original_client = orders_service._client
        cls._users_original_client = user_service._client
        cls._payments_original_client = payment_service._client

        menu_service.MONGO_DB_NAME = cls.test_db_name
        orders_service.MONGO_DB_NAME = cls.test_db_name
        user_service.MONGO_DB_NAME = cls.test_db_name
        payment_service.MONGO_DB_NAME = cls.test_db_name
        menu_service._client = cls.client
        orders_service._client = cls.client
        user_service._client = cls.client
        payment_service._client = cls.client

    @classmethod
    def tearDownClass(cls):
        # cleanup
        db = cls.client[cls.test_db_name]
        db["vendors"].delete_many({})
        db["orders"].delete_many({})
        db["users"].delete_many({})
        db["payments"].delete_many({})

        # reaset config to original values, close.
        menu_service.MONGO_DB_NAME = cls._menu_original_db
        orders_service.MONGO_DB_NAME = cls._orders_original_db
        user_service.MONGO_DB_NAME = cls._users_original_db
        payment_service.MONGO_DB_NAME = cls._payments_original_db
        menu_service._client = cls._menu_original_client
        orders_service._client = cls._orders_original_client
        user_service._client = cls._users_original_client
        payment_service._client = cls._payments_original_client
        cls.client.close()

    def setUp(self):
        # reset test db before each test to ensure isolation
        db = self.client[self.test_db_name]
        db["vendors"].delete_many({})
        db["orders"].delete_many({})
        db["users"].delete_many({})
        db["payments"].delete_many({})

    # helper to insert user into test db for integration tests
    def _insert_user(self, uid, username, student_id):
        self.client[self.test_db_name]["users"].insert_one(
            {
                "uid": uid,
                "username": username,
                "student_id": student_id,
            }
        )

    # UC1 Register - success and account-gating flow.
    async def test_uc1_register_success(self):
        reply_text = AsyncMock()
        # create fake user
        user = SimpleNamespace(id=9001, first_name="Acane", username="acane")

        # fake incoming tele message
        register_update = SimpleNamespace(
            message=SimpleNamespace(text="Register acane 1001234", reply_text=reply_text),
            effective_user=user,
        )
        # router called with fake update and empty context (context not required)
        await router(register_update, SimpleNamespace())

        # assert that profile was indeed created in test db
        created = self.client[self.test_db_name]["users"].find_one({"uid": 9001}, {"_id": 0})
        self.assertIsNotNone(created)
        self.assertEqual(created["username"], "acane")
        self.assertEqual(created["student_id"], "1001234")

        # and assert that reply_text was called with success message
        with patch("handlers.router.browse_menu", new=AsyncMock()) as mocked_browse:
            browse_update = SimpleNamespace(
                message=SimpleNamespace(text="Browse Menu", reply_text=AsyncMock()),
                effective_user=user,
            )
            await router(browse_update, SimpleNamespace()) # call router w/ fake update (Browse Menu) and empty context
            mocked_browse.assert_awaited_once() # called 0 times if user not registered, this would fail.

    # UC1 alternative flow - invalid SUTD ID rejected.
    async def test_uc1_register_invalid_sutd_id(self):
        reply_text = AsyncMock()
        user = SimpleNamespace(id=9002, first_name="Nira", username="nira")
        update = SimpleNamespace(
            message=SimpleNamespace(text="Register nira abc", reply_text=reply_text),
            effective_user=user,
        )

        await router(update, SimpleNamespace())

        reply_text.assert_awaited_once()
        self.assertIn("Invalid registration format or SUTD ID", reply_text.await_args.args[0])
        created = self.client[self.test_db_name]["users"].find_one({"uid": 9002})
        self.assertIsNone(created)

    # UC2 Create Bounty - success path.
    def test_uc2_create_bounty_success(self):
        # helper defined above
        self._insert_user(321, "test_orderer321", "1000321")

        cart = [
            {"food": {"id": 101, "name": "Chicken Chop", "price": 6.5}, "quantity": 2},
            {"food": {"id": 202, "name": "Dumpling Ban Mian", "price": 5.5}, "quantity": 1},
        ]

        inserted_id = orders_service.create_order(321, cart)
        self.assertIsNotNone(inserted_id)

        # check that order is indeed in db
        order = self.client[self.test_db_name]["orders"].find_one({"_id": inserted_id})
        self.assertIsNotNone(order)
        self.assertEqual(order["status"], "placed")
        self.assertEqual(order["total"], 18.5)

    # UC2 Create Bounty - unavailable menu item alternative flow.
    async def test_uc2_create_bounty_unavailable_item(self):
        query = SimpleNamespace(data="food:999", answer=AsyncMock(), edit_message_text=AsyncMock())
        update = SimpleNamespace(callback_query=query) # fake update with callback_query containing data "food:999" (unavailable item)

        with patch("handlers.menu.get_food", return_value=None): # set get_food to return None, simulating unavailable item
            await menu_handlers.food_selected(update, SimpleNamespace()) # call food_selected with fake update and empty context

        query.edit_message_text.assert_awaited_once_with("Food not found")

    # UC3 Make Payment - successful fake payment verification and transaction record.
    def test_uc3_make_payment_success(self):
        self._insert_user(444, "test_payer444", "1000444")

        # ensure creation and mark as paid working
        payment = payment_service.create_payment_request(444, 12.34)
        self.assertIsNotNone(payment)
        self.assertEqual(payment["status"], "pending")
        self.assertIn("qr_payload", payment)

        paid = payment_service.mark_payment_paid(payment["payment_id"])
        self.assertIsNotNone(paid)
        self.assertEqual(paid["status"], "paid")
        self.assertTrue(payment_service.is_payment_verified(payment["payment_id"]))

    # UC3 alternative flow - payment gateway unavailable.
    def test_uc3_make_payment_gateway_unavailable(self):
        self._insert_user(445, "test_payer445", "1000445")

        # patch db retrieval to simulate payment gateway down (returns None)
        with patch("services.payment_service._get_collection", return_value=None):
            payment = payment_service.create_payment_request(445, 10.0)

        self.assertIsNone(payment)

    # UC3 alternative flow - payment QR expires / negative verification.
    def test_uc3_make_payment_qr_expires(self):
        self._insert_user(446, "test_payer446", "1000446")

        payment = payment_service.create_payment_request(446, 8.0)
        self.assertIsNotNone(payment)
        expired = payment_service.mark_payment_expired(payment["payment_id"])
        self.assertIsNotNone(expired)
        self.assertEqual(expired["status"], "expired")
        self.assertFalse(payment_service.is_payment_verified(payment["payment_id"]))

    # UC4 Track Bounty - test_orderer can see status progression in their order history.
    def test_uc4_track_bounty_status_progression(self):
        self._insert_user(2020, "test_orderer2020", "1002020")
        self._insert_user(7001, "test_rider7001", "1007001")

        cart = [{"food": {"id": 101, "name": "Chicken Chop", "price": 6.5}, "quantity": 1}]
        inserted_id = orders_service.create_order(2020, cart)
        self.assertIsNotNone(inserted_id)

        accepted = orders_service.accept_bounty(str(inserted_id), 7001)
        self.assertIsNotNone(accepted)
        picked_up = orders_service.mark_order_picked_up(str(inserted_id), 7001)
        self.assertIsNotNone(picked_up)

        rows = orders_service.get_orders_by_user(2020, limit=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "picked_up")

        delivered = orders_service.mark_order_delivered(str(inserted_id), 7001)
        self.assertIsNotNone(delivered)

        rows = orders_service.get_orders_by_user(2020, limit=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "delivered")

    # UC4 alternative flow - test_orderer has no active bounties.
    async def test_uc4_track_bounty_no_active(self):
        reply_text = AsyncMock()
        update = SimpleNamespace(message=SimpleNamespace(reply_text=reply_text), effective_user=SimpleNamespace(id=333))

        # force empty and verify correct message sent to user
        with patch("handlers.menu.get_orders_by_user", return_value=[]):
            await menu_handlers.view_orders(update, SimpleNamespace())

        reply_text.assert_awaited_once_with("You have no orders yet.")

    # UC5 View Bounties - open bounties are shown.
    def test_uc5_view_open_bounties(self):
        orders = self.client[self.test_db_name]["orders"]
        orders.insert_many(
            [
                {
                    "user_id": 111,
                    "items": [{"quantity": 1}],
                    "total": 7.0,
                    "status": "placed",
                    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
                },
                {
                    "user_id": 222,
                    "items": [{"quantity": 1}],
                    "total": 9.0,
                    "status": "accepted",
                    "assigned_rider_id": 99,
                    "created_at": datetime(2026, 1, 2, tzinfo=UTC),
                },
            ]
        )

        open_bounties = orders_service.get_open_bounties(limit=10)
        self.assertEqual(len(open_bounties), 1) # check only open bounoty shown (status "placed" only)
        self.assertEqual(open_bounties[0]["total"], 7.0)
        self.assertIn("order_id", open_bounties[0])

    # UC5 alternative flow - no open bounties.
    async def test_uc5_view_open_bounties_none(self):
        reply_text = AsyncMock()
        update = SimpleNamespace(message=SimpleNamespace(reply_text=reply_text), effective_user=SimpleNamespace(id=77))

        with patch("handlers.menu.get_open_bounties", return_value=[]):
            await menu_handlers.view_bounties(update, SimpleNamespace())

        reply_text.assert_awaited_once_with("No available bounties right now.")

    # UC6 Accept Bounty - exclusive assignment and removal from open list.
    def test_uc6_accept_bounty_exclusive_assignment(self):
        self._insert_user(1, "test_orderer1", "1000001")
        self._insert_user(7001, "test_rider7001", "1007001")
        self._insert_user(7002, "test_rider7002", "1007002")

        cart = [{"food": {"id": 501, "name": "Rice", "price": 4.0}, "quantity": 1}]
        inserted_id = orders_service.create_order(1, cart)
        self.assertIsNotNone(inserted_id)

        first = orders_service.accept_bounty(str(inserted_id), 7001)
        self.assertIsNotNone(first)
        self.assertEqual(first["status"], "accepted")

        second = orders_service.accept_bounty(str(inserted_id), 7002)
        self.assertIsNone(second)

        open_bounties = orders_service.get_open_bounties(limit=10)
        self.assertEqual(len(open_bounties), 0)

    def test_uc6_accept_bounty_concurrent_limit(self):
        self._insert_user(100, "test_orderer100", "1000100")
        self._insert_user(8001, "test_rider8001", "1008001")

        cart = [{"food": {"id": 601, "name": "Noodles", "price": 5.0}, "quantity": 1}]
        first_id = orders_service.create_order(100, cart);
        second_id = orders_service.create_order(100, cart);
        self.assertIsNotNone(first_id)
        self.assertIsNotNone(second_id) # create two bounties for same user

        first_accept = orders_service.accept_bounty(str(first_id), 8001)
        self.assertIsNotNone(first_accept); self.assertEqual(first_accept["status"], "accepted")

        second_accept = orders_service.accept_bounty(str(second_id), 8001)
        self.assertIsNone(second_accept)

    # UC7 View Assigned Bounty - deliverer sees accepted/picked_up/delivered bounties.
    def test_uc7_view_assigned_bounty(self):
        test_rider_id = 7001
        orders = self.client[self.test_db_name]["orders"]
        orders.insert_many(
            [
                {
                    "user_id": 1,
                    "items": [{"quantity": 1}],
                    "total": 5.0,
                    "status": "accepted",
                    "assigned_rider_id": test_rider_id,
                    "accepted_at": datetime(2026, 1, 2, tzinfo=UTC),
                },
                {
                    "user_id": 2,
                    "items": [{"quantity": 2}],
                    "total": 8.0,
                    "status": "picked_up",
                    "assigned_rider_id": test_rider_id,
                    "accepted_at": datetime(2026, 1, 3, tzinfo=UTC),
                },
            ]
        )

        rows = orders_service.get_bounties_by_rider(test_rider_id, limit=10)
        self.assertEqual(len(rows), 2)
        statuses = {row["status"] for row in rows}
        self.assertEqual(statuses, {"accepted", "picked_up"})

    # UC7 alternative flow - cancelled bounty is not shown in assigned list.
    def test_uc7_view_assigned_bounty_cancelled_filtered_out(self):
        test_rider_id = 7001
        self.client[self.test_db_name]["orders"].insert_one(
            {
                "user_id": 3,
                "items": [{"quantity": 1}],
                "total": 6.0,
                "status": "cancelled",
                "assigned_rider_id": test_rider_id,
                "accepted_at": datetime(2026, 1, 4, tzinfo=UTC),
            }
        )

        rows = orders_service.get_bounties_by_rider(test_rider_id, limit=10)
        self.assertEqual(rows, [])

    # UC8 Fulfill Bounty - complete delivery lifecycle to closed with recorded payout.
    # normal flow
    def test_uc8_fulfill_bounty_success(self):
        self._insert_user(3001, "test_orderer3001", "1003001")
        self._insert_user(9001, "test_rider9001", "1009001")

        cart = [{"food": {"id": 701, "name": "Rice Bowl", "price": 9.0}, "quantity": 1}]
        order_id = orders_service.create_order(3001, cart)
        self.assertIsNotNone(order_id)

        accepted = orders_service.accept_bounty(str(order_id), 9001)
        self.assertIsNotNone(accepted)
        picked = orders_service.mark_order_picked_up(str(order_id), 9001)
        self.assertIsNotNone(picked)
        delivered = orders_service.mark_order_delivered(str(order_id), 9001)
        self.assertIsNotNone(delivered)
        completed = orders_service.mark_order_completed(str(order_id), 9001)
        self.assertIsNotNone(completed)
        self.assertEqual(completed["status"], "completed") # ensure completed

        self.client[self.test_db_name]["orders"].update_one(
            {"_id": order_id},
            {"$set": {"completed_at": datetime.now(UTC) - timedelta(minutes=4)}}, # simulate completed 4 mins ago, so eligible for closing
        )

        closed = orders_service.close_bounty(str(order_id))
        self.assertIsNotNone(closed); self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["delivery_payment"]["status"], "paid_out")

        payment_doc = self.client[self.test_db_name]["payments"].find_one(
            {"source_order_id": str(order_id)},
            {"_id": 0, "status": 1, "payment_type": 1},
        )
        self.assertIsNotNone(payment_doc)
        self.assertEqual(payment_doc["payment_type"], "delivery_payout")
        self.assertEqual(payment_doc["status"], "paid_out")

    # UC8 alternative flow - retract picked_up once returns to accepted.
    def test_uc8_retract_collected_once(self):
        self._insert_user(3101, "test_orderer3101", "1003101")
        self._insert_user(9101, "test_rider9101", "1009101")

        cart = [{"food": {"id": 711, "name": "Set Meal", "price": 8.0}, "quantity": 1}]
        order_id = orders_service.create_order(3101, cart)
        self.assertIsNotNone(order_id)
        self.assertIsNotNone(orders_service.accept_bounty(str(order_id), 9101))
        self.assertIsNotNone(orders_service.mark_order_picked_up(str(order_id), 9101))

        retracted = orders_service.retract_order_picked_up(str(order_id), 9101)
        self.assertIsNotNone(retracted); self.assertEqual(retracted["status"], "accepted")

        # ensure no double retraction. no infinite money glitch.
        second_retract = orders_service.retract_order_picked_up(str(order_id), 9101)
        self.assertIsNone(second_retract)

    # UC8 alternative flow - retract delivered once returns to picked_up.
    def test_uc8_retract_delivered_once(self):
        self._insert_user(3201, "test_orderer3201", "1003201")
        self._insert_user(9201, "test_rider9201", "1009201")

        cart = [{"food": {"id": 721, "name": "Pasta", "price": 7.0}, "quantity": 1}]
        order_id = orders_service.create_order(3201, cart)
        self.assertIsNotNone(order_id)
        self.assertIsNotNone(orders_service.accept_bounty(str(order_id), 9201))
        self.assertIsNotNone(orders_service.mark_order_picked_up(str(order_id), 9201))
        self.assertIsNotNone(orders_service.mark_order_delivered(str(order_id), 9201)) # now at delivered status

        retracted = orders_service.retract_order_delivered(str(order_id), 9201) # retract once delivered --> picked up
        self.assertIsNotNone(retracted); self.assertEqual(retracted["status"], "picked_up")

        second_retract = orders_service.retract_order_delivered(str(order_id), 9201)
        self.assertIsNone(second_retract)

    # UC8 alternative flow - test_orderer retracts completed once returns to delivered.
    def test_uc8_test_orderer_retract_completed_once(self):
        self._insert_user(3301, "test_orderer3301", "1003301")
        self._insert_user(9301, "test_rider9301", "1009301")

        cart = [{"food": {"id": 731, "name": "Soup", "price": 6.0}, "quantity": 1}]
        order_id = orders_service.create_order(3301, cart)
        self.assertIsNotNone(order_id)
        self.assertIsNotNone(orders_service.accept_bounty(str(order_id), 9301))
        self.assertIsNotNone(orders_service.mark_order_picked_up(str(order_id), 9301))
        self.assertIsNotNone(orders_service.mark_order_delivered(str(order_id), 9301))
        self.assertIsNotNone(orders_service.mark_order_completed(str(order_id), 9301))

        retracted = orders_service.retract_order_completed(str(order_id), 3301)
        self.assertIsNotNone(retracted); self.assertEqual(retracted["status"], "delivered")

        second_retract = orders_service.retract_order_completed(str(order_id), 3301) # no infinite money
        self.assertIsNone(second_retract)

    # UC8 error flow - invalid receiving method records pending balance.
    def test_uc8_invalid_receiving_method_records_pending_balance(self):
        self._insert_user(3401, "test_orderer3401", "1003401")
        self._insert_user(9401, "test_rider9401", "1009401")

        self.client[self.test_db_name]["users"].update_one(
            {"uid": 9401},
            {"$set": {"receiving_method_valid": False}},
        )

        cart = [{"food": {"id": 741, "name": "Wrap", "price": 10.0}, "quantity": 1}]
        order_id = orders_service.create_order(3401, cart)
        self.assertIsNotNone(order_id)
        self.assertIsNotNone(orders_service.accept_bounty(str(order_id), 9401))
        self.assertIsNotNone(orders_service.mark_order_picked_up(str(order_id), 9401))
        self.assertIsNotNone(orders_service.mark_order_delivered(str(order_id), 9401))
        self.assertIsNotNone(orders_service.mark_order_completed(str(order_id), 9401)) # speeedrun

        self.client[self.test_db_name]["orders"].update_one(
            {"_id": order_id},
            {"$set": {"completed_at": datetime.now(UTC) - timedelta(minutes=4)}}, # +4mins
        )

        closed = orders_service.close_bounty(str(order_id))
        self.assertIsNotNone(closed); self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["delivery_payment"]["status"], "pending_balance") # error in recieving method, pending balance

        payment_doc = self.client[self.test_db_name]["payments"].find_one(
            {"source_order_id": str(order_id)},
            {"_id": 0, "status": 1, "reason": 1},
        )
        self.assertIsNotNone(payment_doc)
        self.assertEqual(payment_doc["status"], "pending_balance") # payment doc should reflect
        self.assertEqual(payment_doc["reason"], "invalid_receiving_method")


if __name__ == "__main__":
    unittest.main()
