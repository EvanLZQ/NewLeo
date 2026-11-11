"""Move prescription uploads out of public MEDIA_ROOT into PRIVATE_MEDIA_ROOT.

PR #6's first version saved uploads to MEDIA_ROOT/prescription_uploads/,
which nginx serves publicly under /media/. This moves every such file to the
same relative path under PRIVATE_MEDIA_ROOT and deletes the public copy.
The stored FileField name ("prescription_uploads/YYYY/MM/<hex>.<ext>") is
unchanged, so no database rows need rewriting.

Idempotent: safe to run again (migration 0012 and the management command
`move_prescription_uploads_private` both call it).
"""
import os
import shutil

PUBLIC_SUBDIR = "prescription_uploads"


def _ensure_private_dir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)


def move_public_uploads_to_private(media_root, private_root, log=None):
    """Return (moved, removed_duplicates) counts."""
    log = log or (lambda msg: None)
    public_dir = os.path.join(media_root, PUBLIC_SUBDIR)
    moved = duplicates = 0
    if not media_root or not os.path.isdir(public_dir):
        return moved, duplicates
    if os.path.abspath(private_root) == os.path.abspath(media_root):
        raise RuntimeError("PRIVATE_MEDIA_ROOT must not be MEDIA_ROOT")
    for dirpath, dirnames, filenames in os.walk(public_dir, topdown=False):
        for filename in filenames:
            src = os.path.join(dirpath, filename)
            rel = os.path.relpath(src, media_root)
            dst = os.path.join(private_root, rel)
            _ensure_private_dir(os.path.dirname(dst))
            if os.path.exists(dst):
                os.remove(src)
                duplicates += 1
                log(f"removed public duplicate {rel}")
            else:
                shutil.move(src, dst)
                moved += 1
                log(f"moved {rel}")
            try:
                os.chmod(dst, 0o600)
            except OSError:
                pass
        try:
            os.rmdir(dirpath)  # only succeeds when empty
        except OSError:
            pass
    return moved, duplicates
