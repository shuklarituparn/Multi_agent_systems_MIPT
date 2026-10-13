import copy
import json
import unittest
import tempfile
from pathlib import Path

from mas_demo.backends import ScriptedBackend
from mas_demo.pipeline import Task, run_demo
from mas_demo.runner import Agent, AgentError, run_agent
from mas_demo.tools import DOCUMENTS, validate_plan
from mas_demo.report import save_report


class DemoTests(unittest.TestCase):
    def test_complete_plan_obeys_budget_and_covers_sources(self):
        result = run_demo(Task(), ScriptedBackend())
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['review']['issues'], [])
        self.assertEqual(sum(s['minutes'] for s in result['plan']['sessions']), 75)
        self.assertTrue(any(e['kind'] == 'tool_result' for e in result['trace']))

    def test_researcher_recovers_after_citing_unretrieved_documents(self):
        from mas_demo.backends import tool_message, final_message

        class NarrowSearchBackend(ScriptedBackend):
            def complete(self, agent, messages, tools):
                if agent != 'Researcher':
                    return super().complete(agent, messages, tools)
                payload = json.loads(messages[1]['content'])
                if not any(m['role'] == 'tool' for m in messages):
                    query = 'all' if 'correction' in payload else 'LLM agents'
                    return tool_message('search_documents', {'query': query})
                return final_message({'source_ids': ['D1', 'D2', 'D3', 'D4'],
                                      'summary': 'Four lessons.'})

        result = run_demo(Task(), NarrowSearchBackend())
        self.assertEqual(result['status'], 'accepted')
        retries = [e for e in result['trace'] if e['kind'] == 'research_retry']
        self.assertEqual(len(retries), 1)
        self.assertEqual(retries[0]['data']['retrieved_ids'], ['D1'])
        self.assertEqual(len(result['documents']), 4)
        queries = [e['data']['arguments']['query'] for e in result['trace']
                   if e['agent'] == 'Researcher' and e['kind'] == 'tool_call']
        self.assertEqual(queries, ['LLM agents', 'all'])

    def test_researcher_still_rejects_fake_coverage_after_retry(self):
        from mas_demo.backends import tool_message, final_message

        class AlwaysNarrowBackend(ScriptedBackend):
            def complete(self, agent, messages, tools):
                if agent != 'Researcher':
                    return super().complete(agent, messages, tools)
                if not any(m['role'] == 'tool' for m in messages):
                    return tool_message('search_documents', {'query': 'LLM agents'})
                return final_message({'source_ids': ['D1', 'D2', 'D3', 'D4'],
                                      'summary': 'Claimed, not actually retrieved.'})

        with self.assertRaisesRegex(AgentError, 'incomplete evidence after retry'):
            run_demo(Task(), AlwaysNarrowBackend())

    def test_bad_draft_is_rejected_then_repaired(self):
        result = run_demo(Task(), ScriptedBackend(), inject_bad_draft=True)
        self.assertEqual(result['status'], 'accepted')
        reviews = [e for e in result['trace'] if e['kind'] == 'review']
        self.assertFalse(reviews[0]['data']['passed'])
        self.assertTrue(reviews[-1]['data']['passed'])
        self.assertEqual(result['revisions'], 1)

    def test_trace_preserves_first_input_before_feedback_mutation(self):
        result = run_demo(Task(), ScriptedBackend(), inject_bad_draft=True)
        inputs = [e['data']['input'] for e in result['trace']
                  if e['agent'] == 'Planner' and e['kind'] == 'start']
        self.assertEqual(inputs[0]['feedback'], [])
        self.assertNotIn('previous_plan', inputs[0])
        self.assertTrue(inputs[1]['feedback'])

    def test_observer_cannot_rewrite_recorded_events(self):
        def observer(event):
            if event['kind'] == 'start':
                event['data']['instructions'] = 'modified'
        result = run_demo(Task(), ScriptedBackend(), observer=observer)
        starts = [e for e in result['trace'] if e['kind'] == 'start']
        self.assertTrue(all(e['data']['instructions'] != 'modified' for e in starts))

    def test_impossible_budget_does_not_create_plan(self):
        result = run_demo(Task(days=1, daily_minutes=30), ScriptedBackend())
        self.assertEqual(result['status'], 'insufficient_budget')
        self.assertIsNone(result['plan'])

    def test_exhausted_revision_budget_reports_failure(self):
        result = run_demo(Task(), ScriptedBackend(), inject_bad_draft=True, max_revisions=0)
        self.assertEqual(result['status'], 'needs_revision')
        self.assertFalse(result['review']['passed'])

    def test_fabricated_source_is_rejected(self):
        result = run_demo(Task(), ScriptedBackend())
        plan = copy.deepcopy(result['plan'])
        plan['sessions'][0]['source_id'] = 'invented-source'
        self.assertFalse(validate_plan(plan, DOCUMENTS, 3, 45)['passed'])

    def test_missing_topic_is_rejected(self):
        plan = copy.deepcopy(run_demo(Task(), ScriptedBackend())['plan'])
        plan['sessions'].pop()
        self.assertFalse(validate_plan(plan, DOCUMENTS, 3, 45)['passed'])

    def test_bool_is_not_a_valid_minute_count(self):
        plan = copy.deepcopy(run_demo(Task(), ScriptedBackend())['plan'])
        plan['sessions'][0]['minutes'] = True
        self.assertFalse(validate_plan(plan, DOCUMENTS, 3, 45)['passed'])

    def test_non_list_sessions_fail_cleanly(self):
        for value in [None, 'wrong', 1, {}]:
            self.assertFalse(validate_plan({'sessions': value}, DOCUMENTS, 3, 45)['passed'])

    def test_invalid_task_is_rejected(self):
        with self.assertRaises(ValueError):
            Task(days=0)


