# -*- coding: utf-8 -*-
"""prevol.coverage — do the gates have teeth?

The artifact-level tier asks whether a document's declarations are still true. This tier asks something
harder and more useful: **would these checks have noticed had the result been wrong?**

A gate that cannot fail measures nothing, and no amount of re-running reveals that — a gate wired to a
constant passes every run, forever, and looks exactly like a gate that holds. The only evidence that a
gate has teeth is a *negative control*: a deliberate mutation under which the gate must fail. So the
question this module answers, by reading the producer's source rather than its output, is whether each
gate is exercised by such a control, and whether the controls themselves do any work.

## Why source, and why not names

Coverage can be guessed from naming conventions — a control called `N7_..._trips_G3` presumably tests
`G3`. Measured across a real archive of 965 gates, that convention accounted for **4%**. Naming is a
convention people adopt late and unevenly, and demanding it retroactively would only produce renaming.

There is a better signal already present in the code. Where this discipline matures on its own, gates
and their controls end up calling the *same predicate*: the gate asks `pred(real_input)`, the control
asks `not pred(mutated_input)`. That shared call is structural evidence of a link — it survives
renaming, it needs no declaration, and it cannot be produced by writing a nice name.

So coverage is established by, in decreasing order of strength:

  1. a **shared predicate** — gate and control invoke a common function (structural);
  2. a **declared target** — the control's recorded entry names the gate (explicit);
  3. a **name token** — the gate's identifier appears in the control's name (conventional).

## Vacuity

A control can be present, well named, and still test nothing. Two failure modes are detectable without
executing anything:

  * **constant** — the control's expression references no name and calls nothing, so its value is fixed
    at authoring time;
  * **inert** — the control calls nothing at all that any gate also calls, so whatever it computes, it
    is not exercising a gate.

Both are reported rather than assumed fatal, because a checker that misreads unfamiliar code as a defect
teaches people to ignore it. The one exception is a control that is a bare literal: there is no reading
under which `"control": True` demonstrates anything.

Everything here is a pure function from **source text** to findings. Nothing is imported, nothing is
executed: a module that ran the code it audits could be made to lie by that code.
"""
from __future__ import annotations

import ast
import re

from .core import BLOCKING, REPORT

COVERAGE = "coverage"
VACUITY = "vacuity"

#  Names under which a producer collects its gates and its negative controls. Extendable by the caller
#  rather than hard-coded, because these words are a convention and not a law.
#
#  Deliberately *not* including short generic names such as `g`, `n` or `st`: measured against a real
#  archive, they matched ordinary data records — one such record carried a field called `rows`, which was
#  duly reported as a vacuous control. A default that misfires costs more than one that under-reports,
#  because under-reporting shows up in the coverage figure while a false accusation teaches people to
#  ignore the tool. Projects using shorter names pass them explicitly; that is what the parameter is for.
DEFAULT_GATE_NAMES = ("gates",)
DEFAULT_CONTROL_NAMES = ("negatives", "negative_controls")

#  A short leading identifier such as `G3`, `Q10`, `N7`, `S1`, `KA1` — the way gates are labelled when
#  they are labelled at all.
IDENTIFIER_RE = re.compile(r"^([A-Za-z]{1,3}\d+[a-z]?)(?:_|$)")


def _called(node):
    """Every function name invoked anywhere inside an expression, attribute calls included."""
    names = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            target = child.func
            if isinstance(target, ast.Name):
                names.add(target.id)
            elif isinstance(target, ast.Attribute):
                names.add(target.attr)
    return names


def _referenced(node):
    return {c.id for c in ast.walk(node) if isinstance(c, ast.Name)}


def _is_literal(node):
    """True when the expression can be evaluated with no name and no call — its value is fixed in place."""
    return not _referenced(node) and not _called(node)


