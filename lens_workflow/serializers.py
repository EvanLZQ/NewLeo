from rest_framework import serializers

from .models import LensStep, LensOption


class LensOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = LensOption
        fields = [
            "id",
            "code",
            "name",
            "option_type",
            "description",
            "add_on_price",
            "image_url",
            "metadata",
            "sort_order",
            "is_active",
        ]


class LensStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = LensStep
        fields = [
            "id",
            "code",
            "label",
            "description",
            "sort_order",
            "is_active",
        ]


class StepOptionsResponseSerializer(serializers.Serializer):
    """
    Response wrapper for frontend:
    {
      "current_step": {...},
      "options": [...],
      "selection_path": [...]
    }
    """
    current_step = LensStepSerializer(allow_null=True)
    options = LensOptionSerializer(many=True)
    selection_path = serializers.ListField(
        child=serializers.IntegerField(), required=False
    )


class NextStepRequestSerializer(serializers.Serializer):
    """
    Frontend sends the selected option and optionally the path of previous selections.

    Example:
    {
      "selected_option_id": 12,
      "selection_path": [3, 12]
    }
    """
    selected_option_id = serializers.IntegerField()
    selection_path = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        default=list,
    )


class SelectionSummaryRequestSerializer(serializers.Serializer):
    """
    Optional helper endpoint to summarize final selected options.
    """
    selected_option_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
    )
