"""Who may touch a cart item (CompleteSet) or a prescription upload.

Security fix, 2026-11-11 (PR #6 acceptance blocker): cart item ids are
sequential, and the old check let *anyone* read, change or delete any item
that was not yet on an order. Ownership is now explicit:

Signed-in customer U owns CompleteSet S when
  * S is in U's shopping cart, or
  * S is on one of U's orders, or
  * S is not on an order and was created by U (``created_by``), or
  * S is not on an order, has no ``created_by``, and carries this browser
    session's guest token (made while signed out in this same session,
    before it was added to a cart).

A guest (signed-out) session owns S when
  * S is in this session's guest cart (``session['guest_cart_id']``), or
  * S is not on an order, has no ``created_by``, and carries this session's
    guest token (``session['cart_owner_token']``).

There is deliberately no "anything not on an order" fallback any more.
Callers must answer 404 for anything not owned, so an id can't be
confirmed by counting.
"""
import secrets

from django.db.models import Q

SESSION_TOKEN_KEY = 'cart_owner_token'


def _is_authenticated(request):
    user = getattr(request, 'user', None)
    return bool(user is not None and user.is_authenticated)


def get_guest_token(request, create=False):
    """This browser session's random owner token (never sent to the client;
    it lives server-side in the Django session). ``create=True`` mints one."""
    session = getattr(request, 'session', None)
    if session is None:
        return None
    token = session.get(SESSION_TOKEN_KEY)
    if not token and create:
        token = secrets.token_urlsafe(32)
        session[SESSION_TOKEN_KEY] = token
    return token or None


def owned_complete_sets_q(request):
    """Q filter over CompleteSet for the sets this request may access.
    Returns None when the caller owns nothing at all."""
    token = get_guest_token(request)
    session_q = None
    if token:
        session_q = Q(order__isnull=True, created_by__isnull=True, guest_token=token)

    if _is_authenticated(request):
        user = request.user
        q = Q(order__customer=user) | Q(order__isnull=True, created_by=user)
        if user.shopping_cart_id:
            q |= Q(shoppingcart__id=user.shopping_cart_id)
        if session_q is not None:
            q |= session_q
        return q

    q = None
    guest_cart_id = request.session.get('guest_cart_id') if hasattr(request, 'session') else None
    if guest_cart_id:
        q = Q(shoppingcart__id=guest_cart_id)
    if session_q is not None:
        q = session_q if q is None else (q | session_q)
    return q


def owned_complete_sets(request):
    from .models import CompleteSet
    q = owned_complete_sets_q(request)
    if q is None:
        return CompleteSet.objects.none()
    return CompleteSet.objects.filter(q).distinct()


def get_owned_complete_set(request, set_id):
    """The CompleteSet if this request owns it, else None (caller -> 404)."""
    from .models import CompleteSet
    q = owned_complete_sets_q(request)
    if q is None:
        return None
    pk = owned_complete_sets(request).filter(id=set_id).values_list('id', flat=True).first()
    if pk is None:
        return None
    return CompleteSet.objects.get(pk=pk)


def caller_owns_complete_set(request, set_id):
    return owned_complete_sets(request).filter(id=set_id).exists()


def stamp_new_complete_set(request, complete_set):
    """Record who created a new cart item, so only they can claim it."""
    from .models import CompleteSet
    if _is_authenticated(request):
        fields = {'created_by': request.user, 'guest_token': ''}
    else:
        fields = {'created_by': None, 'guest_token': get_guest_token(request, create=True)}
    CompleteSet.objects.filter(pk=complete_set.pk).update(**fields)
    for key, value in fields.items():
        setattr(complete_set, key, value)


# ── Prescription uploads ─────────────────────────────────────────────────────

def upload_owner_fields(request):
    if _is_authenticated(request):
        return {'customer': request.user, 'guest_token': ''}
    return {'customer': None, 'guest_token': get_guest_token(request, create=True)}


def caller_made_upload(request, upload):
    """True if this request uploaded the file (same account, or same signed-out
    session). This is what allows attaching an upload to a cart item."""
    if upload.customer_id is not None:
        return _is_authenticated(request) and request.user.pk == upload.customer_id
    token = get_guest_token(request)
    return bool(token and upload.guest_token and secrets.compare_digest(token, upload.guest_token))


