"""Protocol tests use a local fixture, never a real LLM."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from mas_demo.backends import CompatibleBackend, ScriptedBackend
from mas_demo.pipeline import Task, run_demo
from mas_demo.runner import AgentError


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        received = self.requests

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                received.append({'path': self.path, 'body': request})
                instructions = request['messages'][0]['content']
                role = next(name for name in ['Researcher', 'Planner', 'Reviewer']
                            if 'You are the ' + name in instructions)
                message = ScriptedBackend().complete(role, request['messages'], request.get('tools', []))
                body = json.dumps({'choices': [{'message': message}],
                                   'usage': {'prompt_tokens': 5, 'completion_tokens': 3}}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(body)

        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_full_workflow_over_real_http_with_simulated_responses(self):
        backend = CompatibleBackend(f'http://127.0.0.1:{self.server.server_port}/v1', 'fixture-model')
        result = run_demo(Task(), backend, inject_bad_draft=True)
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(backend.requests, 10)
        self.assertEqual(backend.usage['prompt_tokens'], 50)
        self.assertEqual({r['path'] for r in self.requests}, {'/v1/chat/completions'})
        self.assertTrue(all('tool_choice' not in r['body'] for r in self.requests))
        self.assertTrue(all('tools' in r['body'] for r in self.requests))
        tool_messages = [m for r in self.requests for m in r['body']['messages'] if m['role'] == 'tool']
        self.assertTrue(tool_messages)
        self.assertTrue(all(m.get('tool_call_id') for m in tool_messages))

    def test_connection_error_becomes_readable_agent_error(self):
        backend = CompatibleBackend('http://127.0.0.1:1/v1', 'fixture-model', timeout=1)
        with self.assertRaisesRegex(AgentError, 'Provider request failed'):
            backend.complete('Researcher', [], [])


if __name__ == '__main__':
    unittest.main()
