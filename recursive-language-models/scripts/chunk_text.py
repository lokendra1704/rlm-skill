#!/usr/bin/env python3
"""
Split a large text file into overlapping character chunks and write an index.

This is intentionally dependency-free so it can be used from most coding agents.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    path: str
    start_char: int
    end_char: int
    start_line: int
    end_line: int
    sha256: str


def _compute_newline_positions(text: str) -> List[int]:
    # Using regex is noticeably faster than repeated str.find loops on large inputs.
    return [m.start() for m in re.finditer("\n", text)]


def _line_number_at(newlines: List[int], pos: int) -> int:
    # pos is a 0-based character offset into the full text.
    # Return 1-based line number.
    if pos < 0:
        pos = 0
    return bisect.bisect_right(newlines, pos - 1) + 1


def _safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _would_overwrite_existing_chunks(out_dir: Path) -> bool:
    if not out_dir.exists():
        return False
    if not out_dir.is_dir():
        return True
    return any(p.name.startswith("chunk_") and p.suffix == ".txt" for p in out_dir.iterdir())


def _choose_chunk_end(text: str, start: int, hard_end: int, min_ratio: float = 0.6) -> int:
    """
    Pick a chunk end close to hard_end, preferring a newline boundary.

    min_ratio: if the last newline is too close to start (tiny chunk), ignore it.
    """
    if hard_end >= len(text):
        return len(text)

    min_end = start + int((hard_end - start) * min_ratio)
    nl = text.rfind("\n", start, hard_end)
    if nl != -1 and nl >= min_end:
        # Include the newline.
        return nl + 1
    return hard_end


def _iter_chunk_spans(text: str, max_chars: int, overlap_chars: int) -> List[Tuple[int, int]]:
    if max_chars <= 0:
        raise ValueError("--max-chars must be > 0")
    if overlap_chars < 0:
        raise ValueError("--overlap-chars must be >= 0")
    if overlap_chars >= max_chars:
        raise ValueError("--overlap-chars must be < --max-chars")

    spans: List[Tuple[int, int]] = []
    start = 0
    while start < len(text):
        hard_end = min(start + max_chars, len(text))
        end = _choose_chunk_end(text, start, hard_end)
        if end <= start:
            # Fallback to ensure forward progress.
            end = hard_end
            if end <= start:
                break
        spans.append((start, end))
        if end >= len(text):
            break
        start = max(0, end - overlap_chars)
    return spans


def chunk_text(
    source_path: Path,
    out_dir: Path,
    max_chars: int,
    overlap_chars: int,
    encoding: str,
    force: bool,
) -> List[Chunk]:
    raw = source_path.read_bytes()
    text = raw.decode(encoding, errors="replace")

    _safe_mkdir(out_dir)
    if _would_overwrite_existing_chunks(out_dir) and not force:
        raise RuntimeError(
            f"Refusing to overwrite existing chunk_*.txt files in: {out_dir}\n"
            f"Delete the directory, choose a new --out-dir, or pass --force."
        )

    newlines = _compute_newline_positions(text)
    spans = _iter_chunk_spans(text, max_chars=max_chars, overlap_chars=overlap_chars)

    chunks: List[Chunk] = []
    width = max(4, len(str(len(spans))))
    for i, (start, end) in enumerate(spans, start=1):
        chunk_id = f"chunk_{i:0{width}d}"
        chunk_text = text[start:end]
        digest = hashlib.sha256(chunk_text.encode("utf-8", errors="replace")).hexdigest()

        start_line = _line_number_at(newlines, start)
        end_line = _line_number_at(newlines, max(start, end - 1))

        filename = f"{chunk_id}.txt"
        out_path = out_dir / filename
        out_path.write_text(chunk_text, encoding="utf-8", errors="replace")

        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                path=filename,
                start_char=start,
                end_char=end,
                start_line=start_line,
                end_line=end_line,
                sha256=digest,
            )
        )

    index = {
        "source_file": str(source_path),
        "out_dir": str(out_dir),
        "max_chars": max_chars,
        "overlap_chars": overlap_chars,
        "chunks": [c.__dict__ for c in chunks],
    }
    (out_dir / "index.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return chunks


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="Split a text file into overlapping chunks + index.json")
    p.add_argument("source", type=Path, help="Path to a text file (will be decoded with --encoding)")
    p.add_argument("--out-dir", type=Path, default=None, help="Output directory for chunk_*.txt + index.json")
    p.add_argument("--max-chars", type=int, default=15000, help="Maximum characters per chunk (default: 15000)")
    p.add_argument("--overlap-chars", type=int, default=200, help="Overlap between chunks in characters (default: 200)")
    p.add_argument("--encoding", type=str, default="utf-8", help="File encoding (default: utf-8)")
    p.add_argument("--force", action="store_true", help="Overwrite chunk_*.txt in --out-dir if they exist")
    args = p.parse_args(argv)

    source_path: Path = args.source
    if not source_path.exists():
        print(f"error: source file does not exist: {source_path}", file=sys.stderr)
        return 2
    if not source_path.is_file():
        print(f"error: source path is not a file: {source_path}", file=sys.stderr)
        return 2

    out_dir = args.out_dir
    if out_dir is None:
        out_dir = source_path.parent / "chunks" / source_path.stem

    try:
        chunks = chunk_text(
            source_path=source_path,
            out_dir=out_dir,
            max_chars=args.max_chars,
            overlap_chars=args.overlap_chars,
            encoding=args.encoding,
            force=args.force,
        )
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"Wrote {len(chunks)} chunks to: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

