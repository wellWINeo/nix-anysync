#!/usr/bin/env python3
"""Build every package exposed by the current native flake system."""

import json
import subprocess
import sys


class BuildError(RuntimeError):
    """Package discovery or a local package build failed."""


def run(command, *, capture_output=True):
    try:
        return subprocess.run(command, check=True, capture_output=capture_output, text=True)
    except subprocess.CalledProcessError as error:
        diagnostic = f"{command[0]} command failed (exit {error.returncode}): {' '.join(command[1:])}"
        if error.stderr:
            diagnostic += f"\n{error.stderr.rstrip()}"
        raise BuildError(diagnostic) from None


def current_system():
    system = run(["nix", "eval", "--impure", "--raw", "--expr", "builtins.currentSystem"]).stdout.strip()
    if not system:
        raise BuildError("Nix returned an empty current system")
    return system


def package_names(system):
    raw = run(["nix", "eval", "--json", f".#packages.{system}", "--apply", "builtins.attrNames"]).stdout
    try:
        names = json.loads(raw)
    except json.JSONDecodeError as error:
        raise BuildError("Nix returned invalid package-name JSON") from error
    if (not isinstance(names, list) or not names
            or any(not isinstance(name, str) or not name for name in names)
            or len(names) != len(set(names))):
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
