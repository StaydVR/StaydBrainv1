from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agent_brain import Brain
from agent_brain.dream import run_dream


with tempfile.TemporaryDirectory() as directory:
    brain = Brain.init(Path(directory))
    brain.remember("Power module", "The module is ready.\n\n- fact: power-module | state | ready", page_id="power-module")
    brain.remember(
        "Habitat plan",
        "Use staged activation with [[brain/pages/power-module|Power module]] "
        "<!-- agent-brain:relationship=depends-on -->.",
        page_id="habitat-plan",
    )
    output = {
        "recall": brain.recall("staged activation"),
        "brief": brain.brief("module ready"),
        "dream": run_dream(brain),
        "rebuild": brain.rebuild(),
        "status": brain.status(),
    }
    assert output["status"]["integrity"] == "ok"
    assert output["recall"][0]["citation"]["path"].startswith("brain/")
    assert brain.verify_citation(output["recall"][0]["citation"])["valid"]
    print(json.dumps(output, indent=2, sort_keys=True))
