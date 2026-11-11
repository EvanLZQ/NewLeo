from decimal import Decimal
from types import SimpleNamespace

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
from .serializers import NextStepRequestSerializer, RxQuoteRequestSerializer
from Prescription.models import PrescriptionInfo
from lens_workflow.pricing import (
    CANONICAL_INDEX_LADDER,
    Eye,
    QuoteError,
    QuoteRequest,
    available_index_labels,
    canonical_index,
    catalog_index_available,
    index_profile,
    neighbor_indexes,
    next_higher_index,
    next_lower_index,
    price_table_loaded,
    prism_requested,
    quote,
    quote_to_dict,
    recommended_canonical_index,
)

_LADDER = set(CANONICAL_INDEX_LADDER)

STEP_LABELS = {
    "LENS_TYPE": "What kind of glasses are you looking for today?",
    "FUNCTION": "Lens Type/Lens Color",
    "TINT_TYPE": "Tint Type",
    "COLOR": "Color",
    "INDEX": "Lens Index",
    "COATING": "Coating",
    "READER_STRENGTH": "Reader Strength",
}

STEP_DESCRIPTIONS = {
    "LENS_TYPE": "Frame selected. Now customize your lenses for this frame.",
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
        "description": STEP_DESCRIPTIONS.get(code, ""),
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


def _index_option_dict(index_option, is_recommended=False, group=None,
                       material=None, abbe_number=None):
    metadata = {
        "tier": index_option.tier,
        "index_value": str(index_option.index_value),
        "is_recommended": bool(is_recommended),
    }
    # Index-step contract. `group` is set only for that menu; summary rows
    # stay the older shape. The same keys are copied into metadata so a
    # client reading either place sees one recommendation.
    extra = {}
    if group is not None:
        extra = {
            "recommended": bool(is_recommended),
            "group": group,
            "material": material or "",
            "abbe_number": abbe_number,
        }
        metadata.update(extra)
    payload = _option_dict(
        id=index_option.id, code=index_option.option_label, name=index_option.option_label,
        option_type="INDEX", price=index_option.price,
        description=index_option.notes,
        metadata=metadata,
    )
    payload.update(extra)
    return payload


def _meridian_power(sphere, cylinder):
    """Largest absolute meridian of one eye. The meridians are S and S+C."""
    sphere = sphere if sphere is not None else Decimal("0")
    cylinder = cylinder if cylinder is not None else Decimal("0")
    return max(abs(sphere), abs(sphere + cylinder))


def _combined_power(prescription):
    """Absolute steep meridian, and which eye produced it.

    Each eye contributes two meridians, S and S+C. The power is the larger
    absolute value. The eye with the higher power decides, so a mild eye
    cannot pull the recommendation down. Returns (power, direction).
    Direction is the winning eye's sphere sign. The brackets themselves
    are the same for both signs; direction is kept so callers that still
    pass it do not change.

    This is not spherical equivalent, and it does not read the price
    sheet's Recommended SE column. Cylinder above 6.00D is still refused
    by quote/checkout ("Max CYL is 6.00D"), not by this function.
    """
    left_power = _meridian_power(prescription.sphere_l, prescription.cylinder_l)
    right_power = _meridian_power(prescription.sphere_r, prescription.cylinder_r)
    if right_power > left_power:
        power = right_power
        sphere = prescription.sphere_r
    else:
        power = left_power
        sphere = prescription.sphere_l
    sphere = sphere if sphere is not None else Decimal("0")
    if sphere < 0:
        direction = LensIndexRecommendationRule.Direction.NEARSIGHTED
    else:
        direction = LensIndexRecommendationRule.Direction.FARSIGHTED
    return power, direction


def _match_recommendation_rule(category, combined_power, direction):
    """Map a steep-meridian power to one recommended index and its neighbors.

    `direction` does not change the bracket. The same table is used for
    every lens category and both signs:

        0.00 to ±2.00 → 1.50
        ±2.25 to ±4.00 → 1.60 (catalog 1.61)
        ±4.25 to ±6.00 → 1.67
        ±6.25 and above → 1.74

    Stored LensIndexRecommendationRule rows mirror this table for the
    admin. They are not read: a stale Recommended SE bracket must not
    win. Returns None when the lens type has no recommendation category.
    """
    del direction
    if not category:
        return None
    recommended = recommended_canonical_index(combined_power)
    return SimpleNamespace(
        recommended_canonical=recommended,
        recommended_index_value=f"{recommended.quantize(Decimal('0.01'))}",
        available_index_values=available_index_labels(recommended),
    )


def _priced_tier(index_options, recommended):
    """Nearest priced rung at or above `recommended`, else the nearest below.

    A high prescription whose 1.74 cell is missing still gets 1.67 when
    that cell exists. Walking only upward used to return an empty menu
    even though a lower index was on the sheet.
    """
    def has(tier):
        return any(canonical_index(io.index_value) == tier for io in index_options)

    tier = recommended
    while tier is not None:
        if has(tier):
            return tier
        tier = next_higher_index(tier)
    tier = next_lower_index(recommended)
    while tier is not None:
        if has(tier):
            return tier
        tier = next_lower_index(tier)
    return None


def _load_prescription(prescription_id):
    if not prescription_id:
        return None
    try:
        return PrescriptionInfo.objects.get(id=prescription_id)
    except PrescriptionInfo.DoesNotExist:
        return None


# A non-prescription lens has no power: every value is 0.00.
_PLANO_PRESCRIPTION = SimpleNamespace(
    sphere_r=Decimal("0"), sphere_l=Decimal("0"),
    cylinder_r=Decimal("0"), cylinder_l=Decimal("0"),
    add_r=Decimal("0"), add_l=Decimal("0"),
    pd_r=Decimal("0"), pd_l=Decimal("0"),
)


def _is_non_rx_lens_type(lens_type):
    return bool(lens_type is not None and not lens_type.is_prescription_required
                and not lens_type.is_reader and lens_type.code != "READER")


def _rx_decimal(value):
    # Decimal("0") is falsy, so `value or 0` would turn a real zero into an
    # int and then break Decimal arithmetic. None is the only empty value.
    return value if value is not None else Decimal("0")


def _index_quote_request(function_path, prescription, index_option, color_option):
    """QuoteRequest for one index, using the same eyes checkout will price."""
    lens_type = function_path.lens_type
    sun_type = function_path.sun_type or ""
    is_reader = bool(lens_type.is_reader or lens_type.code == "READER")
    is_non_rx = bool(not lens_type.is_prescription_required and not is_reader)
    return QuoteRequest(
        od=Eye(
            sph=_rx_decimal(prescription.sphere_r), cyl=_rx_decimal(prescription.cylinder_r),
            add=_rx_decimal(prescription.add_r), pd=_rx_decimal(prescription.pd_r)),
        os=Eye(
            sph=_rx_decimal(prescription.sphere_l), cyl=_rx_decimal(prescription.cylinder_l),
            add=_rx_decimal(prescription.add_l), pd=_rx_decimal(prescription.pd_l)),
        lens_type_code=lens_type.code,
        function_code=function_path.function_code,
        sun_type=sun_type,
        color_name=color_option.color_name if color_option is not None else "",
        index_value=index_option.index_value,
        lens_type=lens_type,
        function_path=function_path,
        tint_type=function_path if sun_type else None,
        color_option=color_option,
        index_option=index_option,
        is_reader=is_reader,
        is_non_rx=is_non_rx,
    )


def _rx_recommendation_rule(lens_type, prescription_id):
    """Steep-meridian bracket for this lens type and prescription, or None.

    None means no filtering (Non-Rx, no category, or no prescription).
    The COLOR step uses `available_index_values` (the neighbor tiers,
    including the 1.61 spelling of 1.60) so a color that exists only at a
    hidden index is not offered.
    """
    category = lens_type.index_recommendation_category
    if not category or not prescription_id:
        return None
    prescription = _load_prescription(prescription_id)
    if prescription is None:
        return None
    combined_power, direction = _combined_power(prescription)
    return _match_recommendation_rule(category, combined_power, direction)


_SELECTION_STEPS = {
    "LENS_TYPE", "FUNCTION", "TINT_TYPE", "COLOR", "INDEX",
    "COATING", "READER_STRENGTH",
}


def _parse_selection_path(raw_value):
    """Parse the ``selection_path`` query param.

    The wire format is plain comma-separated ids (``"1,2,3"``), the same
    as the live frontend sends with ``selection_path.join(",")``. Tagged
    tokens (``"LENS_TYPE:1,FUNCTION:2"``) are also accepted.

    Returns ``(ids, tags)``: ``ids`` is the plain integer path, ``tags``
    is ``{position: step_code}`` for the tokens that carried one. The
    tags are only checked against the server's own step order; the ids
    are what gets stored and returned.
    """
    ids, tags = [], {}
    if not raw_value:
        return ids, tags
    for part in str(raw_value).split(","):
        part = part.strip()
        if not part:
            continue
        step = ""
        id_text = part
        if ":" in part:
            step, _, id_text = part.partition(":")
            step = step.strip().upper()
            if step not in _SELECTION_STEPS:
                raise ValueError(f"Unknown selection step '{step}'.")
        try:
            option_id = int(id_text.strip())
        except ValueError:
            raise ValueError(f"Invalid selection path entry '{part}'.")
        if step:
            tags[len(ids)] = step
        ids.append(option_id)
    return ids, tags


def _selection_steps(path_ids):
    """Which step produced each id in a plain integer ``selection_path``.

    Worked out from the workflow's own step order, not from the ids:
    position 0 is the lens type; position 1 is READER_STRENGTH for a
    reader lens type and FUNCTION otherwise. The FUNCTION row then decides
    the rest (Sun: TINT_TYPE, COLOR, INDEX; color_required: COLOR, INDEX;
    otherwise INDEX). Anything after INDEX is a coating.

    Each id is looked up only in its own step's table. A fresh seed gives
    lens type 1 and Classic function 1, and an index id can equal the
    Blue Light function id; a bare id is never compared across tables.

    An id whose row is gone leaves the steps after it unknown (``""``).
    """
    if not path_ids:
        return []
    steps = ["LENS_TYPE"]
    if len(path_ids) == 1:
        return steps
    lens_type = LensType.objects.filter(pk=path_ids[0]).first()
    if lens_type is not None and lens_type.is_reader:
        sequence = ["READER_STRENGTH"]
    else:
        function = LensFunctionPath.objects.filter(pk=path_ids[1]).first()
        if function is None:
            sequence = ["FUNCTION"]
        elif function.function_code == LensFunctionPath.FunctionCode.SUN:
            sequence = ["FUNCTION", "TINT_TYPE", "COLOR", "INDEX", "COATING"]
        elif function.color_required:
            sequence = ["FUNCTION", "COLOR", "INDEX", "COATING"]
        else:
            sequence = ["FUNCTION", "INDEX", "COATING"]
    for position in range(1, len(path_ids)):
        if position - 1 < len(sequence):
            steps.append(sequence[position - 1])
        elif sequence[-1] == "COATING":
            steps.append("COATING")
        else:
            steps.append("")
    return steps


def _path_before_step(path_ids, steps, step_code):
    """The path as it stood before ``step_code`` was answered.

    The frontend sends the path from the previous response, so the step
    being answered is normally not in it yet. If it is (a replay, or the
    shopper went back), drop it and everything after it so the new answer
    replaces the old one instead of being appended twice.
    """
    if step_code in steps:
        return list(path_ids[:steps.index(step_code)])
    return list(path_ids)


def _blue_light_function_selected(path_ids):
    """True when the FUNCTION step was Blue Light Filtering.

    ``path_ids`` is the plain integer path. Only the id at the FUNCTION
    position (see `_selection_steps`) is looked up, and only in
    LensFunctionPath.
    """
    steps = _selection_steps(path_ids)
    if "FUNCTION" not in steps:
        return False
    function_id = path_ids[steps.index("FUNCTION")]
    return LensFunctionPath.objects.filter(
        pk=function_id,
        function_code=LensFunctionPath.FunctionCode.BLUE_LIGHT_FILTERING,
    ).exists()


def _color_option_dict(color_option):
    return _option_dict(
        id=color_option.id, code=color_option.color_name, name=color_option.color_name,
        option_type="COLOR", price=color_option.extra_price,
        metadata={
            "swatch_hex": color_option.swatch_hex,
            "density": float(color_option.swatch_density),
            "family": color_option.swatch_family,
            "base_color": color_option.base_color,
        },
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


# Shown on the index step when the price sheet has no cell for this
# prescription at any index we sell. A blank option list is not enough
# for the shopper to understand why.
INDEX_UNAVAILABLE_REASON = (
    "This prescription isn't available online yet. Please contact us."
)


def _step_response(step_code, option_dicts, selection_path, is_complete=False,
                    step_index=None, total_steps=None, unavailable_reason=None):
    current = None if is_complete else _step_dict(step_code)
    if current is not None and unavailable_reason:
        current["description"] = unavailable_reason
    body = {
        "current_step": current,
        "options": [] if is_complete else option_dicts,
        # Plain list of ids, same shape as before. The live frontend
        # echoes it back with join(","); it must never contain objects.
        "selection_path": list(selection_path),
        # Additive, informational: the step code for each selection_path
        # entry, same order. Clients don't need to send it back.
        "selection_steps": _selection_steps(selection_path),
        "is_complete": is_complete,
        # Progress-indicator hints — null until the path is determined (see
        # NextStepRequestSerializer's docstring). Omitted entirely when
        # is_complete, since there's no next step left to show progress for.
        "step_index": None if is_complete else step_index,
        "total_steps": None if is_complete else total_steps,
    }
    if unavailable_reason:
        body["unavailable_reason"] = unavailable_reason
    return Response(body, status=status.HTTP_200_OK)


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
            "selection_steps": [],
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
      - selection_path: comma-separated ids (optional), echoed back from
                        the previous response, e.g. ``1,1,2``. The server
                        works out which step each id belongs to from the
                        workflow order. Tagged tokens such as
                        ``LENS_TYPE:1,FUNCTION:1`` are also accepted; a tag
                        that disagrees with the workflow order is a 400.
      - prescription_id: int (optional; only used when transitioning into INDEX)
      - current_step_index / total_steps: int (optional; progress-indicator
        state echoed back from the previous response — see
        NextStepRequestSerializer's docstring)
    """

    def get(self, request):
        try:
            path_ids, path_tags = _parse_selection_path(
                request.query_params.get("selection_path", ""))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        serializer = NextStepRequestSerializer(data={
            "current_step_code": request.query_params.get("current_step_code"),
            "selected_option_id": request.query_params.get("selected_option_id"),
            "selected_option_ids": _safe_parse(request.query_params.get("selected_option_ids", "")),
            "selection_path": path_ids,
            "prescription_id": request.query_params.get("prescription_id") or None,
            "current_step_index": request.query_params.get("current_step_index") or None,
            "total_steps": request.query_params.get("total_steps") or None,
        })
        if not serializer.is_valid():
            return Response({"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        current_step_code = data["current_step_code"]
        selection_path = data["selection_path"]
        prescription_id = data.get("prescription_id")
        current_step_index = data.get("current_step_index")
        total_steps = data.get("total_steps")

        steps = _selection_steps(selection_path)
        for position, tag in path_tags.items():
            if steps[position] != tag:
                return Response(
                    {"detail": f"selection_path entry {position} is a "
                               f"{steps[position] or 'unknown'} choice, not {tag}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        base_path = _path_before_step(selection_path, steps, current_step_code)

        if current_step_code == "COATING":
            selected_ids = data.get("selected_option_ids") or []
            # Coating ids go after the index, one per distinct coating. They
            # are not compared with earlier ids: those come from other tables.
            updated_path = base_path + list(dict.fromkeys(selected_ids))
            return self._after_coating(selected_ids, updated_path)

        selected_option_id = data["selected_option_id"]
        # Always appended. A bare id equal to an earlier one (lens type 1,
        # Classic function 1) is a different table's row, not a repeat.
        updated_path = [*base_path, selected_option_id]

        handler = {
            "LENS_TYPE": self._after_lens_type,
            "FUNCTION": self._after_function,
            "TINT_TYPE": self._after_tint_type,
            "COLOR": self._after_color,
            "INDEX": self._after_index,
            "READER_STRENGTH": self._after_reader_strength,
        }[current_step_code]

        try:
            return handler(selected_option_id, updated_path, prescription_id,
                            current_step_index, total_steps)
        except DOES_NOT_EXIST_ERRORS:
            return Response(
                {"detail": f"Selected option id={selected_option_id} not found for step {current_step_code}."},
                status=status.HTTP_404_NOT_FOUND,
            )

    def _after_lens_type(self, selected_option_id, path, prescription_id,
                          current_step_index, total_steps):
        lens_type = LensType.objects.get(id=selected_option_id, is_active=True)

        if lens_type.is_reader:
            return self._enter_reader_strength_step(path)

        # Group function paths by function_code — one representative row per
        # group is shown as the Step-2 button (Postgres-only: distinct(*fields)).
        # Postgres requires DISTINCT ON's leading ORDER BY columns to match
        # the distinct(*fields) call, so function_code has to stay first in
        # the query itself — cheapest-first display order is applied
        # afterward, as a plain Python sort over the already-deduped list.
        function_paths = sorted(
            LensFunctionPath.objects.filter(
                lens_type=lens_type, is_active=True)
            .order_by("function_code", "sort_order", "id")
            .distinct("function_code"),
            key=lambda fp: fp.extra_price,
        )
        # total_steps stays null here — it depends on which Function gets
        # picked next (Sun's path is longer than Classic's) and only
        # becomes knowable once that choice is made — see _after_function.
        return _step_response(
            "FUNCTION", [_function_option(fp) for fp in function_paths], path,
            step_index=1, total_steps=None)

    def _enter_reader_strength_step(self, path):
        strengths = LensReaderStrength.objects.filter(
            is_active=True).order_by("sort_order", "id")
        # Reader's path never branches further — total_steps is knowable
        # immediately, unlike the main Function-first path above.
        return _step_response(
            "READER_STRENGTH", [_reader_strength_option(s) for s in strengths], path,
            step_index=1, total_steps=1)

    def _after_reader_strength(self, selected_option_id, path, prescription_id,
                                current_step_index, total_steps):
        LensReaderStrength.objects.get(id=selected_option_id, is_active=True)
        # No Function/Tint/Color/Material/Coating choice for a readymade
        # reader — straight to complete.
        return _step_response("READER_STRENGTH", [], path, is_complete=True)

    def _after_function(self, selected_option_id, path, prescription_id,
                         current_step_index, total_steps):
        clicked = LensFunctionPath.objects.get(
            id=selected_option_id, is_active=True)

        # This is the one point where total_steps becomes knowable — the
        # chosen Function fully determines how many steps remain.
        if clicked.function_code == LensFunctionPath.FunctionCode.SUN:
            # FUNCTION -> TINT_TYPE -> COLOR -> INDEX -> COATING
            return self._enter_tint_type_step(clicked, path, step_index=2, total_steps=5)

        if not clicked.color_required:
            # FUNCTION -> INDEX -> COATING
            return self._enter_index_step(
                clicked, path, prescription_id, step_index=2, total_steps=3)

        # Photochromic (or any future color_required, non-Sun function):
        # colors scoped directly to this one function_path — Sun is the
        # only function_code with siblings, disambiguated by Tint Type.
        # FUNCTION -> COLOR -> INDEX -> COATING
        return self._enter_color_step(
            clicked, path, prescription_id, step_index=2, total_steps=4)

    def _enter_tint_type_step(self, clicked_sun_function_path, path, step_index, total_steps):
        siblings = LensFunctionPath.objects.filter(
            lens_type=clicked_sun_function_path.lens_type,
            function_code=LensFunctionPath.FunctionCode.SUN,
            is_active=True,
        ).exclude(sun_type="").order_by("extra_price", "sort_order", "id")
        return _step_response(
            "TINT_TYPE", [_tint_type_option(fp) for fp in siblings], path,
            step_index=step_index, total_steps=total_steps)

    def _after_tint_type(self, selected_option_id, path, prescription_id,
                          current_step_index, total_steps):
        clicked = LensFunctionPath.objects.get(
            id=selected_option_id, is_active=True)
        return self._enter_color_step(
            clicked, path, prescription_id,
            step_index=current_step_index + 1, total_steps=total_steps)

    def _enter_color_step(self, function_path, path, prescription_id, step_index, total_steps):
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

        return _step_response(
            "COLOR", [_color_option_dict(co) for co in color_options], path,
            step_index=step_index, total_steps=total_steps)

    def _after_color(self, selected_option_id, path, prescription_id,
                      current_step_index, total_steps):
        color_option = LensColorOption.objects.select_related("function_path").get(
            id=selected_option_id, is_active=True)
        return self._enter_index_step(
            color_option.function_path, path, prescription_id,
            color_option=color_option,
            color_available_index_values=color_option.available_index_values,
            step_index=current_step_index + 1, total_steps=total_steps,
        )

    def _enter_index_step(self, function_path, path, prescription_id,
                           color_available_index_values=None,
                           color_option=None,
                           step_index=None, total_steps=None):
        # Index/Material is scoped to Lens Type, not Function Path — the
        # same list applies no matter which Function got picked. Prices for
        # "is this cell on the sheet" come from the selected function and,
        # when there is one, the selected color.
        index_options = [
            io for io in LensIndexOption.objects.filter(
                lens_type=function_path.lens_type, is_active=True
            ).order_by("price", "sort_order", "id")
            if canonical_index(io.index_value) in _LADDER
        ]

        if color_available_index_values is not None:
            # A color that is only made at some indexes (Polarized Green at
            # 1.56/1.61, for example) cannot offer the others.
            color_allowed = {canonical_index(value) for value in color_available_index_values}
            index_options = [
                io for io in index_options
                if canonical_index(io.index_value) in color_allowed
            ]

        prescription = _load_prescription(prescription_id)
        category = function_path.lens_type.index_recommendation_category
        if _is_non_rx_lens_type(function_path.lens_type):
            # Non-prescription lenses are plano: 0.00 on both eyes. Price and
            # recommend them exactly like a 0.00 prescription, so unavailable
            # indexes are hidden and 1.50 is recommended (2026-11-11).
            prescription = _PLANO_PRESCRIPTION
            category = category or "PLANO"
        if prescription is not None and price_table_loaded():
            index_options = [
                io for io in index_options
                if catalog_index_available(_index_quote_request(
                    function_path, prescription, io, color_option))
            ]

        if prescription is None or not category:
            option_dicts = []
            for io in index_options:
                material, abbe = index_profile(io.index_value)
                option_dicts.append(_index_option_dict(
                    io, is_recommended=False, group="other_available",
                    material=material, abbe_number=abbe,
                ))
            return _step_response(
                "INDEX", option_dicts, path, step_index=step_index, total_steps=total_steps)

        power, direction = _combined_power(prescription)
        rule = _match_recommendation_rule(category, power, direction)
        chosen = _priced_tier(index_options, rule.recommended_canonical)

        if chosen is None:
            return _step_response(
                "INDEX", [], path, step_index=step_index, total_steps=total_steps,
                unavailable_reason=INDEX_UNAVAILABLE_REASON)

        visible = set(neighbor_indexes(chosen))
        shown = [
            io for io in index_options
            if canonical_index(io.index_value) in visible
        ]
        at_tier = [io for io in shown if canonical_index(io.index_value) == chosen]
        # Two catalog rows can share the rung (Popular 1.61 and Driving 1.61).
        # Recommend the cheaper one, and do not list the other as a neighbor.
        winner = min(at_tier, key=lambda io: (io.price, io.sort_order, io.id))
        shown = [
            io for io in shown
            if io.id == winner.id or canonical_index(io.index_value) != chosen
        ]
        shown.sort(key=lambda io: (
            CANONICAL_INDEX_LADDER.index(canonical_index(io.index_value)),
            io.price, io.sort_order, io.id,
        ))

        option_dicts = []
        for io in shown:
            material, abbe = index_profile(io.index_value)
            recommended = io.id == winner.id
            option_dicts.append(_index_option_dict(
                io,
                is_recommended=recommended,
                group="recommended" if recommended else "other_available",
                material=material,
                abbe_number=abbe,
            ))
        return _step_response(
            "INDEX", option_dicts, path, step_index=step_index, total_steps=total_steps)

    def _after_index(self, selected_option_id, path, prescription_id,
                      current_step_index, total_steps):
        LensIndexOption.objects.get(id=selected_option_id, is_active=True)
        # Color (when needed) already happened before Index now, so Index
        # always leads straight to Coating.
        return self._enter_coating_step(
            path, step_index=current_step_index + 1, total_steps=total_steps)

    def _enter_coating_step(self, path, step_index=None, total_steps=None):
        # Every active coating is returned — both the always-included ones
        # (Anti-scratch/Anti-glare/UV-protection) and the pickable add-ons.
        # metadata.is_included tells the frontend which is which; the
        # included ones are shown as static "already included" text, not a
        # choice — see _after_coating for the corresponding server-side
        # rejection if one is submitted as if it were a selection.
        #
        # Blue Light Filtering is already the step-3 function when that
        # was picked, so it is not offered again here. Classic, Sun/Tint,
        # and Photochromic still get it as a coating.
        coatings = LensCoating.objects.filter(
            is_active=True).order_by("price", "sort_order", "id")
        if _blue_light_function_selected(path):
            coatings = coatings.exclude(code=LensCoating.Code.BLUE_LIGHT_FILTERING)
        return _step_response(
            "COATING", [_coating_option_dict(c) for c in coatings], path,
            step_index=step_index, total_steps=total_steps)

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
            if (c.code == LensCoating.Code.BLUE_LIGHT_FILTERING
                    and _blue_light_function_selected(path)):
                return Response(
                    {"detail": "Blue Light Filtering is already part of the Blue Light "
                               "lens and can't be selected again."},
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

        tint_type = None
        tint_type_id = request.query_params.get("tint_type_id")
        if tint_type_id:
            try:
                tint_type = LensFunctionPath.objects.get(id=int(tint_type_id))
            except (TypeError, ValueError, LensFunctionPath.DoesNotExist):
                return Response(
                    {"detail": "tint_type_id was not found."},
                    status=status.HTTP_404_NOT_FOUND)

        body = {
            "selected_options": selected,
            "total_add_on_price": str(total),
            "missing_option_ids": [],
        }
        try:
            result = quote(_summary_quote_request(
                request, lens_type, function_path, tint_type, index_option,
                color_option, coatings))
        except QuoteError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        body["pricing_source"] = result.pricing_source
        body["quote"] = quote_to_dict(result)
        if result.blocked or not result.available:
            body["total_add_on_price"] = None
            body["block_reason"] = result.block_reason or (
                result.selection.reason if result.selection is not None else None)
        else:
            body["total_add_on_price"] = str(result.total_lens_price)
            body["block_reason"] = None
        return Response(body, status=status.HTTP_200_OK)


def _eye_from_query(request, side, prescription, sph_attr, cyl_attr, add_attr, pd_attr):
    prefix = "od" if side == "od" else "os"
    if request.query_params.get(f"{prefix}_sph") is not None or request.query_params.get(f"{prefix}_cyl") is not None:
        return Eye(
            sph=Decimal(request.query_params.get(f"{prefix}_sph") or "0"),
            cyl=Decimal(request.query_params.get(f"{prefix}_cyl") or "0"),
            add=Decimal(request.query_params.get(f"{prefix}_add") or "0"),
            pd=Decimal(request.query_params.get(f"{prefix}_pd") or "0"),
        )
    if prescription is None:
        return Eye()
    return Eye(
        sph=getattr(prescription, sph_attr) or Decimal("0"),
        cyl=getattr(prescription, cyl_attr) or Decimal("0"),
        add=getattr(prescription, add_attr) or Decimal("0"),
        pd=getattr(prescription, pd_attr) or Decimal("0"),
    )


def _summary_quote_request(request, lens_type, function_path, tint_type,
                           index_option, color_option, coatings):
    prescription = None
    prescription_id = request.query_params.get("prescription_id")
    if prescription_id:
        try:
            prescription = PrescriptionInfo.objects.get(id=int(prescription_id))
        except (TypeError, ValueError, PrescriptionInfo.DoesNotExist):
            raise QuoteError(f"Prescription id {prescription_id} was not found.")
    sent_powers = any(
        request.query_params.get(key) is not None
        for key in ("od_sph", "od_cyl", "os_sph", "os_cyl"))
    od = _eye_from_query(request, "od", prescription, "sphere_r", "cylinder_r", "add_r", "pd_r")
    os = _eye_from_query(request, "os", prescription, "sphere_l", "cylinder_l", "add_l", "pd_l")
    sun_type = tint_type.sun_type if tint_type is not None and tint_type.sun_type else (
        function_path.sun_type if function_path is not None else "")
    is_reader = bool(lens_type.is_reader or lens_type.code == "READER")
    is_non_rx = bool(not lens_type.is_prescription_required and not is_reader)
    prism = prism_requested(request.query_params.get("prism"))
    if not prism and prescription is not None and not sent_powers:
        prism = prescription.prism.exists()
    return QuoteRequest(
        od=od, os=os, prism=prism,
        lens_type_code=lens_type.code,
        function_code=function_path.function_code if function_path is not None else "",
        sun_type=sun_type or "",
        color_name=color_option.color_name if color_option is not None else "",
        index_value=index_option.index_value if index_option is not None else None,
        coating_codes=tuple(c.code for c in coatings),
        lens_type=lens_type, function_path=function_path, tint_type=tint_type,
        color_option=color_option, index_option=index_option, coatings=tuple(coatings),
        prescription_missing=(
            lens_type.is_prescription_required and prescription is None and not sent_powers),
        is_reader=is_reader, is_non_rx=is_non_rx)


class LensWorkflowRxQuoteView(APIView):
    """POST /api/lens-workflow/rx-quote/

    Authoritative all-in lens price for a prescription and a lens selection.
    The response is what summary and checkout charge. The client must not
    send a price; this server ignores any price field.
    """

    def post(self, request):
        serializer = RxQuoteRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            req = _rx_quote_request(serializer.validated_data)
            result = quote(req, include_options=True, require_index=False)
        except QuoteError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(quote_to_dict(result), status=status.HTTP_200_OK)


def _rx_quote_request(data):
    from decimal import Decimal as _D
    prescription = None
    if data.get("prescription_id"):
        try:
            prescription = PrescriptionInfo.objects.get(id=data["prescription_id"])
        except PrescriptionInfo.DoesNotExist:
            raise QuoteError(f"Prescription id {data['prescription_id']} was not found.")
    if data.get("od"):
        od = Eye(
            sph=data["od"]["sph"], cyl=data["od"].get("cyl") or _D("0"),
            add=data["od"].get("add") or _D("0"), pd=data["od"].get("pd") or _D("0"))
        os_data = data["os"]
        os = Eye(
            sph=os_data["sph"], cyl=os_data.get("cyl") or _D("0"),
            add=os_data.get("add") or _D("0"), pd=os_data.get("pd") or _D("0"))
    elif prescription is not None:
        od = Eye(prescription.sphere_r or _D("0"), prescription.cylinder_r or _D("0"),
                 prescription.add_r or _D("0"), prescription.pd_r or _D("0"))
        os = Eye(prescription.sphere_l or _D("0"), prescription.cylinder_l or _D("0"),
                 prescription.add_l or _D("0"), prescription.pd_l or _D("0"))
    else:
        raise QuoteError("Provide od and os, or prescription_id.")

    lens_type = None
    if data.get("lens_type_id"):
        try:
            lens_type = LensType.objects.get(id=data["lens_type_id"])
        except LensType.DoesNotExist:
            raise QuoteError(f"Lens type id {data['lens_type_id']} was not found.")
        code = lens_type.code
    else:
        code = data.get("lens_type_code") or ""
        lens_type = LensType.objects.filter(code=code).first()

    function_path = None
    function_code = data.get("function_code") or ""
    if data.get("function_path_id"):
        try:
            function_path = LensFunctionPath.objects.get(id=data["function_path_id"])
        except LensFunctionPath.DoesNotExist:
            raise QuoteError(f"Function path id {data['function_path_id']} was not found.")
        function_code = function_path.function_code
    sun_type = data.get("sun_type") or ""
    tint_type = None
    if data.get("tint_type_id"):
        try:
            tint_type = LensFunctionPath.objects.get(id=data["tint_type_id"])
        except LensFunctionPath.DoesNotExist:
            raise QuoteError(f"Tint type id {data['tint_type_id']} was not found.")
        if tint_type.sun_type:
            sun_type = tint_type.sun_type
    elif not sun_type and function_path is not None and function_path.sun_type:
        sun_type = function_path.sun_type

    color_option = None
    color_name = data.get("color_name") or ""
    if data.get("color_option_id"):
        try:
            color_option = LensColorOption.objects.get(id=data["color_option_id"])
        except LensColorOption.DoesNotExist:
            raise QuoteError(f"Color id {data['color_option_id']} was not found.")
        color_name = color_option.color_name

    index_option = None
    index_value = data.get("index_value")
    if data.get("index_option_id"):
        try:
            index_option = LensIndexOption.objects.get(id=data["index_option_id"])
        except LensIndexOption.DoesNotExist:
            raise QuoteError(f"Index id {data['index_option_id']} was not found.")
        index_value = index_option.index_value

    coatings = []
    coating_ids = data.get("coating_ids") or []
    if coating_ids:
        coatings = list(LensCoating.objects.filter(id__in=coating_ids))
        if len(coatings) != len(set(coating_ids)):
            raise QuoteError("One or more coating ids were not found.")
    codes = list(data.get("coating_codes") or [])
    if codes:
        found = list(LensCoating.objects.filter(code__in=codes))
        known = {choice for choice, _label in LensCoating.Code.choices}
        unknown = [code for code in codes if code not in known]
        if unknown:
            raise QuoteError(f"Unknown coating code(s): {unknown}.")
        present = {row.code for row in found}
        missing_priced = [
            code for code in codes
            if code not in present and code not in ("BLUE_LIGHT_FILTERING",
                                                    "ANTI_SCRATCH", "ANTI_GLARE", "UV_PROTECTION")]
        if missing_priced:
            raise QuoteError(
                f"Coating code(s) {missing_priced} are not in the catalog, so they cannot be priced.")
        by_code = {row.code: row for row in coatings}
        for row in found:
            by_code.setdefault(row.code, row)
        coatings = list(by_code.values())
    seen_groups = {}
    for coating in coatings:
        if not coating.exclusive_group:
            continue
        if coating.exclusive_group in seen_groups:
            raise QuoteError(
                f"'{coating.label}' and '{seen_groups[coating.exclusive_group]}' can't both be selected.")
        seen_groups[coating.exclusive_group] = coating.label
    coating_codes = tuple(dict.fromkeys(
        [c.code for c in coatings] + [c for c in codes if c not in {row.code for row in coatings}]))

    if "prism" in data:
        prism = prism_requested(data.get("prism"))
    elif prescription is not None and not data.get("od"):
        prism = prescription.prism.exists()
    else:
        prism = False

    is_reader = bool(lens_type and (lens_type.is_reader or lens_type.code == "READER")) or code == "READER"
    is_non_rx = bool(lens_type and not lens_type.is_prescription_required and not is_reader) or code == "NON_RX"
    return QuoteRequest(
        od=od, os=os, prism=prism,
        lens_type_code=code, function_code=function_code, sun_type=sun_type or "",
        color_name=color_name, density=data.get("density") or "",
        index_value=index_value, coating_codes=coating_codes,
        lens_type=lens_type, function_path=function_path, tint_type=tint_type,
        color_option=color_option, index_option=index_option, coatings=tuple(coatings),
        prescription_missing=False,
        is_reader=is_reader, is_non_rx=is_non_rx)

