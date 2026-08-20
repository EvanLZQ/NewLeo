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
    LensReaderStrength,
)
from .serializers import NextStepRequestSerializer
from Prescription.models import PrescriptionInfo

STEP_LABELS = {
    "LENS_TYPE": "Lens Type",
    "FUNCTION": "Lens Function",
    "TINT_TYPE": "Tint Type",
    "COLOR": "Color",
    "INDEX": "Lens Index",
    "COATING": "Coating",
    "READER_STRENGTH": "Reader Strength",
}

DOES_NOT_EXIST_ERRORS = (
    LensType.DoesNotExist, LensFunctionPath.DoesNotExist,
    LensIndexOption.DoesNotExist, LensColorOption.DoesNotExist,
    LensCoating.DoesNotExist, LensReaderStrength.DoesNotExist,
)


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


def _safe_parse(raw_value):
    try:
        return _parse_int_list(raw_value)
    except ValueError:
        return []


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
        metadata={
            "is_prescription_required": lens_type.is_prescription_required,
            "is_reader": lens_type.is_reader,
        },
    )


def _function_option(function_path):
    """The Step-2 button for a whole function_code group (may stand in for
    the SUN function_code's tint-type siblings)."""
    return _option_dict(
        id=function_path.id, code=function_path.function_code, name=function_path.function_label,
        option_type="FUNCTION", price=function_path.extra_price,
        description=function_path.function_description,
        metadata={"color_required": function_path.color_required},
    )


