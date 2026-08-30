# -*- coding: utf-8 -*-
"""preflight_core — pure checks over claim-bearing artifacts.

Every function here is a **pure function over plain dicts**. Nothing in this module knows about
directory layouts, file naming schemes, or any particular project: filesystem facts are *injected* by
the caller. That is what makes the module portable, and what makes it testable without a repository.

## The idea

A computational result should not travel alone. It travels with the conditions under which it was
produced and with the means to check what one is entitled to conclude from it. An artifact that carries
those conditions is a *claim-bearing artifact*: a JSON document that declares, alongside its numbers,

  * which **gates** it passed (named boolean checks that had to hold),
  * which **negative controls** were exercised (deliberate mutations that had to make a gate fail —
    evidence that the gate can detect an error at all),
  * which upstream artifacts it consumed, **pinned by hash**,
  * the hash of the **producer** that emitted it,
  * and what it explicitly does *not* establish.

Preflight answers the question a reader has before trusting such a document: *are these declarations
still true today?* Producers drift, upstream files are revised, counters are edited by hand. None of
that is caught by re-running the computation, because re-running produces a fresh document rather than
auditing the one already published.

## Design commitments

**Read defensively; publish unreadability.** Real artifact sets are polymorphic — the same field may be
a string in one document and an object in another. A checker that assumes a shape crashes on contact
with reality. Here, a block that cannot be interpreted by a generic reader is reported as UNREADABLE:
neither compliant nor at fault, but *unauditable*, which is itself the finding.

**Severity is not a property of a check, it is a property of scope.** The same drift that must stop a
document from going to review is merely debt when surveying an entire archive. A tool that fails on its
first run over an existing archive is never run a second time.

**Never rewrite the past.** These checks are read-only by construction. An archive of hash-pinned
artifacts is append-only: editing a producer would invalidate the recorded producer hash of every
artifact it ever emitted, and with it the provenance chain. History is measured, never repaired.
"""
from __future__ import annotations

import re

BLOCKING = "BLOCKING"     # must be resolved before the artifact is relied upon
REPORT = "REPORT"         # worth knowing; never stops anything on its own
UNREADABLE = "UNREADABLE"  # a generic checker cannot interpret this — the finding is the opacity

PROBE = "probe"
FRESHNESS = "freshness"
COUNTERS = "counters"
PROVENANCE = "provenance"
PARTIAL_RUN = "partial_run"

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

#  Keys under which a nested object may record a boolean outcome. Deliberately broad: the point is to
#  read what people actually write, not to impose a spelling before anyone has agreed to one.
STATUS_KEYS = ("ok", "pass", "passed", "value", "result", "status", "holds", "green", "breaks")


def read_boolean_table(block):
    """Interpret a gate or negative-control block as a table ``name -> bool``.

    Returns ``(table, note)``. ``table`` is ``None`` when no generic reading is possible, and ``note``
    then carries the reason. Three shapes are accepted, in decreasing order of how common they are in
    practice:

      * ``{name: bool}`` — the natural form;
      * ``{name: {...}}`` — readable when the nested object records a boolean outcome;
      * ``[{...}, ...]`` — readable only when each element carries both an identity and an outcome.

    A list of anonymous objects is *not* readable: without stable identities, individual entries cannot
    be referred to, compared across revisions, or targeted by a negative control.
    """
    if isinstance(block, dict):
        table, opaque = {}, []
        for name, value in block.items():
            if isinstance(value, bool):
                table[name] = value
            elif isinstance(value, dict):
                found = [value[k] for k in STATUS_KEYS if isinstance(value.get(k), bool)]
                (table.__setitem__(name, found[0]) if found else opaque.append(name))
            else:
                opaque.append(name)
        if not table and opaque:
            return None, f"no readable boolean entry ({len(opaque)} opaque)"
        if opaque:
            return table, f"{len(opaque)} non-boolean entry/entries ignored: {sorted(opaque)[:3]}"
        return table, ""
    if isinstance(block, list):
        table = {}
        for index, element in enumerate(block):
            if not isinstance(element, dict):
                return None, "list of non-object elements"
            name = next((element[k] for k in ("name", "id", "label", "kind")
                         if isinstance(element.get(k), str)), None)
            found = [element[k] for k in STATUS_KEYS if isinstance(element.get(k), bool)]
            if name is None or not found:
                return None, "list without stable identity (no name/id, or no boolean outcome)"
            table[f"{name}#{index}" if name in table else name] = found[0]
        return table, ""
    return None, f"unexpected type: {type(block).__name__}"


