# IP provenance plan

## Goal

Preserve a verifiable Haruspex creation and publication inventory without exposing sensitive records or asserting legal ownership that the evidence does not establish.

## Plan

- [ ] #7 Bootstrap repository-local provenance controls.
- [ ] #6 Add public-safe copyright and contribution metadata.
- [ ] #8 Create a private IP ledger and full-history preservation archive.
- [ ] #9 Validate the inventory and archive hashes.

## Public/private boundary

The public repository may contain observed repository facts, non-sensitive contributor declarations, third-party notices, and the pre-publication checklist. Contracts, identity documents, credentials, privileged communications, confidential employer material, and underlying private evidence must remain outside Git. The private ledger stores references and SHA-256 hashes, not those underlying documents.

Git history is publication evidence, not conclusive proof of human authorship or legal ownership. Unverified facts remain `unknown` until supported by an identified record or reviewed by counsel.

## Out of scope

- Legal interpretation or a clean-title representation.
- Copyright, patent, or trademark filing.
- Choosing an open-source or commercial licence.
- Rewriting or deleting repository history.

## Test plan

1. Run the existing self-test and evidence-integrity regression suite.
2. Build the release archives.
3. Validate private ledger fields, allowed statuses, evidence references, and forbidden paths.
4. Verify the full-history Git bundle and compare its recorded commit and SHA-256 digest.
5. Inspect the public diff for sensitive content and unsupported ownership claims.

## Release condition

Keep the pull request in draft until automated checks pass, the private ledger and archive exist, and a human confirms the public/private boundary. Legal ownership remains a separate counsel decision.
