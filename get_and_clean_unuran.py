"""Download the UNU.RAN library and clean it for use in PySATL."""

import os
import re
import argparse
import gzip
import logging
import pathlib
import platform
import urllib.request
import shutil
import tarfile
import zipfile
import tempfile
import datetime

logging.basicConfig()
logger = logging.getLogger("get-and-clean-unuran")

def _normalize_version(tag: str) -> str:
    match = re.match(r"\d+(?:\.\d+)*", tag.strip())
    if not match:
        raise ValueError(f"Unsupported UNU.RAN version string: {tag!r}")
    return match.group(0)

def _download_unuran(version: str) -> None:
    # base is where this script is located
    base = pathlib.Path(__file__).parent
    UNURAN_VERSION = _normalize_version(version)
    archive_name = f"unuran-{UNURAN_VERSION}"
    suffix = "tar.gz"

    # some version need zip files for windows
    # see http://statmath.wu.ac.at/src/ for a list of such files
    winversions = ["0.5.0", "0.6.0", "1.0.1", "1.1.0", "1.2.0"]

    # 32-bit windows has different file name
    # see http://statmath.wu.ac.at/src/ for a list of such files
    is_win32: bool = platform.system() == "Windows" and platform.architecture()[0] == "32bit"

    # replace suffix for windows if the version is in winversion.
    if platform.system() == "Windows" and UNURAN_VERSION in winversions:
        archive_name += "-win"
        if is_win32 and UNURAN_VERSION in winversions[2:]:
            archive_name += "32"
        suffix = "zip"
    
    # download url
    url = f"http://statmath.wu.ac.at/src/{archive_name}.{suffix}"

    # Start download
    logger.info(f" Downloading UNU.RAN version {UNURAN_VERSION} from {url}")
    start = datetime.datetime.now()
    
    with urllib.request.urlopen(url) as response:
        if suffix == "tar.gz":
            with gzip.GzipFile(fileobj=response) as uncompressed, tempfile.NamedTemporaryFile(delete=False, suffix=".tar") as ntf:
                logger.info(f" Saving UNU.RAN tarball to {ntf.name}")
                shutil.copyfileobj(uncompressed, ntf)
                ntf_path = ntf.name
            
            logger.info(" Starting to extract tar.gz")
            with tempfile.TemporaryDirectory() as tmpdir:
                dst = pathlib.Path(tmpdir)
                with tarfile.open(ntf_path, "r") as tar:
                    tar.extractall(path=dst)
                
                if (base / "unuran").exists():
                    shutil.rmtree(base / "unuran")
                shutil.move(dst / archive_name, base / "unuran")
            os.remove(ntf_path)
            
        else:
            with tempfile.TemporaryDirectory() as tmpdir:
                dst = pathlib.Path(tmpdir)
                with zipfile.ZipFile(response, "r") as zip_ref:
                    zip_ref.extractall(path=dst)
                if (base / "unuran").exists():
                    shutil.rmtree(base / "unuran")
                shutil.move(dst / archive_name, base / "unuran")

    logger.info(f" Finished download and extraction in {datetime.datetime.now() - start}")

    # Cleanup unwanted files/dirs
    unuran_dir = base / "unuran"
    files_to_move = [("README", "UNURAN_README.txt"), ("README.win32", "UNURAN_README_win32.txt"),
                     ("ChangeLog", "UNURAN_ChangeLog"), ("AUTHORS", "UNURAN_AUTHORS")]
    for src, target in files_to_move:
        if (unuran_dir / src).exists():
            shutil.move(unuran_dir / src, base / target)

    dirs_to_remove = ["src/uniform", "autoconf", "tests", "doc", "examples", "experiments", "scripts"]
    for d in dirs_to_remove:
        if (unuran_dir / d).exists():
            shutil.rmtree(unuran_dir / d)

def _clean_makefiles() -> None:
    logger.info(" Removing Makefiles")
    base = pathlib.Path(__file__).parent / "unuran"
    for p in base.rglob("Makefile*"):
        p.unlink()

