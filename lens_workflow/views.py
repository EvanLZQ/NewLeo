from decimal import Decimal

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    LensType,
    LensFunctionPath,
    LensIndexOption,
    LensColorOption,
    LensCoating,
    LensIndexRecommendationRule,
)
from .serializers import NextStepRequestSerializer
from Prescription.models import PrescriptionInfo

STEP_LABELS = {
    "LENS_TYPE": "Lens Type",
    "FUNCTION": "Lens Function",
    "SUN_TYPE": "Sun Type",
    "INDEX": "Lens Index",
    "COLOR": "Color",
    "COATING": "Coating",
}

SUN_TYPE_LABELS = dict(LensFunctionPath.SunType.choices)


def _parse_int_list(raw_value):
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


def _step_dict(code):
    return {
        "id": 0,
        "code": code,
        "label": STEP_LABELS[code],
        "description": "",
        "sort_order": 0,
        "is_active": True,
    }


def _option_dict(*, id, code, name, option_type, price, description="", metadata=None):
    return {
        "id": id,
        "code": code,
        "name": name,
        "option_type": option_type,
        "description": description,
        "add_on_price": str(price),
        "image_url": "",
        "metadata": metadata or {},
        "sort_order": 0,
        "is_active": True,
    }


def _lens_type_option(lens_type):
    return _option_dict(
        id=lens_type.id, code=lens_type.code, name=lens_type.label,
        option_type="LENS_TYPE", price=Decimal("0.00"),
        description=lens_type.description,
        metadata={"is_prescription_required": lens_type.is_prescription_required},
    )


def _function_option(function_path):
    """The Step-2 button for a whole function_code group (may stand in for >1 sun_type row)."""
    return _option_dict(
        id=function_path.id, code=function_path.function_code, name=function_path.function_label,
        option_type="FUNCTION", price=function_path.extra_price,
        description=function_path.function_description,
        metadata={"color_required": function_path.color_required},
    )


def _sun_type_option(function_path):
    return _option_dict(
        id=function_path.id, code=function_path.sun_type,
        name=SUN_TYPE_LABELS.get(function_path.sun_type, function_path.sun_type),
        option_type="SUN_TYPE", price=Decimal("0.00"),
        metadata={"color_required": function_path.color_required},
    )


def _index_option_dict(index_option, is_recommended=False):
    return _option_dict(
        id=index_option.id, code=index_option.option_label, name=index_option.option_label,
        option_type="INDEX", price=index_option.price,
        metadata={
            "tier": index_option.tier,
            "index_value": str(index_option.index_value),
            "is_recommended": is_recommended,
        },
    )


def _combined_power(prescription):
    """|sphere|+|cylinder| per eye, worse (larger) eye wins — matches the
    bracket thresholds in LensIndexRecommendationRule."""
    left = abs(prescription.sphere_l or 0) + abs(prescription.cylinder_l or 0)
    right = abs(prescription.sphere_r or 0) + abs(prescription.cylinder_r or 0)
    return max(left, right)


def _match_recommendation_rule(category, combined_power):
    rules = LensIndexRecommendationRule.objects.filter(
        category=category).order_by("sort_order")
    for rule in rules:
        if rule.max_combined_power is None or combined_power <= rule.max_combined_power:
            return rule
    return None


def _color_option_dict(color_option):
    return _option_dict(
        id=color_option.id, code=color_option.color_name, name=color_option.color_name,
        option_type="COLOR", price=color_option.extra_price,
    )


def _coating_option_dict(coating):
    return _option_dict(
        id=coating.id, code=coating.code, name=coating.label,
        option_type="COATING", price=coating.price, description=coating.description,
        metadata={"is_recommended": coating.is_recommended},
    )


def _step_response(step_code, option_dicts, selection_path, is_complete=False):
    return Response({
        "current_step": None if is_complete else _step_dict(step_code),
        "options": [] if is_complete else option_dicts,
        "selection_path": selection_path,
        "is_complete": is_complete,
    }, status=status.HTTP_200_OK)


