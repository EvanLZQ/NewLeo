import io

from django.contrib import admin, messages
from django.db.models import Count, Max, Min
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    LensType,
    LensFunctionPath,
    LensIndexOption,
    LensColorOption,
    LensCoating,
    LensIndexRecommendationRule,
    LensReaderStrength,
    LensPriceBlock,
    LensPriceImport,
)
from . import price_table


# ---------- Inlines ----------

class LensFunctionPathInline(admin.TabularInline):
    model = LensFunctionPath
    extra = 0
    fields = ("function_code", "function_label", "sun_type",
              "color_required", "extra_price", "sort_order", "is_active")
    ordering = ("sort_order", "id")


class LensIndexOptionInline(admin.TabularInline):
    model = LensIndexOption
    extra = 0
    fields = ("tier", "option_label", "index_value",
              "price", "sort_order", "is_active")
    ordering = ("sort_order", "id")


class LensColorOptionInline(admin.TabularInline):
    model = LensColorOption
    extra = 0
    fields = ("color_name", "extra_price", "swatch_hex", "swatch_density",
              "swatch_family", "sort_order", "is_active")
    ordering = ("sort_order", "id")


# ---------- Admin registrations ----------

@admin.register(LensType)
class LensTypeAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "is_prescription_required", "is_reader",
                     "index_recommendation_category", "sort_order", "is_active", "updated_at")
    list_filter = ("is_prescription_required", "is_reader",
                   "index_recommendation_category", "is_active")
    search_fields = ("label", "code", "description")
    ordering = ("sort_order", "id")
    # Index is scoped per Lens Type now (not per Function Path), so its
    # inline moved here alongside Function Path.
    inlines = [LensFunctionPathInline, LensIndexOptionInline]


@admin.register(LensFunctionPath)
class LensFunctionPathAdmin(admin.ModelAdmin):
    list_display = ("lens_type", "function_code", "sun_type",
                     "color_required", "extra_price", "sort_order", "is_active", "updated_at")
    list_filter = ("lens_type", "function_code", "sun_type", "is_active")
    search_fields = ("function_label", "function_description",
                      "notes", "lens_type__label", "lens_type__code")
    autocomplete_fields = ("lens_type",)
    ordering = ("lens_type__sort_order", "sort_order", "id")
    inlines = [LensColorOptionInline]


@admin.register(LensIndexOption)
class LensIndexOptionAdmin(admin.ModelAdmin):
    list_display = ("lens_type", "tier", "option_label",
                     "index_value", "price", "sort_order", "is_active", "updated_at")
    list_filter = ("tier", "is_active", "lens_type")
    search_fields = ("option_label", "notes", "lens_type__label", "lens_type__code")
    autocomplete_fields = ("lens_type",)
    ordering = ("lens_type__sort_order", "sort_order", "id")


@admin.register(LensColorOption)
class LensColorOptionAdmin(admin.ModelAdmin):
    list_display = ("function_path", "color_name", "swatch_preview", "swatch_hex",
                     "swatch_density", "swatch_family", "extra_price",
                     "available_index_values", "sort_order", "is_active", "updated_at")
    list_filter = ("is_active", "swatch_family", "function_path__lens_type",
                   "function_path__function_code")
    search_fields = ("color_name", "function_path__function_code",
                      "function_path__lens_type__label")
    autocomplete_fields = ("function_path",)
    ordering = ("function_path__sort_order", "sort_order", "id")

    @admin.display(description="Swatch")
    def swatch_preview(self, obj):
        if not obj.swatch_hex:
            return "—"
        return format_html(
            '<span style="display:inline-block;width:18px;height:18px;'
            'border-radius:50%;border:1px solid #ccc;background:{};'
            'opacity:{};"></span>',
            obj.swatch_hex, obj.swatch_density,
        )


@admin.register(LensCoating)
class LensCoatingAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "price", "is_included", "exclusive_group",
                     "is_recommended", "sort_order", "is_active", "updated_at")
    list_filter = ("is_included", "is_recommended", "is_active", "exclusive_group")
    search_fields = ("label", "code", "description")
    ordering = ("sort_order", "id")


@admin.register(LensReaderStrength)
class LensReaderStrengthAdmin(admin.ModelAdmin):
    list_display = ("label", "strength_value", "price", "sort_order", "is_active", "updated_at")
    ordering = ("sort_order", "id")


@admin.register(LensIndexRecommendationRule)
class LensIndexRecommendationRuleAdmin(admin.ModelAdmin):
    list_display = ("category", "max_combined_power", "available_index_values",
                     "recommended_index_value", "sort_order", "updated_at")
    list_filter = ("category",)
    ordering = ("category", "sort_order")


# ── Lens price table ─────────────────────────────────────────────────────────
# Read-only here: the table is maintained in Excel. "Export" downloads the
# current table; "Import" validates an uploaded file in the same layout and,
# if it has no errors, replaces the prices with it.

