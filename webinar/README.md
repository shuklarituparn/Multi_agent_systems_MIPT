# Multi-agent systems: executable webinar example

This repository provides a small, explainable multi-agent workflow. Each agent uses
its own prompt and allowed tools. Python executes calls, coordinates handoffs,
checks schedules independently of the model, and limits retries.

## Real LLM: local Ollama (recommended for the webinar)

1. Install [Ollama](https://ollama.com/download) and open the Ollama app.
2. Download a model with tool support in Terminal: `ollama pull qwen3:8b`.
3. Change into this `webinar` folder and run:

```bash
./ollama-demo.sh qwen3:8b
open runs/live/report.html  
```

For a live fault/revision scenario:

```bash
./ollama-demo.sh qwen3:8b --inject-bad-draft --max-revisions 3 --out runs/live-revision
open runs/live-revision/report.html
```


## Real LLM: hosted OpenAI-compatible API

Set the provider's endpoint and model in your own shell. Never add credentials
to Git, screenshots, or notebook cells.

```bash
export LLM_BASE_URL='https://api.openai.com/v1'
export LLM_MODEL='YOUR_AVAILABLE_TOOL_CAPABLE_MODEL'
```

`LLM_API_KEY` works for other compatible providers. Only Chat Completions
function tools are implemented; an unrelated API format may not work.
`LLM_TIMEOUT_SECONDS` defaults to 90 seconds; the Ollama wrapper uses 300 seconds.
Hosted inference may incur charges.


| Path | Responsibility |
| --- | --- |
| `mas_demo/prompts.py` | Researcher, Planner, Reviewer instructions |
| `mas_demo/backends.py` | Real network backend versus scripted test fixture |
| `mas_demo/runner.py` | Tool-call protocol and per-role loop |
| `mas_demo/tools.py` | Source documents, Python tools, deterministic checks |
| `mas_demo/pipeline.py` | Handoffs, review feedback, revision budget |
| `mas_demo/__main__.py` | `--backend live`, CLI setup and summary |
| `mas_demo/report.py` | HTML and JSON event exports |
| `ollama-demo.sh` | Local model launch and environment setup |
| `notebooks/webinar.ipynb` | Classroom walk-through, optional runnable live cell |
| `tests/` | Unit tests and HTTP protocol fixture (not actual live LLM tests) |
| `docs/exercises.md` | Student experiments |
| `docs/resources.md` | Readings and external example repositories |

