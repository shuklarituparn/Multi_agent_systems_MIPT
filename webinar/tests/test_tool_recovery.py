import json
import unittest

from mas_demo.backends import ScriptedBackend, final_message, tool_message
from mas_demo.pipeline import Task, run_demo
from mas_demo.runner import Agent, AgentError, run_agent
from mas_demo.tools import BUDGET_SCHEMA, get_budget


class ToolRecoveryTests(unittest.TestCase):
    def test_reviewer_recovers_from_extra_context_arguments(self):
        class ExtraContextBackend(ScriptedBackend):
            def complete(self, agent, messages, tools):
                if agent != 'Reviewer':
                    return super().complete(agent, messages, tools)
                payload = json.loads(messages[1]['content'])
                results = [json.loads(m['content']) for m in messages if m['role'] == 'tool']
                if not results:
                    # Reproduce Qwen's call, including an attempted budget override.
                    return tool_message('validate_plan', {**payload, 'daily_minutes': 999})
                if 'error' in results[-1]:
                    return tool_message('validate_plan', {'plan': payload['plan']})
                return final_message({'passed': results[-1]['passed'],
                                      'issues': results[-1]['issues']})

        result = run_demo(Task(), ExtraContextBackend(), inject_bad_draft=True)
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['revisions'], 1)
        errors = [e for e in result['trace'] if e['kind'] == 'tool_error']
        self.assertEqual(len(errors), 2)
        self.assertIn('daily_minutes', errors[0]['data']['output']['error'])
        reviews = [e['data'] for e in result['trace'] if e['kind'] == 'review']
        self.assertFalse(reviews[0]['passed'])
        self.assertTrue(reviews[-1]['passed'])

    def test_invalid_calls_are_not_executed_before_retry(self):
        for bad in [{'days': 3, 'daily_minutes': 45, 'extra': 1},
                    {'days': 3}, {'days': 0, 'daily_minutes': 45}]:
            with self.subTest(arguments=bad):
                executed = []

                def budget(days, daily_minutes):
                    value = get_budget(days, daily_minutes)
                    executed.append(value)
                    return value

                class RetryBackend:
                    mode = 'test-fixture'

                    def complete(self, agent, messages, tools):
                        results = [json.loads(m['content']) for m in messages if m['role'] == 'tool']
                        if not results:
                            return tool_message('get_budget', bad)
                        if 'error' in results[-1]:
                            return tool_message('get_budget', {'days': 3, 'daily_minutes': 45})
                        return final_message(results[-1])

                trace = []
                result = run_agent(Agent('Planner', 'test', {
                    'get_budget': (budget, BUDGET_SCHEMA)}), {}, RetryBackend(), trace)
                self.assertEqual(result['total_minutes'], 135)
                self.assertEqual(len(executed), 1)
                self.assertEqual(sum(e['kind'] == 'tool_error' for e in trace), 1)

    def test_repeated_invalid_calls_stop_at_turn_limit(self):
        class InvalidBackend:
            mode = 'test-fixture'

            def complete(self, agent, messages, tools):
                return tool_message('get_budget', {'days': 3, 'daily_minutes': 45, 'extra': 1})

        trace = []
        with self.assertRaisesRegex(AgentError, 'turn limit'):
            run_agent(Agent('Planner', 'test', {'get_budget': (get_budget, BUDGET_SCHEMA)}),
                      {}, InvalidBackend(), trace, max_turns=3)
        self.assertEqual(sum(e['kind'] == 'tool_error' for e in trace), 3)

    def test_rejected_tool_does_not_satisfy_required_tool(self):
        class SkippingBackend:
            mode = 'test-fixture'

            def complete(self, agent, messages, tools):
                if not any(m['role'] == 'tool' for m in messages):
                    return tool_message('get_budget', {'days': 0, 'daily_minutes': 45})
                return final_message({'total_minutes': 135})

        trace = []
        with self.assertRaisesRegex(AgentError, 'turn limit'):
            run_agent(Agent('Planner', 'test', {'get_budget': (get_budget, BUDGET_SCHEMA)}),
                      {}, SkippingBackend(), trace, max_turns=3,
                      required_tools={'get_budget'})
        self.assertEqual(sum(e['kind'] == 'required_tool_missing' for e in trace), 2)
        self.assertFalse(any(e['kind'] == 'tool_result' for e in trace))
