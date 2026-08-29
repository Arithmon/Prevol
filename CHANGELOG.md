# Changelog

All notable changes to `preflight`. Dates are ISO 8601. Versions follow semantic versioning.

## [0.3.0] — 2026-08-29

The executed tier, and with it the question the whole tool exists for: **did the gate actually fail?**

### Added
- `check_mutation_probe` — reads a `mutation_probe` block of the shape `{gate: {mutation: went_red}}`.
  A gate listed with no mutation that made it fail **blocks**: a gate surviving every attempt to break it
  has not been shown to measure anything. A gate absent from the block is merely unprobed; an absent
  block yields no findings at all, because the tier is opt-in and a producer that has not adopted it is
  not at fault.

### The division of labour, and why it is not a compromise
The producer runs its own mutations and records the outcome; this tool reads the record. That is not a
limitation worked around — it is the invariant. A checker that executed the code it audits could be made
to lie by that code. Execution belongs where execution already happens.

### Validated on a real subject
The first producer to adopt the convention carried five gates, each with two or three mutations of the
inputs its predicate reads. All five failed under mutation, and the artifact passed with no probe
finding. Its gates also reached full coverage in the source tier, from shared predicates alone.

## [0.2.0] — 2026-08-29

The source-level tier: **do the gates have teeth?** The first tier asks whether a document's declarations
are still true. This one asks whether the checks in it would have noticed had the result been wrong.

### Added
- `prevol.coverage` — pure functions from a producer's **source text** to findings. Nothing is imported
  and nothing is executed: a module that ran the code it audits could be made to lie by that code.
- **Gate coverage**, established in decreasing order of strength: a *shared predicate* (gate and control
  invoke a common function — structural, survives renaming, cannot be faked by writing a nice name), a
  *declared target*, or a *name token*. Reported, never blocking.
- **Vacuity detection**: a control that is a bare literal blocks — there is no reading under which a
  constant demonstrates that a gate can fail. A control sharing no call with any gate is reported.
- `--no-source` to skip the tier; `gate_names` / `control_names` in the tree layout for projects whose
  producers collect gates under other names.

### Measured
Across 161 producers carrying 1279 gates in the reference archive, the naming convention alone accounted
for **4%** of coverage. Reading the code instead raises that to **12.4%**, and two thirds of the links
found come from shared predicates that no naming convention would have revealed. Eight producers reach
full coverage; the median is zero. The figure is published rather than enforced: a check that fails
everywhere on its first run is a check nobody runs twice.

### Learned from first contact, again
- Short generic variable names (`g`, `n`, `st`) were **removed from the defaults**. Measured against real
  code they matched ordinary data records — one such record carried a field named `rows`, duly reported
  as a vacuous control. A default that misfires costs more than one that under-reports: under-reporting
  shows up in the coverage figure, while a false accusation teaches people to ignore the tool. Projects
  using short names declare them.
- A control may be **seeded** with a placeholder and computed further down (`controls["N8"] = False  #
  recomputed below`). Reading only the literal reported two perfectly sound controls as constants. Later
  assignments now override what the literal said.

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
