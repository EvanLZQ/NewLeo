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
    """POST multipart `file` → the stored upload (id, url, name, type, size).

    The id is what the cart item sends back as `prescription_upload`.
    """
    upload = request.FILES.get('file')
    try:
        content_type = validate_upload(upload)
    except UploadRejected as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    record = PrescriptionUpload(
        customer=request.user if request.user.is_authenticated else None,
        original_name=(upload.name or "")[:255],
        content_type=content_type,
        size=upload.size,
    )
    record.file.save(upload.name, upload, save=False)
    record.save()
    return Response(PrescriptionUploadSerializer(record).data, status=status.HTTP_201_CREATED)
