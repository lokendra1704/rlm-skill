#!/usr/bin/env python3
"""
Split code into syntax-aware chunks using tree-sitter.

Why:
- Naive character/line chunking can cut mid-function/class and reduce reader accuracy.
- For semantic retrieval (vector embeddings), AST chunks usually index better than arbitrary slices.

This script is intentionally lightweight and optional:
- If tree-sitter deps are missing, it prints install instructions and exits non-zero.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


try:
    from tree_sitter_languages import get_parser  # type: ignore
except Exception:  # pragma: no cover
    get_parser = None


EXT_TO_LANG: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "jsx",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".sh": "bash",
}


INTERESTING_NODE_TYPES: Dict[str, Set[str]] = {
    "python": {"function_definition", "class_definition", "decorated_definition"},
    "javascript": {"function_declaration", "class_declaration"},
    "jsx": {"function_declaration", "class_declaration"},
    "typescript": {
        "function_declaration",
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "type_alias_declaration",
    },
    "tsx": {
        "function_declaration",
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "type_alias_declaration",
    },
    "go": {"function_declaration", "method_declaration", "type_declaration"},
    "rust": {"function_item", "struct_item", "enum_item", "impl_item", "trait_item", "mod_item"},
    "java": {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "method_declaration",
        "constructor_declaration",
    },
    "c": {"function_definition", "struct_specifier", "enum_specifier", "union_specifier"},
    "cpp": {"function_definition", "class_specifier", "struct_specifier", "enum_specifier", "namespace_definition"},
    "ruby": {"method", "class", "module"},
    "php": {"function_definition", "class_declaration", "interface_declaration", "trait_declaration"},
    "bash": {"function_definition"},
}


WRAPPER_NODE_TYPES: Dict[str, Set[str]] = {
    "python": {"decorated_definition"},
    "javascript": {"export_statement", "export_default_declaration"},
    "jsx": {"export_statement", "export_default_declaration"},
    "typescript": {"export_statement", "export_default_declaration"},
    "tsx": {"export_statement", "export_default_declaration"},
}


SKIP_DIR_NAMES = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__"}


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source_file: str
    language: str
    node_type: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    path: str
    sha256: str


def _iter_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES and not d.startswith(".")]
        for fn in filenames:
            if fn.startswith("."):
                continue
            p = Path(dirpath) / fn
            if p.suffix.lower() in EXT_TO_LANG:
                yield p


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _detect_language(path: Path, explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    return EXT_TO_LANG.get(path.suffix.lower())


def _has_interesting_descendant(node, interesting: Set[str]) -> bool:
    # Shallow search: many wrappers put the declaration as a direct named child.
    stack = list(getattr(node, "named_children", []))
    while stack:
        n = stack.pop()
        if getattr(n, "type", None) in interesting:
            return True
        # Avoid deep recursion for performance; 2 levels is enough for common wrappers.
        stack.extend(getattr(n, "named_children", [])[:8])
    return False


def _top_level_chunks(tree, language: str):
    root = tree.root_node
    interesting = INTERESTING_NODE_TYPES.get(language, set())
    wrappers = WRAPPER_NODE_TYPES.get(language, set())

    nodes = []
    for child in getattr(root, "named_children", []):
        t = getattr(child, "type", "")
        if t in interesting:
            nodes.append(child)
            continue
        if t in wrappers and _has_interesting_descendant(child, interesting):
            # Keep the wrapper so decorators/exports remain attached.
            nodes.append(child)
            continue
    return nodes


def _clear_existing_chunks(chunk_dir: Path) -> None:
    if not chunk_dir.exists():
        return
    if not chunk_dir.is_dir():
        raise RuntimeError(f"Output path exists and is not a directory: {chunk_dir}")
    for p in chunk_dir.iterdir():
        if p.name == "index.json" or (p.name.startswith("chunk_") and p.suffix == ".txt"):
            p.unlink()


def split_code(
    source_root: Path,
    out_dir: Path,
    language_override: Optional[str],
    force: bool,
) -> List[Chunk]:
    if get_parser is None:
        raise RuntimeError(
            "tree-sitter dependencies are not installed.\n"
            "Install with:\n"
            "  python3 -m pip install tree_sitter tree_sitter_languages"
        )

    files: List[Path]
    if source_root.is_file():
        files = [source_root]
        root_for_rel = source_root.parent
    else:
        files = list(_iter_files(source_root))
        root_for_rel = source_root

    out_dir.mkdir(parents=True, exist_ok=True)

    all_chunks: List[Chunk] = []
    for src in files:
        language = _detect_language(src, language_override)
        if not language:
            continue

        try:
            parser = get_parser(language)
        except Exception:
            # Unknown language in the installed bundle.
            continue

        data = src.read_bytes()
        tree = parser.parse(data)
        nodes = _top_level_chunks(tree, language)
        if not nodes:
            continue

        rel_path = src.relative_to(root_for_rel)
        chunk_dir = out_dir / rel_path.parent / (rel_path.name + ".chunks")
        chunk_dir.mkdir(parents=True, exist_ok=True)
        if force:
            _clear_existing_chunks(chunk_dir)
        else:
            if any(p.name.startswith("chunk_") and p.suffix == ".txt" for p in chunk_dir.iterdir()):
                raise RuntimeError(
                    f"Refusing to overwrite existing chunk_*.txt files in: {chunk_dir}\n"
                    f"Choose a new --out-dir or pass --force."
                )

        width = max(4, len(str(len(nodes))))
        file_chunks: List[Chunk] = []
        for i, node in enumerate(nodes, start=1):
            start_b = int(getattr(node, "start_byte"))
            end_b = int(getattr(node, "end_byte"))
            chunk_bytes = data[start_b:end_b]

            chunk_id = f"{rel_path.as_posix()}::chunk_{i:0{width}d}"
            filename = f"chunk_{i:0{width}d}.txt"
            out_path = chunk_dir / filename
            out_path.write_bytes(chunk_bytes)

            start_line = int(getattr(node, "start_point")[0]) + 1
            end_line = int(getattr(node, "end_point")[0]) + 1

            c = Chunk(
                chunk_id=chunk_id,
                source_file=str(rel_path.as_posix()),
                language=language,
                node_type=str(getattr(node, "type")),
                start_line=start_line,
                end_line=end_line,
                start_byte=start_b,
                end_byte=end_b,
                path=str((chunk_dir.relative_to(out_dir) / filename).as_posix()),
                sha256=_sha256(chunk_bytes),
            )
            file_chunks.append(c)
            all_chunks.append(c)

        (chunk_dir / "index.json").write_text(
            json.dumps(
                {
                    "source_file": str(rel_path.as_posix()),
                    "language": language,
                    "chunks": [asdict(c) for c in file_chunks],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    (out_dir / "index.json").write_text(
        json.dumps(
            {
                "source_root": str(source_root),
                "out_dir": str(out_dir),
                "language_override": language_override,
                "chunks": [asdict(c) for c in all_chunks],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    return all_chunks


def main(argv: Sequence[str]) -> int:
    p = argparse.ArgumentParser(description="Split code using tree-sitter into top-level declaration chunks")
    p.add_argument("source", type=Path, help="Path to a source file or a directory to scan recursively")
    p.add_argument("--out-dir", type=Path, required=True, help="Output directory for per-file *.chunks dirs + index.json")
    p.add_argument(
        "--language",
        type=str,
        default=None,
        help="Override language for single-file inputs (e.g. python, typescript). If omitted, infer from extension.",
    )
    p.add_argument("--force", action="store_true", help="Overwrite chunk_*.txt files in the output")
    args = p.parse_args(list(argv))

    if not args.source.exists():
        print(f"error: source path does not exist: {args.source}", file=sys.stderr)
        return 2

    try:
        chunks = split_code(
            source_root=args.source,
            out_dir=args.out_dir,
            language_override=args.language,
            force=args.force,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"Wrote {len(chunks)} chunks to: {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

