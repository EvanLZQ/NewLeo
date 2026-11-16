"""Guest "Saved prescriptions" survive a refresh (2026-11-15).

Bug: a guest saved a prescription on the lens page, refreshed, and the saved
list was empty although the row was still in the database. Ownership of a
guest Rx lived only in the Django session; a new visitor's concurrent first
requests each created their own session, the browser kept the last
Set-Cookie, and the Rx stamped with the losing session's token was orphaned.

Fix: the storefront sends a random per-browser token in the ``elw_guest``
cookie (Order/ownership.py). These tests pin down:
  * the exact race above no longer orphans the Rx,
  * the token is stored hashed and never echoed,
  * malformed / short tokens are ignored (old behaviour),
  * another browser (other token, no token, other account) still sees nothing,
  * rows from before the fix (session token) stay visible,
  * cart items and guest checkout ownership work with the token,
  * signing in claims the browser's guest Rx into the account, and nothing
    else's.
"""
import hashlib
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from Order.models import CompleteSet
from Order.ownership import BROWSER_TOKEN_COOKIE
from Order.tests import _frame
from Prescription.models import PrescriptionInfo

User = get_user_model()

TOKEN_A = "A" * 10 + "b-c_d" + "x" * 28          # 43 chars, like the storefront's
TOKEN_B = "Zz0_-" * 8 + "Q" * 3                  # 43 chars, a different browser
RX = dict(sphere_r="-2.00", sphere_l="-2.25", cylinder_r="0", cylinder_l="0",
          axis_r="0", pd_r="31.5", pd_l="31.5", nickname="guest-rx")


def _browser(token=None):
    """A fresh browser (no session cookie yet), optionally with the
    storefront's guest-token cookie."""
    c = APIClient(enforce_csrf_checks=False)
    c.defaults["HTTP_X_FORWARDED_PROTO"] = "https"
    if token is not None:
        c.cookies[BROWSER_TOKEN_COOKIE] = token
    return c


def _save_rx(client, **extra):
    res = client.post("/api/prescriptions/", {**RX, **extra}, format="json")
    assert res.status_code == 201, res.content
    return res.data["id"]


def _batch_ids(client, ids):
    res = client.post("/api/prescriptions/batch", {"ids": ids}, format="json")
    assert res.status_code == 200, res.content
    return [r["id"] for r in res.data]


def _lose_session(client):
    """What the browser does when another response's Set-Cookie replaced the
    session cookie: the next request carries a different (or no) session."""
    client.cookies.pop("sessionid", None)


class GuestRxSurvivesSessionLossTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_rx_still_listed_after_the_session_cookie_is_replaced(self):
        browser = _browser(TOKEN_A)
        rx_id = _save_rx(browser)
        _lose_session(browser)
        # The refresh: the page's guest-cart call starts a brand-new session.
        self.assertEqual(browser.post("/api/order/guest_cart", {"action": "get"},
                                      format="json").status_code, 200)
        self.assertEqual(_batch_ids(browser, [rx_id]), [rx_id])
        self.assertEqual(browser.get(f"/api/prescriptions/{rx_id}").status_code, 200)

    def test_concurrent_first_requests_race(self):
        """Two first requests with no session cookie: one saves the Rx, the
        other fetches the guest cart; the cart's session wins the cookie."""
        rx_req = _browser(TOKEN_A)
        cart_req = _browser(TOKEN_A)
        rx_id = _save_rx(rx_req)
        cart_req.post("/api/order/guest_cart", {"action": "get"}, format="json")
        # The browser now only has the cart request's session cookie.
        self.assertEqual(_batch_ids(cart_req, [rx_id]), [rx_id])

    def test_without_the_token_cookie_the_old_race_still_loses(self):
        """Documents the bug (and that old clients behave exactly as before)."""
        rx_req = _browser()
        cart_req = _browser()
        rx_id = _save_rx(rx_req)
        cart_req.post("/api/order/guest_cart", {"action": "get"}, format="json")
        self.assertEqual(_batch_ids(cart_req, [rx_id]), [])
        self.assertEqual(_batch_ids(rx_req, [rx_id]), [rx_id])

    def test_token_is_stored_hashed_and_never_returned(self):
        browser = _browser(TOKEN_A)
        res = browser.post("/api/prescriptions/", RX, format="json")
        rx = PrescriptionInfo.objects.get(id=res.data["id"])
        self.assertEqual(rx.guest_token, hashlib.sha256(TOKEN_A.encode()).hexdigest())
        self.assertNotIn(TOKEN_A, json.dumps(res.data))
        self.assertNotIn("guest_token", res.data)
        # Not put in the session either: a token-carrying guest does not
        # need one, so saving an Rx does not start a session.
        self.assertNotIn("cart_owner_token", browser.session)


class GuestTokenIsolationTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.owner = _browser(TOKEN_A)
        self.rx_id = _save_rx(self.owner)

    def _assert_hidden(self, client, label):
        self.assertEqual(_batch_ids(client, [self.rx_id]), [], label)
        for method, data in (("get", None), ("patch", {"nickname": "x"}), ("delete", None)):
            res = getattr(client, method)(f"/api/prescriptions/{self.rx_id}", data, format="json")
            self.assertEqual(res.status_code, 404, f"{label} {method}")
        self.assertEqual(PrescriptionInfo.objects.get(id=self.rx_id).nickname, "guest-rx")

    def test_other_browsers_see_nothing(self):
        eve = User.objects.create_user(username="eve@example.com", password="pw-123456")
        signed_in = _browser(TOKEN_B)
        signed_in.force_login(eve)
        for label, client in (("no token", _browser()),
                              ("other token", _browser(TOKEN_B)),
                              ("other signed-in account", signed_in)):
            self._assert_hidden(client, label)

    def test_malformed_tokens_are_ignored(self):
        """Too short, bad characters, or the stored hash itself: never an
        owner token (falls back to the session, which is empty here)."""
        stored = PrescriptionInfo.objects.get(id=self.rx_id).guest_token
        for bad in ("", "short", TOKEN_A[:31], TOKEN_A[:-1] + "!", "A" * 129, stored + "x"):
            self._assert_hidden(_browser(bad), f"token {bad!r}")
        # A malformed token does not stamp rows with it either.
        weak = _browser("abc")
        rx = PrescriptionInfo.objects.get(id=_save_rx(weak))
        self.assertEqual(rx.guest_token, weak.session["cart_owner_token"])

    def test_stored_hash_as_cookie_is_not_the_owner(self):
        stored = PrescriptionInfo.objects.get(id=self.rx_id).guest_token
        self._assert_hidden(_browser(stored), "hash replayed as cookie")

    def test_owner_can_read_edit_delete(self):
        self.assertEqual(self.owner.patch(f"/api/prescriptions/{self.rx_id}",
                                          {"nickname": "mine"}, format="json").status_code, 200)
        _lose_session(self.owner)
        self.assertEqual(self.owner.delete(f"/api/prescriptions/{self.rx_id}").status_code, 204)


class BackwardCompatibilityTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_rows_from_before_the_fix_stay_visible_to_their_session(self):
        browser = _browser()                      # old storefront: no token cookie
        old_id = _save_rx(browser)
        browser.cookies[BROWSER_TOKEN_COOKIE] = TOKEN_A   # new storefront deployed
        new_id = _save_rx(browser)
        self.assertEqual(_batch_ids(browser, [old_id, new_id]), [old_id, new_id])
        new = PrescriptionInfo.objects.get(id=new_id)
        self.assertEqual(new.guest_token, hashlib.sha256(TOKEN_A.encode()).hexdigest())


class GuestCartWithTokenTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.frame = _frame("GRX-FRAME-1", "20.00")

    def test_cart_item_with_rx_and_add_to_cart(self):
        browser = _browser(TOKEN_A)
        rx_id = _save_rx(browser)
        cs = CompleteSet.objects.create(frame=self.frame, prescription_id=rx_id)
        from Order.ownership import stamp_new_complete_set

        class _Req:  # the request the create endpoint would have seen
            COOKIES = {BROWSER_TOKEN_COOKIE: TOKEN_A}
            session = {}
            user = None
        stamp_new_complete_set(_Req, cs)
        self.assertEqual(cs.guest_token, hashlib.sha256(TOKEN_A.encode()).hexdigest())
        _lose_session(browser)
        res = browser.post("/api/order/guest_cart",
                           {"action": "add", "complete_set_id": cs.id}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual([s["id"] if isinstance(s, dict) else s
                          for s in res.data["eyeglasses_set"]], [cs.id])
        # Another browser cannot pull it into its cart.
        other = _browser(TOKEN_B)
        res = other.post("/api/order/guest_cart",
                         {"action": "add", "complete_set_id": cs.id}, format="json")
        self.assertEqual(res.data["eyeglasses_set"], [])


class SignInClaimsGuestRxTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user(username="ann@example.com", password="pw-123456")

    def test_sign_in_lists_this_browsers_guest_rx_only(self):
        browser = _browser(TOKEN_A)
        mine = _save_rx(browser, nickname="mine-as-guest")
        other_guest = _browser(TOKEN_B)
        theirs = _save_rx(other_guest, nickname="someone-else")
        legacy = PrescriptionInfo.objects.create(nickname="legacy", customer=None, guest_token="")

        _lose_session(browser)
        res = browser.post("/api/user/login",
                           {"username": "ann@example.com", "password": "pw-123456"}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        res = browser.get("/api/prescriptions/")
        self.assertEqual([r["id"] for r in res.data], [mine])
        rx = PrescriptionInfo.objects.get(id=mine)
        self.assertEqual((rx.customer_id, rx.guest_token), (self.user.id, ""))
        # Untouched: the other browser's guest Rx and pre-fix rows.
        self.assertIsNone(PrescriptionInfo.objects.get(id=theirs).customer_id)
        self.assertIsNone(PrescriptionInfo.objects.get(id=legacy.id).customer_id)
        self.assertEqual(_batch_ids(other_guest, [theirs]), [theirs])

    def test_session_only_guest_rx_is_claimed_too(self):
        browser = _browser()
        mine = _save_rx(browser)
        browser.post("/api/user/login",
                     {"username": "ann@example.com", "password": "pw-123456"}, format="json")
        self.assertEqual([r["id"] for r in browser.get("/api/prescriptions/").data], [mine])

    def test_signed_in_without_guest_rows_unchanged(self):
        own = PrescriptionInfo.objects.create(nickname="own", customer=self.user)
        c = _browser()
        c.force_login(self.user)
        self.assertEqual([r["id"] for r in c.get("/api/prescriptions/").data], [own.id])

    def test_guest_list_endpoint_still_empty(self):
        browser = _browser(TOKEN_A)
        _save_rx(browser)
        self.assertEqual(browser.get("/api/prescriptions/").data, [])
