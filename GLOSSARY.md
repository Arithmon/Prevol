# Glossary

The vocabulary this tool uses, and — where it matters — what it deliberately does *not* mean.

### claim-bearing artifact
A machine-readable document that carries, alongside its numbers, the conditions under which they were
produced: the gates that had to hold, the negative controls that were exercised, the upstream inputs
pinned by hash, the hash of the producer, and an explicit statement of what the document does not
establish. The unit this tool audits.

### producer
The program that emitted an artifact. An artifact should **declare** its producer rather than leave it
to be guessed from a file name; guessing leaves any artifact whose name differs from its producer's
unauditable.

### gate
A named boolean check that had to hold for a result to be published. A gate is only worth its name if it
would have failed had the result been wrong — which is a property of the gate, not of its author's
intentions, and has to be demonstrated rather than asserted.

### negative control
A deliberate mutation of a gate's inputs, together with the requirement that the gate fail under it.
Borrowed from experimental practice, where a control that cannot come out negative measures nothing. A
negative control that passes without exercising the mechanism it names is *vacuous*: it is worse than
absent, because it looks like coverage.

### freshness
Whether an artifact still corresponds to the producer that emitted it, established by comparing the
recorded producer hash against the producer on disk. Drift means the artifact describes a program that
no longer exists.

### provenance pin
A declared upstream dependency, recorded with the hash of the exact file consumed. A pin whose target
has since moved is the ordinary way a result silently starts describing a world that no longer exists.

### partial run
A deliberately truncated run, used to validate a chain cheaply before paying for a full one. Never
authoritative. It is normal for a partial run to remain on disk describing an earlier revision; drift in
a partial run is reported, drift in an authoritative artifact blocks.

### append-only
The property that makes an archive of hash-pinned artifacts auditable: producers are never rewritten,
because editing one would invalidate the recorded producer hash of every artifact it ever emitted.
History is measured, never repaired. This is why every check here operates read-only.

### scope
Whether the audit concerns one artifact or a whole archive. Scope, not the check, decides severity: a
blocking finding stops a single artifact from being relied upon, while the same finding in an archive
survey is debt to be measured.

### BLOCKING / REPORT / UNREADABLE
The three outcomes of a check. `UNREADABLE` is not a failure and not a pass: it means a generic checker
cannot interpret the block at all. Opacity is itself the finding — a tally no one can reproduce is an
auditability defect whether or not it happens to be correct.

### ratchet
The mechanism this tool belongs to. Adversarial readers find defects; the finding is then encoded as a
gate and a negative control; the gate holds that ground from then on. Deliberately *not* a **compiler**:
a compiler rejects wrong programs by construction, which nothing here can do. What a ratchet does is
accumulate ground that can no longer be given back.

### proof-carrying computation
The property being aimed at: a numerical result never circulates alone, but with the conditions of its
production and the means to verify what may legitimately be concluded from it.
