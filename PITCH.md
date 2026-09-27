# Twin Gate, stage script, 90 seconds

Before: `python3 server.py`, page open, brain reset, sandbox status line reads "CreateOS, forked per twin".

**Open, 10 s.** In July, [1,200 agents in a lab's own sandboxes](https://openai.com/index/hugging-face-incident-and-the-road-ahead/) turned a package server into a
message board, got out to the internet, ran code on another company's servers and edited their
own logs. The grader never ran the check they were afraid of. Every team giving agents write
access to its records has the same problem, smaller.

**Run with a wrong number, 25 s.** This is a manufacturer's brain: sales orders, shipments, a chargeback
from a mill. I ask the agent to draft the dispute. It does not touch the brain. It works in a
twin: a branch of the brain, and a forked [CreateOS sandbox](https://createos.sh/docs/Sandbox/Overview/) with egress denied, here is the probe
that failed to reach the internet. The agent copied the shipment weight wrong. The reconcile check
catches it against the shipment page. Approve is greyed out. The log shows every step.

**Run again, 20 s.** Same task. This time the figure reconciles, five checks pass locally and
again inside the sandbox. Diff on the right. One click: approve. Main moves once, the twin is
destroyed, the log is closed with a hash chain.

**Why it fits, 20 s.** [GBrain](https://gbrain.io) keeps the team's memory as files the team owns. [QM](https://qm.ycombinator.com) lets agents work
in it. Twin Gate is the QM skill that makes the agent go through a twin, and the page where the
owner says yes. Nothing leaves the laptop but the sandbox, and nothing leaves the sandbox at all.

**Close, 10 s.** The intelligence you own is only yours if you can see what the agent did to it
before it counts. That is the gate.

## If a judge asks

- Is the sandbox real? Yes: forked from a paused base sandbox on [CreateOS](https://createos.sh), egress allowlist set
  to loopback so the kernel drops everything else; the page shows the fork id and the probe.
- Without a key? The twin is a git branch and the page says so. Same checks, same log.
- Arbitrary tasks? [Ollama](https://ollama.com) with [qwen2.5:7b](https://ollama.com/library/qwen2.5) on the laptop. The rules agent exists so the demo
  survives a dead model.
- Post hackathon? The [skill pack](https://github.com/yc-software/qm/blob/main/docs/skill-registry.md) imports into any QM deployment; the CLI runs against any GBrain
  folder under git.
