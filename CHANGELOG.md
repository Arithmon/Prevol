# Changelog

All notable changes to `preflight`. Dates are ISO 8601. Versions follow semantic versioning.

## [0.1.0] — 2026-08-29

First working tier: artifact-level checks, runnable over an existing archive without modifying any
producer.

### Added
- `preflight_core` — pure checks over plain dicts, with all filesystem facts injected by the caller.
  Portable and testable without a repository.
- `preflight` — command line over a configurable tree layout; single-artifact and archive scopes.
- Four checks: `freshness`, `counters`, `provenance`, `partial run`.
- Chaining of external linters, absorbing their differing command lines and exit conventions.
- `--json` report that is itself a claim-bearing artifact and passes its own audit.
- Self-check: 8 gates and 10 negative controls, each negative control naming the gate it must trip.

### Findings from the first survey of the reference archive (606 artifacts)
- **7 authoritative artifacts stale** — the recorded producer hash no longer matches the producer.
- **18 counter incoherences** — serialised tallies that do not reproduce their block.
- **9 provenance mismatches** — declared upstream pins whose target has since moved. One of these was
  a document pinning a specification that had been revised *after* it ran: the pre-review audit of that
  document correctly refuses, while a sibling produced after the revision passes.
- **25 artifacts unreadable** by a generic checker, including four declaring a count of passing negative
  controls while carrying no entry a checker can evaluate. Either the count is wrong or the shape is
  unauditable; both are work for this tool.

### Learned from first contact, rather than assumed
- A stale **partial run** is expected, not a fault: partial runs validate a chain cheaply at a given
  revision and are never authoritative. Reported, not blocking. A stale *authoritative* artifact is a
  different matter. (8 partial versus 7 authoritative in the reference archive.)
- An artifact must be able to **declare its producer**. Guessing from the file name leaves any artifact
  whose name differs from its producer's unauditable — including this tool's own report, which is how
  the gap was found.

### Deliberately not included
Gate-to-negative-control coverage, detection of vacuous negative controls, and executed mutation probes.
Measurement of the reference archive puts current coverage at **0 of 965 gates** under a strict reading:
the link between a gate and the control that tests it does not yet exist in practice. Establishing that
link comes before probing it.
