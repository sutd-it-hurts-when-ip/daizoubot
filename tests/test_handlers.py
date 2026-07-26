import unittest
from types import SimpleNamespace  # fake object
from unittest.mock import ANY, AsyncMock, patch  # async mock, patching, wildcard matcher

# imports
from handlers.menu import add_to_cart, clear_cart, view_cart
import handlers.menu as menu_handlers
from handlers.router import router
from handlers.start import start
from keyboards.inline_menu import (
	cart_keyboard,
	checkout_keyboard,
	empty_card_keyboard,
	food_detail_keyboard,
	food_keyboard,
	vendor_keyboard,
)
from keyboards.main_menu import main_menu
from services.cart_service import (
	add_to_cart as cart_add,
	cart_item_count,
	cart_total,
	clear_cart as cart_clear,  # conflicting name from handlers.menu
	format_cart,
	get_cart,
	remove_from_cart,
)
import services.menu_service as menu_service


# Local fixture data so tests are independent of services.fake_db.
VENDORS = [
	{
		"id": 1,
		"name": "Western",
		"foods": [
			{"id": 101, "name": "Chicken Chop", "price": 6.5, "description": "desc cc"},
			{"id": 102, "name": "Fish & Chips", "price": 7.0, "description": "desc fnc"},
			{"id": 103, "name": "Pasta", "price": 6.0, "description": "desc p"},
		],
	},
	{
		"id": 2,
		"name": "Ban Mian",
		"foods": [
			{"id": 201, "name": "Signature Ban Mian", "price": 5.0, "description": "desc sbm"},
			{"id": 202, "name": "Dumpling Ban Mian", "price": 5.5, "description": "desc dbm"},
		],
	},
]


# fake Telegram context
def make_context(cart=None):
	# context.user_data is frequently used by handlers/services
	return SimpleNamespace(user_data={} if cart is None else {"cart": cart})


# helper for verifying button texts for inline keyboards
def inline_texts(markup):
	return [[button.text for button in row] for row in markup.inline_keyboard]


# helper for verifying button texts for reply keyboards
def reply_texts(markup):
	return [[button.text for button in row] for row in markup.keyboard]


# check that keyboard generation gives correct results
class KeyboardTests(unittest.TestCase):
	# test that main menu contains the expected choices for a user
	def test_main_menu_contains_expected_choices(self):
		markup = main_menu(SimpleNamespace(first_name="Himeko"))

		self.assertEqual(
			reply_texts(markup),
			[["Browse Menu"], ["Available Bounties"], ["My Orders"], ["My Profile"]],
		)

	# example: vendor ids 1 and 2 should render buttons "Western" and "Ban Mian"
	# with callback data "vendor:1" and "vendor:2"
	def test_vendor_keyboard_uses_vendor_ids(self):
		markup = vendor_keyboard(VENDORS)

		# inline_keyboard: row 0
		# button 0 - text = "Western", callback_data = "vendor:1"
		# row 1, button 0 - text = "Ban Mian", callback_data = "vendor:2"
		# etc.
		# reminder that inline_texts is a helper that breaks down markup (keyboard) into list of lists to validate against...
		self.assertEqual(inline_texts(markup), [["Western"], ["Ban Mian"]])
		self.assertEqual(markup.inline_keyboard[0][0].callback_data, "vendor:1")
		self.assertEqual(markup.inline_keyboard[1][0].callback_data, "vendor:2")

		# refer to above for the rest of the functions, basically the same thing
		# declare keyboard, check text correct, check callback_data correct.

	# test that food buttons show food names, prices, and food:<id> callbacks
	def test_food_keyboard_uses_food_ids(self):
		markup = food_keyboard(VENDORS[0]["foods"][:2])

		self.assertEqual(inline_texts(markup), [["Chicken Chop: $6.5."], ["Fish & Chips: $7.0."]])
		self.assertEqual(markup.inline_keyboard[0][0].callback_data, "food:101")
		self.assertEqual(markup.inline_keyboard[1][0].callback_data, "food:102")

	# test that the food detail keyboard shows the expected cart actions
	def test_food_detail_keyboard_contains_actions(self):
		markup = food_detail_keyboard(101)

		self.assertEqual(inline_texts(markup), [["Add to Cart"], ["View Cart"], ["Back"]])
		self.assertEqual(markup.inline_keyboard[0][0].callback_data, "cart_add:101")
		self.assertEqual(markup.inline_keyboard[1][0].callback_data, "view_cart")
		self.assertEqual(markup.inline_keyboard[2][0].callback_data, "back")

	# test that the cart keyboard shows checkout and browsing actions
	def test_cart_keyboard_contains_checkout_actions(self):
		markup = cart_keyboard()

		self.assertEqual(inline_texts(markup), [["Checkout"], ["Clear Cart"], ["Continue Shopping"]])

	# test that the empty cart keyboard offers a way back to browsing
	def test_empty_cart_keyboard_contains_browse_button(self):
		markup = empty_card_keyboard()

		self.assertEqual(inline_texts(markup), [["Browse Menu"]])
		self.assertEqual(markup.inline_keyboard[0][0].callback_data, "back")

	# test that the checkout keyboard shows place-order and cancel actions
	def test_checkout_keyboard_contains_order_actions(self):
		markup = checkout_keyboard()

		self.assertEqual(inline_texts(markup), [["Place Order"], ["Cancel"]])
		self.assertEqual(markup.inline_keyboard[0][0].callback_data, "place_order")
		self.assertEqual(markup.inline_keyboard[1][0].callback_data, "view_cart")


