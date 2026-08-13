import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import handlers.menu as menu_handlers


def make_context(cart=None):
    # helper: if cart is None, start with empty user_data; else preload cart.
    return SimpleNamespace(user_data={} if cart is None else {"cart": cart});


VENDORS = [
    {
        "id": 1,
        "name": "Western",
        "foods": [
            {"id": 101, "name": "Chicken Chop", "price": 6.5, "description": "desc cc"},
        ],
    }
]


class SystemFlowAndRobustnessTests(unittest.IsolatedAsyncioTestCase):
    # end-to-end happy flow for customer: browse -> add -> checkout -> place order.
    async def test_end_to_end_customer_flow_browse_add_checkout_place_order(self):
        context = make_context();

        # browse menu renders vendor list.
        browse_update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()));
        with patch("handlers.menu.get_vendors", return_value=VENDORS):
            await menu_handlers.browse_menu(browse_update, context)

        browse_update.message.reply_text.assert_awaited_once()
        self.assertIn("Select a vendor", browse_update.message.reply_text.await_args.args[0])

        # add one item to cart and assert quantity is tracked.
        add_query = SimpleNamespace(data="cart_add:101", answer=AsyncMock(), edit_message_text=AsyncMock())
        add_update = SimpleNamespace(callback_query=add_query)
        with patch("handlers.menu.get_food", return_value=VENDORS[0]["foods"][0]):
            await menu_handlers.add_to_cart(add_update, context)

        self.assertEqual(context.user_data["cart"][0]["quantity"], 1)

        # checkout text should show computed total.
        checkout_query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
        checkout_update = SimpleNamespace(callback_query=checkout_query)
        await menu_handlers.checkout(checkout_update, context)
        self.assertIn("Total: $6.50", checkout_query.edit_message_text.await_args.kwargs["text"])

        # place order should clear cart after successful fake payment + order creation.
        place_query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
        place_update = SimpleNamespace(callback_query=place_query, effective_user=SimpleNamespace(id=42))
        with patch(
            "handlers.menu.create_payment_request",
            return_value={"payment_id": "pay-1", "status": "pending", "qr_payload": "q"},
        ), patch("handlers.menu.mark_payment_paid", return_value={"payment_id": "pay-1", "status": "paid"}), patch(
            "handlers.menu.is_payment_verified", return_value=True
        ), patch("handlers.menu.create_order", return_value="order-1") as create_order_mock:
            await menu_handlers.place_order(place_update, context)

        create_order_mock.assert_called_once()
        self.assertEqual(context.user_data["cart"], [])
        place_query.edit_message_text.assert_awaited_once_with("Your order has been placed")

    # rider UI flow should render proper status messages on each transition.
    async def test_rider_lifecycle_handlers_render_status_transitions(self):
        # accept
        accept_query = SimpleNamespace(data="bounty_accept:oid-1", answer=AsyncMock(), edit_message_text=AsyncMock())
        accept_update = SimpleNamespace(callback_query=accept_query, effective_user=SimpleNamespace(id=7))
        accepted = {"order_id": "oid-1", "items": [{"quantity": 1}], "total": 6.5, "status": "accepted"}
        with patch("handlers.menu.accept_bounty", return_value=accepted):
            await menu_handlers.accept_bounty_handler(accept_update, SimpleNamespace())
        self.assertIn("Bounty accepted", accept_query.edit_message_text.await_args.args[0])

        # picked up
        pickup_query = SimpleNamespace(data="delivery_pickup:oid-1", answer=AsyncMock(), edit_message_text=AsyncMock())
        pickup_update = SimpleNamespace(callback_query=pickup_query, effective_user=SimpleNamespace(id=7))
        picked = {"order_id": "oid-1", "items": [{"quantity": 1}], "total": 6.5, "status": "picked_up"}
        with patch("handlers.menu.mark_order_picked_up", return_value=picked):
            await menu_handlers.mark_delivery_picked_up(pickup_update, SimpleNamespace())
        self.assertIn("Order picked up", pickup_query.edit_message_text.await_args.args[0])

        # delivered
        done_query = SimpleNamespace(data="delivery_done:oid-1", answer=AsyncMock(), edit_message_text=AsyncMock())
        done_update = SimpleNamespace(callback_query=done_query, effective_user=SimpleNamespace(id=7))
        delivered = {"order_id": "oid-1", "items": [{"quantity": 1}], "total": 6.5, "status": "delivered"}
        with patch("handlers.menu.mark_order_delivered", return_value=delivered):
            await menu_handlers.mark_delivery_done(done_update, SimpleNamespace())
        self.assertIn("Order delivered", done_query.edit_message_text.await_args.args[0])

        # completed
        complete_query = SimpleNamespace(data="delivery_complete:oid-1", answer=AsyncMock(), edit_message_text=AsyncMock())
        complete_update = SimpleNamespace(callback_query=complete_query, effective_user=SimpleNamespace(id=7))
        completed = {"order_id": "oid-1", "items": [{"quantity": 1}], "total": 6.5, "status": "completed"}
        with patch("handlers.menu.mark_order_completed", return_value=completed):
            await menu_handlers.mark_delivery_completed(complete_update, SimpleNamespace())
        self.assertIn("Order completed", complete_query.edit_message_text.await_args.args[0])

    # malformed food payload should still render safely with fallback formatting.
    async def test_food_selected_robust_to_bad_price_and_missing_description(self):
        query = SimpleNamespace(data="food:101", answer=AsyncMock(), edit_message_text=AsyncMock())
        update = SimpleNamespace(callback_query=query)
        bad_food = {"id": 101, "name": "Chicken Chop", "price": "oops", "description": None}

        with patch("handlers.menu.get_food", return_value=bad_food):
            await menu_handlers.food_selected(update, SimpleNamespace())

        rendered = query.edit_message_text.await_args.kwargs["text"]
        self.assertIn("Price: $0.00", rendered)
        self.assertIn("No description available.", rendered)

    # malformed vendor rows should be filtered without crashing menu rendering.
    async def test_browse_menu_robust_to_malformed_vendor_records(self):
        update = SimpleNamespace(message=SimpleNamespace(reply_text=AsyncMock()))
        malformed_vendors = [
            {"id": 1, "name": "Valid Vendor", "foods": []},
            {"id": 2, "foods": []},
            "bad-row",
        ]

        with patch("handlers.menu.get_vendors", return_value=malformed_vendors):
            await menu_handlers.browse_menu(update, make_context())

        update.message.reply_text.assert_awaited_once()
        markup = update.message.reply_text.await_args.kwargs["reply_markup"]
        self.assertEqual(len(markup.inline_keyboard), 1)
        self.assertEqual(markup.inline_keyboard[0][0].text, "Valid Vendor")


if __name__ == "__main__":
    unittest.main()