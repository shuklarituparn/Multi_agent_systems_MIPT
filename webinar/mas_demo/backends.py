"""A labelled scripted fixture and a real OpenAI-compatible HTTP backend."""
import json
import os
import urllib.error
import urllib.request

from .runner import AgentError


def tool_message(name: str, arguments: dict) -> dict:
    return {'role': 'assistant', 'content': None, 'tool_calls': [{
        'id': 'call_' + name, 'type': 'function',
        'function': {'name': name, 'arguments': json.dumps(arguments)}}]}


def final_message(value: dict) -> dict:
    return {'role': 'assistant', 'content': json.dumps(value, ensure_ascii=False)}


class ScriptedBackend:
    """Simulation ONLY. It ignores prompts; it is not an LLM or an AI evaluation."""
    mode = 'SIMULATED: deterministic rehearsal, no LLM'

    def complete(self, agent, messages, tools):
        payload = json.loads(messages[1]['content'])
        tool_results = [json.loads(m['content']) for m in messages if m['role'] == 'tool']
        if agent == 'Researcher':
            if not tool_results:
                return tool_message('search_documents', {'query': 'all'})
            documents = tool_results[-1]
            return final_message({'source_ids': [d['id'] for d in documents],
                                  'summary': 'Four local lesson topics retrieved.'})
        if agent == 'Planner':
            if not tool_results:
                return tool_message('get_budget', {'days': payload['days'],
                                                   'daily_minutes': payload['daily_minutes']})
            sessions = []
            day, remaining = 1, payload['daily_minutes']
            for doc in payload['documents']:
                needed = doc['minutes']
                while needed:
                    if remaining == 0:
                        day += 1
                        remaining = payload['daily_minutes']
                    minutes = min(needed, remaining)
                    sessions.append({'day': day, 'topic': doc['topic'],
                                     'minutes': minutes, 'source_id': doc['id']})
                    needed -= minutes
                    remaining -= minutes
            return final_message({'sessions': sessions, 'summary': 'All required topics scheduled.'})
        if agent == 'Reviewer':
            if not tool_results:
                return tool_message('validate_plan', {'plan': payload['plan']})
            return final_message({'passed': tool_results[-1]['passed'],
                                  'issues': tool_results[-1]['issues']})
        raise AgentError(f'No scripted role named {agent}')


class CompatibleBackend:
    """Real network calls. Model must support Chat Completions function tools."""
    mode = 'LIVE LLM: OpenAI-compatible HTTP'

    def __init__(self, base_url: str, model: str, api_key: str = '', timeout: float = 90):
        if not base_url.startswith(('http://', 'https://')) or not model:
            raise ValueError('An HTTP(S) base URL and a model name are required')
        self.url = base_url.rstrip('/') + '/chat/completions'
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.requests = 0
        self.usage = {'prompt_tokens': 0, 'completion_tokens': 0}

    @classmethod
    def from_env(cls):
        model = os.environ.get('LLM_MODEL', '')
        if not model:
            raise ValueError('Set LLM_MODEL to a tool-capable model available to you')
        base = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
        key = os.environ.get('LLM_API_KEY') or os.environ.get('OPENAI_API_KEY', '')
        if base.rstrip('/') == 'https://api.openai.com/v1' and not key:
            raise ValueError('Set OPENAI_API_KEY or LLM_API_KEY for the OpenAI endpoint')
        return cls(base, model, key, float(os.environ.get('LLM_TIMEOUT_SECONDS', '90')))

    def complete(self, agent, messages, tools):
        payload = {'model': self.model, 'messages': messages}
        if tools:
            payload['tools'] = tools  # Default tool selection is automatic; Ollama omits tool_choice support
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = 'Bearer ' + self.api_key
        request = urllib.request.Request(self.url, data=json.dumps(payload).encode(), headers=headers)
        self.requests += 1
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            # Do not dump provider bodies: they may echo sensitive request data.
            raise AgentError(f'Provider returned HTTP {exc.code}. Check endpoint, model, credentials and quota.') from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise AgentError('Provider request failed. Check connection, timeout and JSON compatibility.') from exc
        try:
            message = result['choices'][0]['message']
            if not isinstance(message, dict):
                raise TypeError('message is not an object')
        except (KeyError, IndexError, TypeError) as exc:
            raise AgentError('Provider response does not contain choices[0].message') from exc
        usage = result.get('usage') or {}
        for key in self.usage:
            value = usage.get(key)
            if type(value) is int:
                self.usage[key] += value
        return message
