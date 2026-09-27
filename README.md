# Twin Gate

The agent works in a live twin of the brain. Production takes only what the twin proved.

Built at the YC Own Your Intelligence hackathon, 27 September 2026. Standard library Python,
no framework. Runs on a laptop with Ollama, or with a rules fallback when no model is present.

## What it does

A team keeps its records as a GBrain folder: markdown pages with front matter, under git.
Agents want to write to it. Twin Gate makes that safe without slowing the agent down:

1. **Propose.** `twingate.py propose --task "..."` creates a twin: a branch of the brain in a
   git worktree, and, when `CREATEOS_SANDBOX_API_KEY` is set, a fork of a paused CreateOS
   sandbox that holds the brain at its known state, with egress denied in the host kernel.
2. **Work.** The agent (Ollama, or the rules fallback) makes its edits in the twin only. Every
   action is appended to a hash-chained log.
3. **Prove.** Checks run on the twin, and again inside the sandbox: front matter present, links
   resolve, declared figures reconcile with their source pages, no new outbound URLs, no key
   material. A failed check blocks approval.
4. **Approve.** The owner sees diff, checks and log on one page and merges with one click.
   Reject discards the branch and destroys the sandbox. Nothing reaches main another way.

## Run

```bash
git clone https://github.com/naman485/twin-gate && cd twin-gate
cp .env.example .env            # add CREATEOS_SANDBOX_API_KEY for the real twin; optional
ollama pull qwen2.5:7b          # optional; without it the rules agent runs
python3 server.py               # open http://localhost:8790
```

Or from the shell:

```bash
python3 twingate.py propose --task "Draft the dispute for the short staple chargeback on INV-102"
python3 twingate.py propose --task "..." --inject-error    # the demo's wrong number
python3 twingate.py review tg-xxxx
python3 twingate.py approve tg-xxxx
```

## The sample brain

`brain/` starts from `brain-seed/`: a cotton gin's records, synthetic, designed around a working
gin that is not named. Sales orders, shipments, customers, a broker. The demo task drafts a
chargeback dispute from a sales order and a shipment; the `net_kg` on the draft must reconcile
with the shipment page.

## QM

`skills/twin-gate/SKILL.md` is a QM skill. Register this repository as a skill pack in QM's admin
(Skill packs, pinned to a commit), import it, and any QM agent asked to change the brain proposes
through a twin and hands the member the review link. Pair it with QM's Strict posture so the
approve step is the human step.

## GBrain

The brain is a GBrain memory folder: plain markdown, typed pages, `[[links]]`, on a machine the
team owns. Twin Gate adds one thing GBrain does not have: a way for agents to change it that a
person can check before it counts.

## Honest limits

- The rules agent only knows the demo task. Ollama handles arbitrary tasks, with the usual
  quality of a 7B model.
- The sandbox fork carries the brain files; attached data disks are not forked yet.
- Approval is one click by whoever holds the page. Identity and roles are the deployment's job.
