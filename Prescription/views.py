from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from .models import PrescriptionInfo
from .serializer import PrescriptionSerializer


def _can_access_prescription(user, prescription):
    """
    Ownership check — a user may only access a prescription if:
    • they are authenticated AND the prescription belongs to them, OR
    • the prescription is a guest prescription (customer is NULL).
    """
    if prescription.customer is None:
        return True
    return user.is_authenticated and prescription.customer_id == user.pk


@api_view(['GET', 'POST'])
def prescription_list_create(request):
    if request.method == 'GET':
        if request.user.is_authenticated:
            # CustomerInfo IS the user model (AbstractUser) — filter directly
            prescriptions = PrescriptionInfo.objects.filter(
                customer=request.user)
        else:
            prescriptions = PrescriptionInfo.objects.none()
        serializer = PrescriptionSerializer(prescriptions, many=True)
        return Response(serializer.data)

    elif request.method == 'POST':
        serializer = PrescriptionSerializer(data=request.data)
        if serializer.is_valid():
            # Link to the logged-in customer so it appears in their GET list.
            # Guest prescriptions (unauthenticated) are saved with customer=null
            # and retrieved later via the batch endpoint using localStorage IDs.
            if request.user.is_authenticated:
                serializer.save(customer=request.user)
            else:
                serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PATCH', 'DELETE'])
def prescription_detail(request, pk):
    try:
        prescription = PrescriptionInfo.objects.get(pk=pk)
    except PrescriptionInfo.DoesNotExist:
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    # Ownership guard: prevent cross-user access
    if not _can_access_prescription(request.user, prescription):
        return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = PrescriptionSerializer(prescription)
        return Response(serializer.data)

    elif request.method == 'PATCH':
        serializer = PrescriptionSerializer(
            prescription, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        prescription.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
def fetch_prescriptions_by_ids_post(request):
    ids = request.data.get('ids')

    if not ids or not isinstance(ids, list):
        return Response(
            {"error": "'ids' must be a non-empty list."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Ownership filter: authenticated users see their own + guest prescriptions;
    # unauthenticated users see only guest (customer=NULL) prescriptions.
    qs = PrescriptionInfo.objects.filter(id__in=ids)
    if request.user.is_authenticated:
        qs = qs.filter(Q(customer=request.user) | Q(customer__isnull=True))
    else:
        qs = qs.filter(customer__isnull=True)

    serializer = PrescriptionSerializer(qs, many=True)
    return Response(serializer.data)


# ── Prescription photo / PDF upload (2026-11-11 QA, issue 1) ─────────────────

from rest_framework.decorators import parser_classes, throttle_classes  # noqa: E402
from rest_framework.parsers import MultiPartParser, FormParser  # noqa: E402
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle  # noqa: E402

from .models import PrescriptionUpload  # noqa: E402
from .serializer import PrescriptionUploadSerializer  # noqa: E402
from .uploads import UploadRejected, validate_upload  # noqa: E402


class _AnonUploadThrottle(AnonRateThrottle):
    scope = "prescription_upload_anon"
    rate = "30/hour"


class _UserUploadThrottle(UserRateThrottle):
    scope = "prescription_upload_user"
    rate = "60/hour"


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
@throttle_classes([_AnonUploadThrottle, _UserUploadThrottle])
def prescription_upload(request):
    """POST multipart `file` → the stored upload (id, name, type, size,
    download_url). No public URL: the file goes to private storage.

    The id is what the cart item sends back as `prescription_upload`. Only
    this account (or this signed-out session) can attach it.
    """
    upload = request.FILES.get('file')
    try:
        content_type = validate_upload(upload)
    except UploadRejected as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    from Order.ownership import upload_owner_fields
    record = PrescriptionUpload(
        **upload_owner_fields(request),
        original_name=(upload.name or "")[:255],
        content_type=content_type,
        size=upload.size,
    )
    record.file.save(upload.name, upload, save=False)
    record.save()
    return Response(PrescriptionUploadSerializer(record).data, status=status.HTTP_201_CREATED)


# ── Authenticated download of a prescription upload ──────────────────────────

from django.http import FileResponse, Http404  # noqa: E402
from rest_framework.decorators import authentication_classes, permission_classes  # noqa: E402
from rest_framework.permissions import AllowAny  # noqa: E402
from rest_framework.authentication import SessionAuthentication  # noqa: E402
from Leoptique.authentication import AccessTokenAuthentication  # noqa: E402

from .uploads import ALLOWED as _ALLOWED_TYPES  # noqa: E402


def _not_found():
    return Response({"error": "Not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@authentication_classes([SessionAuthentication, AccessTokenAuthentication])
@permission_classes([AllowAny])
def prescription_upload_file(request, upload_id):
    """GET → the file, for staff, the uploader (account or the same signed-out
    session), or the owner of a cart item / order it is attached to.
    Everyone else gets 404, the same as for an id that doesn't exist.

    Always sent as an attachment with the stored (sniffed) Content-Type and
    `X-Content-Type-Options: nosniff`, and never cached by shared caches.
    """
    from Order.ownership import caller_can_read_upload
    try:
        upload = PrescriptionUpload.objects.get(pk=upload_id)
    except PrescriptionUpload.DoesNotExist:
        return _not_found()
    if not caller_can_read_upload(request, upload) or not upload.file:
        return _not_found()
    content_type = upload.content_type
    if content_type not in _ALLOWED_TYPES:
        content_type = "application/octet-stream"
    try:
        handle = upload.file.open("rb")
    except (FileNotFoundError, OSError):
        return _not_found()
    ext = _ALLOWED_TYPES.get(content_type, ("",))[0]
    download_name = upload.original_name or f"prescription{ext}"
    response = FileResponse(handle, as_attachment=True, filename=download_name,
                            content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return response