def check_counter_coherence(artifact):
    """Do the serialised counters still reproduce the block they summarise?

    Counters are the part of an artifact a reader is most likely to quote and least likely to verify.
    They are also the easiest to edit by hand and forget. A counter that no checker can reproduce is an
    auditability defect regardless of whether it happens to be right.

    ## Partial runs legitimately count fewer entries than they carry

    A run over a reduced sample cannot evaluate every gate: those needing the full sample are *neutralised*
    and excluded from the total, so the artifact honestly reports an **effective** count lower than the
    number of entries it carries. Measured against a real archive, this convention accounted for **every
    one** of the counter blockers — five partial artifacts, eighteen findings, none of them a defect.

    The asymmetry is what makes this safe to relax. Under-counting on a partial run is the documented
    convention, and such artifacts are non-authoritative by construction. **Over**-counting is never
    explainable that way: claiming more gates than are present can only be an error or an inflation, so
    it keeps blocking everywhere. An authoritative artifact keeps blocking in both directions.
    """
    findings = []
    partial = bool(artifact.get("limited_run"))
    for block, passed_key, total_key in (("gates", "gates_passed", "gates_total"),
                                         ("negatives", "negatives_passed", "negatives_total")):
        if block not in artifact:
            continue
        table, note = read_boolean_table(artifact[block])
        if table is None:
            findings.append((UNREADABLE, COUNTERS,
                             f"`{block}` cannot be read by a generic checker — {note}"))
            continue
        if note:
            findings.append((REPORT, COUNTERS, f"`{block}` only partially readable — {note}"))
        if passed_key in artifact:
            declared, actual = artifact[passed_key], sum(1 for v in table.values() if v)
            if declared != actual:
                undercount = partial and declared < actual
                findings.append((REPORT if undercount else BLOCKING, COUNTERS,
                                 f"`{passed_key}` = {declared} but `{block}` holds {actual} true entry/entries"
                                 + (" — partial run, gates needing the full sample are neutralised"
                                    if undercount else "")))
        else:
            findings.append((REPORT, COUNTERS, f"`{block}` carries no `{passed_key}` counter"))
        if total_key in artifact and artifact[total_key] != len(table):
            undercount = partial and artifact[total_key] < len(table)
            findings.append((REPORT if undercount else BLOCKING, COUNTERS,
                             f"`{total_key}` = {artifact[total_key]} but `{block}` holds {len(table)} entries"
                             + (" — partial run, gates needing the full sample are neutralised"
                                if undercount else "")))
    return findings


def declared_pins(artifact, roots=("upstream", "upstream_sha256", "upstream_sha_pins")):
    """Collect declared upstream pins as ``(label, sha256, path_or_None)``.

    Two spellings coexist wherever this pattern grows on its own: a flat mapping ``label -> hash``, and
    a nested object carrying ``path`` and ``sha256`` together. Both are collected. When an object *is*
    a pin, its own ``path``/``sha256`` keys are consumed by that pin and are not collected a second time
    as bare hashes — an early version double-counted them, and its own self-test caught it.
    """
    pins, seen = [], set()

    def add(pin):
        if pin not in seen:
            seen.add(pin)
            pins.append(pin)

    def walk(node, label):
        if isinstance(node, dict):
            sha_key = next((k for k in ("sha256", "sha")
                            if isinstance(node.get(k), str) and SHA256_RE.match(node[k])), None)
            path_key = next((k for k in ("path", "file") if isinstance(node.get(k), str)), None)
            consumed = {k for k in (sha_key, path_key) if k}
            if sha_key:
                add((label, node[sha_key], node.get(path_key) if path_key else None))
            for key, value in node.items():
                if key in consumed:
                    continue
                if isinstance(value, str) and SHA256_RE.match(value):
                    add((key, value, None))
                elif isinstance(value, (dict, list)):
                    walk(value, key)
        elif isinstance(node, list):
            for value in node:
                walk(value, label)

    for root in roots:
        if root in artifact:
            walk(artifact[root], root)
    return pins


def check_provenance(artifact, resolve):
    """Does every declared upstream pin still resolve to a file with the declared hash?

    ``resolve(label, path)`` is injected and returns ``(display_name, live_sha256)``; either may be
    ``None`` when the pin cannot be located. A pin whose target has since moved is the ordinary way a
    result silently starts describing a world that no longer exists.
    """
    findings = []
    for label, sha256, path in declared_pins(artifact):
        name, live = resolve(label, path)
        if name is None:
            findings.append((REPORT, PROVENANCE, f"pin `{label}` cannot be resolved"))
        elif live != sha256:
            findings.append((BLOCKING, PROVENANCE,
                             f"pin `{label}` -> {name}: declared {sha256[:12]}… != live {str(live)[:12]}…"))
    return findings


