from decimal import Decimal

from rest_framework import serializers

from .models import (
    LensType,
    LensFunctionPath,
    LensIndexOption,
    LensColorOption,
    LensCoating,
    LensReaderStrength,
)


class LensTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LensType
        fields = ["id", "code", "label", "description",
                  "is_prescription_required", "index_recommendation_category",
                  "sort_order", "is_active"]


class LensFunctionPathSerializer(serializers.ModelSerializer):
    class Meta:
        model = LensFunctionPath
        fields = ["id", "lens_type", "function_code", "function_label",
                  "function_description", "sun_type", "color_required",
                  "extra_price", "sort_order", "is_active"]


class LensIndexOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LensIndexOption
        fields = ["id", "lens_type", "tier", "option_label",
                  "index_value", "price", "sort_order", "is_active"]


class LensColorOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LensColorOption
        fields = ["id", "function_path", "color_name",
                  "extra_price", "sort_order", "is_active"]


class LensCoatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = LensCoating
        fields = ["id", "code", "label", "description",
                  "price", "is_recommended", "sort_order", "is_active"]


class LensReaderStrengthSerializer(serializers.ModelSerializer):
    class Meta:
        model = LensReaderStrength
        fields = ["id", "strength_value", "label", "price"]


class NextStepRequestSerializer(serializers.Serializer):
    """
    Frontend sends which step it was on, what was selected there, and the
    path of previous selections.

    prescription_id is optional and only used when transitioning into the
    INDEX step (to compute the recommended/available index bracket) — sent
    on every call from FUNCTION onward, ignored elsewhere.

    current_step_index / total_steps: for the progress indicator. The
    frontend echoes back whatever it received in the PREVIOUS response's
    step_index/total_steps (both start null while on LENS_TYPE/FUNCTION,
    since the path length depends on which Function gets picked — not
    knowable until then). Once total_steps becomes non-null (the response
    to submitting FUNCTION), every step after just increments step_index by
    1 and passes total_steps straight through — see views.py.

    COATING is the one step that's multi-select — it uses
    selected_option_ids (a list, possibly empty) instead of
    selected_option_id. Every other step uses the singular field and it's
    required for them (enforced in validate() below, since a plain
    IntegerField can't be conditionally required per-step on its own).

    Example (single-select step):
    {
      "current_step_code": "FUNCTION",
      "selected_option_id": 12,
      "selection_path": [3],
      "prescription_id": 7
    }

    selection_path is a plain list of ids (query string ``3`` or ``3,12``), exactly
    as the previous response returned it. The server works out which step
    each id belongs to from the workflow order (lens type, then function,
    then tint/color/index as that function requires, then coatings) and
    looks each id up only in its own step's table. The same number can be
    a lens type and a function; position, not the number, tells them apart.

    Example (COATING):
    {
      "current_step_code": "COATING",
      "selected_option_ids": [21, 23],
      "selection_path": [3, 12, 18],
      "prescription_id": 7
    }
    """
    current_step_code = serializers.ChoiceField(
        choices=["LENS_TYPE", "FUNCTION", "TINT_TYPE", "COLOR", "INDEX",
                 "COATING", "READER_STRENGTH"])
    selected_option_id = serializers.IntegerField(required=False, allow_null=True)
    selected_option_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        default=list,
    )
    selection_path = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        default=list,
    )
    prescription_id = serializers.IntegerField(required=False, allow_null=True)
    current_step_index = serializers.IntegerField(required=False, allow_null=True)
    total_steps = serializers.IntegerField(required=False, allow_null=True)

    def validate(self, data):
        if data.get("current_step_code") != "COATING" and data.get("selected_option_id") is None:
            raise serializers.ValidationError(
                {"selected_option_id": "This field is required for this step."})
        return data


class _PowerField(serializers.DecimalField):
    """Sphere/cylinder. Accepts the sheet's "Plano" label as 0."""

    def to_internal_value(self, data):
        if isinstance(data, str) and data.strip().lower() == "plano":
            data = "0"
        return super().to_internal_value(data)


class RxEyeSerializer(serializers.Serializer):
    sph = _PowerField(max_digits=6, decimal_places=2)
    cyl = _PowerField(max_digits=6, decimal_places=2, required=False, default=Decimal("0"))
    add = _PowerField(max_digits=6, decimal_places=2, required=False, default=Decimal("0"))
    pd = _PowerField(max_digits=6, decimal_places=2, required=False, default=Decimal("0"))
    axis = _PowerField(max_digits=6, decimal_places=2, required=False, default=Decimal("0"))


class RxQuoteRequestSerializer(serializers.Serializer):
    """POST /api/lens-workflow/rx-quote/ body.

    Send `od` and `os`, or `prescription_id` to load a saved prescription.
    Lens identity is by code (`lens_type_code`, `function_code`, ...) or by
    the ids the shopping steps already return. `index_value` may be omitted
    to get the index menu in `options` instead of one `selection` price.
    """

    od = RxEyeSerializer(required=False)
    os = RxEyeSerializer(required=False)
    prescription_id = serializers.IntegerField(required=False)
    prism = serializers.JSONField(required=False)
    lens_type_code = serializers.CharField(required=False, allow_blank=True)
    lens_type_id = serializers.IntegerField(required=False)
    function_code = serializers.CharField(required=False, allow_blank=True)
    function_path_id = serializers.IntegerField(required=False)
    sun_type = serializers.CharField(required=False, allow_blank=True)
    tint_type_id = serializers.IntegerField(required=False)
    color_name = serializers.CharField(required=False, allow_blank=True)
    color_option_id = serializers.IntegerField(required=False)
    index_value = serializers.DecimalField(
        max_digits=4, decimal_places=2, required=False)
    index_option_id = serializers.IntegerField(required=False)
    coating_codes = serializers.ListField(
        child=serializers.CharField(), required=False, default=list)
    coating_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list)
    density = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, data):
        if not data.get("od") and not data.get("prescription_id"):
            raise serializers.ValidationError(
                "Provide od and os, or prescription_id.")
        if data.get("od") and not data.get("os"):
            raise serializers.ValidationError("os is required when od is sent.")
        if data.get("os") and not data.get("od"):
            raise serializers.ValidationError("od is required when os is sent.")
        if not data.get("lens_type_code") and not data.get("lens_type_id"):
            raise serializers.ValidationError(
                "lens_type_code or lens_type_id is required.")
        return data