def read_structure(source, gate_names=DEFAULT_GATE_NAMES, control_names=DEFAULT_CONTROL_NAMES):
    """Extract gates and negative controls from a producer's source.

    Returns ``{"gates": {name: entry}, "controls": {name: entry}}`` where each entry records the set of
    functions its expression calls and whether that expression is a bare literal. Raises nothing: a
    source that cannot be parsed yields empty tables, and the caller reports that as its own finding.
    """
    out = {"gates": {}, "controls": {}}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return out
    #  An entry may be *seeded* with a placeholder and computed further down — the shape
    #  `controls["N8"] = False  # recomputed below` is common enough that reading only the dict literal
    #  would report perfectly sound controls as constants. Later assignments to a subscript therefore
    #  override what the literal said. Measured against a real archive, this accounted for two of the
    #  three constants the first version reported, and both were sound.
    reassigned = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)):
                reassigned.setdefault(target.value.id, {})[target.slice.value] = {
                    "calls": _called(node.value), "literal": _is_literal(node.value)}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
        if targets & set(gate_names):
            bucket = "gates"
        elif targets & set(control_names):
            bucket = "controls"
        else:
            continue
        for key, value in zip(node.value.keys, node.value.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            entry = {"calls": _called(value), "literal": _is_literal(value)}
            later = {k: v for name in targets for k, v in reassigned.get(name, {}).items()}
            if key.value in later:      # seeded here, computed further down
                entry = {"calls": entry["calls"] | later[key.value]["calls"],
                         "literal": later[key.value]["literal"]}
            out[bucket][key.value] = entry
    return out


def identifier_of(name):
    """The short leading identifier of a gate name, if it has one (``G3_holds`` -> ``G3``)."""
    found = IDENTIFIER_RE.match(name)
    return found.group(1) if found else None


def covers(gate_name, gate_entry, control_name, control_entry, declared_targets=()):
    """Does this control exercise this gate? Returns the strongest reason, or ``None``.

    Shared calls are checked first because they are the only evidence a rename cannot fake.
    """
    shared = gate_entry["calls"] & control_entry["calls"]
    if shared:
        return f"shared predicate: {sorted(shared)[0]}"
    if gate_name in declared_targets:
        return "declared target"
    identifier = identifier_of(gate_name)
    if identifier and re.search(rf"(?:^|_){re.escape(identifier)}(?:_|$)", control_name):
        return f"name token: {identifier}"
    return None


def check_coverage(structure, declared_targets_by_control=None):
    """Report gates that no negative control exercises.

    Always REPORT, never blocking. Coverage across an existing archive is close to nothing, and a check
    that fails everywhere on its first run is a check nobody runs twice. It is here to be *measured*, and
    to stop new work from drifting further, not to condemn what already exists.
    """
    declared = declared_targets_by_control or {}
    gates, controls = structure["gates"], structure["controls"]
    if not gates:
        return [], {"gates": 0, "covered": 0, "by_reason": {}}
    findings, covered, reasons = [], 0, {}
    for gate_name, gate_entry in gates.items():
        hit = None
        for control_name, control_entry in controls.items():
            hit = covers(gate_name, gate_entry, control_name, control_entry,
                         declared.get(control_name, ()))
            if hit:
                break
        if hit:
            covered += 1
            kind = hit.split(":")[0]
            reasons[kind] = reasons.get(kind, 0) + 1
        else:
            findings.append((REPORT, COVERAGE, f"gate `{gate_name}` is exercised by no negative control"))
    return findings, {"gates": len(gates), "covered": covered, "by_reason": reasons}


def check_vacuity(structure):
    """Report negative controls that cannot be testing anything.

    A bare literal blocks: there is no reading under which a constant demonstrates that a gate can fail.
    A control that shares no call with any gate is reported rather than blocked — it may be exercising
    something through a path this reading does not follow, and a checker that mistakes unfamiliar code
    for a defect teaches people to ignore it.
    """
    gates, controls = structure["gates"], structure["controls"]
    gate_calls = set().union(*(g["calls"] for g in gates.values())) if gates else set()
    findings = []
    for name, entry in controls.items():
        if entry["literal"]:
            findings.append((BLOCKING, VACUITY,
                             f"negative control `{name}` is a constant expression — it holds by "
                             f"construction and demonstrates nothing"))
        elif gates and not (entry["calls"] & gate_calls):
            findings.append((REPORT, VACUITY,
                             f"negative control `{name}` shares no call with any gate — it may not be "
                             f"exercising one"))
    return findings


def audit_source(source, declared_targets_by_control=None, **names):
    """Both checks over one producer's source. Returns ``(findings, coverage_summary)``."""
    structure = read_structure(source, **names)
    coverage_findings, summary = check_coverage(structure, declared_targets_by_control)
    return coverage_findings + check_vacuity(structure), summary


def self_check():
    """Gates and negative controls for this module, in the discipline it exists to measure.

    Written so that the module's own coverage is established by *shared predicates* rather than by the
    naming convention it declines to rely on.
    """
    linked = ("def pred(x):\n    return bool(x)\n"
              "gates = {'G1_holds': pred(1)}\n"
              "negatives = {'N1_mutation_trips_G1': not pred(0)}\n")
    unlinked = ("gates = {'G1_holds': compute(1)}\n"
                "negatives = {'N1_unrelated': other(0)}\n")
    constant = "gates = {'G1_holds': compute(1)}\nnegatives = {'N1_asserted': True}\n"
    named = ("gates = {'G3_holds': compute(1)}\n"
             "negatives = {'N1_mutation_trips_G3': other(0)}\n")

    gates, negatives = {}, {}
    gates["G1_extracts_gates_and_controls"] = (
        set(read_structure(linked)["gates"]) == {"G1_holds"}
        and set(read_structure(linked)["controls"]) == {"N1_mutation_trips_G1"})
    gates["G2_shared_predicate_establishes_coverage"] = (
        check_coverage(read_structure(linked))[1]["covered"] == 1)
    gates["G3_name_token_establishes_coverage"] = (
        "name token" in str(check_coverage(read_structure(named))[1]["by_reason"]))
    gates["G4_constant_control_blocks"] = any(
        f[0] == BLOCKING for f in check_vacuity(read_structure(constant)))
    gates["G5_unparsable_source_yields_empty_tables"] = (
        read_structure("def broken(:") == {"gates": {}, "controls": {}})
    gates["G6_identifier_is_read_from_the_name"] = (
        identifier_of("Q10_budget") == "Q10" and identifier_of("plain") is None)

    negatives["N1_unlinked_control_leaves_gate_uncovered_trips_G2"] = (
        check_coverage(read_structure(unlinked))[1]["covered"] == 0)
    negatives["N2_unlinked_control_is_reported_trips_G4"] = any(
        f[1] == VACUITY for f in check_vacuity(read_structure(unlinked)))
    negatives["N3_linked_control_is_not_flagged_vacuous_trips_G4"] = (
        check_vacuity(read_structure(linked)) == [])
    negatives["N4_absent_gates_yield_no_coverage_claim_trips_G1"] = (
        check_coverage(read_structure("x = 1"))[1]["gates"] == 0)
    negatives["N5_name_alone_never_beats_a_shared_call_trips_G3"] = (
        covers("G1_holds", {"calls": {"pred"}}, "N1_trips_G1", {"calls": {"pred"}}, ())
        .startswith("shared predicate"))
    negatives["N6_a_gate_without_identifier_is_not_matched_by_accident_trips_G6"] = (
        covers("plain_gate", {"calls": set()}, "N1_plain_gate_ish", {"calls": set()}, ()) is None)
    seeded = ("gates = {'G1_holds': pred(1)}\n"
              "negatives = {'N1_seeded': False}\n"
              "negatives['N1_seeded'] = not pred(0)\n")
    negatives["N7_a_seeded_control_computed_later_is_not_constant_trips_G4"] = (
        check_vacuity(read_structure(seeded)) == [])
    return gates, negatives
