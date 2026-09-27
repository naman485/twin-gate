---
name: twin-gate
description: Change the team brain only through a twin. Propose the change in a forked twin of the brain, let the checks run, and hand the owner a review link. Never write to the brain's main branch directly.
scope: company
version: 0.1.0
---

# Twin Gate

Use this skill whenever a task would change a page in the team's brain (the [GBrain](https://gbrain.io) folder of
markdown records): a new record, an edit to a figure, a drafted document that will be filed.

## What you do

1. Do not edit the brain directly. Run the proposal in a twin:

   ```bash
   python3 skills/twin-gate/twingate.py propose --task "<the task, in one sentence>"
   ```

   The command creates a twin (a branch of the brain and, when a [CreateOS](https://createos.sh) key is present, a
   forked [sandbox](https://createos.sh/docs/Sandbox/Overview/) with egress denied), applies the change there, runs the checks, and prints
   a JSON result with the twin id, the changed pages and each check.

2. Read the checks. If any check failed, fix the cause in a new proposal. Common causes:
   - `numbers reconcile`: a figure you copied does not match its source page. Declare it in
     front matter as `reconcile: <field> = <page-path>#<field>` and copy the exact value.
   - `links resolve`: a `[[link]]` names a page that does not exist. Link by path, for example
     `[[shipping/shp-0031]]`.
   - `no new external URLs`: do not add outbound links to brain pages.

3. Reply to the member with the twin id, the one-line note, and the review link
   `http://localhost:8790` (or the deployment's Twin Gate URL). Say which checks passed.
   Do not approve. Approval is the owner's action on the review page.

## What you never do

- Write, move or delete files under the brain's main checkout.
- Merge a twin branch.
- Invent a number. If a value is missing, say so on the page and leave the field empty.

## Why

Every action in the twin is logged on a hash chain and the log is shown at review. The owner
sees the diff, the checks and the log in one place and merges with one click. Nothing reaches
the brain another way.
