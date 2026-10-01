# Data migration: brief is meant to be plain text, and BlogInfo.save() has
# stripped HTML from it on every save since the 0003/0004 model changes —
# but rows written before that still have raw tags sitting in the stored
# string (e.g. "<p>Some text<br>"), which show up as literal angle
# brackets now that the frontend renders brief as plain text instead of
# (wrongly) as HTML. One-time cleanup for existing rows only; nothing
# about this needs to run again.
from django.db import migrations

from Blog.models import strip_html_to_text


def strip_brief_html(apps, schema_editor):
    BlogInfo = apps.get_model('Blog', 'BlogInfo')
    for blog in BlogInfo.objects.exclude(brief__isnull=True).exclude(brief=''):
        cleaned = strip_html_to_text(blog.brief)
        if cleaned != blog.brief:
            blog.brief = cleaned
            blog.save(update_fields=['brief'])


def noop_reverse(apps, schema_editor):
    # Not reversible — the original markup isn't worth restoring.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('Blog', '0004_blogpreview'),
    ]

    operations = [
        migrations.RunPython(strip_brief_html, noop_reverse),
    ]