def _tint_type_option(function_path):
    return _option_dict(
        id=function_path.id, code=function_path.sun_type, name=function_path.function_label,
        option_type="TINT_TYPE", price=function_path.extra_price,
        description=function_path.function_description,
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
    """
    Combined power per eye, worse (larger-magnitude) eye wins — matches the
    bracket thresholds in LensIndexRecommendationRule.

    Two different formulas apply depending on that eye's own prescription
    sign (source: the "折射率算法" sheet in Eyelovewear Pricing.xlsx):
      - Nearsighted (sphere < 0):  |sphere| + |cylinder|
      - Farsighted  (sphere >= 0): sphere + cylinder / 2
    Each eye is evaluated by its own sign — correctly handles the rare case
    of one nearsighted eye and one farsighted eye.
    """
    def per_eye(sphere, cylinder):
        sphere = sphere or 0
        cylinder = cylinder or 0
        if sphere < 0:
            return abs(sphere) + abs(cylinder)
        return sphere + cylinder / 2

    left = per_eye(prescription.sphere_l, prescription.cylinder_l)
    right = per_eye(prescription.sphere_r, prescription.cylinder_r)
    return max(left, right)


def _match_recommendation_rule(category, combined_power):
    rules = LensIndexRecommendationRule.objects.filter(
        category=category).order_by("sort_order")
    for rule in rules:
        if rule.max_combined_power is None or combined_power <= rule.max_combined_power:
            return rule
    return None


def _rx_recommendation_rule(lens_type, prescription_id):
    """The LensIndexRecommendationRule matching this lens_type + prescription,
    or None when no filtering applies (Non-Rx, no category configured on this
    lens_type, or no prescription supplied/found). Shared by the COLOR step
    (to pre-filter by availability) and the INDEX step (to narrow + flag the
    recommended option) so both agree on the same allowed bracket."""
    category = lens_type.index_recommendation_category
    if not category or not prescription_id:
        return None
    try:
        prescription = PrescriptionInfo.objects.get(id=prescription_id)
    except PrescriptionInfo.DoesNotExist:
        return None
    return _match_recommendation_rule(category, _combined_power(prescription))


def _color_option_dict(color_option):
    return _option_dict(
        id=color_option.id, code=color_option.color_name, name=color_option.color_name,
        option_type="COLOR", price=color_option.extra_price,
    )


def _coating_option_dict(coating):
    return _option_dict(
        id=coating.id, code=coating.code, name=coating.label,
        option_type="COATING", price=coating.price, description=coating.description,
        metadata={
            "is_recommended": coating.is_recommended,
            "is_included": coating.is_included,
            "exclusive_group": coating.exclusive_group,
        },
    )


def _reader_strength_option(strength):
    return _option_dict(
        id=strength.id, code=strength.label, name=strength.label,
        option_type="READER_STRENGTH", price=strength.price,
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

    Two flows:
      - Normal: LENS_TYPE -> FUNCTION -> [TINT_TYPE, Sun only] -> COLOR
        (conditional) -> INDEX -> COATING.
      - Reader: LENS_TYPE -> READER_STRENGTH -> complete. No Function,
        Tint, Color, Material, or Coating choice — see LensType.is_reader.

    There's no separate "pick Solid vs Polarized/Mirrored first" step for
    Sun beyond the Tint Type step itself — each tint (Solid/Gradient/
    Mirrored/Polarized) is its own priced LensFunctionPath sibling, and
    picking one resolves which sibling's colors and index pricing apply
    from there on.

    COATING is multi-select (any combination, except at most one of a
    given exclusive_group — e.g. Oleophobic/Hydrophobic) and is submitted
    differently from every other step — see selected_option_ids below.

    GET params:
      - current_step_code: LENS_TYPE / FUNCTION / TINT_TYPE / COLOR / INDEX
                            / COATING / READER_STRENGTH
      - selected_option_id: int — the id picked on current_step_code.
                            Required for every step except COATING.
      - selected_option_ids: comma-separated ints — COATING only. May be
                            empty (picking none of the optional add-ons is
                            valid).
      - selection_path: comma-separated ids (optional)
      - prescription_id: int (optional; only used when transitioning into INDEX)
    """

    def get(self, request):
        serializer = NextStepRequestSerializer(data={
            "current_step_code": request.query_params.get("current_step_code"),
            "selected_option_id": request.query_params.get("selected_option_id"),
            "selected_option_ids": _safe_parse(request.query_params.get("selected_option_ids", "")),
            "selection_path": _safe_parse(request.query_params.get("selection_path", "")),
            "prescription_id": request.query_params.get("prescription_id") or None,
        })
        if not serializer.is_valid():
            return Response({"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        current_step_code = data["current_step_code"]
        selection_path = data["selection_path"]
        prescription_id = data.get("prescription_id")

        if current_step_code == "COATING":
            selected_ids = data.get("selected_option_ids") or []
            updated_path = selection_path + [
                i for i in selected_ids if i not in selection_path]
            return self._after_coating(selected_ids, updated_path)

        selected_option_id = data["selected_option_id"]
        updated_path = (
            selection_path if selected_option_id in selection_path
            else [*selection_path, selected_option_id]
        )

        handler = {
            "LENS_TYPE": self._after_lens_type,
            "FUNCTION": self._after_function,
            "TINT_TYPE": self._after_tint_type,
            "COLOR": self._after_color,
            "INDEX": self._after_index,
            "READER_STRENGTH": self._after_reader_strength,
        }[current_step_code]

        try:
            return handler(selected_option_id, updated_path, prescription_id)
        except DOES_NOT_EXIST_ERRORS:
            return Response(
                {"detail": f"Selected option id={selected_option_id} not found for step {current_step_code}."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def _after_lens_type(self, selected_option_id, path, prescription_id):
        lens_type = LensType.objects.get(id=selected_option_id, is_active=True)

        if lens_type.is_reader:
            return self._enter_reader_strength_step(path)

        # Group function paths by function_code — one representative row per
        # group is shown as the Step-2 button (Postgres-only: distinct(*fields)).
        function_paths = (
            LensFunctionPath.objects.filter(
                lens_type=lens_type, is_active=True)
            .order_by("function_code", "sort_order", "id")
            .distinct("function_code")
        )
        return _step_response("FUNCTION", [_function_option(fp) for fp in function_paths], path)

    def _enter_reader_strength_step(self, path):
        strengths = LensReaderStrength.objects.filter(
            is_active=True).order_by("sort_order", "id")
        return _step_response(
            "READER_STRENGTH", [_reader_strength_option(s) for s in strengths], path)

    def _after_reader_strength(self, selected_option_id, path, prescription_id):
        LensReaderStrength.objects.get(id=selected_option_id, is_active=True)
        # No Function/Tint/Color/Material/Coating choice for a readymade
        # reader — straight to complete.
        return _step_response("READER_STRENGTH", [], path, is_complete=True)

    def _after_function(self, selected_option_id, path, prescription_id):
        clicked = LensFunctionPath.objects.get(
            id=selected_option_id, is_active=True)

        if clicked.function_code == LensFunctionPath.FunctionCode.SUN:
            return self._enter_tint_type_step(clicked, path)

        if not clicked.color_required:
            return self._enter_index_step(clicked, path, prescription_id)

        # Photochromic (or any future color_required, non-Sun function):
        # colors scoped directly to this one function_path — Sun is the
        # only function_code with siblings, disambiguated by Tint Type.
        return self._enter_color_step(clicked, path, prescription_id)

    def _enter_tint_type_step(self, clicked_sun_function_path, path):
        siblings = LensFunctionPath.objects.filter(
            lens_type=clicked_sun_function_path.lens_type,
            function_code=LensFunctionPath.FunctionCode.SUN,
            is_active=True,
        ).exclude(sun_type="").order_by("sort_order", "id")
        return _step_response("TINT_TYPE", [_tint_type_option(fp) for fp in siblings], path)

    def _after_tint_type(self, selected_option_id, path, prescription_id):
        clicked = LensFunctionPath.objects.get(
            id=selected_option_id, is_active=True)
        return self._enter_color_step(clicked, path, prescription_id)

    def _enter_color_step(self, function_path, path, prescription_id):
        color_options = list(
            LensColorOption.objects.filter(
                function_path=function_path, is_active=True
            ).order_by("sort_order", "id")
        )

        rule = _rx_recommendation_rule(function_path.lens_type, prescription_id)
        if rule is not None:
            # Only offer colors that are actually available at some index
            # value within this prescription's bracket — e.g. SVD's
            # Polarized Green/Brown drop off above 1.61, so they shouldn't
            # appear as a pickable color for a prescription that only
            # qualifies for 1.67/1.74.
            allowed = set(rule.available_index_values)
            color_options = [
                co for co in color_options
                if set(co.available_index_values) & allowed
            ]

        return _step_response("COLOR", [_color_option_dict(co) for co in color_options], path)

    def _after_color(self, selected_option_id, path, prescription_id):
        color_option = LensColorOption.objects.select_related("function_path").get(
            id=selected_option_id, is_active=True)
        return self._enter_index_step(
            color_option.function_path, path, prescription_id,
            color_available_index_values=color_option.available_index_values,
        )

    def _enter_index_step(self, function_path, path, prescription_id, color_available_index_values=None):
        # Index/Material is scoped to Lens Type, not Function Path — the
        # same list and prices apply no matter which Function got picked.
        index_options = list(
            LensIndexOption.objects.filter(
                lens_type=function_path.lens_type, is_active=True
            ).order_by("sort_order", "id")
        )

        rule = _rx_recommendation_rule(function_path.lens_type, prescription_id)
        allowed = set(rule.available_index_values) if rule is not None else None
        recommended_value = rule.recommended_index_value if rule is not None else None

        if color_available_index_values is not None:
            # Narrow further to whichever index values the chosen color is
            # actually offered at (e.g. picking Polarized Green means only
            # 1.56/1.61 remain, even if the prescription bracket also allows
            # 1.67).
            color_allowed = set(color_available_index_values)
            allowed = color_allowed if allowed is None else (allowed & color_allowed)

        if allowed is not None:
            index_options = [
                io for io in index_options if str(io.index_value) in allowed]

        option_dicts = [
            _index_option_dict(
                io, is_recommended=(recommended_value is not None
                                     and str(io.index_value) == recommended_value))
            for io in index_options
        ]

        return _step_response("INDEX", option_dicts, path)

    def _after_index(self, selected_option_id, path, prescription_id):
        LensIndexOption.objects.get(id=selected_option_id, is_active=True)
        # Color (when needed) already happened before Index now, so Index
        # always leads straight to Coating.
        return self._enter_coating_step(path)

    def _enter_coating_step(self, path):
        # Every active coating is returned — both the always-included ones
        # (Anti-scratch/Anti-glare/UV-protection) and the pickable add-ons.
        # metadata.is_included tells the frontend which is which; the
        # included ones are shown as static "already included" text, not a
        # choice — see _after_coating for the corresponding server-side
        # rejection if one is submitted as if it were a selection.
        coatings = LensCoating.objects.filter(
            is_active=True).order_by("sort_order", "id")
        return _step_response("COATING", [_coating_option_dict(c) for c in coatings], path)

    def _after_coating(self, selected_ids, path):
        selected_ids = list(dict.fromkeys(selected_ids))  # de-dupe, keep order
        coatings = list(LensCoating.objects.filter(
            id__in=selected_ids, is_active=True))

        found_ids = {c.id for c in coatings}
        missing = [i for i in selected_ids if i not in found_ids]
        if missing:
            return Response(
                {"detail": f"Coating id(s) not found or inactive: {missing}."},
                status=status.HTTP_404_NOT_FOUND,
            )

        for c in coatings:
            if c.is_included:
                return Response(
                    {"detail": f"'{c.label}' is already included with every lens — "
                               "it can't be submitted as a selection."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        seen_groups = {}
        for c in coatings:
            if not c.exclusive_group:
                continue
            if c.exclusive_group in seen_groups:
                return Response(
                    {"detail": f"'{c.label}' and '{seen_groups[c.exclusive_group]}' "
                               "can't both be selected."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            seen_groups[c.exclusive_group] = c.label

        return _step_response("COATING", [], path, is_complete=True)


class LensWorkflowSummaryView(APIView):
    """
    Optional helper endpoint: given one id per resolved step, return the
    resolved objects + total add-on price.

    Not currently called by the frontend (kept for parity/debugging).

    GET params:
      - lens_type_id, function_path_id, index_option_id: required
      - color_option_id: optional
      - coating_ids: optional, comma-separated (coatings are multi-select)
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
        coating_ids = _safe_parse(request.query_params.get("coating_ids", ""))

        try:
            lens_type = LensType.objects.get(id=lens_type_id)
            function_path = LensFunctionPath.objects.get(
                id=function_path_id)
            index_option = LensIndexOption.objects.get(id=index_option_id)
            color_option = (
                LensColorOption.objects.get(id=int(color_option_id))
                if color_option_id else None
            )
            coatings = list(LensCoating.objects.filter(id__in=coating_ids))
            if len(coatings) != len(set(coating_ids)):
                raise LensCoating.DoesNotExist
        except DOES_NOT_EXIST_ERRORS as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)

        total = (
            function_path.extra_price
            + index_option.price
            + (color_option.extra_price if color_option else Decimal("0.00"))
            + sum((c.price for c in coatings), Decimal("0.00"))
        )

        selected = [_lens_type_option(lens_type), _function_option(
            function_path), _index_option_dict(index_option)]
        if color_option:
            selected.append(_color_option_dict(color_option))
        selected.extend(_coating_option_dict(c) for c in coatings)

        return Response({
            "selected_options": selected,
            "total_add_on_price": str(total),
            "missing_option_ids": [],
        }, status=status.HTTP_200_OK)
