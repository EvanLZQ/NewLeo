from decimal import Decimal

from django.db.models import Prefetch
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LensStep, LensOption, LensStepRule, LensOptionAvailability
from .serializers import (
    LensStepSerializer,
    LensOptionSerializer,
    NextStepRequestSerializer,
    SelectionSummaryRequestSerializer,
)


class LensWorkflowStartView(APIView):
    """
    Returns the first active step and its available options.

    Usually the first step is COLOR_TYPE.
    """

    def get(self, request):
        first_step = (
            LensStep.objects.filter(is_active=True)
            .order_by("sort_order", "id")
            .first()
        )

        if not first_step:
            return Response(
                {"detail": "No active lens workflow steps configured."},
                status=status.HTTP_404_NOT_FOUND,
            )

        options = (
            LensOption.objects.filter(
                is_active=True,
                option_type=first_step.code,
            )
            .order_by("sort_order", "id")
        )

        return Response(
            {
                "current_step": LensStepSerializer(first_step).data,
                "options": LensOptionSerializer(options, many=True).data,
                "selection_path": [],
            },
            status=status.HTTP_200_OK,
        )


class LensWorkflowNextView(APIView):
    """
    Given a selected option, return the next step and the valid options for that next step.

    Logic:
    1) Find selected option
    2) Find the active step rule for that selected option
    3) Determine next step from rule
    4) Find child options from LensOptionAvailability(parent=selected)
    5) Filter children so they match next_step.code
    """

    def post(self, request):
        serializer = NextStepRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        selected_option_id = serializer.validated_data["selected_option_id"]
        selection_path = serializer.validated_data.get("selection_path", [])

        try:
            selected_option = LensOption.objects.get(
                id=selected_option_id,
                is_active=True,
            )
        except LensOption.DoesNotExist:
            return Response(
                {"detail": f"Selected option id={selected_option_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Find workflow rule for this selected option
        # We do not require the frontend to send current_step_id; selected_option uniquely maps
        # in this seeded design. If later you add ambiguity, include current_step_id in request.
        rule = (
            LensStepRule.objects.select_related("current_step", "next_step")
            .filter(
                selected_option=selected_option,
                is_active=True,
                current_step__is_active=True,
                next_step__is_active=True,
            )
            .order_by("priority", "id")
            .first()
        )

        # No next step means end of flow
        if not rule:
            # still return updated path so frontend can finalize
            updated_path = self._append_unique(
                selection_path, selected_option.id)
            return Response(
                {
                    "current_step": None,
                    "options": [],
                    "selection_path": updated_path,
                    "is_complete": True,
                    "message": "No next step configured. Flow complete.",
                },
                status=status.HTTP_200_OK,
            )

        next_step = rule.next_step

        # Child options available from selected parent
        availability_qs = (
            LensOptionAvailability.objects.select_related("child_option")
            .filter(
                parent_option=selected_option,
                is_active=True,
                child_option__is_active=True,
                child_option__option_type=next_step.code,
            )
            .order_by("sort_order", "id")
        )

        child_options = [row.child_option for row in availability_qs]

        updated_path = self._append_unique(selection_path, selected_option.id)

        return Response(
            {
                "current_step": LensStepSerializer(next_step).data,
                "options": LensOptionSerializer(child_options, many=True).data,
                "selection_path": updated_path,
                "is_complete": False,
            },
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _append_unique(selection_path, option_id):
        # Keep order, avoid accidental duplicates
        if option_id in selection_path:
            return selection_path
        return [*selection_path, option_id]


class LensWorkflowSummaryView(APIView):
    """
    Optional helper endpoint:
    Given selected option IDs, return selected option details + total add_on_price.
    Useful for final review screen before add-to-cart.
    """

    def post(self, request):
        serializer = SelectionSummaryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        selected_ids = serializer.validated_data["selected_option_ids"]

        options = list(
            LensOption.objects.filter(id__in=selected_ids, is_active=True)
            .order_by("option_type", "sort_order", "id")
        )

        found_ids = {opt.id for opt in options}
        missing_ids = [oid for oid in selected_ids if oid not in found_ids]

        total = Decimal("0.00")
        for opt in options:
            total += opt.add_on_price or Decimal("0.00")

        return Response(
            {
                "selected_options": LensOptionSerializer(options, many=True).data,
                "total_add_on_price": str(total),
                "missing_option_ids": missing_ids,
            },
            status=status.HTTP_200_OK,
        )
