# -*- coding: utf-8 -*-
"""preflight — audit the declarations carried by claim-bearing artifacts.

A computational result should not travel alone. It should travel with the conditions under which it was
produced, and with the means to check what one is entitled to conclude from it. This tool audits whether
those declarations are *still true*, which re-running the computation cannot answer: re-running produces
a fresh document, it does not audit the one already published.

Four checks, all performed on the artifact alone, so that an existing archive can be audited without
touching a single producer:

    freshness     the recorded producer hash still matches the producer on disk
    counters      serialised tallies still reproduce the blocks they summarise
    provenance    every declared upstream pin still resolves to its declared hash
    partial run   a cheap validation run does not occupy the place of a full result

Optionally, external linters are chained and their exit status reported (``--linters``).

Scope decides severity. Auditing one artifact — the gesture performed before relying on it — stops on a
blocking finding and exits non-zero. Surveying a whole archive never stops: it measures debt rather than
passing judgement, because a tool that fails on its first survey is never run a second time.

The report emitted by ``--json`` is itself a claim-bearing artifact, and auditing that report with this
tool yields no findings. A checker that cannot describe itself in the shape it demands of others is
asking for a shape that does not work.

Usage:
    prevol --artifact NAME [--root DIR]      audit one artifact (blocking)
    prevol --survey [--root DIR] [--json F]  survey the archive (never blocking)
    prevol --self-check                      run this tool's own gates and negative controls
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import time
from pathlib import Path

from .core import (
    BLOCKING, REPORT, UNREADABLE,
    check_counter_coherence, check_freshness, check_partial_run_discipline, check_provenance,
    self_check, severity_counts, verdict,
)

#  Layout of the audited tree. Every project-specific assumption lives here and nowhere else.
DEFAULTS = {
    "artifacts": "results",        # directory holding the artifacts, relative to --root
    "producers": "scripts",        # directory holding the producers
    "partial_suffix": "_limited",  # name suffix marking a partial run
    "extra_search": [],            # further directories in which a bare pin label may be resolved
}


class Tree:
    """Everything that knows where files live. The checks themselves know none of this."""

    def __init__(self, root: Path, layout=None):
        self.root = root.resolve()
        self.layout = {**DEFAULTS, **(layout or {})}
        self.artifacts = self.root / self.layout["artifacts"]
        self.producers = self.root / self.layout["producers"]
        self._sha_cache = {}

    def sha256(self, path: Path):
        key = str(path)
        if key not in self._sha_cache:
            try:
                self._sha_cache[key] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                self._sha_cache[key] = None
        return self._sha_cache[key]

    def is_partial_name(self, name):
        return name.endswith(self.layout["partial_suffix"])

    def producer_of(self, name, artifact):
        """Locate the producer of an artifact. Two routes, in this order.

        **Declared** — the artifact names its producer (``producer``, or ``provenance.producer``). This
        is the robust route, and dogfooding made it necessary: this tool's own report is named after the
        report, not after the tool, and no naming rule relates the two. Any archive contains artifacts
        whose names do not match their producer; without a declared route they are simply unauditable.

        **Guessed** — a producer with the same base name, ignoring the partial-run suffix.
        """
        if isinstance(artifact, dict):
            declared = artifact.get("producer")
            if not isinstance(declared, str):
                provenance = artifact.get("provenance")
                declared = provenance.get("producer") if isinstance(provenance, dict) else None
            if isinstance(declared, str):
                candidate = (self.root / declared) if "/" in declared else (self.producers / declared)
                if candidate.is_file():
                    return candidate
        base = name[: -len(self.layout["partial_suffix"])] if self.is_partial_name(name) else name
        candidate = self.producers / f"{base}.py"
        return candidate if candidate.is_file() else None

    def resolver(self):
        """Build the ``resolve(label, path)`` callable that provenance checking needs."""
        def resolve(label, path):
            if path:
                candidate = Path(path)
                candidate = candidate if candidate.is_absolute() else (self.root / path)
            else:
                search = [self.artifacts, self.producers] + [
                    self.root / d for d in self.layout["extra_search"]]
                candidate = next((d / label for d in search if (d / label).is_file()), None)
            if candidate is None or not candidate.is_file():
                return None, None
            return candidate.name, self.sha256(candidate)
        return resolve

    def load(self, name):
        path = self.artifacts / f"{name}.json"
        if not path.is_file():
            return None
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        return loaded if isinstance(loaded, dict) else None

    def names(self):
        return sorted(p.stem for p in self.artifacts.glob("*.json"))


def audit_artifact(tree: Tree, name, artifact):
    """Run the four artifact-level checks. The only place the pure core meets the filesystem."""
    producer = tree.producer_of(name, artifact)
    producer_sha = tree.sha256(producer) if producer else None
    producer_name = producer.name if producer else "?"
    return (check_freshness(artifact, producer_name, producer_sha, tree.is_partial_name(name))
            + check_counter_coherence(artifact)
            + check_provenance(artifact, tree.resolver())
            + check_partial_run_discipline(tree.is_partial_name(name), artifact))


def run_linters(tree: Tree, specs):
    """Chain external linters. Their command lines and exit conventions differ from one another;
    absorbing that difference is the whole purpose of this adapter."""
    findings = []
    for spec in specs:
        parts = spec.split(":")
        script, clean_exit = parts[0], (int(parts[1]) if len(parts) > 1 else 0)
        path = tree.producers / script
        if not path.is_file():
            findings.append((REPORT, "linters", f"linter `{script}` not found"))
            continue
        try:
            done = subprocess.run([sys.executable, str(path)], cwd=str(tree.root),
                                  capture_output=True, text=True, timeout=600)
        except (subprocess.TimeoutExpired, OSError) as error:
            findings.append((REPORT, "linters", f"linter `{script}` could not run: {error}"))
            continue
        if done.returncode != clean_exit:
            tail = (done.stdout or done.stderr or "").strip().splitlines()
            findings.append((REPORT, "linters",
                             f"linter `{script}` exited {done.returncode} — {tail[-1][:120] if tail else ''}"))
    return findings


def main():
    #  Wrapping stdout belongs to the entry point, never to import: a module that mutates global state on
    #  import closes the wrapper of whatever imported it. Found by the adapter that wraps it too.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="prevol",
                                     description="audit claim-bearing artifacts")
    parser.add_argument("--root", default=".", help="root of the audited tree")
    parser.add_argument("--artifact", help="audit a single artifact by name (blocking)")
    parser.add_argument("--survey", action="store_true", help="survey the whole archive (never blocking)")
    parser.add_argument("--extra-search", default="",
                        help="comma-separated extra directories for resolving bare pin labels")
    parser.add_argument("--linters", default="", help="comma-separated linters, each `script.py[:clean_exit]`")
    parser.add_argument("--json", metavar="PATH", help="write a report that is itself a claim-bearing artifact")
    parser.add_argument("--self-check", action="store_true", help="this tool's own gates and negative controls")
    args = parser.parse_args()
    started = time.time()

    if args.self_check:
        gates, negatives = self_check()
        for name, value in {**gates, **negatives}.items():
            print(f"  {'PASS' if value else 'FAIL'}  {name}")
        print(f"self-check: gates {sum(gates.values())}/{len(gates)} · "
              f"negative controls {sum(negatives.values())}/{len(negatives)}")
        sys.exit(0 if all(gates.values()) and all(negatives.values()) else 1)

    if not (args.artifact or args.survey):
        parser.error("choose --artifact NAME or --survey")

    tree = Tree(Path(args.root),
                {"extra_search": [d for d in args.extra_search.split(",") if d]})
    single = bool(args.artifact)
    names = [args.artifact] if single else tree.names()
    per_artifact, findings = {}, []
    for name in names:
        artifact = tree.load(name)
        if artifact is None:
            findings.append((BLOCKING if single else REPORT, "artifact",
                             f"{name}: missing or unreadable"))
            continue
        found = audit_artifact(tree, name, artifact)
        if found:
            per_artifact[name] = [{"severity": s, "check": c, "detail": d} for s, c, d in found]
        findings += found

    if args.linters:
        findings += run_linters(tree, [s for s in args.linters.split(",") if s])

    counts = severity_counts(findings)
    outcome = verdict(findings, single)
    scope = f"artifact {args.artifact}" if single else f"archive ({len(names)} artifacts)"
    print(f"preflight — {scope}")
    for severity in (BLOCKING, UNREADABLE, REPORT):
        for found_severity, check, detail in findings:
            if found_severity == severity:
                print(f"  {found_severity:10s} {check:12s} {detail}")
    print(f"-> blocking {counts[BLOCKING]} · unreadable {counts[UNREADABLE]} · "
          f"report {counts[REPORT]} · {round(time.time() - started, 1)}s")
    print(f"outcome: {outcome}")

    if args.json:
        gates, negatives = self_check()
        here = Path(__file__).resolve()
        report = {
            "artifact": "preflight_report",
            "kind": "preflight_report",
            "summary": "audit of the declarations carried by claim-bearing artifacts",
            "scope": ("artifact:" + args.artifact) if single else "archive",
            "artifacts_examined": len(names),
            "findings_by_artifact": per_artifact,
            "severity_counts": counts,
            "gates": gates, "gates_passed": sum(gates.values()), "gates_total": len(gates),
            "negatives": negatives,
            "negatives_passed": sum(negatives.values()), "negatives_total": len(negatives),
            "outcome": outcome,
            "does_not_establish": [
                "artifact-level checks only: no gate-to-negative-control coverage, no detection of "
                "vacuous negative controls, no executed mutation probe",
                "an UNREADABLE artifact is neither compliant nor at fault — it is unauditable by a "
                "generic checker, which is the finding rather than the verdict",
                "archive scope never blocks: it measures debt, it does not pass judgement",
                "no producer is modified — an archive of hash-pinned artifacts is append-only, and "
                "editing a producer would invalidate every recorded producer hash it ever emitted",
            ],
            "seconds": round(time.time() - started, 1),
            "self_sha256": hashlib.sha256(here.read_bytes()).hexdigest(),
            "provenance": {"producer": here.name, "python": sys.version.split()[0],
                           "linters_chained": [s for s in args.linters.split(",") if s]},
        }
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"report: {args.json}")

    sys.exit(1 if outcome == "PREFLIGHT-BLOCKED" else 0)


if __name__ == "__main__":
    main()
