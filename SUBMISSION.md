# Submission: Twin Gate

**One line.** The agent works in a live twin of the brain. Production takes only what the twin proved.

**Repo.** https://github.com/naman485/twin-gate (public, Apache 2.0, built during hackathon hours on 27 Sep 2026)

**Hosted demo.** https://production-twin-gate.tyzo.nodeops.app (auto-deploys from `main`; rules agent, real sandbox forks)

**Team.** Naman Kabra, individual entry

**What it is.** Teams are starting to let agents write into the memory they run on, the [GBrain](https://gbrain.io)
folder of records and procedures. Today that write lands on main the moment the agent makes it,
and the owner finds out afterwards. Twin Gate puts a gate in front of the write. An agent asked to
change the brain works in a twin instead, a branch of the brain plus a forked
[CreateOS Sandbox](https://createos.sh/docs/Sandbox/Overview/) that holds the brain at its known state and cannot reach the internet.
Five checks run on the branch and again inside the sandbox: front matter, links resolve, copied
figures match their source pages, no new outbound URLs, no key material. Every action lands on a
hash-chained log. The owner sees the diff, the checks and the log on one page and approves with
one click. Approve is the merge. It also syncs GBrain and destroys the sandbox. A failed check
greys out approve. A model that failed gets the failures back and retries once in the same twin.

**Plant example.** [`/plant`](https://production-twin-gate.tyzo.nodeops.app/plant) runs a textile plant's two automations,
truckload to grower payment and chargeback defence, through the same gate: each run's records go
into one twin, and approve is the merge.

**Built with.** [GBrain](https://gbrain.io) (a keyless local GBrain indexes the brain; `gbrain sync` runs on approve, so recall knows a change only after the gate), [QM](https://qm.ycombinator.com) (shipped
as a [skill pack](https://github.com/yc-software/qm/blob/main/docs/skill-registry.md) that any QM deployment imports from this repo; pairs with QM's Strict posture),
[CreateOS Sandbox](https://createos.sh/docs/Sandbox/Overview/) (fork from a paused base, egress allowlist set to loopback), [Ollama](https://ollama.com) with
[qwen2.5:7b](https://ollama.com/library/qwen2.5) on the laptop, with a rules fallback so the demo survives a dead model. Standard
library Python, no framework.

**Demo.** Reset. Ask for a chargeback dispute with a wrong weight: the twin runs, the reconcile
check fails against the shipment page, approve is disabled. Ask again: five checks pass twice,
approve, main moves once. Ask GBrain before and after: nothing, then the new page. The page shows
the forked sandbox id, its egress list and the probe that failed to reach the internet.

**Why "own your intelligence".** A team's memory is only theirs if they can see what an agent did
to it before it counts. Twin Gate is that gate, on files they own, on a machine they own, with a
sandbox that cannot phone home.

**What is not done.** The sandbox fork carries the brain files, not attached data disks. The
rules agent knows one task; Ollama handles the rest at 7B quality. Identity and roles belong to
the deployment, not to this repo.
