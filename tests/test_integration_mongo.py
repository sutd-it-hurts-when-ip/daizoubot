import os
import unittest
from datetime import UTC, datetime # timezone info
from pymongo import MongoClient
import services.menu_service as menu_service
import services.orders_service as orders_service
import services.user_service as user_service


class MongoIntegrationTests(unittest.TestCase):
    # annotation @classmethod means this method belongs to the class, not object. 
    # so it essentially lets us "modify the blueprint".
    # e.g: in a few lines, cls.client = MongoClient(...) essentially creates a new attribute for the class instead of the obj
    # so we can access it later in all generated objects of this class (self.client)
    @classmethod
    # run once before all tests
    def setUpClass(cls):
        cls.mongo_uri = os.getenv("MONGO_URI");
        if not cls.mongo_uri:
            raise unittest.SkipTest("MONGO_URI is not set")

        cls.client = MongoClient(cls.mongo_uri, serverSelectionTimeoutMS=1000);
        try:
            # are you alive
            cls.client.admin.command("ping")
        except Exception as exc:
            raise unittest.SkipTest(f"MongoDB is not reachable: {exc}")

        cls.test_db_name = os.getenv("MONGO_TEST_DB_NAME", "daizoubu_integration_test");

        # original module-level config values so we can restore them later
        cls._menu_original_db = menu_service.MONGO_DB_NAME;
        cls._orders_original_db = orders_service.MONGO_DB_NAME;
        cls._users_original_db = user_service.MONGO_DB_NAME;
        # save original client
        cls._menu_original_client = menu_service._client;
        cls._orders_original_client = orders_service._client;
        cls._users_original_client = user_service._client;

        # test database config
        menu_service.MONGO_DB_NAME = cls.test_db_name;
        orders_service.MONGO_DB_NAME = cls.test_db_name;
        user_service.MONGO_DB_NAME = cls.test_db_name;
        # test client
        menu_service._client = cls.client;
        orders_service._client = cls.client;
        user_service._client = cls.client;

    @classmethod
    # cleanup, runs once after all tests
    def tearDownClass(cls):
        # cleanup test db
        db = cls.client[cls.test_db_name];
        db["vendors"].delete_many({})
        db["orders"].delete_many({})
        db["users"].delete_many({})

        # refer to above, restore original config
        menu_service.MONGO_DB_NAME = cls._menu_original_db;
        orders_service.MONGO_DB_NAME = cls._orders_original_db;
        user_service.MONGO_DB_NAME = cls._users_original_db;
        menu_service._client = cls._menu_original_client;
        orders_service._client = cls._orders_original_client;
        user_service._client = cls._users_original_client;

        cls.client.close()

    def setUp(self):
        # delete all docs before each test
        # remember the setUpClass(cls) @classmethod above?
        db = self.client[self.test_db_name];
        db["vendors"].delete_many({})
        db["orders"].delete_many({})
        db["users"].delete_many({})

    def _insert_user(self, uid, username, student_id):
        self.client[self.test_db_name]["users"].insert_one(
            {
                "uid": uid,
                "username": username,
                "student_id": student_id,
            }
        )

    def test_menu_service_reads_from_mongo(self):
        # insert something to read
        self.client[self.test_db_name]["vendors"].insert_one(
            {
                "id": 9001,
                "name": "Integration Vendor",
                "foods": [
                    {
                        "id": 900101,
                        "name": "Integration Noodles",
                        "price": 9.9,
                        "description": "integration food",
                    }
                ],
            }
        )

        # test get_vendors
        vendors = menu_service.get_vendors()
        # check if inserted vendor (id 9001) is in list of vendors returned by get_vendors
        self.assertTrue(any(v.get("id") == 9001 for v in vendors))

        # test solo get_vendor
        vendor = menu_service.get_vendor(9001)
        # must exist and hav correct name
        self.assertIsNotNone(vendor)
        self.assertEqual(vendor["name"], "Integration Vendor")

        # test get_food
        food = menu_service.get_food(900101)
        # must exist and have correct name
        self.assertIsNotNone(food)
        self.assertEqual(food["name"], "Integration Noodles")

    def test_create_order_persists_to_mongo(self):
        self._insert_user(123456, "test_orderer", "1001234")

        cart = [
            {"food": {"id": 101, "name": "Chicken Chop", "price": 6.5}, "quantity": 2},
            {"food": {"id": 202, "name": "Dumpling Ban Mian", "price": 5.5}, "quantity": 1},
        ]

        # publish cart to mongo as doc
        inserted_id = orders_service.create_order(123456, cart)
        # ensure an ID is returned, implying successful insert
        self.assertIsNotNone(inserted_id)

        # verify that order is indeed in db
        order = self.client[self.test_db_name]["orders"].find_one(
            {"user_id": 123456},
        )
        # assertions
        self.assertIsNotNone(order)
        self.assertEqual(order["status"], "placed")
        self.assertEqual(order["total"], 18.5)
        self.assertEqual(len(order["items"]), 2)

    def test_get_orders_by_user_returns_newest_first_with_limit(self):
        # check that returns correct user's order, order returned in correct order (that is trippy) and limit works
        # get the correct collection, insert orders (insert_many)
        orders_collection = self.client[self.test_db_name]["orders"]
        orders_collection.insert_many(
            [
                {
                    "user_id": 999,
                    "items": [{"quantity": 1}],
                    "total": 10.0,
                    "status": "placed",
                    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
                },
                {
                    "user_id": 999,
                    "items": [{"quantity": 2}],
                    "total": 20.0,
                    "status": "placed",
                    "created_at": datetime(2026, 2, 1, tzinfo=UTC),
                },
                {
                    "user_id": 1000,
                    "items": [{"quantity": 3}],
                    "total": 30.0,
                    "status": "placed",
                    "created_at": datetime(2026, 3, 1, tzinfo=UTC),
                },
            ]
        )

        latest_only = orders_service.get_orders_by_user(999, limit=1)
        # respect limit param
        self.assertEqual(len(latest_only), 1)
        # check that it is the latest one (not 30.0, that's the wrong user)
        self.assertEqual(latest_only[0]["total"], 20.0)

        # all orders for user 999 (so 2 total)
        all_user_orders = orders_service.get_orders_by_user(999, limit=5)
        self.assertEqual(len(all_user_orders), 2)
        # ensure the first one is indeed the latest one
        self.assertEqual(all_user_orders[0]["total"], 20.0);
        self.assertEqual(all_user_orders[1]["total"], 10.0);

    def test_delivery_lifecycle_accept_pickup_deliver(self):
        self._insert_user(2020, "test_orderer2020", "1002222")
        self._insert_user(7001, "test_rider7001", "1003333")
        self._insert_user(7002, "test_rider7002", "1004444")

        cart = [{"food": {"id": 101, "name": "Chicken Chop", "price": 6.5}, "quantity": 1}]
        inserted_id = orders_service.create_order(2020, cart)
        self.assertIsNotNone(inserted_id)

        bounties = orders_service.get_open_bounties(limit=5)
        self.assertEqual(len(bounties), 1)

        accepted = orders_service.accept_bounty(str(inserted_id), 7001)
        self.assertIsNotNone(accepted)
        self.assertEqual(accepted["status"], "accepted")

        second_attempt = orders_service.accept_bounty(str(inserted_id), 7002)
        self.assertIsNone(second_attempt)

        active = orders_service.get_active_delivery(7001)
        self.assertIsNotNone(active)
        self.assertEqual(active["status"], "accepted")

        picked_up = orders_service.mark_order_picked_up(str(inserted_id), 7001)
        self.assertIsNotNone(picked_up)
        self.assertEqual(picked_up["status"], "picked_up")

        delivered = orders_service.mark_order_delivered(str(inserted_id), 7001)
        self.assertIsNotNone(delivered)
        self.assertEqual(delivered["status"], "delivered")

        no_active = orders_service.get_active_delivery(7001)
        self.assertIsNone(no_active)


if __name__ == "__main__":
    unittest.main()