def check_freshness(artifact, producer_name, producer_sha, is_partial_run):
    """Does the artifact still correspond to the producer that emitted it?

    ``producer_sha`` is injected; ``producer_name`` is used only for the message. ``producer_sha`` of
    ``None`` means the producer could not be located, which is reported rather than judged.

    A **partial run** is treated differently on purpose. Partial runs exist to validate a chain cheaply
    before paying for a full one; they are never authoritative, and it is normal for one to remain on
    disk describing an earlier revision while the producer moves on. Measuring the drift is still
    useful — it says the chain was not re-validated cheaply before the expensive run — but it must not
    block. Drift in an authoritative artifact is a different matter entirely.
    """
    declared = artifact.get("self_sha256")
    if not isinstance(declared, str):
        return []
    if producer_sha is None:
        return [(REPORT, FRESHNESS, "producer could not be located")]
    if producer_sha == declared:
        return []
    severity = REPORT if is_partial_run else BLOCKING
    what = ("partial run not re-validated at the current revision (never authoritative)"
            if is_partial_run else "STALE")
    return [(severity, FRESHNESS,
             f"{what} — artifact {declared[:12]}… != {producer_name} live {producer_sha[:12]}…")]


def check_partial_run_discipline(is_partial_name, artifact):
    """A partial run must not occupy the place of an authoritative result.

    ``is_partial_name`` says whether the artifact's *name* marks it as partial. The flag inside the
    document and the name outside it must agree: a document that declares itself partial while sitting
    under an authoritative name silently replaces a full result with a cheap one, and the substitution
    is invisible until someone diffs the archive.
    """
    flag = artifact.get("limited_run", artifact.get("partial_run"))
    if flag is True and not is_partial_name:
        return [(BLOCKING, PARTIAL_RUN,
                 "declared a partial run but named as authoritative — a cheap run is occupying "
                 "the place of a full one")]
    if flag is False and is_partial_name:
        return [(REPORT, PARTIAL_RUN, "named as a partial run but declares itself full")]
    return []


def check_mutation_probe(artifact, probe_key="mutation_probe"):
    """The executed tier: did each gate actually fail under a deliberate mutation?

    Reading that a control invokes a gate's predicate is evidence of a link; it is not proof that the
    gate *fails*. Only running the mutation proves that — and running it is not this checker's business.
    A checker that executed the code it audits could be made to lie by that code. So the producer runs
    its own probe and records the outcome; this reads the record.

    The block is ``{gate: {mutation_name: gate_went_red}}``. A gate listed with no mutation that made it
    fail is the finding this whole tool exists for: a gate that survives every attempt to break it has
    not been shown to measure anything. A gate absent from the probe is merely unprobed.

    Absent block, no findings: the tier is opt-in, and a producer that has not adopted it is not at fault.
    """
    probe = artifact.get(probe_key)
    if not isinstance(probe, dict) or not probe:
        return []
    gates, _ = read_boolean_table(artifact.get("gates", {}))
    findings = []
    for gate, mutations in probe.items():
        if not isinstance(mutations, dict) or not mutations:
            findings.append((REPORT, PROBE, f"gate `{gate}` has an empty probe entry"))
            continue
        if not any(v is True for v in mutations.values()):
            findings.append((BLOCKING, PROBE,
                             f"gate `{gate}` survived every mutation ({len(mutations)} tried) — it has "
                             f"not been shown to detect anything"))
    for gate in (gates or {}):
        if gate not in probe:
            findings.append((REPORT, PROBE, f"gate `{gate}` is never probed by a mutation"))
    return findings


def severity_counts(findings):
    """Aggregate findings by severity."""
    return {s: sum(1 for f in findings if f[0] == s) for s in (BLOCKING, REPORT, UNREADABLE)}


def verdict(findings, scoped_to_single_artifact):
    """The decision, as a pure function.

    Blocking findings stop a *single* artifact — the gesture performed before relying on it. Over a
    whole archive nothing stops, because a survey measures debt rather than passing judgement, and a
    tool that fails on its first survey is never run again.
    """
    counts = severity_counts(findings)
    if scoped_to_single_artifact and counts[BLOCKING]:
        return "PREFLIGHT-BLOCKED"
    if any(counts.values()):
        return "PREFLIGHT-OK-WITH-DEBT"
    return "PREFLIGHT-CLEAN"


