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
