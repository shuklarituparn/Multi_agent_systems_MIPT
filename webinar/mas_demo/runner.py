"""The loop to explain on screen: model -> tool call -> result -> model."""
import copy
import json
import re
from dataclasses import dataclass
from typing import Callable


class AgentError(RuntimeError):
    pass


_THINK = re.compile(r'<think>.*?</think>', re.S)


def parse_json_object(text) -> tuple[dict, bool]:
    """Return (object, was_extracted). Local models (e.g. via Ollama) often wrap
    the JSON in ```json fences, add a sentence, or emit a <think> block first.
    We take the first complete JSON object; anything else is still an error."""
    if not isinstance(text, str):
        raise ValueError('expected text content')
    cleaned = _THINK.sub('', text).strip()
    try:
        value, extracted = json.loads(cleaned), cleaned != text.strip()
    except ValueError:
        start = cleaned.find('{')
        if start < 0:
            raise
        value, _ = json.JSONDecoder().raw_decode(cleaned, start)
        extracted = True
    if not isinstance(value, dict):
        raise ValueError('expected JSON object')
    return value, extracted


@dataclass
class Agent:
    name: str
    instructions: str
    tools: dict[str, tuple[Callable, dict]]


def emit(trace: list, agent: str, kind: str, data, observer=None):
    event = {'seq': len(trace) + 1, 'agent': agent, 'kind': kind, 'data': copy.deepcopy(data)}
    trace.append(event)
    if observer:
        observer(copy.deepcopy(event))


def run_agent(agent: Agent, payload: dict, backend, trace: list,
              observer=None, max_turns: int = 6, required_tools=None) -> dict:
    messages = [
        {'role': 'system', 'content': agent.instructions},
        {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
    ]
    schemas = [definition for _, definition in agent.tools.values()]
    required_tools = set(required_tools or ())
    if not required_tools.issubset(agent.tools):
        raise ValueError('Required tools must belong to the agent')
    called_tools = set()
    emit(trace, agent.name, 'start', {'instructions': agent.instructions,
         'input': payload, 'allowed_tools': list(agent.tools)}, observer)
    for turn in range(1, max_turns + 1):
        emit(trace, agent.name, 'model_call', {'turn': turn, 'mode': backend.mode}, observer)
        reply = backend.complete(agent.name, messages, schemas)
        if not isinstance(reply, dict):
            raise AgentError(f'{agent.name}: expected an assistant message object')
        # Keep only message fields understood by the compatible wire protocol.
        message = {'role': 'assistant', 'content': reply.get('content')}
        calls = reply.get('tool_calls') or []
        if calls:
            if not isinstance(calls, list):
                raise AgentError(f'{agent.name}: invalid tool_calls')
            message['tool_calls'] = calls
            messages.append(message)
            for call in calls:
                try:
                    name = call['function']['name']
                    call_id = call['id']
                except (KeyError, TypeError) as exc:
                    raise AgentError(f'{agent.name}: malformed tool call') from exc
                if not isinstance(name, str) or name not in agent.tools:
                    raise AgentError(f'{agent.name}: tool {name!r} is not allowed')
                try:
                    arguments = call['function']['arguments']
                    if isinstance(arguments, str):  # OpenAI sends a string; some servers send an object
                        arguments = json.loads(arguments)
                    if not isinstance(arguments, dict):
                        raise ValueError('expected argument object')
                except (KeyError, TypeError, ValueError) as exc:
                    raise AgentError(f'{agent.name}: invalid tool arguments') from exc
                function, definition = agent.tools[name]
                emit(trace, agent.name, 'tool_call', {'name': name, 'arguments': arguments}, observer)
                try:
                    parameters = definition.get('function', {}).get('parameters', {})
                    properties = parameters.get('properties', {})
                    unexpected = set(arguments) - set(properties)
                    missing = set(parameters.get('required', [])) - set(arguments)
                    if parameters.get('additionalProperties') is False and unexpected:
                        raise ValueError('Unexpected arguments: ' + ', '.join(sorted(unexpected)))
                    if missing:
                        raise ValueError('Missing arguments: ' + ', '.join(sorted(missing)))
                    output = function(**arguments)
                except (TypeError, ValueError) as exc:
                    # Return a tool response so the model can repair its call.
                    # Rejected calls never count as successful required-tool use.
                    output = {'error': str(exc),
                              'retry': 'Correct the arguments and call the tool again.',
                              'parameters': definition.get('function', {}).get('parameters', {})}
                    emit(trace, agent.name, 'tool_error', {'name': name, 'output': output}, observer)
                    messages.append({'role': 'tool', 'tool_call_id': call_id,
                                     'content': json.dumps(output, ensure_ascii=False)})
                    continue
                emit(trace, agent.name, 'tool_result', {'name': name, 'output': output}, observer)
                called_tools.add(name)
                messages.append({'role': 'tool', 'tool_call_id': call_id,
                                 'content': json.dumps(output, ensure_ascii=False)})
            continue
        missing = required_tools - called_tools
        if missing:
            # A local model can output the final JSON without executing required tools.
            # Give it a chance to correct the omission rather than treating the claim
            # that validation happened as proof that it actually happened.
            emit(trace, agent.name, 'required_tool_missing',
                 {'tools': sorted(missing)}, observer)
            messages.append({'role': 'assistant', 'content': reply.get('content') or ''})
            messages.append({'role': 'user',
                             'content': 'Before giving a final JSON answer, you MUST call these tools: ' +
                                        ', '.join(sorted(missing)) + '. Call them now.'})
            continue
        try:
            output, extracted = parse_json_object(reply.get('content') or '')
        except (TypeError, ValueError) as exc:
            raise AgentError(f'{agent.name}: final output must be a JSON object') from exc
        if extracted:
            # Stay honest in the trace: show the raw reply that was unwrapped.
            emit(trace, agent.name, 'json_extracted', {
                'explanation': 'Model wrapped its JSON in extra text; the first JSON object was used.',
                'raw_content': reply.get('content')}, observer)
        emit(trace, agent.name, 'final', output, observer)
        return output
    raise AgentError(f'{agent.name}: exceeded model turn limit ({max_turns})')
