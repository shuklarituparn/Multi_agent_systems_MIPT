# Multi-Agent Systems | MIPT webinar
Материалы курса по мультиагентным системам для студентов


Runnable Python study-planning example with three roles: **Researcher → Planner → Reviewer**.
The application supports an **actual LLM** via Ollama (no API key required) or another
OpenAI-compatible Chat Completions provider, plus a clearly labelled offline fixture.

**Start here:** [Webinar setup, live commands, and file guide](webinar/README.md)

```bash
cd webinar
python3 -m unittest discover -s tests -v
./ollama-demo.sh qwen3:8b  # requires local Ollama and model
```

Students: see [experiments](webinar/docs/exercises.md) and [reading sources](webinar/docs/resources.md).
Python 3.10+; no Python dependencies for the command-line examples.

The scripted mode is deterministic and does **not** make LLM calls. Do not treat simulated traces as model performance evidence.
