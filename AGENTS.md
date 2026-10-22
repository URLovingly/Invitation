# Instructions for AI assistants

This repository has a mandatory context file: [.github/skills/urlovingly-workspace/SKILL.md](.github/skills/urlovingly-workspace/SKILL.md).

1. **Before any change, read that file completely.**
2. After you change structure, behaviour, routes, tables, env vars, commands, plans, conventions or decisions, **update that file in the same change** and append a line to its change log.
3. Run `python -m pytest -q` (and `npm test` in `edge/` when it is touched). `tests/test_skill_file.py` fails if the skill file falls out of date.
4. Requirements changes also go into `docs/REQUIREMENTS.md`.
