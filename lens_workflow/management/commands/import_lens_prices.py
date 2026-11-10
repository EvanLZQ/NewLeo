import io
import os

from django.core.management.base import BaseCommand, CommandError

from lens_workflow import price_table


class Command(BaseCommand):
    help = ("Load the lens price table from an Excel file (same as the admin's "
            "'Replace prices from Excel'). Prints every problem with its sheet and cell. "
            "Re-running replaces only the sheets in the file; it is safe to run again.")

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to the .xlsx file")
        parser.add_argument("--dry-run", action="store_true", help="Only check the file")

    def handle(self, *args, path, dry_run, **options):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError as exc:
            raise CommandError(f"Cannot read {path}: {exc}")
        result = price_table.parse_workbook(io.BytesIO(data))
        for w in result.warnings:
            self.stdout.write(self.style.WARNING(f"warning  {w.sheet} {w.cell}: {w.message}"))
        for e in result.errors:
            self.stdout.write(self.style.ERROR(f"error    {e.sheet} {e.cell}: {e.message}"))
        if not result.ok:
            raise CommandError(f"{len(result.errors)} error(s); nothing was changed.")
        self.stdout.write(f"{len(result.warnings)} warning(s). Summary: {result.summary()}")
        if dry_run:
            self.stdout.write("Dry run: nothing was changed.")
            return
        price_table.apply_import(result, filename=os.path.basename(path), file_bytes=data)
        self.stdout.write(self.style.SUCCESS("Price table replaced."))
