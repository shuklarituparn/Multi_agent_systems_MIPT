# Teaching sources and official code

## Read these first

| Material | Use in the webinar | Suggested preparation |
| --- | --- | --- |
| [Hugging Face: What is an Agent?](https://huggingface.co/learn/agents-course/unit1/what-are-agents) | Establish model, capabilities and interaction with the environment | 10 min |
| [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | Explain fixed workflows versus dynamic agency; inspect the workflow patterns | 15 min |
| [OpenAI: orchestration and handoffs](https://developers.openai.com/api/docs/guides/agents/orchestration) | Distinguish specialist helpers from transferring conversation ownership | 10 min |
| [OpenAI: function calling](https://developers.openai.com/api/docs/guides/function-calling) | Follow the request → execution → result loop | 10 min |
| [LangGraph: workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents) | Inspect chaining, routing, parallelism and evaluator patterns | 10 min |

You can prepare the main concepts from those five readings in roughly one focused
hour, then spend a separate block rehearsing the demo. Do not attempt to teach
three frameworks in the same introductory webinar.

## Official GitHub examples students can explore

| Repository | Why share it | Where to start |
| --- | --- | --- |
| [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | SDK-based agents, tools and handoffs | Follow the [quickstart](https://developers.openai.com/api/docs/guides/agents/quickstart?lang=python), then the repository's agent-pattern examples |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | Explicit orchestration graphs | Read its introduction alongside the workflows documentation |
| [microsoft/autogen](https://github.com/microsoft/autogen) | A second agent-system implementation for later comparison | Start with its current README; avoid copying version-specific tutorials blindly |

The webinar's own example uses ordinary Python so students can inspect the loop
before learning a framework. It does not import these repositories or inherit
their current dependency versions.

## Optional deeper reading

- [Anthropic: How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system): a production example of coordinating research specialists. Use it for architecture discussion, not as proof that more agents help every task.
- [OpenAI Python SDK: agent orchestration](https://openai.github.io/openai-agents-python/multi_agent/): implementation patterns and code-controlled orchestration.
- [Ollama: OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility): setup reference for the local-model option. Check your chosen model's tool support separately.

