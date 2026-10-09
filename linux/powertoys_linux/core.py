# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Desktop-independent operations. Never overwrite a user's existing file."""

import base64
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote


MAX_TEXT_BYTES = 2_000_000


def fingerprint(path):
    info = Path(path).lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Select regular files; folders and symbolic links are not supported yet.")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


@dataclass(frozen=True)
class Rename:
    source: Path
    target: Path
    identity: tuple


def rename_plan(paths, search, replacement, case_sensitive=False, stem_only=True, all_matches=True):
    if not search or "\x00" in search:
        raise ValueError("Enter a non-empty search string without NUL characters.")
    if any(c in replacement for c in ("/", "\x00")):
        raise ValueError("Replacement must not contain a slash or NUL character.")
    pattern = re.compile(re.escape(search), 0 if case_sensitive else re.IGNORECASE)
    result = []
    seen = set()
    for value in paths:
        source = Path(os.path.abspath(value))
        if source in seen:
            raise ValueError("The same file was selected twice.")
        seen.add(source)
        identity = fingerprint(source)
        name = source.stem if stem_only else source.name
        name = pattern.sub(lambda _: replacement, name, count=0 if all_matches else 1)
        if stem_only:
            name += source.suffix
        if name in ("", ".", "..") or len(os.fsencode(name)) > 255:
            raise ValueError("A resulting filename is empty, reserved, or too long.")
        target = source.with_name(name)
        if target != source:
            result.append(Rename(source, target, identity))
    validate_plan(result)
    return result


def validate_plan(plan):
    sources = set()
    targets = set()
    for entry in plan:
        if entry.source in sources or entry.target in targets:
            raise ValueError("Two selected files would have the same filename.")
        sources.add(entry.source)
        targets.add(entry.target)
        if entry.source.parent != entry.target.parent:
            raise ValueError("Renaming cannot move files to another folder.")
        if fingerprint(entry.source) != entry.identity:
            raise ValueError(f"File changed since preview: {entry.source.name}. Preview again.")
        if os.path.lexists(entry.target):
            raise FileExistsError(f"Already exists: {entry.target.name}")


def apply_renames(plan):
    """Reserve targets without clobbering. Return an inverse plan for session undo.

    All links are created before removing any source name. A link failure leaves
    original names intact. If unlink fails, both names remain for recovery.
    Hard-link-capable local filesystems are required; this isn't crash atomic.
    """
    validate_plan(plan)
    created = []
    try:
        for entry in plan:
            os.link(entry.source, entry.target, follow_symlinks=False)
            created.append(entry)
        for entry in plan:
            if fingerprint(entry.source) != entry.identity or fingerprint(entry.target) != entry.identity:
                raise ValueError("A file changed during rename. No original names were removed.")
    except Exception:
        for entry in reversed(created):
            entry.target.unlink()
        raise
    for entry in plan:
        try:
            entry.source.unlink()
        except OSError as error:
            raise OSError(f"Rename interrupted; all files remain at their new names, and some old names remain. Inspect the folder: {error}") from error
    return [Rename(e.target, e.source, fingerprint(e.target)) for e in plan]


def resize_dimensions(width, height, bound_width, bound_height, shrink_only=True):
    if min(width, height, bound_width, bound_height) <= 0:
        raise ValueError("Image dimensions must be positive.")
    if max(bound_width, bound_height) > 16384:
        raise ValueError("Output dimensions must be at most 16384 pixels.")
    scale = min(bound_width / width, bound_height / height)
    if shrink_only:
        scale = min(scale, 1)
    return max(1, round(width * scale)), max(1, round(height * scale))


TEXT_ACTIONS = ("Format JSON", "Uppercase", "Lowercase", "Trim lines", "Base64 encode", "Base64 decode", "URL encode", "URL decode")


def transform_text(value, action):
    if len(value.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError("Text is limited to 2 MB.")
    if action == "Format JSON":
        return json.dumps(json.loads(value), indent=2, ensure_ascii=False)
    if action == "Uppercase":
        return value.upper()
    if action == "Lowercase":
        return value.lower()
    if action == "Trim lines":
        return "\n".join(line.strip() for line in value.splitlines())
    if action == "Base64 encode":
        return base64.b64encode(value.encode("utf-8")).decode("ascii")
    if action == "Base64 decode":
        return base64.b64decode(value, validate=True).decode("utf-8")
    if action == "URL encode":
        return quote(value, safe="")
    if action == "URL decode":
        return unquote(value, errors="strict")
    raise ValueError("Unknown text operation.")
