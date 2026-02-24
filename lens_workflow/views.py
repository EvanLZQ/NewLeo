from decimal import Decimal

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LensStep, LensOption, LensStepRule, LensOptionAvailability
from .serializers import (
    LensStepSerializer,
    LensOptionSerializer,
)


def _parse_int_list(raw_value):
    """
    Parse comma-separated integers from query param string.
    Example: '1,2,3' -> [1, 2, 3]
    """
    if not raw_value:
        return []
    result = []
    for part in str(raw_value).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.append(int(part))
        except ValueError:
            raise ValueError(f"Invalid integer value: '{part}'")
    return result


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

    GET params:
      - selected_option_id: int (required)
      - selection_path: comma-separated ids (optional), e.g. "1,5,9"
    """

    def get(self, request):
        selected_option_id_raw = request.query_params.get("selected_option_id")
        if not selected_option_id_raw:
            return Response(
                {"detail": "selected_option_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_option_id = int(selected_option_id_raw)
        except ValueError:
            return Response(
                {"detail": "selected_option_id must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        selection_path_raw = request.query_params.get("selection_path", "")
        try:
            selection_path = _parse_int_list(selection_path_raw)
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
        if option_id in selection_path:
            return selection_path
        return [*selection_path, option_id]


class LensWorkflowSummaryView(APIView):
    """
    Optional helper endpoint:
    Given selected option IDs, return selected option details + total add_on_price.

    GET params:
      - selected_option_ids: comma-separated ids (required), e.g. "3,10,21,30"
    """

    def get(self, request):
        selected_ids_raw = request.query_params.get("selected_option_ids", "")

        try:
            selected_ids = _parse_int_list(selected_ids_raw)
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not selected_ids:
            return Response(
                {"detail": "selected_option_ids is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
