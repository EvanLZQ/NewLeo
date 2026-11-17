"""Every third-party module the project imports must be in requirements.txt.

The Docker image installs only requirements.txt, so a package that happens to
be present in a developer's virtualenv (PyYAML for the lens price importer was
one) would make the production image crash at start-up.
"""
import ast
import importlib.util
import inspect
import os
import re
import sys
import sysconfig
from importlib.metadata import distributions
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BASE_DIR = Path(settings.BASE_DIR)
SKIP_DIRS = {"static", "staticfiles", "templates", "nginx", "node_modules", "private_media"}


def _packages_distributions():
    """module -> [distribution] (importlib.metadata.packages_distributions is 3.10+; the image runs 3.9)."""
    mapping = {}
    for dist in distributions():
        tops = (dist.read_text("top_level.txt") or "").split()
        if not tops:
            for f in dist.files or []:
                if f.parts[0].endswith((".dist-info", ".egg-info")) or f.parts[0] == "..":
                    continue
                tops.append(f.parts[0] if len(f.parts) > 1 else inspect.getmodulename(f.parts[0]) or "")
        for top in set(filter(None, tops)):
            mapping.setdefault(top, []).append(dist.metadata["Name"])
    return mapping


def _is_stdlib(mod):
    if hasattr(sys, "stdlib_module_names"):
        return mod in sys.stdlib_module_names
    if mod in sys.builtin_module_names:
        return True
    spec = importlib.util.find_spec(mod)
    if spec is None or not spec.origin:
        return False
    if spec.origin in ("built-in", "frozen"):
        return True
    origin = os.path.realpath(spec.origin)
    stdlib = os.path.realpath(sysconfig.get_paths()["stdlib"])
    return origin.startswith(stdlib) and "site-packages" not in origin


def _norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared():
    names = set()
    for line in (BASE_DIR / "requirements.txt").read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.add(_norm(re.split(r"[\[<>=!~; ]", line, 1)[0]))
    # psycopg2-binary is the local stand-in for psycopg2
    if "psycopg2" in names:
        names.add("psycopg2-binary")
    return names


def _project_files():
    for path in BASE_DIR.rglob("*.py"):
        rel = path.relative_to(BASE_DIR)
        if rel.parts[0].startswith(".") or rel.parts[0] in SKIP_DIRS or "site-packages" in rel.parts:
            continue
        yield path


def _top_level_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


class RequirementsDeclareImportsTests(SimpleTestCase):
    def test_every_third_party_import_is_in_requirements(self):
        local = {p.name for p in BASE_DIR.iterdir() if p.is_dir()} | {p.stem for p in BASE_DIR.glob("*.py")}
        dists = _packages_distributions()
        declared = _declared()
        missing = {}
        for path in _project_files():
            for mod in _top_level_imports(path):
                if mod in local or _is_stdlib(mod) or mod == "__future__":
                    continue
                providers = {_norm(d) for d in dists.get(mod, [])}
                if not providers:
                    missing.setdefault(mod, set()).add(str(path.relative_to(BASE_DIR)))
                    continue
                if not providers & declared:
                    missing.setdefault(mod, set()).add(str(path.relative_to(BASE_DIR)))
        self.assertEqual(missing, {}, "imported but not declared in requirements.txt")
