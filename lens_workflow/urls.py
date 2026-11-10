from django.urls import path

from .views import (
    LensWorkflowStartView,
    LensWorkflowNextView,
    LensWorkflowSummaryView,
    LensWorkflowRxQuoteView,
)

app_name = "lens_workflow"

urlpatterns = [
    path("start/", LensWorkflowStartView.as_view(), name="start"),
    path("next/", LensWorkflowNextView.as_view(), name="next"),
    path("summary/", LensWorkflowSummaryView.as_view(), name="summary"),
    path("rx-quote/", LensWorkflowRxQuoteView.as_view(), name="rx-quote"),
]
