from django.urls import path

from .views import (
    LensWorkflowStartView,
    LensWorkflowNextView,
    LensWorkflowSummaryView,
    LensWorkflowRxQuoteView,
)

from .pricing_v2 import api as v2

app_name = "lens_workflow"

urlpatterns = [
    path("start/", LensWorkflowStartView.as_view(), name="start"),
    path("next/", LensWorkflowNextView.as_view(), name="next"),
    path("summary/", LensWorkflowSummaryView.as_view(), name="summary"),
    path("rx-quote/", LensWorkflowRxQuoteView.as_view(), name="rx-quote"),
    path("v2/config/", v2.ConfigView.as_view(), name="v2-config"),
    path("v2/selections/", v2.SelectionsView.as_view(), name="v2-selections"),
    path("v2/quote/", v2.QuoteView.as_view(), name="v2-quote"),
    path("v2/reader-quote/", v2.ReaderQuoteView.as_view(), name="v2-reader-quote"),
]
