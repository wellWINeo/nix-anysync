#!/usr/bin/env python3
"""Build every package exposed by the current native flake system."""

import importlib.util
from pathlib import Path
import sys

_SPEC = importlib.util.spec_from_file_location("cache_publish", Path(__file__).with_name("cache-publish.py"))
publish = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(publish)


class BuildError(RuntimeError):
    """Package discovery or a local package build failed."""


def run(command, *, capture_output=True):
    try:
        return publish._run(command, capture=capture_output)
    except publish.PublishError as error:
        diagnostic = str(error)
        if error.stderr:
            diagnostic += f"\n{error.stderr.rstrip()}"
        raise BuildError(diagnostic) from None

def current_system():
    system = run(["nix", "eval", "--impure", "--raw", "--expr", "builtins.currentSystem"]).stdout.strip()
    if not system:
        raise BuildError("Nix returned an empty current system")
    return system

def package_names(system):
    try:
        names = publish.discover_packages(system)
    except publish.PublishError as error:
        diagnostic = str(error)
        if error.stderr:
            diagnostic += f"\n{error.stderr.rstrip()}"
        raise BuildError(diagnostic) from None
    if not names:
        raise BuildError("Nix returned an empty or invalid package-name list")
    return names

def build_all():
    system = current_system()
    for name in package_names(system):
        run(["nix", "build", f".#{name}"], capture_output=False)


def main():
    try:
        build_all()
    except BuildError as error:
        print(f"build-all: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