# layer up: menu service lookups
class MenuServiceTests(unittest.TestCase):
	# test that getting vendors returns the patched sample vendor list
	def test_get_vendors_returns_sample_data(self):
		# with patch.object temporarily replaces menu_service's object "vendors" with local VENDORS object
		# so that .get_vendors() returns VENDORS, eliminating dependency on services.fake_db
		with patch.object(menu_service, "vendors", VENDORS):
			self.assertEqual(menu_service.get_vendors(), VENDORS)

	# example: looking up vendor id 1 should return the "Western" vendor dict
	def test_get_vendor_finds_match(self):
		with patch.object(menu_service, "vendors", VENDORS):
			vendor = menu_service.get_vendor(1)

		self.assertIsNotNone(vendor)
		self.assertEqual(vendor["name"], "Western")

	# test that a missing vendor id returns None
	def test_get_vendor_returns_none_for_missing_id(self):
		with patch.object(menu_service, "vendors", VENDORS):
			self.assertIsNone(menu_service.get_vendor(99123))

	# test that food lookup finds the matching food across all vendors
	def test_get_food_finds_match(self):
		with patch.object(menu_service, "vendors", VENDORS):
			food = menu_service.get_food(202)

		self.assertIsNotNone(food)
		self.assertEqual(food["name"], "Dumpling Ban Mian")

	# test that a missing food id returns None
	def test_get_food_returns_none_for_missing_id(self):
		with patch.object(menu_service, "vendors", VENDORS):
			self.assertIsNone(menu_service.get_food(999))


