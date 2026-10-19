import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ['JARVIS_DB'] = ':memory:'
import jarvis
import voice
import actions_tools


class JarvisTests(unittest.TestCase):
    def setUp(self):
        jarvis.db.execute('DELETE FROM memory')
        jarvis.db.execute('DELETE FROM tasks')
        jarvis.db.commit()

    def test_memory_update_and_search(self):
        jarvis.remember('language', 'English')
        jarvis.remember('language', 'Tamil')
        self.assertIn('Tamil', jarvis.recall('language'))
        self.assertNotIn('English', jarvis.recall('language'))

    def test_task_lifecycle_and_duplicate(self):
        jarvis.add_task('Prepare demo', '2030-01-01')
        self.assertIn('Already', jarvis.add_task('Prepare demo', '2030-01-01'))
        task_id = jarvis.db.execute('SELECT id FROM tasks').fetchone()[0]
        self.assertIn('Prepare demo', jarvis.list_tasks())
        jarvis.complete_task(task_id)
        self.assertEqual('No tasks.', jarvis.list_tasks())
        self.assertIn('Prepare demo', jarvis.list_tasks(True))

    def test_invalid_date(self):
        output, error = jarvis.run_tool('add_task', {'title': 'x', 'due_date': 'bad'})
        self.assertTrue(error)
        self.assertIn('Tool error', output)

    def test_confirmation_blocks_execution(self):
        fn = Mock()
        with patch.dict(jarvis.TOOL_REGISTRY, {'danger': (fn, True)}), patch.object(jarvis, 'CONFIRM', return_value=False):
            self.assertTrue(jarvis.run_tool('danger', {})[1])
            fn.assert_not_called()

    def test_unknown_tool(self):
        self.assertTrue(jarvis.run_tool('missing', {})[1])

    def test_briefing_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(jarvis, 'client', None):
            self.assertIn('Nothing due', jarvis.briefing())
            with self.assertRaisesRegex(RuntimeError, 'GROQ_API_KEY'):
                jarvis.get_client()

    def test_tool_conversation(self):
        call = SimpleNamespace(id='call_1', function=SimpleNamespace(name='get_current_time', arguments='{}'))
        first = SimpleNamespace(tool_calls=[call], content=None)
        second = SimpleNamespace(tool_calls=[], content='The time is available.')
        client = Mock()
        client.chat.completions.create.side_effect = [SimpleNamespace(choices=[SimpleNamespace(message=m)]) for m in [first, second]]
        messages = [{'role': 'user', 'content': 'What time is it?'}]
        with patch.object(jarvis, 'get_client', return_value=client):
            self.assertEqual('The time is available.', jarvis.ask(messages))
        self.assertEqual('tool', messages[2]['role'])
        self.assertEqual(2, client.chat.completions.create.call_count)

    def test_voice_confirmation(self):
        self.assertTrue(voice.parse_yes_no('yes please'))
        self.assertFalse(voice.parse_yes_no('yes no stop'))
        self.assertIsNone(voice.parse_yes_no('maybe'))

    def test_speech_cleanup(self):
        self.assertEqual('Hello a link', voice.speakable('**Hello** https://example.com'))

    def test_speech_detector_timeout_and_end(self):
        detector = voice.UtteranceDetector(.1, start_timeout=.2)
        detector.feed(0)
        self.assertEqual('timeout', detector.feed(0))
        detector = voice.UtteranceDetector(.1, silence_end=.2)
        for _ in range(3):
            detector.feed(.5)
        detector.feed(0)
        self.assertEqual('done', detector.feed(0))

    def test_action_validation(self):
        config = {'volume': {'confirm': True, 'params': {'level': {'min': 0, 'max': 100}}, 'command': ['echo', '{level}']}}
        with patch.object(actions_tools, '_load', return_value=config):
            self.assertIn('between', actions_tools.run_action('volume', {'level': 101}))
            self.assertIn('Unexpected', actions_tools.run_action('volume', {'other': 1}))
            self.assertTrue(actions_tools.needs_confirmation({'name': 'volume'}))


if __name__ == '__main__':
    unittest.main()
