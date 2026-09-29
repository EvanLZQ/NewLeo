from django.conf import settings
from django.contrib import admin

from .models import BlogInfo


class BlogInfoAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'slug', 'created_at', 'updated_at')
    list_filter = ('category',)
    search_fields = ('title', 'category', 'slug')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    # JS-only convenience — auto-fills the slug field from the title as the
    # editor types. The model's save() (see models.py) is the real
    # safety net: it fills in a slug even if this never ran (JS disabled,
    # field cleared by hand, API write, ...).
    prepopulated_fields = {'slug': ('title',)}
    change_form_template = "admin/Blog/change_form.html"

    def _add_preview_context(self, extra_context):
        extra_context = dict(extra_context or {})
        extra_context['frontend_base_url'] = settings.FRONTEND_BASE_URL
        return extra_context

    def add_view(self, request, form_url='', extra_context=None):
        return super().add_view(request, form_url, self._add_preview_context(extra_context))

    def change_view(self, request, object_id, form_url='', extra_context=None):
        return super().change_view(
            request, object_id, form_url, self._add_preview_context(extra_context))


admin.site.register(BlogInfo, BlogInfoAdmin)