# cart logic: pure state manipulation
# these are all pure functions
class CartServiceTests(unittest.TestCase):
	# test that get_cart creates an empty cart when user_data has none yet
	def test_get_cart_initializes_user_data(self):
		context = make_context()

		self.assertEqual(get_cart(context), [])
		self.assertIn("cart", context.user_data)

	# example: adding Chicken Chop twice should keep one cart entry with quantity 2
	def test_add_to_cart_merges_duplicate_items(self):
		context = make_context()
		food = VENDORS[0]["foods"][0]

		cart_add(context, food)
		cart_add(context, food)

		self.assertEqual(cart_item_count(context), 2)
		self.assertEqual(context.user_data["cart"][0]["quantity"], 2)

	# test that removing an item decrements quantity before deleting the entry
	def test_remove_from_cart_decrements_and_deletes_item(self):
		context = make_context()
		food = VENDORS[0]["foods"][0]

		cart_add(context, food)
		cart_add(context, food)
		remove_from_cart(context, food)

		self.assertEqual(context.user_data["cart"][0]["quantity"], 1)

		remove_from_cart(context, food)
		self.assertEqual(context.user_data["cart"], [])

	# test that clear_cart removes all items from the stored cart
	def test_clear_cart_empties_cart(self):
		context = make_context([{"food": VENDORS[0]["foods"][0], "quantity": 1}])

		cart_clear(context)

		self.assertEqual(get_cart(context), [])

	# test that cart_total multiplies price by quantity and sums all items
	def test_cart_total_calculates_sum(self):
		context = make_context()
		chicken = {"id": 101, "name": "Chicken Chop", "price": 6.5}
		pasta = {"id": 103, "name": "Pasta", "price": 6.0}

		cart_add(context, chicken)
		cart_add(context, chicken)
		cart_add(context, pasta)

		self.assertEqual(cart_total(context), 19.0)

	# test that format_cart includes item names, counts, and the total price
	def test_format_cart_builds_summary(self):
		context = make_context()
		chicken = VENDORS[0]["foods"][0]

		cart_add(context, chicken)

		formatted = format_cart(context)
		self.assertIn("Your cart contains 1 items.", formatted)
		self.assertIn("Chicken Chop", formatted)
		self.assertIn("Total = $6.5", formatted)

	# test that format_cart returns the empty-cart message when there are no items
	def test_format_cart_handles_empty_cart(self):
		self.assertEqual(format_cart(make_context()), "Your cart is empty.")


# top layer: handlers with fake update/context objects
class HandlerTests(unittest.IsolatedAsyncioTestCase):
	# test personalized welcome message and menu
	async def test_start_sends_welcome_message(self):
		# AsyncMock : mock for async functions. It's like SimpleNamespace, but for async functions
		# it can be awaited and you can check if it was awaited and with what functions It's fake
		reply_text = AsyncMock()
		# create fake object
		update = SimpleNamespace(
			# fake function used here...
			message=SimpleNamespace(reply_text=reply_text),
			effective_user=SimpleNamespace(first_name="Himeko"),
		)

		# awaited here
		await start(update, SimpleNamespace())

		# checked here
		reply_text.assert_awaited_once()
		self.assertEqual(reply_text.await_args.args[0], "Welcome to daizoubu, Himeko!")
		self.assertIsNotNone(reply_text.await_args.kwargs.get("reply_markup"))

	# test that the router sends the browse command to the browse_menu handler
	async def test_router_routes_browse_menu_message(self):
		# reply_text is a function provided by Tele API to send message back to user
		# here we mock it to check if it was called w/ the correct args
		update = SimpleNamespace(message=SimpleNamespace(text="Browse Menu", reply_text=AsyncMock()))
		context = SimpleNamespace()

		# another fake function to test
		with patch("handlers.router.browse_menu", new=AsyncMock()) as mocked_browse_menu:
			await router(update, context)

		mocked_browse_menu.assert_awaited_once_with(update, context)

	# test that the router replies with an error for unknown messages
	async def test_router_handles_unknown_message(self):
		reply_text = AsyncMock()
		# refer to above, etc.
		update = SimpleNamespace(message=SimpleNamespace(text="Something else", reply_text=reply_text))

		await router(update, SimpleNamespace())

		reply_text.assert_awaited_once_with("Unknown command")

	# example: callback data "cart_add:101" should look up food id 101 and answer with
	# "Added Chicken Chop to cart" after calling the cart service
	async def test_add_to_cart_responds_when_food_exists(self):
		query = SimpleNamespace(data="cart_add:101", answer=AsyncMock(), edit_message_text=AsyncMock())
		update = SimpleNamespace(callback_query=query)
		context = make_context()
		# \ in python: line continuation character. cool
		with patch("handlers.menu.get_food", return_value=VENDORS[0]["foods"][0]) as mocked_get_food, \
		patch("handlers.menu.cart_add") as mocked_cart_add:
			await add_to_cart(update, context)
		# defined above
		mocked_get_food.assert_called_once_with(101)
		mocked_cart_add.assert_called_once_with(context, VENDORS[0]["foods"][0])
		query.answer.assert_awaited_once_with(text="Added Chicken Chop to cart", show_alert=False)

	# test that add_to_cart shows an error when the requested food does not exist
	async def test_add_to_cart_shows_error_when_food_missing(self):
		query = SimpleNamespace(data="cart_add:999", answer=AsyncMock(), edit_message_text=AsyncMock())
		update = SimpleNamespace(callback_query=query)

		with patch("handlers.menu.get_food", return_value=None):
			await add_to_cart(update, make_context())

		query.edit_message_text.assert_awaited_once_with("Food not found")

	# test that view_cart uses the empty-cart keyboard when the cart has no items
	async def test_view_cart_uses_empty_keyboard_for_empty_cart(self):
		query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
		update = SimpleNamespace(callback_query=query)

		await view_cart(update, make_context())

		query.edit_message_text.assert_awaited_once()
		self.assertIn("Your cart is empty.", query.edit_message_text.await_args.kwargs["text"])

	# test that clear_cart removes stored items and redraws the empty cart state
	async def test_clear_cart_empties_cart(self):
		query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
		update = SimpleNamespace(callback_query=query)
		context = make_context([{"food": VENDORS[0]["foods"][0], "quantity": 1}])

		await clear_cart(update, context)

		self.assertEqual(context.user_data["cart"], [])
		query.edit_message_text.assert_awaited_once_with("Your cart is empty", reply_markup=ANY)


