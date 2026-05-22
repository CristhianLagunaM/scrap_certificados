from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def create_zip(source_dir: Path, report_path: Path, zip_path: Path) -> Path:
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as archive:
        for path in source_dir.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir))
        archive.write(report_path, report_path.name)
    return zip_path

