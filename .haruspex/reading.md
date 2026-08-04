# HARUSPEX — THE READING

**Stage:** IP provenance inventory specification  
**Recommendation:** PROCEED WITH CONDITIONS

## Outcome

Create a private, evidence-linked inventory and archive while adding only public-safe metadata and a fail-closed pre-publication review to Haruspex.

## Material assumptions

- Validated: GitHub and Git metadata can establish observed publication history, not legal ownership.
- Accepted for this implementation: unavailable employment, contributor, AI, and copied-material evidence remains explicitly unknown.
- Validated: GitHub writes use the `pxm-0` identity.

## Blind spots and failure modes

- Public disclosure of contracts, privileged communications, credentials, or confidential employer material.
- Treating a Git author identity, registration, or an evidence hash as a legal title determination.
- Losing the only archive or failing to verify it against the public commit.
- Publishing a licence before ownership and licensing authority are resolved.

## Gate blockers

- Explicit human approval of the ready-to-build gate.

## Next actions

1. Open the draft PR with issues #6–#9.
2. Obtain ready-to-build approval.
3. Implement public metadata, private ledger, archive, and deterministic validation.
4. Verify evidence and leave legal conclusions unresolved for counsel.