class LensWorkflowStartView(APIView):
    """Step 1: return every active Lens Type."""

    def get(self, request):
        lens_types = LensType.objects.filter(
            is_active=True).order_by("sort_order", "id")
        if not lens_types.exists():
            return Response(
                {"detail": "No active lens types configured."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({
            "current_step": _step_dict("LENS_TYPE"),
            "options": [_lens_type_option(lt) for lt in lens_types],
            "selection_path": [],
        }, status=status.HTTP_200_OK)


class LensWorkflowNextView(APIView):
    """
    Given the option selected while on `current_step_code`, resolve and
    return the next step's options.

    GET params:
      - current_step_code: LENS_TYPE / FUNCTION / SUN_TYPE / INDEX / COLOR / COATING
      - selected_option_id: int (the id of the option picked on current_step_code)
      - selection_path: comma-separated ids (optional)
      - prescription_id: int (optional; only used when transitioning into INDEX)
    """

    def get(self, request):
        serializer = NextStepRequestSerializer(data={
            "current_step_code": request.query_params.get("current_step_code"),
            "selected_option_id": request.query_params.get("selected_option_id"),
            "selection_path": _safe_parse(request.query_params.get("selection_path", "")),
            "prescription_id": request.query_params.get("prescription_id") or None,
        })
        if not serializer.is_valid():
            return Response({"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        current_step_code = data["current_step_code"]
        selected_option_id = data["selected_option_id"]
        selection_path = data["selection_path"]
        prescription_id = data.get("prescription_id")
        updated_path = (
            selection_path if selected_option_id in selection_path
            else [*selection_path, selected_option_id]
        )

        handler = {
            "LENS_TYPE": self._after_lens_type,
            "FUNCTION": self._after_function,
            "SUN_TYPE": self._after_sun_type,
            "INDEX": self._after_index,
            "COLOR": self._after_color,
            "COATING": self._after_coating,
        }[current_step_code]

        try:
            return handler(selected_option_id, updated_path, prescription_id)
        except (LensType.DoesNotExist, LensFunctionPath.DoesNotExist,
                LensIndexOption.DoesNotExist, LensColorOption.DoesNotExist, LensCoating.DoesNotExist):
            return Response(
                {"detail": f"Selected option id={selected_option_id} not found for step {current_step_code}."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def _after_lens_type(self, selected_option_id, path, prescription_id):
        lens_type = LensType.objects.get(id=selected_option_id, is_active=True)
        # Group function paths by function_code — one representative row per
        # group is shown as the Step-2 button (Postgres-only: distinct(*fields)).
        function_paths = (
            LensFunctionPath.objects.filter(
                lens_type=lens_type, is_active=True)
            .order_by("function_code", "sort_order", "id")
            .distinct("function_code")
        )
        return _step_response("FUNCTION", [_function_option(fp) for fp in function_paths], path)

    def _after_function(self, selected_option_id, path, prescription_id):
        clicked = LensFunctionPath.objects.get(
            id=selected_option_id, is_active=True)
        siblings = list(
            LensFunctionPath.objects.filter(
                lens_type=clicked.lens_type,
                function_code=clicked.function_code,
                is_active=True,
            ).order_by("sort_order", "id")
        )
        if len(siblings) > 1:
            return _step_response("SUN_TYPE", [_sun_type_option(fp) for fp in siblings], path)
        return self._enter_index_step(clicked, path, prescription_id)

    def _after_sun_type(self, selected_option_id, path, prescription_id):
        resolved = LensFunctionPath.objects.get(
            id=selected_option_id, is_active=True)
        return self._enter_index_step(resolved, path, prescription_id)

    def _enter_index_step(self, function_path, path, prescription_id):
        index_options = list(
            LensIndexOption.objects.filter(
                function_path=function_path, is_active=True
            ).order_by("sort_order", "id")
        )

        rule = None
        category = function_path.lens_type.index_recommendation_category
        if category and prescription_id:
            try:
                prescription = PrescriptionInfo.objects.get(id=prescription_id)
            except PrescriptionInfo.DoesNotExist:
                prescription = None
            if prescription is not None:
                rule = _match_recommendation_rule(
                    category, _combined_power(prescription))

        if rule is not None:
            # Narrow to only the index values this prescription bracket
            # allows, and flag the recommended one.
            index_options = [
                io for io in index_options
                if str(io.index_value) in rule.available_index_values
            ]
            option_dicts = [
                _index_option_dict(
                    io, is_recommended=str(io.index_value) == rule.recommended_index_value)
                for io in index_options
            ]
        else:
            # Non-Rx, no category configured, or no prescription supplied —
            # show everything, nothing flagged as recommended.
            option_dicts = [_index_option_dict(io) for io in index_options]

        return _step_response("INDEX", option_dicts, path)

    def _after_index(self, selected_option_id, path, prescription_id):
        index_option = LensIndexOption.objects.select_related("function_path").get(
            id=selected_option_id, is_active=True)
        if index_option.function_path.color_required:
            color_options = LensColorOption.objects.filter(
                index_option=index_option, is_active=True
            ).order_by("sort_order", "id")
            return _step_response("COLOR", [_color_option_dict(co) for co in color_options], path)
        return self._enter_coating_step(path)

    def _after_color(self, selected_option_id, path, prescription_id):
        LensColorOption.objects.get(id=selected_option_id, is_active=True)
        return self._enter_coating_step(path)

    def _enter_coating_step(self, path):
        coatings = LensCoating.objects.filter(
            is_active=True).order_by("sort_order", "id")
        return _step_response("COATING", [_coating_option_dict(c) for c in coatings], path)

    def _after_coating(self, selected_option_id, path, prescription_id):
        LensCoating.objects.get(id=selected_option_id, is_active=True)
        return _step_response("COATING", [], path, is_complete=True)


def _safe_parse(raw_value):
    try:
        return _parse_int_list(raw_value)
    except ValueError:
        return []


class LensWorkflowSummaryView(APIView):
    """
    Optional helper endpoint: given one id per step (in step order:
    lens_type, function_path, [sun_type reuses function_path], index_option,
    [color_option], coating), return the resolved objects + total add-on price.

    Not currently called by the frontend (kept for parity/debugging).

    GET params:
      - lens_type_id, function_path_id, index_option_id: required
      - color_option_id, coating_id: optional
    """

    def get(self, request):
        try:
            lens_type_id = int(request.query_params.get("lens_type_id"))
            function_path_id = int(
                request.query_params.get("function_path_id"))
            index_option_id = int(
                request.query_params.get("index_option_id"))
        except (TypeError, ValueError):
            return Response(
                {"detail": "lens_type_id, function_path_id and index_option_id are required integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        color_option_id = request.query_params.get("color_option_id")
        coating_id = request.query_params.get("coating_id")

        try:
            lens_type = LensType.objects.get(id=lens_type_id)
            function_path = LensFunctionPath.objects.get(
                id=function_path_id)
            index_option = LensIndexOption.objects.get(id=index_option_id)
            color_option = (
                LensColorOption.objects.get(id=int(color_option_id))
                if color_option_id else None
            )
            coating = (
                LensCoating.objects.get(id=int(coating_id))
                if coating_id else None
            )
        except (LensType.DoesNotExist, LensFunctionPath.DoesNotExist,
                LensIndexOption.DoesNotExist, LensColorOption.DoesNotExist, LensCoating.DoesNotExist) as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)

        total = (
            function_path.extra_price
            + index_option.price
            + (color_option.extra_price if color_option else Decimal("0.00"))
            + (coating.price if coating else Decimal("0.00"))
        )

        selected = [_lens_type_option(lens_type), _function_option(
            function_path), _index_option_dict(index_option)]
        if color_option:
            selected.append(_color_option_dict(color_option))
        if coating:
            selected.append(_coating_option_dict(coating))

        return Response({
            "selected_options": selected,
            "total_add_on_price": str(total),
            "missing_option_ids": [],
        }, status=status.HTTP_200_OK)
