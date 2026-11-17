import os

from django.core.management.base import BaseCommand, CommandError

from lens_workflow.pricing_v2 import importer

DEFAULT_OVERRIDES = os.path.join(os.path.dirname(__file__), "..", "..", "data", "price_overrides.yaml")


class Command(BaseCommand):
    help = ("Import a lens price file (price_v2.xlsx layout) as a new DRAFT price version. "
            "--dry-run only checks and writes the report. Nothing goes live until "
            "`lens_price_version activate <id>` (or --activate).")

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--overrides", default=DEFAULT_OVERRIDES,
                            help="YAML file of cell overrides (default: lens_workflow/data/price_overrides.yaml); "
                                 "pass '' for none")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--label", default="")
        parser.add_argument("--notes", default="")
        parser.add_argument("--user", default=os.environ.get("USER", ""))
        parser.add_argument("--report-dir", default="", help="write report.json / *.csv / summary.md here")
        parser.add_argument("--activate", action="store_true", help="activate the new version right away")
        parser.add_argument("--quiet-warnings", action="store_true")

    def handle(self, *args, path, overrides, dry_run, label, notes, user, report_dir, activate,
               quiet_warnings, **opts):
        try:
            data = open(path, "rb").read()
        except OSError as exc:
            raise CommandError(f"cannot read {path}: {exc}")
        ov = importer.load_overrides(overrides) if overrides else []
        name = os.path.basename(path)
        if dry_run:
            result, report = importer.dry_run(data, name, ov)
        else:
            try:
                version, report = importer.import_file(data, name, ov, label=label, user=user, notes=notes)
                result = None
            except importer.ImportRefused as exc:
                result, report = exc.result, exc.report
        if report_dir:
            importer.write_report(report, report_dir)
            self.stdout.write(f"report written to {report_dir}")
        if not quiet_warnings:
            for w in report["warnings"]:
                self.stdout.write(self.style.WARNING(f"warning {w['sheet']}!{w['cell']}: {w['message']}"))
        for e in report["errors"]:
            self.stdout.write(self.style.ERROR(f"error   {e['sheet']}!{e['cell']}: {e['message']}"))
        d = report.get("diff") or {}
        self.stdout.write(f"blocks: {report['blocks']}  lines: {report['lines']}  "
                          f"warnings: {len(report['warnings'])}  errors: {len(report['errors'])}")
        self.stdout.write(f"overrides applied: {len(report['overrides_applied'])}  "
                          f"compared with: {report['compared_with']}  changes: {d.get('summary')}")
        if report["errors"]:
            raise CommandError(f"{len(report['errors'])} error(s); nothing was saved.")
        if dry_run:
            self.stdout.write("Dry run: nothing was saved.")
            return
        self.stdout.write(self.style.SUCCESS(f"saved as DRAFT version {version.pk} ({version.label})"))
        if activate:
            importer.activate(version, user=user)
            self.stdout.write(self.style.SUCCESS(f"version {version.pk} is now ACTIVE"))
        else:
            self.stdout.write(f"activate with: python manage.py lens_price_version activate {version.pk}")
