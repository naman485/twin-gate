# Registering Twin Gate in QM

QM imports skills from a git repository of `SKILL.md` files, pinned to a commit, with no change
to QM core ([skill registry](https://github.com/yc-software/qm/blob/main/docs/skill-registry.md)).

1. In the QM admin, open Skill packs and register this repository, or post the body in
   `skill-pack.json` to `POST /v1/admin/skill-packs` (org admin). Replace `ref` with the commit
   you want pinned.
2. Browse the pack and import `twin-gate`. It appears on the Skills page as published.
3. Set the deployment posture to **Strict** for the scopes that hold the brain, so every tool
   call pauses for a person. The twin proposal is the agent's step; approve on the Twin Gate page
   is the person's step.
4. Point the skill at the brain: the agent runs `skills/twin-gate/twingate.py` from the pack's
   materialised directory with `TWIN_BRAIN` set to the brain checkout on the scope's computer,
   and `CREATEOS_SANDBOX_API_KEY` in the deployment's secret store if the twin should be a real
   sandbox fork.

The memory side is separate: GBrain indexes the same brain folder, and `gbrain sync` runs on
approve, so QM's agents recall a change only after the gate opened.
