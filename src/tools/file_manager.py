"""Intelligent File Manager for TATSU Sovereign Agent — Phase 3.

Provides safe directory organization, recursive glob search, and zip archiving.
Enforces workspace boundaries and requires confirmation for bulk operations.
"""

import os
import time
import zipfile
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("TATSU.FileManager")
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class FileManager:
    """Safe, sandboxed file operations: organize, search, and archive."""

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = (root_dir or BASE_DIR).resolve()

    def _resolve_safe_path(self, target_path: str) -> Path:
        """Resolves path and enforces that it remains within allowed directories."""
        p = Path(target_path)
        if not p.is_absolute():
            p = (self.root_dir / p).resolve()
        else:
            p = p.resolve()

        # Confine to workspace or temp directories for safety
        allowed_parents = [self.root_dir, Path("/tmp"), Path(os.environ.get("TMPDIR", "/tmp")).resolve()]
        is_safe = any(p == allowed or allowed in p.parents for allowed in allowed_parents)
        if not is_safe:
            raise PermissionError(f"Access denied: path '{target_path}' is outside permitted workspace.")
        return p

    def search_files(
        self,
        pattern: str = "*",
        directory: str = ".",
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:
        """Recursively searches for files matching a glob pattern."""
        dir_path = self._resolve_safe_path(directory)
        if not dir_path.is_dir():
            return []

        results = []
        for item in dir_path.rglob(pattern):
            # Ignore hidden VCS and cache directories
            if any(part.startswith(".") and part != "." for part in item.parts):
                continue
            if "__pycache__" in item.parts:
                continue

            try:
                stat = item.stat()
                results.append({
                    "name": item.name,
                    "path": str(item.relative_to(self.root_dir) if item.is_relative_to(self.root_dir) else item),
                    "size_bytes": stat.st_size,
                    "modified_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                    "is_dir": item.is_dir(),
                })
            except Exception:
                continue

            if len(results) >= max_results:
                break

        return results

    def organize_directory(
        self,
        directory: str,
        criteria: str = "extension",
        confirm: bool = False,
    ) -> str:
        """Organizes files in a directory into category subfolders based on extension."""
        dir_path = self._resolve_safe_path(directory)
        if not dir_path.is_dir():
            return f"Error: Directory '{directory}' does not exist."

        # Collect top-level files in directory
        files_to_move = [f for f in dir_path.iterdir() if f.is_file() and not f.name.startswith(".")]
        if not files_to_move:
            return f"No loose files to organize in '{directory}'."

        if len(files_to_move) > 5 and not confirm:
            return (
                f"CONFIRMATION REQUIRED: Organizing will move {len(files_to_move)} files in '{directory}'. "
                "Please re-run with confirm=True to proceed."
            )

        categories = {
            "images": [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"],
            "documents": [".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx"],
            "archives": [".zip", ".tar", ".gz", ".rar", ".7z"],
            "code": [".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".sh"],
            "media": [".mp3", ".wav", ".mp4", ".mov", ".mkv"],
        }

        moved_count = 0
        for f in files_to_move:
            ext = f.suffix.lower()
            category = "misc"
            for cat, exts in categories.items():
                if ext in exts:
                    category = cat
                    break

            target_folder = dir_path / category
            target_folder.mkdir(parents=True, exist_ok=True)
            destination = target_folder / f.name

            # Avoid collision
            if destination.exists():
                destination = target_folder / f"{f.stem}_{int(time.time())}{f.suffix}"

            f.rename(destination)
            moved_count += 1

        return f"Successfully organized {moved_count} files into categories in '{directory}'."

    def archive_files(
        self,
        file_list: List[str],
        destination_zip: str,
        confirm: bool = False,
    ) -> str:
        """Compresses a list of files into a ZIP archive."""
        if not file_list:
            return "Error: File list for archiving is empty."

        dest_path = self._resolve_safe_path(destination_zip)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if len(file_list) > 10 and not confirm:
            return (
                f"CONFIRMATION REQUIRED: Archiving {len(file_list)} files into '{destination_zip}'. "
                "Please re-run with confirm=True to proceed."
            )

        valid_files = []
        for file_str in file_list:
            try:
                resolved = self._resolve_safe_path(file_str)
                if resolved.exists() and resolved.is_file():
                    valid_files.append(resolved)
            except Exception:
                continue

        if not valid_files:
            return "Error: None of the specified files could be found for archiving."

        with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zip_out:
            for vf in valid_files:
                arcname = vf.name
                zip_out.write(vf, arcname=arcname)

        return f"Successfully archived {len(valid_files)} files into '{dest_path.name}' ({dest_path.stat().st_size} bytes)."
