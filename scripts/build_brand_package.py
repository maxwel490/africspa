"""Build a branded one-time-sale package from the base engine.

Usage (PowerShell):
python scripts/build_brand_package.py --brand-name "Client Name" --brand-slug clientslug --domain clientdomain.com --db-prefix cs
"""

from __future__ import annotations

import argparse
import fnmatch
from pathlib import Path
import shutil

TEXT_EXTENSIONS = {".py", ".html", ".css", ".js", ".md", ".txt", ".ini", ".cfg", ".env", ".yml", ".yaml"}

EXCLUDE_PATTERNS = [
    ".venv/*",
    "__pycache__/*",
    "instance/*",
    "dist/*",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
]


def should_exclude(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in EXCLUDE_PATTERNS)


def copy_project(src_root: Path, dst_root: Path) -> None:
    if dst_root.exists():
        shutil.rmtree(dst_root)
    dst_root.mkdir(parents=True, exist_ok=True)

    for src_path in src_root.rglob("*"):
        if src_path == dst_root or dst_root in src_path.parents:
            continue
        rel = str(src_path.relative_to(src_root))
        if should_exclude(rel):
            continue

        target = dst_root / rel
        if src_path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, target)


def replace_in_text_files(root: Path, replacements: dict[str, str]) -> int:
    changed_files = 0
    for file_path in root.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            original = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        updated = original
        for old, new in replacements.items():
            updated = updated.replace(old, new)

        if updated != original:
            file_path.write_text(updated, encoding="utf-8")
            changed_files += 1
    return changed_files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a branded package for one-time sale handover.")
    parser.add_argument("--brand-name", required=True)
    parser.add_argument("--brand-slug", required=True)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--db-prefix", required=True)

    parser.add_argument("--from-brand", default="BeautySpace")
    parser.add_argument("--from-slug", default="beautyspace")
    parser.add_argument("--from-domain", default="beautyspace.co.ke")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    output_root = project_root / "dist"
    package_root = output_root / args.brand_slug

    copy_project(project_root, package_root)
    changed_files = replace_in_text_files(
        package_root,
        {
            args.from_brand: args.brand_name,
            args.from_slug: args.brand_slug,
            args.from_domain: args.domain,
        },
    )

    (package_root / "HANDOVER-NOTE.md").write_text(
        "\n".join(
            [
                f"# {args.brand_name} Handover Package",
                f"- Database prefix plan: {args.db_prefix}_",
                f"- Text files branded: {changed_files}",
                "- Warranty: 30 days bug fixes",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Branded package generated at: {package_root}")


if __name__ == "__main__":
    main()
