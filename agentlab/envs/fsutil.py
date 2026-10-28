"""工作区文件工具：路径约束、快照、文本读写。"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

IGNORED_DIRS = {".agentlab", "__pycache__", ".git", ".pytest_cache", ".mypy_cache", "node_modules"}
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024


class PathEscapeError(ValueError):
    """试图访问 workspace 之外的路径。"""


def safe_resolve(root: Path, rel: str | Path) -> Path:
    """把任务内的相对路径解析成绝对路径，并保证不越界。"""
    root = Path(root).resolve()
    if Path(rel).is_absolute():
        raise PathEscapeError(f"不允许绝对路径: {rel}")
    candidate = (root / rel).resolve()
    if candidate != root and root not in candidate.parents:
        raise PathEscapeError(f"路径越界: {rel}")
    return candidate


def rel_posix(root: Path, path: Path) -> str:
    return path.resolve().relative_to(Path(root).resolve()).as_posix()


def iter_files(root: Path) -> list[Path]:
    root = Path(root)
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        for name in sorted(filenames):
            if name.endswith((".pyc", ".pyo")):
                continue
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            out.append(path)
    return out


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(root: Path) -> dict[str, str]:
    """workspace 内容快照：相对路径 -> sha256。忽略编译缓存与内部目录。"""
    root = Path(root)
    if not root.is_dir():
        return {}
    return {rel_posix(root, p): sha256_file(p) for p in iter_files(root)}


def write_text(root: Path, rel: str, content: str) -> Path:
    path = safe_resolve(root, rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


def read_text(root: Path, rel: str, max_bytes: int = 8000) -> str:
    path = safe_resolve(root, rel)
    if not path.exists():
        raise FileNotFoundError(rel)
    if path.is_dir():
        raise IsADirectoryError(rel)
    data = path.read_bytes()
    truncated = len(data) > max_bytes
    text = data[:max_bytes].decode("utf-8", errors="replace")
    if truncated:
        text += f"\n...[已截断，文件共 {len(data)} 字节]"
    return text


def list_tree(root: Path, rel: str = ".", limit: int = 200) -> list[str]:
    root = Path(root).resolve()
    base = safe_resolve(root, rel)
    if not base.exists():
        raise FileNotFoundError(rel)
    if base.is_file():
        return [rel]
    entries: list[str] = []
    for path in sorted(base.rglob("*")):
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_dir():
            continue
        entries.append(rel_posix(root, path))
        if len(entries) >= limit:
            entries.append(f"...[超过 {limit} 项，已截断]")
            break
    return entries


def copy_tree(src: Path, dst: Path) -> None:
    """把任务包 files/ 复制到 workspace（保留相对路径）。"""
    src, dst = Path(src), Path(dst)
    if not src.is_dir():
        return
    for path in iter_files(src):
        rel = path.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
