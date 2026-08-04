<!-- HARUSPEX:START -->
## Haruspex delivery protocol

Before modifying this repository:

1. Read `.haruspex/managed/PROTOCOL.md`.
2. Read `.haruspex/project.json` and `.haruspex/state.json`.
3. Read the active task under `.haruspex/tasks/`.
4. Run `python3 .haruspex/bin/haruspex.py doctor .`.
5. Do not work outside the active task without updating scope and rerunning the affected gate.
6. Record checks through the Haruspex CLI; do not claim evidence that was not produced.
7. Never approve a human-controlled gate.
8. Reopen an earlier stage when new evidence invalidates its outputs.
<!-- HARUSPEX:END -->
