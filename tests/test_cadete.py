import copy
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import update_cadete_calendar as c


class CadeteTests(unittest.TestCase):
    def setUp(self):
        self.html = (Path(__file__).parent/'fixtures/rfaf_cadete.html').read_text(encoding='utf-8')
        self.matches = c.parse_source(self.html)
        self.data, _ = c.reconcile(None, self.matches, '20260914T210000Z')

    def test_official_full_fixture_and_first_time(self):
        self.assertEqual(len(self.matches), 30)
        self.assertEqual(self.matches[0]['time'], '09:30')
        self.assertIsNone(self.matches[1]['time'])
        self.assertEqual(self.matches[-1]['date'], '2027-05-22')

    def test_wrong_category_and_season(self):
        for old, new in [('2026-2027','2025-2026'),('CADETE','INFANTIL')]:
            with self.assertRaises(ValueError):
                c.parse_source(self.html.replace(old,new))

    def test_clubs_with_algeciras_in_name_are_not_our_team(self):
        self.assertTrue(c.is_team('ALGECIRAS C.F., S.A.D.'))
        self.assertFalse(c.is_team('MONITORES FUTBOL DE ALGECIRAS'))
        self.assertFalse(c.is_team('CD ATLETICO PASTORES ALGECIRAS'))

    def test_partial_rejected(self):
        with self.assertRaises(ValueError):
            c.validate(self.matches[:-1])

    def test_noop_ignores_later_run_time(self):
        again, changes = c.reconcile(self.data, self.matches, '20260915T210000Z')
        self.assertEqual(again, self.data)
        self.assertEqual(changes, [])
        self.assertEqual(c.render(again), c.render(self.data))

    def test_confirmed_time_changes_only_target_revision(self):
        changed = copy.deepcopy(self.matches)
        changed[1].update(date='2026-09-27', time='11:00')
        after, changes = c.reconcile(self.data, changed, '20260915T210000Z')
        self.assertEqual(changes, [2])
        for index, match in enumerate(after['matches']):
            self.assertEqual(match['uid'], self.data['matches'][index]['uid'])
            if index != 1:
                self.assertEqual(match, self.data['matches'][index])
        self.assertEqual(after['matches'][1]['sequence'], 1)
        self.assertIn('DTSTART:20260927T090000Z', c.render(after))

    def test_unknown_time_does_not_erase_known(self):
        unknown = copy.deepcopy(self.matches)
        unknown[0].update(date='2026-09-20', time=None)
        with redirect_stdout(io.StringIO()):
            after, changes = c.reconcile(self.data, unknown, '20260915T210000Z')
        self.assertEqual(changes, [])
        self.assertEqual(after, self.data)

    def test_wrong_home_away_rejected(self):
        changed = copy.deepcopy(self.matches)
        changed[0]['home'], changed[0]['away'] = changed[0]['away'], changed[0]['home']
        with self.assertRaises(ValueError):
            c.reconcile(self.data, changed, '20260915T210000Z')

    def test_ics_is_folded_uses_distinct_uids_and_utc(self):
        ics = c.render(self.data)
        self.assertEqual(ics.count('BEGIN:VEVENT'), 30)
        self.assertEqual(ics.count('UID:algeciras-cadete-b-2026-27-'), 30)
        self.assertIn('DTSTART:20260919T073000Z', ics)
        self.assertIn('DTSTART;VALUE=DATE:20260926', ics)
        self.assertNotIn('\n', ics.replace('\r\n',''))
        self.assertTrue(all(len(line.encode('utf-8')) <= 75 for line in ics.split('\r\n')))


if __name__ == '__main__':
    unittest.main()
