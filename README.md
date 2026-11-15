# StaydBrain

Security-first, local-first memory engine for Stayd operations agents. Canonical knowledge is readable Markdown under `brain/`; `.agent-brain/index.sqlite3` is disposable and rebuildable. No network, model, credentials, deployment, or live sources are required. All shipped examples are synthetic.

```sh
python3 -m pip install -e .
staydbrain --root /tmp/stayd-demo init
staydbrain --root /tmp/stayd-demo nightly --fake
staydbrain --root /tmp/stayd-demo recall "mock filter"
make verify
```

See [public interfaces](docs/INTERFACES.md), [security](SECURITY.md), [architecture](docs/architecture.md), and [generic Hermes integration](docs/hermes-integration.md). `agent-brain` and `agent_brain` remain compatibility entry points. Optional vault helpers remain for compatibility; no vault configuration ships in the repository.

The nightly pipeline writes dated operational evidence, marks stale pages for review, then runs deterministic maintenance and contradiction reporting. Sensitive domains always require human review. The standalone `dream` command retains its report-only contract. Source adapters run locally in the host process and must be trusted code.
