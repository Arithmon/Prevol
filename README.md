# prevol

**Audit the declarations that a computational result carries — and check they are still true.**

A result should not travel alone. It should travel with the conditions under which it was produced and
with the means to check what one is entitled to conclude from it. Tools already exist to record *what
ran*: workflow managers, lineage trackers, experiment logs. They answer a different question from the
one a careful reader actually asks, which is whether the declarations attached to a published result
still hold today.

Re-running the computation does not answer it either. Re-running produces a *fresh* document; it does
not audit the one already published.

## What it checks

| check | question |
|---|---|
| `freshness` | does the artifact still correspond to the producer that emitted it? |
| `counters` | do the serialised tallies still reproduce the blocks they summarise? |
| `provenance` | does every declared upstream pin still resolve to its declared hash? |
| `partial run` | is a cheap validation run occupying the place of a full result? |

All four are performed **on the artifact alone**. An existing archive can therefore be audited without
touching a single producer — which matters, because an archive of hash-pinned artifacts is *append-only*
by construction: editing a producer would invalidate the recorded producer hash of every artifact it
ever emitted, and with it the provenance chain. History is measured, never repaired.

External linters can be chained so that a single command is the whole pre-review gesture (`--linters`).

## Two severities, and scope decides

Auditing **one artifact** — the gesture performed before relying on it — stops on a blocking finding and
exits non-zero.

Surveying **the whole archive** never stops. It measures debt rather than passing judgement, because a
tool that fails on its first survey is never run a second time. This is not leniency; it is the only way
a check gets adopted by a body of work that predates it.

## Usage

```sh
pip install -e .

prevol --artifact NAME --root DIR      # audit one artifact — blocking, exits non-zero
prevol --survey --root DIR --json R    # survey the archive — never blocking
prevol --self-check                    # this tool's own gates and negative controls
```

The tree layout is configuration, not convention. Pass `--root`, and override the directory names in
`prevol.cli.DEFAULTS` (or build a `Tree` directly) to match an archive of any shape:

```python
from prevol.cli import Tree, audit_artifact

tree = Tree(Path("."), {"artifacts": "out/results", "producers": "src", "partial_suffix": "_draft"})
findings = audit_artifact(tree, name, tree.load(name))
```

The checks themselves live in `prevol.core` and are pure functions over plain dicts: they take no paths,
open no files, and can be exercised without an archive at all.

## Self-application

The report written by `--json` is itself a claim-bearing artifact, and auditing that report with this
tool yields no findings. This is not a flourish. A checker that cannot describe itself in the shape it
demands of others is asking for a shape that does not work — and the requirement that an artifact be
able to *declare* its producer was discovered exactly this way, by the tool failing its own audit.

The tool's own checks carry gates and negative controls, and **every negative control names the gate it
must trip**. A checker that cannot demonstrate its own checks have teeth has no standing to ask it of
anything else.

## What it does not do — yet

This is the artifact-level tier. It does not measure whether each gate is covered by a negative control,
it does not detect a negative control that passes without testing anything, and it does not execute
mutations to prove a gate can fail. Those tiers come next, in that order: building a mutation probe
before gates and their negative controls are even linked would be putting the roof on the scaffolding.

## Why this exists

Because gates do not find the interesting defects — adversarial readers do. What gates do is *hold the
ground* an adversary won, so it cannot be quietly lost again. The mechanism is a ratchet, not a
compiler: a compiler rejects wrong programs by construction, and nothing here can. What this can do is
accumulate ground that can no longer be given back.
