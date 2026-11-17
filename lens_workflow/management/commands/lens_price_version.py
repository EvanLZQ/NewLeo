import os

from django.core.management.base import BaseCommand, CommandError

from lens_workflow.models import PriceTableVersion
from lens_workflow.pricing_v2 import importer


class Command(BaseCommand):
    help = "List, activate or roll back lens price versions (pricing v2). Nothing is ever deleted."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["list", "activate", "rollback", "show"])
        parser.add_argument("version_id", nargs="?", type=int)
        parser.add_argument("--user", default=os.environ.get("USER", ""))

    def handle(self, *args, action, version_id, user, **opts):
        if action == "list":
            for v in PriceTableVersion.objects.order_by("id"):
                self.stdout.write(
                    f"{v.pk:4}  {v.status:8}  {v.label}  sha={v.file_sha256[:10]}  "
                    f"imported={v.created_at:%Y-%m-%d %H:%M} by {v.imported_by or '-'}  "
                    f"activated={v.activated_at:%Y-%m-%d %H:%M}" if v.activated_at else
                    f"{v.pk:4}  {v.status:8}  {v.label}  sha={v.file_sha256[:10]}  "
                    f"imported={v.created_at:%Y-%m-%d %H:%M} by {v.imported_by or '-'}")
            return
        if action == "rollback":
            try:
                v = importer.rollback(user=user)
            except ValueError as exc:
                raise CommandError(str(exc))
            self.stdout.write(self.style.SUCCESS(f"rolled back: version {v.pk} ({v.label}) is ACTIVE"))
            return
        if version_id is None:
            raise CommandError("version_id is required")
        try:
            v = PriceTableVersion.objects.get(pk=version_id)
        except PriceTableVersion.DoesNotExist:
            raise CommandError(f"no version {version_id}")
        if action == "show":
            r = v.report or {}
            self.stdout.write(f"{v} blocks={v.blocks.count()} overrides={len(v.overrides)} "
                              f"warnings={len(r.get('warnings', []))} diff={((r.get('diff') or {}).get('summary'))}")
            return
        importer.activate(v, user=user)
        self.stdout.write(self.style.SUCCESS(f"version {v.pk} ({v.label}) is ACTIVE"))
