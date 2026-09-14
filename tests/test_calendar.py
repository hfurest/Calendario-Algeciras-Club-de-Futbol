import copy
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import update_calendar as c

FIXTURES = Path(__file__).parent / 'fixtures'


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((FIXTURES/'matches.json').read_text(encoding='utf-8'))
        self.text = (FIXTURES/'calendar.ics').read_bytes().decode('utf-8')
        self.events = c.read_published(self.text, self.data)
        self.rfef = c.parse_rfef_matches((FIXTURES/'rfef.html').read_text(encoding='utf-8'), '2026/27')

    def test_real_rfef_first_and_second_leg(self):
        c.validate_source(self.rfef, self.data)
        self.assertEqual(len(self.rfef), 38)
        self.assertEqual(self.rfef[6]['time'], '18:45')
        self.assertEqual(self.rfef[7]['time'], '18:15')
        self.assertIsNone(self.rfef[20]['time'])

    def test_wrong_season_rejected(self):
        with self.assertRaises(ValueError):
            c.parse_rfef_matches((FIXTURES/'rfef.html').read_text(encoding='utf-8'), '2025/26')

    def test_partial_calendar_rejected(self):
        self.rfef.pop(38)
        with self.assertRaises(ValueError):
            c.validate_source(self.rfef, self.data)

    def test_missing_clock_cannot_use_another_fixture_clock(self):
        html = (FIXTURES/'rfef.html').read_text(encoding='utf-8')
        html = html.replace('fa-clock', 'missing-clock', 1)
        source = c.parse_rfef_matches(html, '2026/27')
        with self.assertRaises(ValueError):
            c.validate_source(source, self.data)

    def test_reversed_home_away_rejected(self):
        row = self.rfef[6]
        row['home'], row['away'] = row['away'], row['home']
        with self.assertRaises(ValueError):
            c.validate_source(self.rfef, self.data)

    def test_wrong_team_not_substring(self):
        self.assertFalse(c.same_team('', 'Algeciras CF'))
        self.assertFalse(c.same_team('Algeciras CF B', 'Algeciras CF'))
        self.assertTrue(c.same_team('Gimnàstic', 'Gimnàstic de Tarragona'))

    def test_invalid_source_time(self):
        self.rfef[6]['time'] = '25:00'
        with self.assertRaises(ValueError):
            c.validate_source(self.rfef, self.data)

    def test_as_actual_results_and_pending_times(self):
        for j, expected in [(1, '19:15'), (6, '18:45'), (8, None), (20, None)]:
            row = c.parse_as_match((FIXTURES/f'as{j}.html').read_text(encoding='utf-8'), j, '2026/27')
            self.assertEqual(row['time'], expected)

    def test_as_winter_timezone(self):
        html = (FIXTURES/'as20.html').read_text(encoding='utf-8').replace('2027-01-17T00:00:00Z', '2027-01-17T17:00:00Z')
        self.assertEqual(c.parse_as_match(html, 20, '2026/27')['time'], '18:00')

    def test_as_wrong_page_and_duplicates(self):
        html = (FIXTURES/'as6.html').read_text(encoding='utf-8')
        for modified, jornada in [(html, 7), (html + html, 6), ('<html>blocked</html>', 6)]:
            with self.assertRaises(ValueError):
                c.parse_as_match(modified, jornada, '2026/27')

    def test_noop_preserves_every_byte_despite_new_clock(self):
        self.assertEqual(c.render_calendar(self.text, self.events, self.data,
            datetime(2027, 2, 1, tzinfo=timezone.utc)), self.text)

    def test_change_only_one_event_preserves_all_uids_and_increments_revision(self):
        self.data['matches'][7].update(time='18:30', source='RFEF')
        rendered = c.render_calendar(self.text, self.events, self.data, datetime(2026, 9, 14, tzinfo=timezone.utc))
        updated = c.read_published(rendered, copy.deepcopy(self.data))
        for j in range(1, 39):
            self.assertEqual(c.properties(updated[j])['UID'], c.properties(self.events[j])['UID'])
            if j != 8:
                self.assertEqual(updated[j], self.events[j])
        props = c.properties(updated[8])
        self.assertEqual(props['SEQUENCE'], '1')
        self.assertEqual(props['DTSTAMP'], '20260914T000000Z')
        self.assertIn('DTSTART;TZID=Europe/Madrid', props)
        self.assertNotIn('DTSTART;VALUE=DATE', props)
        self.assertIn('\\nJornada', props['DESCRIPTION'])
        self.assertNotIn('\\\\n', props['DESCRIPTION'])
        self.assertEqual(c.render_calendar(rendered, updated, self.data), rendered)

    def test_legacy_uid_is_preserved(self):
        text = self.text.replace('algeciras-cf-', 'algeciras-')
        events = c.read_published(text, self.data)
        self.data['matches'][7]['time'] = '18:30'
        rendered = c.render_calendar(text, events, self.data)
        self.assertNotIn('algeciras-cf-', rendered)

    def test_repaired_revision_is_stable_and_next_change_increments_it(self):
        block = self.events[6]
        repaired = block.replace('END:VEVENT', 'SEQUENCE:1\nLAST-MODIFIED:20260914T200000Z\nEND:VEVENT')
        text = self.text.replace(block, repaired)
        events = c.read_published(text, self.data)
        self.assertEqual(c.render_calendar(text, events, self.data), text)
        self.data['matches'][5].update(time='19:00', source='RFEF')
        updated = c.render_calendar(text, events, self.data)
        props = c.properties(c.read_published(updated, copy.deepcopy(self.data))[6])
        self.assertEqual(props['SEQUENCE'], '2')
        self.assertEqual(props['UID'], c.properties(block)['UID'])

    def test_missing_time_never_erases_known_kickoff(self):
        old = copy.deepcopy(self.data['matches'][5])
        self.rfef[6].update(date='2026-10-05', time=None)
        with patch.object(c, 'fetch_rfef_matches', return_value=self.rfef), redirect_stdout(io.StringIO()):
            c.update_matches_from_sources(self.data)
        self.assertEqual(self.data['matches'][5], old)

    def test_primary_preferred_and_fallback_works(self):
        self.rfef[8]['time'] = '18:30'
        with patch.object(c, 'fetch_rfef_matches', return_value=self.rfef), patch.object(c, 'fetch_as_matches') as secondary, redirect_stdout(io.StringIO()):
            c.update_matches_from_sources(self.data)
            secondary.assert_not_called()
        self.assertEqual(self.data['matches'][7]['time'], '18:30')
        fallback = copy.deepcopy(self.rfef)
        fallback[8].update(time='19:00', source='AS')
        with patch.object(c, 'fetch_rfef_matches', side_effect=URLError('offline')), patch.object(c, 'fetch_as_matches', return_value=fallback), redirect_stdout(io.StringIO()):
            c.update_matches_from_sources(self.data)
        rendered = c.render_calendar(self.text, self.events, self.data)
        self.assertIn('pendiente de validaci', c.properties(c.read_published(rendered, copy.deepcopy(self.data))[8])['DESCRIPTION'])

    def test_failed_fetch_leaves_both_files_and_mtimes_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path, output_path = Path(directory)/'matches.json', Path(directory)/'calendar.ics'
            data_path.write_text(json.dumps(self.data), encoding='utf-8')
            output_path.write_bytes(self.text.encode('utf-8'))
            before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in (data_path, output_path)]
            with patch.object(c, 'DATA_FILE', data_path), patch.object(c, 'OUTPUT', output_path), patch.object(c, 'fetch_rfef_matches', return_value={}), patch.object(c, 'fetch_as_matches', side_effect=URLError('403')), redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    c.synchronize()
            self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in (data_path, output_path)])

    def test_stale_json_repaired_then_second_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            data_path, output_path = Path(directory)/'matches.json', Path(directory)/'calendar.ics'
            self.data['matches'][5]['time'] = None
            data_path.write_text(json.dumps(self.data), encoding='utf-8')
            output_path.write_bytes(self.text.encode('utf-8'))
            with patch.object(c, 'DATA_FILE', data_path), patch.object(c, 'OUTPUT', output_path), patch.object(c, 'fetch_rfef_matches', return_value=self.rfef), redirect_stdout(io.StringIO()):
                c.synchronize()
                before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in (data_path, output_path)]
                c.synchronize()
                self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in (data_path, output_path)])
                self.assertEqual(output_path.read_bytes(), self.text.encode('utf-8'))

    def test_utf8_folding(self):
        line = 'DESCRIPTION:' + 'áé😀' * 80
        folded = c.fold_line(line)
        self.assertTrue(all(len(part.encode('utf-8')) <= 75 for part in folded.split('\r\n')))
        self.assertEqual(folded.replace('\r\n ', ''), line)


if __name__ == '__main__':
    unittest.main()
