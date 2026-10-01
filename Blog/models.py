import html
import re
import uuid

import bleach
from bleach.css_sanitizer import CSSSanitizer
from django.db import models
from django.utils.text import slugify
from tinymce.models import HTMLField

# ── HTML sanitization ────────────────────────────────────────────────────────
# `content` is edited by staff through TinyMCE, but "staff who can edit a
# blog post" isn't the same trust level as "can run arbitrary JS on every
# visitor's browser" — sanitize on save so a compromised/careless editor
# account (or a future multi-author workflow) can't stored-XSS the public
# blog. Kept close to what the TINYMCE_DEFAULT_CONFIG toolbar can actually
# produce (see Leoptique/settings.py) rather than a generic allowlist.
BLOG_ALLOWED_TAGS = [
    "p", "br", "div", "span", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s", "strike", "sub", "sup",
    "blockquote", "pre", "code",
    "ul", "ol", "li",
    "a", "img", "figure", "figcaption",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
]
BLOG_ALLOWED_ATTRS = {
    "*": ["class", "style"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}
BLOG_ALLOWED_CSS = [
    "color", "background-color", "text-align", "font-weight", "font-style",
    "text-decoration", "font-size", "width", "height",
]
_css_sanitizer = CSSSanitizer(allowed_css_properties=BLOG_ALLOWED_CSS)


def sanitize_blog_html(raw_html):
    if not raw_html:
        return raw_html
    return bleach.clean(
        raw_html,
        tags=BLOG_ALLOWED_TAGS,
        attributes=BLOG_ALLOWED_ATTRS,
        css_sanitizer=_css_sanitizer,
        strip=True,
    )


def strip_html_to_text(raw_html):
    """
    `brief` is meant to be plain text — used for `brief` on save, and for
    one-time cleanup of legacy rows saved before this existed (see
    migration 0005). Regex-strips every tag rather than bleach.clean(tags=
    []): bleach drops tags but doesn't insert a separator, so e.g.
    "<p>A</p><p>B</p>" collapses to "AB" with the paragraph break silently
    eaten — a space keeps it "A B" instead. Tag removal is complete and
    doesn't need bleach's more careful allowlist handling the way real
    HTML output does, since nothing here is ever re-rendered as HTML.
    """
    if not raw_html:
        return raw_html
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


class BlogInfo(models.Model):
    title = models.CharField(max_length=100)
    category = models.CharField(max_length=150, default="Other", db_index=True)
    slug = models.SlugField(max_length=200, unique=True, null=True, blank=True)
    content = HTMLField()
    sub_title = models.CharField(max_length=200, blank=True, null=True)
    brief = models.TextField(blank=True, null=True)
    home_page_img = models.ImageField(
        upload_to='blog_images/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Auto-generate a slug from the title when the editor leaves it
        # blank — previously a blank slug shipped straight through to the
        # frontend's /blogs/<slug> links as the literal string "null".
        # Uniqueness is enforced by suffixing -2, -3, ... on collision
        # (matches the model's `unique=True`, which would otherwise raise
        # an IntegrityError on save instead of failing loudly earlier).
        if not self.slug:
            base_slug = slugify(self.title)[:200] or "post"
            candidate = base_slug
            suffix = 2
            qs = BlogInfo.objects.exclude(pk=self.pk)
            while qs.filter(slug=candidate).exists():
                suffix_str = f"-{suffix}"
                candidate = f"{base_slug[:200 - len(suffix_str)]}{suffix_str}"
                suffix += 1
            self.slug = candidate

        # `brief` is a plain-text summary (rendered as text, not HTML, on
        # the frontend) — strip any markup a paste might have carried in.
        if self.brief:
            self.brief = strip_html_to_text(self.brief)

        self.content = sanitize_blog_html(str(self.content))

        super().save(*args, **kwargs)

    class Meta:
        db_table = 'BlogInfo'
        verbose_name = 'Blog'
        verbose_name_plural = 'Blogs'


class BlogPreview(models.Model):
    """
    A short-lived, unsaved draft snapshot powering the admin's side-by-side
    mobile/desktop preview panel (see templates/admin/Blog/change_form.html
    and static/admin/js/blog-preview.js). Deliberately NOT tied to a real
    BlogInfo row — previewing a brand-new, not-yet-saved post has to work
    too — and keyed by a client-generated token so repeated "Refresh
    Preview" clicks during one editing session overwrite the same row
    instead of piling up. The public frontend's hidden preview route reads
    this by token (see Blog/views.py getBlogPreview) so what the admin sees
    in the two iframes is rendered by the exact same React component the
    live site uses, not a separate lookalike.
    """
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    title = models.CharField(max_length=100, blank=True)
    category = models.CharField(max_length=150, blank=True, default="Other")
    sub_title = models.CharField(max_length=200, blank=True, null=True)
    content = models.TextField(blank=True)
    brief = models.TextField(blank=True, null=True)
    # Plain URL, not an ImageField — the preview payload just carries
    # whatever image is currently showing in the admin form (either the
    # already-uploaded home_page_img of an existing post, or a TinyMCE
    # inline image URL), never a fresh file upload of its own.
    home_page_img_url = models.URLField(blank=True, null=True, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.content:
            self.content = sanitize_blog_html(self.content)
        if self.brief:
            self.brief = strip_html_to_text(self.brief)
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'BlogPreview'