def caller_can_read_upload(request, upload):
    """Download access: staff, the uploader, or whoever owns a cart item /
    order the file is attached to (e.g. a guest who then signed in)."""
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated and user.is_staff:
        return True
    if caller_made_upload(request, upload):
        return True
    return owned_complete_sets(request).filter(prescription_upload=upload).exists()


# ── Typed prescriptions (PrescriptionInfo) ───────────────────────────────────
#
# Security fix, 2026-11-11 (acceptance follow-up to the cart fix): the
# prescription endpoints treated every row with customer=NULL ("guest Rx") as
# readable, editable and deletable by anyone, and the ids are sequential.
# Same model as the cart now:
#
#   * Staff may access every prescription (detail/batch only; see
#     ``include_staff``).
#   * Signed-in user U owns Rx P when P.customer is U, or P is a guest Rx
#     (customer NULL) that carries this browser session's guest token (typed
#     while signed out in this same session), or P is a guest Rx attached to a
#     cart item / order that U owns.
#   * A guest session owns P when P is a guest Rx carrying this session's
#     guest token, or a guest Rx attached to a cart item this session owns.
#   * Nothing else. Legacy guest rows typed before this fix have no token, so
#     they are reachable only through a cart item / order their owner holds
#     (or by staff). Callers answer 404 for everything not owned.

def _is_staff(request):
    user = getattr(request, 'user', None)
    return bool(user is not None and user.is_authenticated and user.is_staff)


def owned_prescriptions_q(request, include_staff=True):
    """Q over PrescriptionInfo for what this request may access, or None
    when it owns nothing. Staff get an empty Q (everything) when
    ``include_staff``."""
    if include_staff and _is_staff(request):
        return Q()
    q = None
    if _is_authenticated(request):
        q = Q(customer=request.user)
    token = get_guest_token(request)
    if token:
        token_q = Q(customer__isnull=True, guest_token=token)
        q = token_q if q is None else (q | token_q)
    sets_q = owned_complete_sets_q(request)
    if sets_q is not None:
        from .models import CompleteSet
        attached = (CompleteSet.objects.filter(sets_q)
                    .exclude(prescription__isnull=True)
                    .values('prescription_id'))
        via_set_q = Q(customer__isnull=True, id__in=attached)
        q = via_set_q if q is None else (q | via_set_q)
    return q


def owned_prescriptions(request, include_staff=True):
    from Prescription.models import PrescriptionInfo
    q = owned_prescriptions_q(request, include_staff=include_staff)
    if q is None:
        return PrescriptionInfo.objects.none()
    return PrescriptionInfo.objects.filter(q).distinct()


def get_owned_prescription(request, rx_id, include_staff=True):
    """The PrescriptionInfo if this request may access it, else None (the
    caller answers 404 / "not found", same as a missing id)."""
    from Prescription.models import PrescriptionInfo
    try:
        rx_id = int(rx_id)
    except (TypeError, ValueError):
        return None
    pk = (owned_prescriptions(request, include_staff=include_staff)
          .filter(id=rx_id).values_list('id', flat=True).first())
    if pk is None:
        return None
    return PrescriptionInfo.objects.get(pk=pk)


def prescription_owner_fields(request):
    """Owner fields for a new typed prescription: the account, or (signed
    out) this session's guest token, minted if needed."""
    if _is_authenticated(request):
        return {'customer': request.user, 'guest_token': ''}
    return {'customer': None, 'guest_token': get_guest_token(request, create=True)}


# ── Guest wish lists ─────────────────────────────────────────────────────────
# WishList rows have no owner column; a signed-in customer's list is
# CustomerInfo.wish_list. A signed-out visitor's list is bound to the Django
# session when it is created (key below). Anything else answers 404.

SESSION_WISH_LIST_KEY = 'guest_wish_list_id'


def caller_owns_wish_list(request, list_id):
    if _is_staff(request):
        return True
    try:
        list_id = int(list_id)
    except (TypeError, ValueError):
        return False
    if _is_authenticated(request) and request.user.wish_list_id == list_id:
        return True
    session = getattr(request, 'session', None)
    return bool(session is not None and session.get(SESSION_WISH_LIST_KEY) == list_id)
