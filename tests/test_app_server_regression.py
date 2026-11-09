"""Offline verification that the explicit live checker stops on capacity errors."""
import io
import json
from unittest.mock import patch
import unittest

import test_app_server as check


class RecordingInput(io.StringIO):
    def close(self):
        self.recorded = self.getvalue()
        super().close()


class AppServerCheckTests(unittest.TestCase):
    def test_capacity_error_interrupts_the_actual_turn_without_retries(self):
        class Process:
            stdin = RecordingInput()
            stdout = io.StringIO(''.join(json.dumps(event) + '\n' for event in [
                {"id": 1, "result": {}},
                {"id": 2, "result": {"thread": {"id": "test-thread"}}},
                {"id": 3, "result": {"turn": {"id": "test-turn"}}},
                {"method": "error", "params": {"willRetry": True,
                    "error": {"message": "429 RESOURCE_EXHAUSTED"}}},
            ]))

            def wait(self, timeout):
                return 0

        process = Process()
        with patch.object(check.subprocess, 'Popen', return_value=process) as launch:
            with self.assertRaisesRegex(RuntimeError, 'RESOURCE_EXHAUSTED'):
                check.run('unused-launcher', 'http://127.0.0.1:4000', timeout=5)
        command = launch.call_args.args[0]
        self.assertIn('model_providers.argon.request_max_retries=0', command)
        self.assertIn('model_providers.argon.stream_max_retries=0', command)
        sent = [json.loads(line) for line in process.stdin.recorded.splitlines()]
        interrupt = next(item for item in sent if item.get('method') == 'turn/interrupt')
        self.assertEqual(interrupt['params'], {'threadId': 'test-thread', 'turnId': 'test-turn'})
        self.assertEqual(sum(item.get('method') == 'turn/start' for item in sent), 1)


if __name__ == '__main__':
    unittest.main()
