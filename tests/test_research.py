import sqlite3
import tempfile
from pathlib import Path
import unittest
from imdb_analytics.fixture import SCHEMA
from imdb_analytics.research import analyze,write_reports


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.con=sqlite3.connect(':memory:');self.con.executescript(SCHEMA)
        values=[('a',8.,100,'Drama',2000),('b',6.,1000,'Drama,Comedy',2000),
                ('c',9.,10000,'Documentary',2000),('d',7.,100000,None,2000),
                ('e',10.,100000,'Drama',1999)]
        for id,r,v,g,y in values:
            self.con.execute('INSERT INTO titles VALUES (?,?,?,?,?,?,?)',(id,'movie',id,0,y,None,g))
            self.con.execute('INSERT INTO ratings VALUES (?,?,?)',(id,r,v))

    def tearDown(self):self.con.close()

    def test_counts_medians_shortlist_and_unknown_denominators(self):
        r=analyze(self.con,top_n=2);s=r['threshold_summary']
        self.assertEqual([x['n_titles'] for x in s],[4,3,2,1])
        self.assertEqual([x['median_title_rating'] for x in s],[7.5,7.,8.,7.])
        self.assertEqual(s[2]['shortlist_overlap_count'],1)
        self.assertEqual(s[2]['shortlist_new_count'],1)
        self.assertEqual(s[2]['baseline_shortlist_retention'],.5)
        g=next(x for x in r['genre_mix'] if x['vote_floor']==100000 and x['genre']=='Drama')
        self.assertEqual((g['denominator'],g['tagged_titles'],g['share']),(1,0,0.))

    def test_year_standardization_uses_fixed_weights(self):
        self.con.execute('INSERT INTO titles VALUES (?,?,?,?,?,?,?)',('f','movie','f',0,2001,100,'Drama'))
        self.con.execute('INSERT INTO ratings VALUES (?,?,?)',('f',10.,100))
        rows=analyze(self.con)['threshold_summary']
        self.assertIsNone(rows[1]['baseline_year_standardized_rating_delta'])
        self.assertAlmostEqual(rows[1]['standardization_covered_weight'],.8)

    def test_empty_window_fails(self):
        with self.assertRaisesRegex(ValueError,'No baseline'):analyze(self.con,2020,2024)

    def test_reports_preserve_input_fingerprints_for_a_new_run(self):
        result = analyze(self.con)
        result['import_metadata'] = {'basics_sha256': 'example-input-hash'}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_reports(result, output)
            manifest = json.loads((output / 'run_manifest.json').read_text())
            self.assertEqual(manifest['import_metadata'], result['import_metadata'])
            self.assertEqual(manifest['config'], result['config'])
            self.assertIn('generated_at_utc', manifest)
            self.assertIn('run_manifest.json', (output / 'findings.md').read_text())

    def test_exact_genre_tokens(self):
        self.con.execute("UPDATE titles SET genres='Live-Action' WHERE title_id='a'")
        rows=analyze(self.con)['genre_mix']
        g=next(x for x in rows if x['genre']=='Action' and x['vote_floor']==100)
        self.assertEqual(g['tagged_titles'],0)


if __name__=='__main__':unittest.main()

import json
