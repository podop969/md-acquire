# pipeline/bulk.py -- resume-safe bulk runner.
#
# Adapted from the integration guide to this repo's actual API:
# - spec loading uses pipeline.spec.load_from (load_dir doesn't exist here)
# - cli.run(cfg, spec_paths, only, dry_run) -- spec_paths is required
# - per-file parse tolerance so one malformed spec never kills a nightly run
#
# Manifest is the source of truth: a spec is "done" only when every requested
# format has a manifest entry AND the file still exists on disk.
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from . import cli
from .config import Config
from .models import WorkSpec
from .spec import parse_file


def _read_manifest(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def completed_formats(manifest_path: Path, out_dir: Path) -> dict[str, set[str]]:
    """key -> {fmt, ...} for manifest entries whose files still exist."""
    done: dict[str, set[str]] = defaultdict(set)
    for rec in _read_manifest(manifest_path):
        key, fmt, saved_as = rec.get("key"), rec.get("format"), rec.get("saved_as")
        if not key or not fmt or not saved_as:
            continue
        if (out_dir / saved_as).exists():
            done[key].add(fmt)
    return done


def pending_specs(specs: list[WorkSpec], done: dict[str, set[str]], force: bool = False) -> list[WorkSpec]:
    if force:
        return list(specs)
    return [s for s in specs if not all(f in done.get(s.key, set()) for f in s.formats)]


def _load_specs(specs_dir: Path) -> list[WorkSpec]:
    """Parse each spec file individually; bad files are skipped with a note."""
    specs: list[WorkSpec] = []
    failed: list[str] = []
    for p in sorted(specs_dir.glob("*.md")):
        try:
            specs.append(parse_file(p))
        except Exception as exc:
            failed.append(f"{p.name}: {exc}")
    if failed:
        print(f"skipped {len(failed)} unparsable spec file(s):")
        for f in failed:
            print(f"  - {f}")
    return specs


def run(cfg: Config, force: bool = False, dry_run: bool = False,
        only: set[str] | None = None) -> list:
    specs = _load_specs(cfg.specs_dir)
    if only:
        specs = [s for s in specs if s.key in only]
        if not specs:
            print(f"nothing in {cfg.specs_dir} matches {', '.join(sorted(only))}")
            return []
    if not specs:
        print(f"no specs in {cfg.specs_dir}")
        return []

    done = completed_formats(cfg.out_dir / "manifest.jsonl", cfg.out_dir)
    todo = pending_specs(specs, done, force=force)
    if not todo:
        print(f"all {len(specs)} specs complete (use --force to re-fetch)")
        return []

    print(f"{len(todo)} / {len(specs)} specs pending")
    # Pass the already-parsed spec FILES, not the directory: cli.run re-parses
    # its inputs, and one malformed file in the dir would kill the whole pass.
    paths = [s.source_path for s in todo if s.source_path] or [cfg.specs_dir]
    return cli.run(cfg, paths, only={s.key for s in todo}, dry_run=dry_run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser("md-acquire bulk")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--force", action="store_true", help="re-fetch even if complete")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", help="comma-separated spec keys")
    args = parser.parse_args(argv)

    cfg = Config.load(args.config)
    only = {x.strip() for x in args.only.split(",")} if args.only else None
    resolutions = run(cfg, force=args.force, dry_run=args.dry_run, only=only)
    failed = sum(1 for r in resolutions if r.status not in ("ok", "partial"))
    print(f"\nbulk done. {len(resolutions) - failed} resolved, "
          f"{failed} pending -> {cfg.out_dir / 'wanted.md'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())