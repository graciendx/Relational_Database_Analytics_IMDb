import gzip
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing

from imdb_analytics.analysis import (genre_coverage, read_only_connection, run,
    runtime_by_genre, top_movies, validate_database, vote_sensitivity)
from imdb_analytics.fixture import SCHEMA, demo_connection
from imdb_analytics.importer import build_database


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.executescript(SCHEMA)

    def tearDown(self):
        self.connection.close()

    def movie(self, title_id, rating=5, votes=10000, runtime=95, genres="Drama", year=2010, adult=0, kind="movie"):
        self.connection.execute("INSERT INTO titles VALUES (?,?,?,?,?,?,?)", (title_id,kind,"Same display title",adult,year,runtime,genres))
        self.connection.execute("INSERT INTO ratings VALUES (?,?,?)", (title_id,rating,votes))

    def test_bin_is_a_mean_not_an_arbitrary_title_rating(self):
        self.movie("a",rating=2,runtime=91)
        self.movie("b",rating=8,runtime=99)
        row = runtime_by_genre(self.connection,["Drama"])[0]
        self.assertEqual(row["runtime_bin_start"],90)
        self.assertEqual(row["title_count"],2)
        self.assertEqual(row["mean_title_rating"],5)

    def test_minimum_support_and_half_open_runtime_boundary(self):
        self.movie("a",runtime=199);self.movie("b",runtime=200)
        self.assertEqual(runtime_by_genre(self.connection,["Drama"]),[])
        rows = runtime_by_genre(self.connection,["Drama"],min_titles=1)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]["title_count"],1)

    def test_exact_genre_token_does_not_match_substring(self):
        self.movie("a",genres="Live-Action")
        self.movie("b",genres="Action,Drama")
        rows = runtime_by_genre(self.connection,["Action"],min_titles=1)
        self.assertEqual(rows[0]["title_count"],1)

    def test_adult_and_television_exclusion_is_consistent(self):
        self.movie("a",rating=6)
        self.movie("b",rating=10,adult=1)
        self.movie("c",rating=10,kind="tvEpisode")
        self.assertEqual([r["title_id"] for r in top_movies(self.connection,2010)],["a"])
        self.assertEqual(runtime_by_genre(self.connection,["Drama"],min_titles=1)[0]["mean_title_rating"],6)
        self.assertEqual(genre_coverage(self.connection,["Drama"],2010,2019)[0]["eligible_movies"],1)

    def test_multi_genre_shares_use_all_movies_as_denominator(self):
        self.movie("a",genres="Action,Drama,Action")
        self.movie("b",genres="Action,Drama")
        self.movie("c",genres="\\N")
        rows = genre_coverage(self.connection,["Action","Drama"],2010,2019)
        self.assertEqual([r["genre_titles"] for r in rows],[2,2])
        self.assertTrue(all(r["eligible_movies"]==3 for r in rows))
        self.assertAlmostEqual(sum(r["catalogue_share"] for r in rows),4/3)

    def test_empty_decade_is_unknown_share_not_zero_percent(self):
        self.movie("a",year=2010)
        row = genre_coverage(self.connection,["Drama"],2005,2009)[0]
        self.assertEqual(row["window_start_year"],2005)
        self.assertEqual(row["window_end_year"],2009)
        self.assertIsNone(row["catalogue_share"])

    def test_title_id_breaks_rating_and_vote_ties(self):
        self.movie("b",rating=8);self.movie("a",rating=8)
        self.assertEqual([r["title_id"] for r in top_movies(self.connection,2010)],["a","b"])

    def test_vote_sensitivity_reports_actual_overlap(self):
        self.movie("a",rating=9,votes=500);self.movie("b",rating=8,votes=10000)
        rows = vote_sensitivity(self.connection,2010,[200,5000],top_n=2)
        self.assertEqual([r["eligible_titles"] for r in rows],[2,1])
        self.assertEqual(rows[1]["jaccard_with_baseline"],.5)
        self.assertEqual(rows[1]["baseline_retention_share"],.5)

    def test_empty_shortlists_have_no_fictitious_stability(self):
        rows = vote_sensitivity(self.connection,2010,[200,5000])
        self.assertTrue(all(r["jaccard_with_baseline"] is None for r in rows))

    def test_query_parameters_cannot_inject_sql(self):
        self.movie("a")
        rows = runtime_by_genre(self.connection,["Drama' OR 1=1 --"],min_titles=1)
        self.assertEqual(rows,[])
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM titles").fetchone()[0],1)
        with self.assertRaises(ValueError): top_movies(self.connection,2010,top_n=-1)

    def test_duplicate_ids_fail_before_join(self):
        self.connection.execute("DROP TABLE ratings")
        self.connection.execute("CREATE TABLE ratings(title_id TEXT, rating REAL, votes INTEGER)")
        self.connection.executemany("INSERT INTO ratings VALUES (?,?,?)",[("a",5,100),("a",6,100)])
        with self.assertRaisesRegex(ValueError,"duplicate title"):
            validate_database(self.connection)

    def test_demo_end_to_end_is_explicitly_fictional(self):
        with tempfile.TemporaryDirectory() as directory, demo_connection() as connection:
            report = run(connection,Path(directory),"synthetic_fixture")
            self.assertEqual(report["profile"]["titles"],41)
            self.assertEqual(report["profile"]["non_adult_movies"],39)
            self.assertIn("not IMDb findings",report["interpretation"])
            self.assertTrue((Path(directory)/"runtime_bins.png").is_file())


