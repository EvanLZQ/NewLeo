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
      "selection_path": [3, 12],
      "prescription_id": 7
    }

    Example (COATING):
    {
      "current_step_code": "COATING",
      "selected_option_ids": [21, 23],
      "selection_path": [3, 12, 15, 18],
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
