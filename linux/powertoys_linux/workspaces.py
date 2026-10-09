# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
"""Saved desktop application groups; window placement is a later backend."""

import json
import os
import tempfile
from pathlib import Path


def config_path():
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "powertoys-linux/workspaces.json"


def validate(groups):
    if not isinstance(groups, dict) or len(groups) > 100:
        raise ValueError("Workspaces must be a map of at most 100 application groups.")
    for name, ids in groups.items():
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or "\x00" in name:
            raise ValueError("Workspace names must be 1–80 characters.")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 50 or len(set(str(i) for i in ids)) != len(ids):
            raise ValueError("Select 1–50 unique desktop applications per workspace.")
        for app_id in ids:
            if not isinstance(app_id, str) or not app_id.endswith(".desktop") or any(c in app_id for c in ("/", "\x00")) or len(app_id) > 255:
                raise ValueError("Workspaces store desktop application IDs, not shell commands.")
    return groups


def load(path):
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(256001)
    except FileNotFoundError:
        return {}
    if len(data) > 256000:
        raise ValueError("Workspace configuration exceeds 256 KB.")
    try:
        document = json.loads(data)
        if not isinstance(document, dict) or document.get("version") != 1:
            raise ValueError("Unsupported workspace configuration version.")
        return validate(document.get("groups"))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValueError(f"Invalid workspace configuration in {path}: {error}") from error


def save(path, groups):
    validate(groups)
    data = json.dumps({"version": 1, "groups": groups}, indent=2, ensure_ascii=False).encode("utf-8")
    if len(data) > 256000:
        raise ValueError("Workspace configuration exceeds 256 KB.")
    # Preserve an invalid/unknown existing config rather than silently replacing it.
    load(path)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".workspaces-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