def self_check():
    """Gates and negative controls for this module, in the discipline it exists to enforce.

    Each negative control names the gate it must trip. That convention is applied here first, because a
    checker that cannot demonstrate its own checks have teeth has no standing to ask it of anything else.
    """
    gates, negatives = {}, {}
    gates["G1_reads_the_natural_form"] = read_boolean_table({"A": True, "B": False})[0] == {"A": True, "B": False}
    gates["G2_reads_nested_objects"] = read_boolean_table({"A": {"ok": True}})[0] == {"A": True}
    gates["G3_reads_identified_lists"] = read_boolean_table([{"name": "A", "breaks": True}])[0] == {"A": True}
    gates["G4_wrong_counter_blocks"] = any(
        f[0] == BLOCKING for f in check_counter_coherence({"gates": {"A": True}, "gates_passed": 2}))
    gates["G5_collects_all_pin_spellings"] = len(declared_pins(
        {"upstream": {"a.json": "0" * 64, "b": {"path": "x/b.json", "sha256": "1" * 64}},
         "upstream_sha_pins": {"c.py": "2" * 64}})) == 3
    gates["G6_partial_run_under_authoritative_name_blocks"] = any(
        f[0] == BLOCKING for f in check_partial_run_discipline(False, {"limited_run": True}))
    gates["G7_survey_never_blocks"] = verdict([(BLOCKING, FRESHNESS, "x")], False) == "PREFLIGHT-OK-WITH-DEBT"
    gates["G8_stale_authoritative_blocks_partial_only_reports"] = (
        check_freshness({"self_sha256": "a" * 64}, "p.py", "b" * 64, False)[0][0] == BLOCKING
        and check_freshness({"self_sha256": "a" * 64}, "p.py", "b" * 64, True)[0][0] == REPORT)

    negatives["N1_opaque_shape_is_unreadable_not_true_trips_G1"] = read_boolean_table({"A": {"why": "text"}})[0] is None
    negatives["N2_anonymous_list_is_unreadable_trips_G3"] = read_boolean_table([{"breaks": True}])[0] is None
    negatives["N3_correct_counter_does_not_block_trips_G4"] = not any(
        f[0] == BLOCKING for f in check_counter_coherence({"gates": {"A": True}, "gates_passed": 1}))
    gates["G15_partial_undercount_reports_not_blocks"] = not any(
        f[0] == BLOCKING for f in check_counter_coherence(
            {"gates": {"A": True, "B": True}, "gates_total": 1, "limited_run": True}))
    #  The relaxation must stay one-sided in both of the ways it could leak: an inflated count on a
    #  partial run, and any mismatch at all on an authoritative one.
    negatives["N20_partial_overcount_still_blocks_trips_G15"] = any(
        f[0] == BLOCKING for f in check_counter_coherence(
            {"gates": {"A": True}, "gates_total": 5, "limited_run": True}))
    negatives["N21_authoritative_undercount_still_blocks_trips_G15"] = any(
        f[0] == BLOCKING for f in check_counter_coherence(
            {"gates": {"A": True, "B": True}, "gates_total": 1}))
    negatives["N4_absence_of_pins_invents_none_trips_G5"] = declared_pins({"note": "no upstream"}) == []
    negatives["N5_truncated_hash_is_not_a_pin_trips_G5"] = declared_pins({"upstream": {"a": "abc"}}) == []
    negatives["N6_consistent_partial_name_does_not_block_trips_G6"] = not any(
        f[0] == BLOCKING for f in check_partial_run_discipline(True, {"limited_run": True}))
    negatives["N7_single_scope_does_block_trips_G7"] = verdict([(BLOCKING, FRESHNESS, "x")], True) == "PREFLIGHT-BLOCKED"
    negatives["N8_clean_input_yields_clean_verdict_trips_G7"] = verdict([], True) == "PREFLIGHT-CLEAN"
    negatives["N9_matching_producer_yields_no_finding_trips_G8"] = check_freshness(
        {"self_sha256": "a" * 64}, "p.py", "a" * 64, False) == []
    negatives["N10_absent_hash_invents_no_verdict_trips_G8"] = check_freshness({}, "p.py", "b" * 64, False) == []
    gates["G9_a_gate_surviving_every_mutation_blocks"] = any(
        f[0] == BLOCKING for f in check_mutation_probe(
            {"gates": {"A": True}, "mutation_probe": {"A": {"m1": False, "m2": False}}}))
    negatives["N11_a_gate_that_fails_under_one_mutation_passes_trips_G9"] = not any(
        f[0] == BLOCKING for f in check_mutation_probe(
            {"gates": {"A": True}, "mutation_probe": {"A": {"m1": False, "m2": True}}}))
    negatives["N12_absent_probe_invents_no_finding_trips_G9"] = check_mutation_probe(
        {"gates": {"A": True}}) == []
    return gates, negatives