# more stuff
class AdditionalHandlerCoverageTests(unittest.IsolatedAsyncioTestCase):
	
	# example: browse_menu should fetch vendors and send "Select a vendor:"
	# with the vendor keyboard built from that vendor list
	async def test_browse_menu_sends_vendor_prompt_and_keyboard(self):
		reply_text = AsyncMock()
		update = SimpleNamespace(message=SimpleNamespace(reply_text=reply_text))

		# mocked keyboard generator and get_vendors function
		with patch("handlers.menu.get_vendors", return_value=VENDORS) as mocked_get_vendors, patch(
			"handlers.menu.vendor_keyboard", return_value="vendor_markup"
		) as mocked_vendor_keyboard:
		# keyboard generator is already tested in KeyboardTests, we just patch it and check that it passed through
		# the function correctly. 
			await menu_handlers.browse_menu(update, SimpleNamespace())

		# assertions
		mocked_get_vendors.assert_called_once_with()
		mocked_vendor_keyboard.assert_called_once_with(VENDORS)
		reply_text.assert_awaited_once_with("Select a vendor:", reply_markup="vendor_markup")

	# test that vendor_selected reads callback vendor id and loads that vendor menu
	async def test_vendor_selected_shows_selected_vendor_menu(self):
		# create fake callbackquery with data "vendor:1" and mocked answer/edit_message_text functions
		query = SimpleNamespace(data="vendor:1", answer=AsyncMock(), edit_message_text=AsyncMock())
		# fake update w/ callbackquery (above) as attr
		update = SimpleNamespace(callback_query=query)

		with patch("handlers.menu.get_vendor", return_value=VENDORS[0]) as mocked_get_vendor, patch(
			"handlers.menu.food_keyboard", return_value="food_markup"
		) as mocked_food_keyboard:
			await menu_handlers.vendor_selected(update, SimpleNamespace())

		# assertions
		query.answer.assert_awaited_once_with()
		mocked_get_vendor.assert_called_once_with(1)
		mocked_food_keyboard.assert_called_once_with(VENDORS[0]["foods"])
		query.edit_message_text.assert_awaited_once_with(text="Western Menu", reply_markup="food_markup")

	# test that food_selected reads callback food id and shows details/actions
	async def test_food_selected_shows_food_details_and_actions(self):
		query = SimpleNamespace(data="food:101", answer=AsyncMock(), edit_message_text=AsyncMock())
		update = SimpleNamespace(callback_query=query)

		with patch("handlers.menu.get_food", return_value=VENDORS[0]["foods"][0]) as mocked_get_food, patch(
			"handlers.menu.food_detail_keyboard", return_value="detail_markup"
		) as mocked_food_detail_keyboard:
			await menu_handlers.food_selected(update, SimpleNamespace())

		query.answer.assert_awaited_once_with()
		mocked_get_food.assert_called_once_with(101)
		mocked_food_detail_keyboard.assert_called_once_with(101)
		query.edit_message_text.assert_awaited_once_with(
			text="Chicken Chop\n\n6.5\ndesc cc",
			reply_markup="detail_markup",
		)

	# test that add_to_cart missing-food path does not call cart_add or answer callback
	async def test_add_to_cart_missing_food_does_not_add_or_answer(self):
		query = SimpleNamespace(data="cart_add:999", answer=AsyncMock(), edit_message_text=AsyncMock())
		update = SimpleNamespace(callback_query=query)

		with patch("handlers.menu.get_food", return_value=None), patch("handlers.menu.cart_add") as mocked_cart_add:
			await add_to_cart(update, make_context())

		mocked_cart_add.assert_not_called()
		query.answer.assert_not_awaited()
		query.edit_message_text.assert_awaited_once_with("Food not found")

	# test that view_cart uses the cart keyboard when the cart has items
	async def test_view_cart_uses_cart_keyboard_for_non_empty_cart(self):
		query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
		update = SimpleNamespace(callback_query=query)
		context = make_context([{"food": VENDORS[0]["foods"][0], "quantity": 1}])

		await view_cart(update, context)

		query.answer.assert_awaited_once_with()
		self.assertEqual(
			inline_texts(query.edit_message_text.await_args.kwargs["reply_markup"]),
			[["Checkout"], ["Clear Cart"], ["Continue Shopping"]],
		)
		self.assertIn("Your cart contains 1 items.", query.edit_message_text.await_args.kwargs["text"])

	# test that checkout shows empty-cart message when user cart is empty
	async def test_checkout_shows_empty_message_when_cart_is_empty(self):
		query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
		update = SimpleNamespace(callback_query=query)

		await menu_handlers.checkout(update, make_context())

		query.answer.assert_awaited_once_with()
		query.edit_message_text.assert_awaited_once_with("Your cart is empty")

	# test that checkout shows summary text and checkout actions for filled cart
	async def test_checkout_shows_summary_for_non_empty_cart(self):
		query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
		update = SimpleNamespace(callback_query=query)
		# above helper function
		context = make_context(
			[
				{"food": VENDORS[0]["foods"][0], "quantity": 2},
				{"food": VENDORS[0]["foods"][2], "quantity": 1},
			]
		)

		await menu_handlers.checkout(update, context)

		# check that the callbackquery.answer() was called only once with no arguments
		# ** query.answer() is just a method that acknowledges a button click. (Stop Tele loading state)
		query.answer.assert_awaited_once_with()
		# check that the edited message text contains...
		kwargs = query.edit_message_text.await_args.kwargs
		self.assertIn("Checkout", kwargs["text"])
		self.assertIn("Chicken Chop", kwargs["text"])
		self.assertIn("Pasta", kwargs["text"])
		self.assertIn("Total: $19.0", kwargs["text"])
		self.assertEqual(inline_texts(kwargs["reply_markup"]), [["Place Order"], ["Cancel"]])

	# test that back callback returns user to vendor selection
	async def test_back_returns_to_vendor_selection(self):
		query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
		update = SimpleNamespace(callback_query=query)

		with patch("handlers.menu.get_vendors", return_value=VENDORS) as mocked_get_vendors, patch(
			"handlers.menu.vendor_keyboard", return_value="vendor_markup"
		) as mocked_vendor_keyboard:
			await menu_handlers.back(update, SimpleNamespace())

		query.answer.assert_awaited_once_with()
		mocked_get_vendors.assert_called_once_with()
		mocked_vendor_keyboard.assert_called_once_with(VENDORS)
		query.edit_message_text.assert_awaited_once_with(text="Choose a vendor: ", reply_markup="vendor_markup")

	# test that place_order clears cart and sends order confirmation message
	async def test_place_order_clears_cart_and_confirms(self):
		query = SimpleNamespace(answer=AsyncMock(), edit_message_text=AsyncMock())
		update = SimpleNamespace(callback_query=query)
		context = make_context([{"food": VENDORS[1]["foods"][0], "quantity": 2}])

		await menu_handlers.place_order(update, context)

		query.answer.assert_awaited_once_with()
		self.assertEqual(context.user_data["cart"], [])
		query.edit_message_text.assert_awaited_once_with("Your order has been placed")


if __name__ == "__main__":
	unittest.main()
