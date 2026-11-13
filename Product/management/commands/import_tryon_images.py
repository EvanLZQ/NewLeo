"""Bulk-import transparent try-on cut-outs as ProductImage(image_type='tryon').

Usage:
    python manage.py import_tryon_images /path/to/tryon-assets [--dry-run] [--replace]

File naming (both forms may be mixed in one directory tree):
  * <SKU>.png / <SKU>.webp anywhere in the tree, e.g. 1085-BLK-001.png.
    Matching is case-insensitive.
  * <model_number>/<colour>.png, e.g. 1085/Black.png or
    1085/tortoiseshell.webp. The colour is compared with the colour's
    display name, ignoring case, spaces, '-', '_' and '&'/'and'.

Without --replace a colour that already has a try-on image is skipped, so
the command is safe to re-run. With --replace the old try-on rows of the
matched colours are deleted (their files are removed from storage too) and
the new file is stored instead. Nothing else is touched.

Images must open with Pillow. Images without an alpha channel are refused,
since a try-on image with a background would cover the shopper's face.
"""
import os
import re
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image

from Product.models import ProductImage, ProductInstance

EXTENSIONS = {'.png', '.webp'}


def normalise_colour(name):
    name = name.lower().replace('&', 'and')
    return re.sub(r'[\s\-_]+', '', name)


def has_alpha(path):
    with Image.open(path) as im:
        im.load()
        if im.mode in ('RGBA', 'LA', 'PA'):
            return im.getextrema()[-1][0] < 255
        if im.mode == 'P' and 'transparency' in im.info:
            return True
        return False


def match_files(root, instances):
    """Return (matches, unmatched): matches is a list of (path, instance)."""
    by_sku = {inst.sku.lower(): inst for inst in instances}
    by_model_colour = {}
    for inst in instances:
        if inst.product is None:
            continue
        key = (inst.product.model_number.lower(),
               normalise_colour(inst.color_display_name))
        by_model_colour.setdefault(key, inst)

    matches, unmatched = [], []
    for path in sorted(Path(root).rglob('*')):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        stem = path.stem
        inst = by_sku.get(stem.lower())
        if inst is None and path.parent != Path(root):
            inst = by_model_colour.get(
                (path.parent.name.lower(), normalise_colour(stem)))
        if inst is None:
            unmatched.append(path)
        else:
            matches.append((path, inst))
    return matches, unmatched


class Command(BaseCommand):
    help = ("Import transparent PNG/WebP try-on images named by SKU "
            "(or <model_number>/<colour>) as ProductImage type 'tryon'.")

    def add_arguments(self, parser):
        parser.add_argument('directory')
        parser.add_argument('--dry-run', action='store_true',
                            help='Only report what would happen.')
        parser.add_argument('--replace', action='store_true',
                            help='Replace existing try-on images of matched colours.')

    def handle(self, directory, dry_run=False, replace=False, **options):
        if not os.path.isdir(directory):
            raise CommandError(f'Not a directory: {directory}')

        instances = list(ProductInstance.objects.select_related('product'))
        matches, unmatched = match_files(directory, instances)

        seen = {}
        for path, inst in matches:
            if inst.pk in seen:
                raise CommandError(
                    f'Two files map to {inst.sku}: {seen[inst.pk]} and {path}')
            seen[inst.pk] = path

        created = replaced = skipped = refused = 0
        for path, inst in matches:
            label = f'{path.name} -> {inst.sku}'
            try:
                if not has_alpha(path):
                    refused += 1
                    self.stderr.write(f'REFUSED (no transparency) {label}')
                    continue
            except Exception as exc:  # unreadable / not an image
                refused += 1
                self.stderr.write(f'REFUSED (cannot open: {exc}) {label}')
                continue

            existing = list(inst.productImage.filter(image_type='tryon'))
            if existing and not replace:
                skipped += 1
                self.stdout.write(f'skip (already has try-on) {label}')
                continue
            if dry_run:
                self.stdout.write(
                    f'would {"replace" if existing else "add"} {label}')
                if existing:
                    replaced += 1
                else:
                    created += 1
                continue

            with transaction.atomic():
                for old in existing:
                    old.image.delete(save=False)
                    old.delete()
                img = ProductImage(
                    productInstance=inst, image_type='tryon',
                    alt=f'{inst.sku} try-on')
                with open(path, 'rb') as fh:
                    img.image.save(f'tryon_{inst.sku}{path.suffix.lower()}',
                                   File(fh), save=True)
            if existing:
                replaced += 1
            else:
                created += 1
            self.stdout.write(f'{"replaced" if existing else "added"} {label}')

        for path in unmatched:
            self.stderr.write(f'UNMATCHED {path}')

        missing = [inst.sku for inst in instances
                   if inst.online and inst.pk not in seen
                   and not inst.productImage.filter(image_type='tryon').exists()]
        if missing:
            self.stdout.write(
                f'{len(missing)} online colour(s) still without a try-on image: '
                + ', '.join(sorted(missing)))

        prefix = '[dry run] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}added {created}, replaced {replaced}, '
            f'skipped {skipped}, refused {refused}, unmatched {len(unmatched)}'))
