import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bson.errors import InvalidId
from pymongo.errors import PyMongoError

import handlers.menu as menu_handlers
import services.menu_service as menu_service
import services.orders_service as orders_service


def make_context(cart=None):
    # helper: cart_present=T/F controls context.user_data contents for handler tests.
    return SimpleNamespace(user_data={} if cart is None else {"cart": cart})


class MCDCOrdersServiceTests(unittest.TestCase):
    # Test cases for high risk branches in orders service.
    # Mock() --> simulate MongoDB colllection
    # AsyncMock() --> simulate async function (e.g. Telegram bot handler)

    # create_order
    # truth table (decision: collection_none or user_missing or cart_empty):
    # collection_none | user_missing | cart_empty | outcome
    # T               | F            | F          | guard true -> None
    # F               | T            | F          | guard true -> None
    # F               | F            | T          | guard true -> None
    # F               | F            | F          | guard false -> proceed
    # MC/DC create_order guard: collection_none=T, user_missing=F, cart_empty=F -> None
    def test_create_order_guard_collection_none(self):
        cart = [{"food": {"id": 1, "name": "A", "price": 2.0}, "quantity": 1}]
        with patch("services.orders_service._get_collection", return_value=None): self.assertIsNone(orders_service.create_order(7, cart))

    # MC/DC create_order guard: collection_none=F, user_missing=T, cart_empty=F -> None
    def test_create_order_guard_missing_user(self):
        collection = Mock(); cart = [{"food": {"id": 1, "name": "A", "price": 2.0}, "quantity": 1}]
        with patch("services.orders_service._get_collection", return_value=collection): self.assertIsNone(orders_service.create_order(None, cart))

    # MC/DC create_order guard: collection_none=F, user_missing=F, cart_empty=T -> None
    def test_create_order_guard_empty_cart(self):
        collection = Mock()
        with patch("services.orders_service._get_collection", return_value=collection): self.assertIsNone(orders_service.create_order(7, []))

    # MC/DC create_order guard: collection_none=F, user_missing=F, cart_empty=F -> inserted_id
    def test_create_order_happy_path_inserted_id(self):
        collection = Mock(); collection.insert_one.return_value = SimpleNamespace(inserted_id="oid-1")
        cart = [{"food": {"id": 1, "name": "A", "price": 2.0}, "quantity": 2}]
        with patch("services.orders_service._get_collection", return_value=collection), patch(
            "services.orders_service.get_user_by_uid", return_value={"uid": 7, "username": "test_user7", "student_id": "1000007"}
        ):
            self.assertEqual(orders_service.create_order(7, cart), "oid-1")

    # get_orders_by_user
    # truth table (decision: collection_none or user_missing):
    # collection_none | user_missing | outcome
    # T               | F            | guard true -> []
    # F               | T            | guard true -> []
    # F               | F            | guard false -> proceed
    # MC/DC get_orders_by_user guard: collection_none=T, user_missing=F -> []
    def test_get_orders_by_user_guard_collection_none(self):
        with patch("services.orders_service._get_collection", return_value=None): self.assertEqual(orders_service.get_orders_by_user(7), [])

    # MC/DC get_orders_by_user guard: collection_none=F, user_missing=T -> []
    def test_get_orders_by_user_guard_missing_user(self):
        with patch("services.orders_service._get_collection", return_value=Mock()): self.assertEqual(orders_service.get_orders_by_user(None), [])

    # MC/DC get_orders_by_user: guard_false + query_ok=T -> rows
    def test_get_orders_by_user_happy_path(self):
        # create test data
        collection = Mock(); cursor = Mock(); rows = [{"user_id": 7, "total": 3.5}];
        # configure mock object to simulate MongoDB query behaviour.
        collection.find.return_value = cursor; cursor.sort.return_value.limit.return_value = rows
        # validate
        with patch("services.orders_service._get_collection", return_value=collection): self.assertEqual(orders_service.get_orders_by_user(7, limit=1), rows)

    # MC/DC get_orders_by_user: guard_false + query_ok=F(PyMongoError) -> []
    # ensure graceful handling of error
    def test_get_orders_by_user_handles_pymongo_error(self):
        # simulate error raised during query.
        collection = Mock(); collection.find.side_effect = PyMongoError("https://www.youtube.com/watch?v=o2tonXY8lCY")
        with patch("services.orders_service._get_collection", return_value=collection): self.assertEqual(orders_service.get_orders_by_user(7), [])

    # get_active_delivery
    # truth table (decision: collection_none or test_rider_missing):
    # collection_none | test_rider_missing | outcome
    # T               | F             | guard true -> None
    # F               | T             | guard true -> None
    # F               | F             | guard false -> proceed
    # MC/DC get_active_delivery guard: collection_none=T, test_rider_missing=F -> None
    def test_get_active_delivery_guard_collection_none(self):
        with patch("services.orders_service._get_collection", return_value=None): self.assertIsNone(orders_service.get_active_delivery(7))

    # MC/DC get_active_delivery guard: collection_none=F, test_rider_missing=T -> None
    def test_get_active_delivery_guard_missing_test_rider(self):
        with patch("services.orders_service._get_collection", return_value=Mock()): self.assertIsNone(orders_service.get_active_delivery(None))

    # MC/DC get_active_delivery: guard_false + find_one_returns_order=T -> normalized order
    def test_get_active_delivery_happy_path_normalized(self):
        collection = Mock(); collection.find_one.return_value = {"_id": "507f1f77bcf86cd799439011", "status": "accepted", "items": [], "total": 1}
        with patch("services.orders_service._get_collection", return_value=collection):
            out = orders_service.get_active_delivery(9); self.assertEqual(out["status"], "accepted"); self.assertEqual(out["order_id"], "507f1f77bcf86cd799439011")

    # accept_bounty
    # truth table (guard decision: collection_none or order_missing or test_rider_missing):
    # collection_none | order_missing | test_rider_missing | outcome
    # T               | F             | F             | guard true -> None
    # F               | T             | F             | guard true -> None
    # F               | F             | T             | guard true -> None
    # F               | F             | F             | guard false -> proceed
    # post-guard branch (ObjectId validity):
    # order_id_valid | outcome
    # F              | InvalidId raised
    # T              | DB update path
    # MC/DC accept_bounty guard: collection_none=T, order_missing=F, test_rider_missing=F -> None
    def test_accept_bounty_guard_collection_none(self):
        with patch("services.orders_service._get_collection", return_value=None): self.assertIsNone(orders_service.accept_bounty("507f1f77bcf86cd799439011", 7))

    # MC/DC accept_bounty guard: collection_none=F, order_missing=T, test_rider_missing=F -> None
    def test_accept_bounty_guard_missing_order_id(self):
        with patch("services.orders_service._get_collection", return_value=Mock()): self.assertIsNone(orders_service.accept_bounty("", 7))

    # MC/DC accept_bounty guard: collection_none=F, order_missing=F, test_rider_missing=T -> None
    def test_accept_bounty_guard_missing_test_rider(self):
        with patch("services.orders_service._get_collection", return_value=Mock()): self.assertIsNone(orders_service.accept_bounty("507f1f77bcf86cd799439011", None))

    # branch accept_bounty post-guard: order_id_valid=F -> InvalidId propagates
    def test_accept_bounty_invalid_order_id_value_error(self):
        with patch("services.orders_service._get_collection", return_value=Mock()), patch(
            "services.orders_service.get_user_by_uid", return_value={"uid": 7, "username": "test_rider7", "student_id": "1000007"}
        ):
            with self.assertRaises(InvalidId): orders_service.accept_bounty("bad-objectid", 7)

    # branch accept_bounty post-guard: order_id_valid=T, update_returns_order=T -> normalized order
    def test_accept_bounty_happy_path_normalized(self):
        collection = Mock(); collection.find_one_and_update.return_value = {"_id": "507f1f77bcf86cd799439011", "status": "accepted", "items": [], "total": 1}
        with patch("services.orders_service._get_collection", return_value=collection), patch(
            "services.orders_service.get_user_by_uid", return_value={"uid": 7, "username": "test_rider7", "student_id": "1000007"}
        ):
            out = orders_service.accept_bounty("507f1f77bcf86cd799439011", 7); self.assertEqual(out["status"], "accepted"); self.assertEqual(out["order_id"], "507f1f77bcf86cd799439011")


