# Submission: Twin Gate

**One line.** The agent works in a live twin of the brain. Production takes only what the twin proved.

**Repo.** https://github.com/naman485/twin-gate (public, Apache 2.0, built during hackathon hours on 27 Sep 2026)

**Team.** Naman Kabra, individual entry

**What it is.** A QM skill plus a review page. When an agent is asked to change the team's [GBrain](https://gbrain.io)
folder, it does not write to main. It proposes in a twin: a branch of the brain, and a fork of a
paused [CreateOS Sandbox](https://createos.sh/docs/Sandbox/Overview/) holding the brain at its known state, with egress denied in the kernel.
The agent edits there. Every action goes on a hash-chained log. Five checks run on the twin and
again inside the sandbox: front matter, links, figures reconcile with their source pages, no new
outbound URLs, no key material. The owner sees diff, checks and log on one page and approves
with one click, which merges the branch and destroys the sandbox. A failed check greys out
approve.

**Built with.** [GBrain](https://gbrain.io) (the brain is a GBrain memory folder of typed markdown pages), [QM](https://qm.ycombinator.com) (shipped
as a [skill pack](https://github.com/yc-software/qm/blob/main/docs/skill-registry.md) that any QM deployment imports from this repo; pairs with QM's Strict posture),
[CreateOS Sandbox](https://createos.sh/docs/Sandbox/Overview/) (fork from a paused base, egress allowlist set to loopback), [Ollama](https://ollama.com) with
[qwen2.5:7b](https://ollama.com/library/qwen2.5) on the laptop, with a rules fallback so the demo survives a dead model. Standard
library Python, no framework.

**Demo.** Reset. Ask for a chargeback dispute with a wrong weight: the twin runs, the reconcile
check fails against the shipment page, approve is disabled. Ask again: five checks pass twice,
approve, main moves once. The page shows the forked sandbox id, its egress list and the probe
that failed to reach the internet.

**Why "own your intelligence".** A team's memory is only theirs if they can see what an agent did
to it before it counts. Twin Gate is that gate, on files they own, on a machine they own, with a
sandbox that cannot phone home.

**What is not done.** The sandbox fork carries the brain files, not attached data disks. The
rules agent knows one task; Ollama handles the rest at 7B quality. Identity and roles belong to
the deployment, not to this repo.