class ImportTests(unittest.TestCase):
    def fixture(self, directory, duplicate=False):
        basics=Path(directory)/"basics.tsv.gz";ratings=Path(directory)/"ratings.tsv.gz"
        with gzip.open(basics,"wt") as f:
            f.write("tconst\ttitleType\tprimaryTitle\tisAdult\tstartYear\truntimeMinutes\tgenres\n")
            f.write("test-a\tmovie\tFictional One\t0\t2010\t95\tDrama\n")
            f.write("test-b\tmovie\tFictional Two\t0\t2010\t\\N\t\\N\n")
            f.write("test-c\tmovie\tFictional Adult\t1\t2010\t95\tDrama\n")
            if duplicate:f.write("test-a\tmovie\tDuplicate\t0\t2010\t95\tDrama\n")
        with gzip.open(ratings,"wt") as f:
            f.write("tconst\taverageRating\tnumVotes\ntest-a\t8.0\t10000\ntest-c\t9.0\t10000\n")
        return basics,ratings

    def test_import_normalizes_missing_values_and_filters_population(self):
        with tempfile.TemporaryDirectory() as directory:
            b,r=self.fixture(directory);out=Path(directory)/"new.db"
            build_database(b,r,out)
            before=hashlib.sha256(out.read_bytes()).hexdigest()
            with closing(read_only_connection(out)) as connection:
                validate_database(connection)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM titles").fetchone()[0],2)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM ratings").fetchone()[0],1)
                self.assertEqual(connection.execute("SELECT runtime_minutes,genres FROM titles WHERE title_id='test-b'").fetchone(),(None,None))
                with self.assertRaises(sqlite3.OperationalError):connection.execute("DELETE FROM titles")
            self.assertEqual(before,hashlib.sha256(out.read_bytes()).hexdigest())

    def test_missing_database_does_not_create_an_empty_file(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/"missing.db"
            with self.assertRaises(FileNotFoundError):read_only_connection(out)
            self.assertFalse(out.exists())

    def test_failed_import_leaves_no_partial_database(self):
        with tempfile.TemporaryDirectory() as directory:
            b,r=self.fixture(directory,duplicate=True);out=Path(directory)/"bad.db"
            with self.assertRaises(sqlite3.IntegrityError):build_database(b,r,out)
            self.assertFalse(out.exists());self.assertEqual(list(Path(directory).glob('*.tmp')),[])

    def test_existing_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            b,r=self.fixture(directory);out=Path(directory)/"existing.db";out.write_bytes(b"unchanged")
            with self.assertRaises(FileExistsError):build_database(b,r,out)
            self.assertEqual(out.read_bytes(),b"unchanged")


if __name__ == "__main__":unittest.main()
