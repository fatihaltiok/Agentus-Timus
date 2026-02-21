---
name: stockholm-cafe-skill-test
description: Create a curated list of cozy and vintage cafes in Stockholm for long stays and relaxed fika.
version: 1.0.0
author: Timus
---

# Stockholm Cafe Skill Test

## Quick Start

Use this skill when the user asks for:
- best cafes in Stockholm
- cozy or vintage cafe atmosphere
- places for long stay, reading, or laptop-friendly fika

## Usage

```python
# via run_skill
# {"name":"stockholm-cafe-skill-test","params":{"query":"cozy vintage cafes stockholm","limit":8}}
```

Supported params:
- `query` (string, optional): user request, used for ranking
- `limit` (integer, optional): max number of cafes (default 8, max 15)

Output:
- ranked markdown list in script stdout
- saved markdown file in `results/`

## References

- See [REFERENCE.md](references/REFERENCE.md)