MAX_REPORTED = 300   # problems shown per list on the import page


@admin.register(LensPriceBlock)
class LensPriceBlockAdmin(admin.ModelAdmin):
    change_list_template = "admin/lens_workflow/lenspriceblock/change_list.html"
    list_display = ("tier", "prescription_type", "lens_type", "coating_main",
                    "coating_add_on", "lens_index", "material", "priced_cells",
                    "price_range")
    list_filter = ("tier", "prescription_type", "lens_type", "lens_index")
    search_fields = ("prescription_type", "lens_type", "coating_main",
                     "coating_add_on", "material")
    ordering = ("tier", "position")
    list_per_page = 100

    def get_queryset(self, request):
        return (super().get_queryset(request)
                .annotate(_n=Count("cells"), _lo=Min("cells__price"), _hi=Max("cells__price")))

    @admin.display(description="Priced powers", ordering="_n")
    def priced_cells(self, obj):
        return obj._n

    @admin.display(description="Price range")
    def price_range(self, obj):
        if not obj._n:
            return "no prices"
        return f"{obj._lo} - {obj._hi}" if obj._lo != obj._hi else f"{obj._lo}"

    # Prices change only through the Excel upload.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        return {}   # no site-wide "Export to Excel" action on this table

    def _can_manage(self, request):
        return request.user.has_perm("lens_workflow.import_price_table")

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name
        # Drop the site-wide generic "Import from Excel" URL (Leoptique/admin_import.py):
        # it would update individual blocks from a different layout.
        urls = [u for u in super().get_urls()
                if not (getattr(u, "name", "") or "").endswith("_import_xlsx")]
        custom = [
            path("export-prices/", self.admin_site.admin_view(self.export_view),
                 name="%s_%s_export_prices" % info),
            path("import-prices/", self.admin_site.admin_view(self.import_view),
                 name="%s_%s_import_prices" % info),
        ]
        return custom + urls

    def changelist_view(self, request, extra_context=None):
        info = self.model._meta.app_label, self.model._meta.model_name
        extra_context = extra_context or {}
        extra_context.update(
            can_manage_prices=self._can_manage(request),
            export_url=reverse("admin:%s_%s_export_prices" % info),
            import_url=reverse("admin:%s_%s_import_prices" % info),
        )
        return super().changelist_view(request, extra_context)

    def export_view(self, request):
        if not self._can_manage(request):
            messages.error(request, "You don't have permission to export the price table.")
            return redirect("admin:lens_workflow_lenspriceblock_changelist")
        data = price_table.build_workbook()
        stamp = timezone.localtime().strftime("%m%d%Y-%H%M")
        response = HttpResponse(
            data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="Eyelovewear Lens Pricing {stamp}.xlsx"'
        return response

    def import_view(self, request):
        info = self.model._meta.app_label, self.model._meta.model_name
        changelist = reverse("admin:%s_%s_changelist" % info)
        if not self._can_manage(request):
            messages.error(request, "You don't have permission to replace the price table.")
            return redirect(changelist)

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Replace the lens price table from Excel",
            "changelist_url": changelist,
            "export_url": reverse("admin:%s_%s_export_prices" % info),
            "recent_imports": LensPriceImport.objects.all()[:10],
            "max_reported": MAX_REPORTED,
        }
        if request.method == "POST":
            upload = request.FILES.get("xlsx_file")
            apply_it = request.POST.get("action") == "apply"
            if upload is None:
                context["form_error"] = "Choose an .xlsx file first."
            elif not upload.name.lower().endswith(".xlsx"):
                context["form_error"] = "The file must be an Excel workbook ending in .xlsx."
            else:
                data = upload.read()
                result = price_table.parse_workbook(io.BytesIO(data))
                context.update(
                    filename=upload.name,
                    errors=result.errors[:MAX_REPORTED],
                    error_total=len(result.errors),
                    warnings=result.warnings[:MAX_REPORTED],
                    warning_total=len(result.warnings),
                    summary=result.summary(),
                    checked=True,
                )
                if result.ok and apply_it:
                    price_table.apply_import(
                        result, user=request.user, filename=upload.name, file_bytes=data)
                    context["applied"] = True
                    context["recent_imports"] = LensPriceImport.objects.all()[:10]
        return render(request, "admin/lens_workflow/price_table_import.html", context)


@admin.register(LensPriceImport)
class LensPriceImportAdmin(admin.ModelAdmin):
    """History of uploaded price files (download one and upload it again to roll back)."""
    list_display = ("created_at", "original_filename", "uploaded_by", "warning_count", "download")
    readonly_fields = ("created_at", "original_filename", "uploaded_by", "warning_count",
                       "summary", "file")
    ordering = ("-created_at",)

    @admin.display(description="File")
    def download(self, obj):
        return format_html('<a href="{}">download</a>', obj.file.url) if obj.file else "-"

    def get_actions(self, request):
        return {}

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