class MCDCMenuServiceTests(unittest.TestCase):
    # Test cases for menu-service decision paths and fallback behavior.

    # _get_collection
    # truth table (decision: uri_missing or db_missing):
    # uri_missing | db_missing | outcome
    # T           | F          | guard true -> None
    # F           | T          | guard true -> None
    # F           | F          | guard false -> proceed
    # MC/DC _get_collection guard: uri_missing=T, db_missing=F -> None
    def test_get_collection_guard_missing_uri(self):
        with patch.object(menu_service, "MONGO_URI", None), patch.object(menu_service, "MONGO_DB_NAME", "db"): self.assertIsNone(menu_service._get_collection())

    # MC/DC _get_collection guard: uri_missing=F, db_missing=T -> None
    def test_get_collection_guard_missing_db_name(self):
        with patch.object(menu_service, "MONGO_URI", "mongodb://x"), patch.object(menu_service, "MONGO_DB_NAME", None): self.assertIsNone(menu_service._get_collection())

    # MC/DC _get_collection guard: uri_missing=F, db_missing=F -> collection lookup path
    def test_get_collection_happy_path_returns_collection(self):
        # SimpleNamespace works as lightweight fake collection here.
        fake_collection = SimpleNamespace(kind="collection"); fake_client = {"db": {"vendors": fake_collection}}

        with patch.object(menu_service, "MONGO_URI", "mongodb://x"), patch.object(menu_service, "MONGO_DB_NAME", "db"), patch.object(
            menu_service, "_client", fake_client
        ):
            out = menu_service._get_collection()

        self.assertIs(out, fake_collection)

    # get_vendors
    # truth table (decision flow):
    # collection_none | query_raises | mongo_rows_non_empty | outcome
    # T               | -            | -                    | fallback vendors
    # F               | T            | -                    | fallback vendors
    # F               | F            | T                    | mongo rows
    # F               | F            | F                    | fallback vendors
    # MC/DC get_vendors: collection_none=T -> fallback vendors
    def test_get_vendors_fallback_when_no_collection(self):
        fake = [{"id": 1, "name": "fallback"}]
        with patch("services.menu_service._get_collection", return_value=None), patch.object(menu_service, "vendors", fake): self.assertEqual(menu_service.get_vendors(), fake)

    # MC/DC get_vendors: collection_none=F, mongo_rows_non_empty=T -> mongo rows
    def test_get_vendors_returns_mongo_list_when_non_empty(self):
        mongo_rows = [{"id": 2, "name": "mongo"}]; collection = Mock(); collection.find.return_value = mongo_rows
        with patch("services.menu_service._get_collection", return_value=collection), patch.object(menu_service, "vendors", [{"id": 1}]): self.assertEqual(menu_service.get_vendors(), mongo_rows)

    # MC/DC get_vendors: collection_none=F, mongo_rows_non_empty=F -> fallback vendors
    def test_get_vendors_fallback_when_mongo_empty(self):
        fallback = [{"id": 1, "name": "fallback"}]; collection = Mock(); collection.find.return_value = []
        with patch("services.menu_service._get_collection", return_value=collection), patch.object(menu_service, "vendors", fallback): self.assertEqual(menu_service.get_vendors(), fallback)

    # MC/DC get_vendors: collection_none=F, query_raises=T -> fallback vendors
    def test_get_vendors_fallback_on_pymongo_error(self):
        fallback = [{"id": 1, "name": "fallback"}]; collection = Mock(); collection.find.side_effect = PyMongoError("boom")
        with patch("services.menu_service._get_collection", return_value=collection), patch.object(menu_service, "vendors", fallback): self.assertEqual(menu_service.get_vendors(), fallback)


