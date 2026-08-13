# Skill resolver

Load `manifest.json`, normalize the request to lowercase single-spaced text, and match complete trigger phrases. Select the skill with the longest matching trigger; if equal-length matches select the earlier manifest entry. Load only that `SKILL.md` initially.

Use `brain-first` when the request says to consult existing memory but no more specific trigger matches. Combine skills only when separate requested actions require them. Apply gates before dependent work: `ingest-gate` before external ingestion, `data-loss-gate` before destructive steps, and `cited-answer` when the requested output must carry evidence.

No match means no automatic skill selection. Never infer permission to capture, ingest, forget, migrate, or contact an external system.
