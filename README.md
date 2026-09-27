# Twin Gate

The agent works in a live twin of the brain. Production takes only what the twin proved.

Built at the YC Own Your Intelligence hackathon, 27 September 2026, by Naman Kabra. The sandbox is [CreateOS Sandbox](https://createos.sh/docs/Sandbox/Overview/). Standard library Python,
no framework. Runs on a laptop with [Ollama](https://ollama.com), or with a rules fallback when no model is present.

## What it does

A team keeps its records as a [GBrain](https://gbrain.io) folder: markdown pages with front matter, under git.
Agents want to write to it. Twin Gate makes that safe without slowing the agent down:

1. **Propose.** `twingate.py propose --task "..."` creates a twin: a branch of the brain in a
   git worktree, and, when `CREATEOS_SANDBOX_API_KEY` is set, a fork of a paused [CreateOS Sandbox](https://createos.sh/docs/Sandbox/Overview/)
   VM that holds the brain at its known state, with egress denied in the host kernel.
2. **Work.** The agent ([qwen2.5:7b](https://ollama.com/library/qwen2.5) on Ollama, or the rules fallback) makes its edits in the twin only. Every
   action is appended to a hash-chained log.
3. **Prove.** Checks run on the twin, and again inside the sandbox: front matter present, links
   resolve, declared figures reconcile with their source pages, no new outbound URLs, no key
   material. A failed check blocks approval.
4. **Approve.** The owner sees diff, checks and log on one page and merges with one click.
   The merge is synced into GBrain, so the brain's memory moves only when the gate opens.
   Reject discards the branch and destroys the sandbox. Nothing reaches main another way.

When the model's first attempt fails a check, the failed checks are fed back to it and it
retries once inside the same twin; both attempts stay on the log.

## Run

```bash
git clone https://github.com/naman485/twin-gate && cd twin-gate
cp .env.example .env            # add CREATEOS_SANDBOX_API_KEY for the real twin; optional
ollama pull qwen2.5:7b          # optional, https://ollama.com; without it the rules agent runs
python3 server.py               # open http://localhost:8790
```

Or from the shell:

```bash
python3 twingate.py propose --task "Draft the dispute for the short staple chargeback on INV-102"
python3 twingate.py propose --task "..." --inject-error    # the demo's wrong number
python3 twingate.py review tg-xxxx
python3 twingate.py approve tg-xxxx
```

## Why this shape

In July 2026, about 1,200 agents running in a lab's own sandboxes turned a package server into a
message board, reached the internet through it, ran code on another company's servers and edited
their own activity logs to hide it. The grader never ran the check the agents were afraid of
([OpenAI's report](https://openai.com/index/hugging-face-incident-and-the-road-ahead/); the
[UN scientific panel's brief](https://www.un.org/independent-international-scientific-panel-ai/)
on it). Every one of those failures is a property of the environment, not the model. Twin Gate is
built as the environment that would have held:

| Failure in the incident | What Twin Gate does | Status |
| --- | --- | --- |
| Agents reached the internet through a tool inside the sandbox | Egress denied on the host, outside the VM; the twin cannot switch it off | Works; the page shows the probe that failed |
| Agents coordinated across runs through a shared store | One forked sandbox per twin, destroyed on approve or reject | Works |
| Agents edited their own activity records | Hash-chained log; the page verifies the chain on every view | Works |
| The grader never ran the check | Five checks, run twice, before approve is enabled | Works |
| Agents used a credential found in the open | Secrets stay outside the twin; the sandbox holds only the brain files | Works for this demo; per-agent identity is a build item |
| Nobody looked until it was late | Diff, checks and log on one page, one click to merge or discard | Works |

The bet underneath: as agents take over the writing, the check before production becomes the
product, and it has to live inside the customer's own boundary. This repo is the smallest working
version of that bet. Tell us where it is wrong: [three questions](.github/ISSUE_TEMPLATE/thesis-feedback.md).

## Status, honestly

| Piece | State |
| --- | --- |
| Twin as a git branch, checks, hash-chained log, approve and reject | Working |
| Twin as a forked CreateOS sandbox with egress denied, checks re-run inside | Working with a key; falls back to the branch without one |
| GBrain index moving only on approve; recall before and after | Working with the gbrain CLI installed |
| QM skill pack | Written and importable; not yet exercised inside a QM deployment |
| Model agent (qwen2.5:7b) with one retry on failed checks | Working; the rules agent is the stage default |
| Fork carrying attached data disks | Not yet; the twin carries the brain files |
| Deterministic replay of a run | Not yet; the log records actions, it does not replay them |
| Identity and roles for who may approve | Not in this repo; the deployment's job |

## Hosted

A hosted copy runs on [CreateOS](https://createos.sh) from this repository, auto-deploying on
every push to `main`. It uses the rules agent (no Ollama in a 1 GB container) and forks real
sandboxes when the deployment carries a sandbox key.

[![Open the hosted demo](https://img.shields.io/badge/Open-hosted%20demo-0E6B55?style=for-the-badge)](https://production-twin-gate.tyzo.nodeops.app)
[![Deploy your own on CreateOS](https://img.shields.io/badge/Deploy%20your%20own-CreateOS-111111?style=for-the-badge)](https://createos.sh/app/deploy)

To deploy your own: open [createos.sh/app/deploy](https://createos.sh/app/deploy), pick this repository, keep
`hasDockerfile` on, port 3000, and set `CREATEOS_SANDBOX_API_KEY` in the environment if you want
real twins. The `Dockerfile` in this repo is what the platform builds.

## The sample brain

`brain/` starts from `brain-seed/`: a textile manufacturer's records, synthetic, designed around a working
plant that is not named. Sales orders, shipments, customers, a broker. The demo task drafts a
chargeback dispute from a sales order and a shipment; the `net_kg` on the draft must reconcile
with the shipment page.

## QM

`skills/twin-gate/SKILL.md` is a [QM](https://qm.ycombinator.com) skill ([source](https://github.com/yc-software/qm)). Register this repository as a [skill pack](https://github.com/yc-software/qm/blob/main/docs/skill-registry.md) in QM's admin
(Skill packs, pinned to a commit), import it, and any QM agent asked to change the brain proposes
through a twin and hands the member the review link. Pair it with QM's Strict posture so the
approve step is the human step.

## GBrain

The brain is a [GBrain](https://gbrain.io) content root: plain markdown, typed pages, `[[links]]`, on a machine the
team owns, indexed by a keyless local GBrain (`gbrain init --pglite --no-embedding`, then
`gbrain import`). Approve runs `gbrain sync --repo brain`, which is commit-driven, so only what
the gate merged is ever indexed. The page has an "Ask GBrain" box: recall before approve knows
nothing about the change; recall after approve returns the new page first. Twin Gate adds the one
thing GBrain does not have: a way for agents to change the brain that a person checks before it
counts.

## How it maps to the hackathon

| Challenge | What Twin Gate does |
| --- | --- |
| Build with GBrain | The brain is a GBrain content root; a keyless local GBrain indexes it; `gbrain sync` runs on approve; recall on the page shows the change only after the gate |
| Extend QM | A skill pack any deployment imports ([`qm/`](qm/)), paired with Strict posture: the agent proposes, the person approves |
| Own your intelligence | Files the team owns, on a machine the team owns, a sandbox that cannot phone home, a log that cannot be edited |
| UFO | The same skill shape works for UFO's team agents; a CreateOS carrier for UFO is a separate, in-progress piece |

## Honest limits

- The rules agent only knows the demo task. Ollama handles arbitrary tasks, with the usual
  quality of a 7B model.
- The sandbox fork carries the brain files; attached data disks are not forked yet. Sandbox API: [SDK and reference](https://github.com/nodeops-app/createos-sandbox-sdk).
- Approval is one click by whoever holds the page. Identity and roles are the deployment's job.