def _normalize_line_endings() -> None:
    logger.info(" Normalizing line endings to LF")
    base = pathlib.Path(__file__).parent / "unuran"
    extensions = {".c", ".h", ".ch", ".txt", ".md", ".in", ".am"}
    for path in base.rglob("*"):
        if path.is_file() and path.suffix.lower() in extensions:
            data = path.read_bytes()
            normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            if normalized != data:
                path.write_bytes(normalized)

def _clean_deprecated() -> None:
    logger.info(" Removing deprecated files")
    base = pathlib.Path(__file__).parent / "unuran"
    for p in base.glob("./*/*/deprecated*"):
        p.unlink()
    
    unuran_h = base / "src" / "unuran.h"
    if unuran_h.exists():
        content = unuran_h.read_text(encoding="utf-8", errors="ignore")
        content = re.sub(r"/\* <1> `deprecated_(.*).h\' \*/(.|\n)*/\* end of `deprecated_(.*).h\' \*/",
                         r"/* Removed `deprecated_\1.h' */", content)
        unuran_h.write_text(content, encoding="utf-8", newline="\n")

def _ch_to_h() -> None:
    """Rename .ch to .h and update all includes in one pass."""
    logger.info(" Renaming `.ch` -> `.h` and updating includes")
    base = pathlib.Path(__file__).parent / "unuran"
    
    # 1. Rename all .ch files to .h
    for p in base.rglob("*.ch"):
        new_path = p.with_suffix(".h")
        p.rename(new_path)

    # 2. Update includes in all .c and .h files (ONE pass)
    for p in base.rglob("*"):
        if p.suffix in {".c", ".h"}:
            content = p.read_text(encoding="utf-8", errors="ignore")
            new_content = re.sub(r"#include <(.*)\.ch>", r"#include <\1.h>", content)
            new_content = re.sub(r'#include "(.*)\.ch"', r'#include "\1.h"', new_content)
            if new_content != content:
                p.write_text(new_content, encoding="utf-8", newline="\n")

def _replace_urng_default() -> None:
    logger.info(" Replacing URNG API")
    base_dir = pathlib.Path(__file__).parent
    unuran_src = base_dir / "unuran" / "src"
    
    # Copy modified urng_default
    if (base_dir / "urng_default_mod.c").exists():
        shutil.copy(base_dir / "urng_default_mod.c", unuran_src / "urng" / "urng_default.c")

    # Update unuran.h
    unuran_h = unuran_src / "unuran.h"
    if unuran_h.exists():
        content = unuran_h.read_text(encoding="utf-8", errors="ignore")
        for h in ["urng_builtin.h", "urng_fvoid.h", "urng_randomshift.h"]:
            content = re.sub(rf"/\* <1> `{h}\' \*/(.|\n)*/\* end of `{h}\' \*/", f"/* Removed {h} */", content)
        unuran_h.write_text(content, encoding="utf-8", newline="\n")

    # Update unuran_config.h
    cfg_h = unuran_src / "unuran_config.h"
    if cfg_h.exists():
        content = cfg_h.read_text(encoding="utf-8", errors="ignore")
        content = re.sub(r"# *define *UNUR_URNG_DEFAULT *\(?unur_urng_builtin\(\)?\)", 
                         "#define UNUR_URNG_DEFAULT unur_get_default_urng()", content)
        content = re.sub(r"# *define *UNUR_URNG_AUX_DEFAULT *\(?unur_urng_builtin_aux\(\)?\)",
                         "#define UNUR_URNG_AUX_DEFAULT unur_get_default_urng_aux()", content)
        cfg_h.write_text(content, encoding="utf-8", newline="\n")

def _remove_misc():
    logger.info(" Removing miscellaneous files")
    base = pathlib.Path(__file__).parent / "unuran"
    for ext in ["*.pl", "*.in", "*.dh"]:
        for p in base.rglob(ext):
            p.unlink()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--unuran-version", type=str, default="1.8.1")
    parser.add_argument("-v", action="store_true", default=False)
    args = parser.parse_args()
    
    if args.v:
        logger.setLevel(logging.INFO)

    _download_unuran(args.unuran_version)
    _clean_makefiles()
    _clean_deprecated()
    _ch_to_h()
    _replace_urng_default()
    _remove_misc()
    _normalize_line_endings()
    logger.info(" Done!")