class FixedBackend:
    mode = 'test-fixture'

    def __init__(self, message):
        self.message = message

    def complete(self, agent, messages, tools):
        return self.message


class RunnerTests(unittest.TestCase):
    def test_unknown_tool_cannot_be_executed(self):
        backend = FixedBackend({'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'x', 'type': 'function', 'function': {'name': 'delete_files', 'arguments': '{}'}}]})
        with self.assertRaisesRegex(AgentError, 'not allowed'):
            run_agent(Agent('test', 'test', {}), {}, backend, [])

    def test_malformed_tool_arguments_fail_clearly(self):
        backend = FixedBackend({'role': 'assistant', 'tool_calls': [
            {'id': 'x', 'type': 'function', 'function': {'name': 'ok', 'arguments': '{bad'}}]})
        with self.assertRaisesRegex(AgentError, 'arguments'):
            run_agent(Agent('test', 'test', {'ok': (lambda: {}, {})}), {}, backend, [])

    def test_non_json_final_output_is_rejected(self):
        with self.assertRaisesRegex(AgentError, 'JSON'):
            run_agent(Agent('test', 'test', {}), {}, FixedBackend({'content': 'hello'}), [])

    def test_fenced_or_thinking_json_is_unwrapped_and_flagged(self):
        for content in ['```json\n{"ok": 1}\n```',
                        'Here it is: {"ok": 1} hope that helps',
                        '<think>maybe {"ok": 0}?</think>\n{"ok": 1}']:
            trace = []
            output = run_agent(Agent('test', 'test', {}), {}, FixedBackend({'content': content}), trace)
            self.assertEqual(output, {'ok': 1})
            self.assertIn('json_extracted', [e['kind'] for e in trace])

    def test_plain_json_is_not_flagged(self):
        trace = []
        run_agent(Agent('test', 'test', {}), {}, FixedBackend({'content': '{"ok": 1}'}), trace)
        self.assertNotIn('json_extracted', [e['kind'] for e in trace])

    def test_json_array_final_output_is_still_rejected(self):
        with self.assertRaisesRegex(AgentError, 'JSON'):
            run_agent(Agent('test', 'test', {}), {}, FixedBackend({'content': '```json\n[1, 2]\n```'}), [])

    def test_object_tool_arguments_are_accepted(self):
        calls = iter([{'role': 'assistant', 'content': '', 'tool_calls': [
            {'id': 'x', 'type': 'function', 'function': {'name': 'ok', 'arguments': {'n': 2}}}]},
            {'role': 'assistant', 'content': '{"done": true}'}])

        class Seq:
            mode = 'test-fixture'

            def complete(self, agent, messages, tools):
                return next(calls)
        trace = []
        run_agent(Agent('test', 'test', {'ok': (lambda n: {'n': n}, {})}), {}, Seq(), trace)
        self.assertEqual([e['data'] for e in trace if e['kind'] == 'tool_result'], [{'name': 'ok', 'output': {'n': 2}}])

    def test_required_tool_prompts_model_to_retry(self):
        class RetryBackend:
            mode = 'test-fixture'

            def complete(self, agent, messages, tools):
                if any(m['role'] == 'tool' for m in messages):
                    return {'content': '{"passed": true}'}
                if any(m['role'] == 'user' and 'MUST call' in m['content'] for m in messages):
                    return {'content': None, 'tool_calls': [{
                        'id': 'validate1', 'type': 'function',
                        'function': {'name': 'validate_plan', 'arguments': '{}'}}]}
                return {'content': '{"passed": true}'}

        trace = []
        output = run_agent(Agent('Reviewer', 'test', {'validate_plan': (lambda: {'passed': True}, {})}),
                           {}, RetryBackend(), trace, required_tools={'validate_plan'})
        self.assertEqual(output, {'passed': True})
        self.assertEqual([e['kind'] for e in trace].count('required_tool_missing'), 1)
        self.assertIn('tool_result', [e['kind'] for e in trace])

    def test_required_tool_cannot_be_skipped(self):
        trace = []
        with self.assertRaisesRegex(AgentError, 'turn limit'):
            run_agent(Agent('Reviewer', 'test', {'validate_plan': (lambda: {}, {})}), {},
                      FixedBackend({'content': '{"passed": true}'}), trace,
                      max_turns=3, required_tools={'validate_plan'})
        self.assertEqual(len([e for e in trace if e['kind'] == 'required_tool_missing']), 3)

    def test_model_loop_stops_at_limit(self):
        backend = FixedBackend({'role': 'assistant', 'tool_calls': [
            {'id': 'x', 'type': 'function', 'function': {'name': 'ok', 'arguments': '{}'}}]})
        with self.assertRaisesRegex(AgentError, 'turn limit'):
            run_agent(Agent('test', 'test', {'ok': (lambda: {}, {})}), {}, backend, [], max_turns=2)


class ReportTests(unittest.TestCase):
    def test_invalid_plan_can_still_be_exported_for_inspection(self):
        result = run_demo(Task(), ScriptedBackend())
        result.update(status='needs_revision', plan={'sessions': None})
        with tempfile.TemporaryDirectory() as directory:
            save_report(result, Path(directory))
            self.assertIn('needs_revision', (Path(directory) / 'report.html').read_text())
            self.assertEqual(json.loads((Path(directory) / 'trace.json').read_text())['plan']['sessions'], None)


if __name__ == '__main__':
    unittest.main()