class MCDCHandlerMenuTests(unittest.IsolatedAsyncioTestCase):
    # Handler-focused branch tests for menu UI rendering and cart-dependent buttons.

    # browse_menu / back ternary hasattr(context, "user_data")
    # truth table (expression: bool(get_cart(context)) if has_user_data else False):
    # has_user_data | cart_non_empty | show_view_cart
    # F             | -              | F
    # T             | F              | F
    # T             | T              | T
    # MC/DC browse_menu ternary: has_user_data=F -> show_view_cart=False
    async def test_browse_menu_no_user_data_sets_show_view_cart_false(self):
        update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock())); context = SimpleNamespace()
        with patch("handlers.menu.get_vendors", return_value=[]), patch("handlers.menu.vendor_keyboard", return_value="mk") as vk:
            await menu_handlers.browse_menu(update, context); vk.assert_called_once_with([], show_view_cart=False)

    # MC/DC browse_menu ternary: has_user_data=T and cart_non_empty=T -> show_view_cart=True
    async def test_browse_menu_user_data_with_cart_sets_show_view_cart_true(self):
        update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock())); context = make_context([{"food": {"id": 1}, "quantity": 1}])
        with patch("handlers.menu.get_vendors", return_value=[]), patch("handlers.menu.vendor_keyboard", return_value="mk") as vk:
            await menu_handlers.browse_menu(update, context); vk.assert_called_once_with([], show_view_cart=True)

    # MC/DC browse_menu ternary: has_user_data=T and cart_non_empty=F -> show_view_cart=False
    async def test_browse_menu_user_data_empty_cart_sets_show_view_cart_false(self):
        update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock())); context = make_context([])
        with patch("handlers.menu.get_vendors", return_value=[]), patch("handlers.menu.vendor_keyboard", return_value="mk") as vk:
            await menu_handlers.browse_menu(update, context); vk.assert_called_once_with([], show_view_cart=False)

    # MC/DC back ternary: has_user_data=F -> show_view_cart=False
    async def test_back_no_user_data_sets_show_view_cart_false(self):
        query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock()); update = SimpleNamespace(callback_query=query); context = SimpleNamespace()
        with patch("handlers.menu.get_vendors", return_value=[]), patch("handlers.menu.vendor_keyboard", return_value="mk") as vk:
            await menu_handlers.back(update, context); vk.assert_called_once_with([], show_view_cart=False)

    # MC/DC back ternary: has_user_data=T and cart_non_empty=T -> show_view_cart=True
    async def test_back_user_data_with_cart_sets_show_view_cart_true(self):
        query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock()); update = SimpleNamespace(callback_query=query); context = make_context([{"food": {"id": 1}, "quantity": 1}])
        with patch("handlers.menu.get_vendors", return_value=[]), patch("handlers.menu.vendor_keyboard", return_value="mk") as vk:
            await menu_handlers.back(update, context); vk.assert_called_once_with([], show_view_cart=True)

    # MC/DC back ternary: has_user_data=T and cart_non_empty=F -> show_view_cart=False
    async def test_back_user_data_empty_cart_sets_show_view_cart_false(self):
        query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock()); update = SimpleNamespace(callback_query=query); context = make_context([])
        with patch("handlers.menu.get_vendors", return_value=[]), patch("handlers.menu.vendor_keyboard", return_value="mk") as vk:
            await menu_handlers.back(update, context); vk.assert_called_once_with([], show_view_cart=False)

    # view_orders created_at branch
    # truth table (branch: isinstance(created_at, datetime)):
    # created_at_is_datetime | outcome
    # T                      | formatted timestamp
    # F                      | "unknown time"
    # branch view_orders: created_at_is_datetime=T -> formatted timestamp branch
    async def test_view_orders_formats_datetime_timestamp(self):
        reply_text = AsyncMock(); update = SimpleNamespace(message=SimpleNamespace(reply_text=reply_text), effective_user=SimpleNamespace(id=1))
        rows = [{"created_at": datetime(2026, 1, 1, 10, 30, tzinfo=UTC), "items": [{"quantity": 1}], "total": 3.5, "status": "placed"}]
        with patch("handlers.menu.get_orders_by_user", return_value=rows): await menu_handlers.view_orders(update, SimpleNamespace())
        self.assertIn("2026-01-01 10:30", reply_text.await_args.args[0])

    # branch view_orders: created_at_is_datetime=F -> "unknown time" branch
    async def test_view_orders_uses_unknown_time_for_non_datetime(self):
        reply_text = AsyncMock(); update = SimpleNamespace(message=SimpleNamespace(reply_text=reply_text), effective_user=SimpleNamespace(id=1))
        rows = [{"created_at": "2026-01-01T10:30:00", "items": [{"quantity": 1}], "total": 3.5, "status": "placed"}]
        with patch("handlers.menu.get_orders_by_user", return_value=rows): await menu_handlers.view_orders(update, SimpleNamespace())
        self.assertIn("unknown time", reply_text.await_args.args[0])

    # view_accepted_bounties actionable filter branch
    # truth table (filter branch: status in {accepted, picked_up}):
    # status     | included_in_actionable
    # accepted   | T
    # picked_up  | T
    # delivered  | F
    #
    # downstream branch (after filter):
    # actionable_empty | outcome
    # T                | "no active accepted bounties"
    # F                | send header + actionable entries
    # branch actionable filter: statuses={delivered} only -> actionable_empty=T -> no active message
    async def test_view_accepted_bounties_delivered_only_reports_no_active(self):
        reply_text = AsyncMock(); update = SimpleNamespace(message=SimpleNamespace(reply_text=reply_text), effective_user=SimpleNamespace(id=9))
        rows = [{"order_id": "a", "items": [{"quantity": 1}], "total": 1, "status": "delivered"}]
        with patch("handlers.menu.get_bounties_by_rider", return_value=rows): await menu_handlers.view_accepted_bounties(update, SimpleNamespace())
        reply_text.assert_awaited_once_with("You have no active accepted bounties.")

    # branch actionable filter: statuses include accepted/picked_up + delivered -> actionable_non_empty and delivered excluded
    async def test_view_accepted_bounties_mixed_sends_only_actionable(self):
        reply_text = AsyncMock(); update = SimpleNamespace(message=SimpleNamespace(reply_text=reply_text), effective_user=SimpleNamespace(id=9))
        rows = [
            {"order_id": "a", "items": [{"quantity": 1}], "total": 1, "status": "accepted"},
            {"order_id": "b", "items": [{"quantity": 1}], "total": 1, "status": "picked_up"},
            {"order_id": "c", "items": [{"quantity": 1}], "total": 1, "status": "delivered"},
        ]
        with patch("handlers.menu.get_bounties_by_rider", return_value=rows): await menu_handlers.view_accepted_bounties(update, SimpleNamespace())
        self.assertEqual(reply_text.await_count, 3); self.assertIn("Order a", reply_text.await_args_list[1].args[0]); self.assertIn("Order b", reply_text.await_args_list[2].args[0]); self.assertNotIn("Order c", "\n".join(call.args[0] for call in reply_text.await_args_list[1:]))

    # add_to_cart item-match branch
    # truth table (loop branch: item.food.id == food.id):
    # match_found | outcome
    # T           | quantity from matched item
    # F           | default quantity=1
    # branch add_to_cart loop: matched_item_found=T -> message uses matched quantity
    async def test_add_to_cart_existing_item_reports_current_quantity(self):
        query = SimpleNamespace(data="cart_add:101", answer=AsyncMock(), edit_message_text=AsyncMock()); update = SimpleNamespace(callback_query=query)
        context = make_context([{"food": {"id": 101, "name": "Chicken Chop", "price": 6.5}, "quantity": 3}]); food = {"id": 101, "name": "Chicken Chop", "price": 6.5}
        with patch("handlers.menu.get_food", return_value=food), patch("handlers.menu.cart_add"):
            await menu_handlers.add_to_cart(update, context)
        query.answer.assert_awaited_once_with(text="Added Chicken Chop to cart (3 in cart)", show_alert=False)

    # branch add_to_cart loop: matched_item_found=F -> default quantity=1
    async def test_add_to_cart_new_item_reports_default_quantity(self):
        query = SimpleNamespace(data="cart_add:101", answer=AsyncMock(), edit_message_text=AsyncMock()); update = SimpleNamespace(callback_query=query)
        context = make_context([{"food": {"id": 202, "name": "Other", "price": 1.0}, "quantity": 2}]); food = {"id": 101, "name": "Chicken Chop", "price": 6.5}
        with patch("handlers.menu.get_food", return_value=food), patch("handlers.menu.cart_add"):
            await menu_handlers.add_to_cart(update, context)
        query.answer.assert_awaited_once_with(text="Added Chicken Chop to cart (1 in cart)", show_alert=False)


if __name__ == "__main__":
    unittest.main()

# ????????????
