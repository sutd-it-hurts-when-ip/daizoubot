import re
import unittest
from types import SimpleNamespace

from hypothesis import given, settings, strategies as st

from handlers.router import _parse_register_payload
from services.cart_service import add_to_cart, cart_item_count, cart_total, format_cart, get_cart, remove_from_cart
from services.user_service import is_valid_student_id


class FuzzUserValidationTests(unittest.TestCase):
    # fuzz tests for user validation functions
    @settings(max_examples=200, deadline=None)
    @given(st.text()) 
    # verify student ID matches regex pattern 
    def test_is_valid_student_id_matches_regex_for_strings(self, s):
        expected = bool(re.fullmatch(r"\d{7}", s.strip()))
        self.assertEqual(is_valid_student_id(s), expected)

    @settings(max_examples=120, deadline=None)
    @given( # given input is ...
        st.one_of(
            st.none(), # None
            st.integers(), # integers
            st.floats(allow_nan=True, allow_infinity=True), # floats
            st.booleans(), # bools
            st.lists(st.integers()), # list of integers
            st.dictionaries(st.text(min_size=1, max_size=3), st.integers(), max_size=3), # dicts
        )
    )
    # verify student ID rejects 
    def test_is_valid_student_id_rejects_non_strings(self, x):
        self.assertFalse(is_valid_student_id(x))


class FuzzRegisterParserTests(unittest.TestCase):
    @settings(max_examples=200, deadline=None)
    @given( # given :
        text=st.text(), # text input, username and first name opotional, uid is an int between 1 and 1 mil
        username=st.one_of(st.none(), st.text(max_size=20)), # username & first_name nullable, max 20 chars
        first_name=st.one_of(st.none(), st.text(max_size=20)),
        uid=st.integers(min_value=1, max_value=1_000_000),
    )
    # verify function never throws. Invalid inputs return None and are handled in later functions gracefully.
    def test_parse_register_payload_never_throws(self, text, username, first_name, uid):
        user = SimpleNamespace(username=username, first_name=first_name, id=uid) # create mock user object
        username_out, student_id_out = _parse_register_payload(text, user)

        # verify output from helper function
        self.assertTrue(username_out is None or isinstance(username_out, str))
        self.assertTrue(student_id_out is None or isinstance(student_id_out, str))

    @settings(max_examples=120, deadline=None)
    @given(
        # username and sid must be alphanumeric and 1-12 chars long
        uname=st.from_regex(r"[A-Za-z0-9_]{1,12}", fullmatch=True),
        sid=st.from_regex(r"[A-Za-z0-9_]{1,12}", fullmatch=True),
    )
    def test_parse_register_payload_extracts_first_two_tokens(self, uname, sid):
        text = f"Register {uname} {sid} extra tokens are ignored abcdefg ZUTOMAYO"
        # extract uname + sid, no Telegram user fallback
        username_out, student_id_out = _parse_register_payload(text, None)
        self.assertEqual(username_out, uname) # ensure parsing works correctly
        self.assertEqual(student_id_out, sid)


class FuzzCartInvariantTests(unittest.TestCase):
    def _ctx(self):
        return SimpleNamespace(user_data={})

    @settings(max_examples=120, deadline=None)
    @given(
        ids=st.lists(st.integers(min_value=1, max_value=12), min_size=1, max_size=40), # create list of food IDs between
        # 1 and 12, where list length between 1 and 40. 
        # Price of each food item dynamically created between 0 and 30, 12 prices in total. (min=max=12)
        prices=st.lists(st.floats(min_value=0.0, max_value=30.0, allow_nan=False, allow_infinity=False), min_size=12, max_size=12),
    )
    def test_add_to_cart_preserves_count_and_total(self, ids, prices):
        ctx = self._ctx() # defined above (mock context object with user_data dict)
        expected_total = 0.0
        price_by_id = {i + 1: float(prices[i]) for i in range(12)} # set prices 1:price1, 2:price2

        for food_id in ids: # loop through each food ID, add to cart and calculate total expected price
            price = price_by_id[food_id] # currentl testing single price
            expected_total += price
            add_to_cart(ctx, {"id": food_id, "name": f"f{food_id}", "price": price})

        self.assertEqual(cart_item_count(ctx), len(ids))
        self.assertAlmostEqual(cart_total(ctx), expected_total, places=6) # ensure total matches expected total, wwhile accounting for 
        # floating point precision issues.
        self.assertGreaterEqual(len(get_cart(ctx)), 1) # ensure cart not empty

    @settings(max_examples=120, deadline=None)
    @given(
        # how much, how much to remove, price
        qty=st.integers(min_value=1, max_value=20),
        removals=st.integers(min_value=0, max_value=25),
        price=st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    )
    def test_remove_from_cart_never_goes_negative(self, qty, removals, price):
        ctx = self._ctx()
        food = {"id": 99, "name": "food99", "price": float(price)}

        for _ in range(qty): # repeat qty times, add to cart
            add_to_cart(ctx, food)

        for _ in range(removals): # repeat removals times, remove from cart
            remove_from_cart(ctx, food)

        self.assertGreaterEqual(cart_item_count(ctx), 0)
        self.assertGreaterEqual(cart_total(ctx), 0.0)

        for item in get_cart(ctx):
            self.assertGreater(item.get("quantity", 0), 0) # if items remain, qty must stay positive

    @settings(max_examples=100, deadline=None)
    @given(
        ids=st.lists(st.integers(min_value=1, max_value=10), min_size=0, max_size=25),
        price=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    )
    def test_format_cart_never_throws(self, ids, price):
        ctx = self._ctx()
        # fill with random stuff, add to cart, ensure format_cart does't thrwow
        for food_id in ids:
            add_to_cart(ctx, {"id": food_id, "name": f"menu-{food_id}", "price": float(price)})

        rendered = format_cart(ctx)
        # ensure a string of len >0 reetrnd,
        self.assertIsInstance(rendered, str)
        self.assertGreater(len(rendered), 0)


if __name__ == "__main__":
    unittest.main()
