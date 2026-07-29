from rest_framework import serializers

from .models import (
    LensType,
    LensFunctionPath,
    LensIndexOption,
    LensColorOption,
    LensCoating,
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
        fields = ["id", "function_path", "tier", "option_label",
                  "index_value", "price", "sort_order", "is_active"]


class LensColorOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LensColorOption
        fields = ["id", "index_option", "color_name",
                  "extra_price", "sort_order", "is_active"]


class LensCoatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = LensCoating
        fields = ["id", "code", "label", "description",
                  "price", "is_recommended", "sort_order", "is_active"]


class NextStepRequestSerializer(serializers.Serializer):
    """
    Frontend sends which step it was on, what was selected there, and the
    path of previous selections.

    prescription_id is optional and only used when transitioning into the
    INDEX step (to compute the recommended/available index bracket) — sent
    on every call from FUNCTION onward, ignored elsewhere.

    Example:
    {
      "current_step_code": "FUNCTION",
      "selected_option_id": 12,
      "selection_path": [3, 12],
      "prescription_id": 7
    }
    """
    current_step_code = serializers.ChoiceField(
        choices=["LENS_TYPE", "FUNCTION", "SUN_TYPE", "INDEX", "COLOR", "COATING"])
    selected_option_id = serializers.IntegerField()
    selection_path = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        default=list,
    )
    prescription_id = serializers.IntegerField(required=False, allow_null=True)
