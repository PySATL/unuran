"""Build the UNU.RAN C library for use in PySATL (https://github.com/PySATL/pysatl-core).

Orchestrates the full build pipeline:
  1. get_and_clean_unuran.py  — download the tarball, strip unneeded directories
     (tests, docs, examples, src/uniform), rename .ch→.h, replace the URNG
     back-end with the NumPy-compatible urng_default_mod.c, normalise line endings.
  2. Write a stub config.h to satisfy ``#include <config.h>`` in the UNU.RAN
     sources (all real defines are passed as Meson compiler flags).
  3. meson setup <build_dir> && meson compile -C <build_dir>
     Produces out/libunuran.a and out/libunuran.so / .dylib.

Invoked automatically by _cffi_build.py (the Poetry build hook defined in
pyproject.toml) when the compiled library is missing.  The CFFI extension
_unuran_cffi, imported by pysatl_core.sampling.unuran, is then linked against
the resulting library.

Usage::

    python build_unuran.py [--unuran-version VERSION] [--build-dir DIR]

--unuran-version  UNU.RAN release to fetch (default: 1.11.0).
--build-dir       Meson build directory relative to this file (default: out).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import logging
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
CONFIG_H = """#ifndef UNURAN_CONFIG_H_GENERATED
            #define UNURAN_CONFIG_H_GENERATED

            /* Meson-driven build: configuration macros are provided via compiler
            * definitions in meson.build (unuran_defines). This header exists only
            * to satisfy '#include <config.h>' from the original sources. */

            #endif /* UNURAN_CONFIG_H_GENERATED */
            """


def run_cmd(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run get_and_clean_unuran.py, normalize sources, and run Meson."
    )
    parser.add_argument(
        "--unuran-version",
        default="1.11.0",
        help="UNU.RAN version to fetch (default: %(default)s)",
    )
    parser.add_argument(
        "--build-dir",
        default="out",
        help="Meson build directory (default: %(default)s)",
    )
    args = parser.parse_args()

    get_script = REPO_ROOT / "get_and_clean_unuran.py"
    if not get_script.exists():
        raise SystemExit("get_and_clean_unuran.py is missing.")

    run_cmd([sys.executable, str(get_script), "--unuran-version", args.unuran_version])

    config_path = REPO_ROOT / "config.h"
    config_path.write_text(CONFIG_H)

    run_cmd(["meson", "setup", args.build_dir])
    run_cmd(["meson", "compile", "-C", args.build_dir])


if __name__ == "__main__":
    main()
