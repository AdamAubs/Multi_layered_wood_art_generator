"""Deterministic Etsy-constrained buyer ZIP creation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import zipfile

from release_tools.run_facts import ReleaseValidationError, sha256_file


ETSY_MAX_FILES = 5
ETSY_MAX_BYTES = 20 * 1024 * 1024
ETSY_POLICY_URL = "https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings"
ETSY_POLICY_VERIFIED_ON = "2026-08-06"


@dataclass(frozen=True)
class ArchiveDetail:
    name: str
    size: int
    sha256: str


def create_buyer_archives(buyer_root: Path, package_dir: Path, archive_stem: str) -> list[ArchiveDetail]:
    _validate_buyer_tree(package_dir)
    files = [path for path in sorted(package_dir.rglob("*")) if path.is_file()]
    all_archive = buyer_root / f"{archive_stem}.zip"
    _write_zip(all_archive, package_dir, files)
    if all_archive.stat().st_size <= ETSY_MAX_BYTES:
        return [_detail(all_archive)]
    all_archive.unlink()
    shared = [path for path in files if path.name in {"READ_ME_FIRST.txt", "LICENSE.txt", "FILE_MANIFEST.txt"}]
    vectors = [path for path in files if path.parts[-2] in {"DXF_Layers", "SVG_Layers"} or "Cut_Layouts" in path.parts]
    references = [path for path in files if path not in vectors and path not in shared]
    groups = [("Vectors", shared + vectors), ("References", shared + references)]
    details: list[ArchiveDetail] = []
    for suffix, group in groups:
        archive = buyer_root / f"{archive_stem}_{suffix}.zip"
        _write_zip(archive, package_dir, group)
        if archive.stat().st_size > ETSY_MAX_BYTES:
            raise ReleaseValidationError(f"{archive.name} exceeds Etsy's 20 MB limit; reduce required source asset sizes before release.")
        details.append(_detail(archive))
    if len(details) > ETSY_MAX_FILES:
        raise ReleaseValidationError("Buyer delivery exceeds Etsy's five-file limit.")
    return details


def write_upload_instructions(path: Path, details: list[ArchiveDetail]) -> None:
    rows = ["Upload these digital files to Etsy in this order:", ""]
    rows.extend(f"{position}. {detail.name} | {detail.size} bytes | {detail.sha256}" for position, detail in enumerate(details, 1))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_zip(destination: Path, root: Path, files: list[Path]) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def _validate_buyer_tree(package_dir: Path) -> None:
    allowed_top = {"DXF_Layers", "SVG_Layers", "Cut_Layouts", "PNG_References", "Assembly_References", "READ_ME_FIRST.txt", "LICENSE.txt", "FILE_MANIFEST.txt"}
    for path in package_dir.rglob("*"):
        if path.is_symlink():
            raise ReleaseValidationError(f"Buyer tree may not contain symlinks: {path.name}")
        if path.is_file():
            relative = path.relative_to(package_dir)
            if relative.parts[0] not in allowed_top or path.suffix.lower() == ".mp4" or path.name.startswith("._") or path.name == ".DS_Store":
                raise ReleaseValidationError(f"Unapproved buyer archive path: {relative.as_posix()}")
            if not re.fullmatch(r"[A-Za-z0-9._/-]+", relative.as_posix()):
                raise ReleaseValidationError(f"Buyer archive path has unsupported characters: {relative.as_posix()}")


def _detail(path: Path) -> ArchiveDetail:
    return ArchiveDetail(path.name, path.stat().st_size, sha256_file(path))