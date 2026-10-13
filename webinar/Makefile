.PHONY: demo test check failure live live-revision

MODEL ?= qwen3:8b

demo:
	python3 -m mas_demo --inject-bad-draft --show-prompts

live:
	./ollama-demo.sh $(MODEL)

live-revision:
	./ollama-demo.sh $(MODEL) --inject-bad-draft --max-revisions 3 --out runs/live-revision

test:
	python3 -m unittest discover -s tests -v

check: test
	python3 -m compileall -q mas_demo tests

failure:
	python3 -m mas_demo --days 1 --daily-minutes 30; test $$? -eq 2
