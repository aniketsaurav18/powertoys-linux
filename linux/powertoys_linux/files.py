# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Unprivileged file preview and open-file inspection backends."""

import os
from pathlib import Path

from .core import fingerprint


def copy_template(source, folder, name):
    if not name or name in (".", "..") or any(c in name for c in ("/", "\x00")):
        raise ValueError("Enter a filename without slashes or NUL characters.")
    if len(os.fsencode(name)) > 255:
        raise ValueError("The filename is too long.")
    identity = fingerprint(source)
    if identity[2] > 50_000_000:
        raise ValueError("Templates are limited to 50 MB.")
    target = Path(folder) / name
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as output, Path(source).open("rb") as template:
            count = 0
            while data := template.read(65536):
                count += len(data)
                if count > 50_000_000:
                    raise ValueError("Template grew beyond the 50 MB limit.")
                output.write(data)
            if fingerprint(source) != identity:
                raise ValueError("Template changed during copying. Try again.")
    except Exception:
        target.unlink()
        raise
    return target


def text_preview(path, limit=200_000):
    fingerprint(path)
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    truncated = len(data) > limit
    data = data[:limit]
    if b"\x00" in data:
        raise ValueError("Binary files cannot be shown as text.")
    # An incomplete final Unicode codepoint is permitted only at the size limit.
    import codecs
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    try:
        text = decoder.decode(data, final=not truncated)
    except UnicodeError as error:
        raise ValueError("This preview supports UTF-8 text, PNG and JPEG images.") from error
    if truncated:
        text += "\n\n[Preview truncated at 200 KB]"
    return text


def open_file_processes(path, proc_root=Path("/proc")):
    identity = fingerprint(path)[:2]
    matches = []
    inaccessible = 0
    for process in Path(proc_root).iterdir():
        if not process.name.isdecimal():
            continue
        try:
            descriptors = list((process / "fd").iterdir())
        except PermissionError:
            inaccessible += 1
            continue
        except OSError:
            continue
        found = False
        for descriptor in descriptors:
            try:
                info = descriptor.stat()
                if (info.st_dev, info.st_ino) == identity:
                    found = True
                    break
            except OSError:
                continue
        if found:
            try:
                name = (process / "comm").read_text()[:200].strip()
            except OSError:
                name = "Unknown process"
            matches.append((int(process.name), name))
    return sorted(matches), inaccessible
