from __future__ import annotations
import argparse
from pathlib import Path

from .adapters import build as build_adapters
from .config import Config
from .download import download
from .handoff import manual_links
from .http import Client
from .manifest import Manifest
from .metadata import enrich
from .models import Candidate, Resolution, WorkSpec
from .report import write
from .spec import load_from


def _rank(spec: WorkSpec, candidates: list[Candidate]) -> list[Candidate]:
    order = {fmt: i for i, fmt in enumerate(spec.formats)}
    return sorted(candidates, key=lambda c: (-c.score, order.get(c.fmt, 99)))


def run(cfg: Config, spec_paths: list[Path], only: set[str] | None = None,
        dry_run: bool = False) -> list[Resolution]:
    client = Client(cfg.min_interval, cfg.timeout, cfg.retries)
    adapters = build_adapters(cfg.adapters, cfg)
    manifest = Manifest(cfg.out_dir / "manifest.jsonl")
    specs = load_from(spec_paths)
    if only:
        specs = [s for s in specs if s.key in only]

    resolutions: list[Resolution] = []
    for spec in specs:
        print(f"[{spec.key}] {spec.title}")
        hints: list[str] = []
        try:
            hints += enrich(client, spec)
        except Exception as exc:
            hints.append(f"enrichment failed: {exc}")

        candidates: list[Candidate] = []
        failures: list[str] = []
        borrow_hints: list[str] = []
        for adapter in adapters:
            try:
                found = adapter.lookup(client, spec)
                candidates += found
                print(f"  {adapter.name}: {len(found)} candidate(s)")
                borrow_hints += list(getattr(adapter, "borrow_hints", []) or [])
            except Exception as exc:
                failures.append(f"{adapter.name}: {exc}")

        ranked = _rank(spec, candidates)
        by_fmt: dict[str, list[Candidate]] = {}
        for cand in ranked:
            by_fmt.setdefault(cand.fmt, []).append(cand)

        if not by_fmt:
            detail = "; ".join(failures) or "no open-access source had a matching copy"
            manual = manual_links(spec)
            resolutions.append(Resolution(spec, "not_found", detail=detail,
                                          hints=hints + borrow_hints, manual=manual))
            print("  -> not found in open sources (see wanted.md for manual links)")
            continue

        if dry_run:
            for fmt, cands_in_fmt in by_fmt.items():
                print(f"  -> would fetch {cands_in_fmt[0].source} {cands_in_fmt[0].url} ({fmt})")
            resolutions.append(Resolution(spec, "ok", detail="dry-run", hints=hints))
            continue

        res = Resolution(spec, "ok", hints=hints)
        sources: list[str] = []
        errors: list[str] = []
        for fmt, cands_in_fmt in by_fmt.items():
            # README contract: per format, try ranked candidates in order until
            # one downloads and validates -- one flaky mirror can't sink a spec.
            for cand in cands_in_fmt:
                try:
                    saved, sha = download(client, cand, spec, cfg.out_dir)
                    res.saved.append(saved)
                    sources.append(cand.source)
                    manifest.record(spec, cand, saved, sha)
                    print(f"  -> saved {saved.name} [{cand.source}, {cand.license or 'license n/a'}]")
                    break
                except Exception as exc:
                    errors.append(f"{fmt}<-{cand.source}: {exc}")
                    print(f"  -> failed {fmt} from {cand.source}: {exc}")
        if not res.saved:
            res.status = "failed"
            res.manual = manual_links(spec)
        res.detail = ", ".join(sources) or "; ".join(errors)
        resolutions.append(res)

    write(resolutions, cfg.out_dir)
    return resolutions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        "md-acquire",
        description="MD-spec downloader for open-access books and papers. "
                    "Non-open works get manual search links in wanted.md.",
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--specs", action="append", default=[],
                        help="spec MD file or folder (repeatable; default: specs_dir from config)")
    parser.add_argument("--only", help="comma-separated spec keys (filename stems)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--html", action="store_true",
                        help="only regenerate library/wanted.html from existing wanted.md")
    args = parser.parse_args(argv)

    cfg = Config.load(args.config)
    if args.html:
        from .htmlwanted import build as build_html
        out = build_html(cfg.out_dir / "wanted.md")
        print(f"wrote {out}")
        return 0
    spec_paths = [Path(p) for p in args.specs] or [cfg.specs_dir]
    only = {x.strip() for x in args.only.split(",")} if args.only else None
    resolutions = run(cfg, spec_paths, only, args.dry_run)
    bad = sum(1 for r in resolutions if r.status not in ("ok", "partial"))
    print(f"\ndone. {len(resolutions) - bad} resolved, {bad} unresolved.")
    print(f"report: {cfg.out_dir / 'report.md'}")
    print(f"wanted: {cfg.out_dir / 'wanted.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())