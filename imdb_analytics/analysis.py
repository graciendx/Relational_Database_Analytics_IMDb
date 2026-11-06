"""SQL-first catalogue diagnostics with explicit eligibility and denominators."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sqlite3

from .fixture import demo_connection

SQL = Path(__file__).resolve().parent / "queries"
REQUIRED = {"titles": {"title_id", "type", "primary_title", "is_adult", "premiered", "runtime_minutes", "genres"},
            "ratings": {"title_id", "rating", "votes"}}


def read_only_connection(path: Path):
    path = path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Database not found: {path.name}; no empty file was created")
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)


def validate_database(connection):
    for table, required in REQUIRED.items():
        columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
        if not required.issubset(columns):
            raise ValueError(f"{table}: missing columns {sorted(required-columns)}")
        # Identifiers here come from the fixed REQUIRED allowlist, never user SQL.
        if connection.execute(f'SELECT 1 FROM "{table}" WHERE title_id IS NULL OR title_id="" LIMIT 1').fetchone():
            raise ValueError(f"{table}: missing title ID")
        if connection.execute(f'SELECT 1 FROM "{table}" GROUP BY title_id HAVING COUNT(*)>1 LIMIT 1').fetchone():
            raise ValueError(f"{table}: duplicate title IDs would multiply joins")
    invalid = connection.execute("""SELECT 1 FROM ratings WHERE
        rating IS NOT NULL AND (typeof(rating) NOT IN ('integer','real') OR rating < 0 OR rating > 10)
        OR votes IS NOT NULL AND (typeof(votes) <> 'integer' OR votes < 0) LIMIT 1""").fetchone()
    if invalid:
        raise ValueError("Ratings require numeric 0-10 values and nonnegative integer vote counts")


def query(connection, filename, params):
    if filename not in {"runtime_by_genre.sql", "genre_coverage.sql", "top_movies.sql", "eligible_count.sql"}:
        raise ValueError("Unknown query")
    cursor = connection.execute((SQL / filename).read_text(), params)
    fields = [item[0] for item in cursor.description]
    return [dict(zip(fields, row)) for row in cursor.fetchall()]


def integer(value, name, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def runtime_by_genre(connection, genres, min_votes=200, min_runtime=40, max_runtime=200,
                     bin_width=10, min_titles=2):
    integer(min_votes, "min_votes", 0, 10**10)
    integer(min_runtime, "min_runtime", 1, 2000); integer(max_runtime, "max_runtime", 2, 2001)
    integer(bin_width, "bin_width", 1, 60); integer(min_titles, "min_titles", 1, 10**7)
    if min_runtime >= max_runtime or not genres or len(genres) != len(set(genres)):
        raise ValueError("Supply distinct genres and an increasing runtime interval")
    records = []
    for genre in genres:
        if not isinstance(genre, str) or not genre.strip() or "," in genre:
            raise ValueError("Each genre must be one nonempty token")
        records.extend({"genre": genre, **row} for row in query(connection, "runtime_by_genre.sql", {
            "genre": genre, "min_votes": min_votes, "min_runtime": min_runtime, "max_runtime": max_runtime,
            "bin_width": bin_width, "min_titles": min_titles}))
    return records


def genre_coverage(connection, genres, start_year=1920, end_year=2019):
    integer(start_year, "start_year", 1800, 2200); integer(end_year, "end_year", start_year, 2200)
    if not genres or len(genres) != len(set(genres)):
        raise ValueError("Supply distinct genres")
    rows = query(connection, "genre_coverage.sql", {"start_year": start_year, "end_year": end_year})
    indexed = {(r["genre"], r["decade"]): r for r in rows}
    denominators = dict(connection.execute("""SELECT CAST(premiered/10 AS INTEGER)*10, COUNT(*)
        FROM titles WHERE type='movie' AND is_adult=0 AND premiered BETWEEN ? AND ? GROUP BY 1""", (start_year, end_year)))
    result = []
    for genre in genres:
        for decade in range(start_year//10*10, end_year//10*10+1, 10):
            denominator = denominators.get(decade, 0)
            row = indexed.get((genre, decade), {"genre": genre, "decade": decade, "genre_titles": 0,
                                              "eligible_movies": denominator,
                                              "catalogue_share": 0.0 if denominator else None})
            result.append(row | {"window_start_year": max(start_year, decade),
                                 "window_end_year": min(end_year, decade+9)})
    return result


def top_movies(connection, year, min_votes=5000, top_n=25):
    integer(year, "year", 1800, 2200); integer(min_votes, "min_votes", 0, 10**10)
    integer(top_n, "top_n", 1, 100)
    return query(connection, "top_movies.sql", {"year": year, "min_votes": min_votes, "top_n": top_n})


def vote_sensitivity(connection, year, thresholds=(200, 5000, 50000), top_n=25):
    if not thresholds or len(thresholds) != len(set(thresholds)):
        raise ValueError("Supply distinct vote thresholds")
    thresholds = sorted(integer(v, "vote threshold", 0, 10**10) for v in thresholds)
    baseline = {r["title_id"] for r in top_movies(connection, year, thresholds[0], top_n)}
    result = []
    for threshold in thresholds:
        shortlist = top_movies(connection, year, threshold, top_n)
        ids = {r["title_id"] for r in shortlist}
        eligible = query(connection, "eligible_count.sql", {"year": year, "min_votes": threshold})[0]["eligible_titles"]
        union = baseline | ids
        result.append({"year": year, "minimum_votes": threshold, "eligible_titles": eligible,
                       "returned_titles": len(shortlist), "retained_from_baseline": len(baseline & ids),
                       "jaccard_with_baseline": len(baseline & ids)/len(union) if union else None,
                       "baseline_retention_share": len(baseline & ids)/len(baseline) if baseline else None})
    return result


def profile_database(connection):
    return {
        "titles": connection.execute("SELECT COUNT(*) FROM titles").fetchone()[0],
        "ratings": connection.execute("SELECT COUNT(*) FROM ratings").fetchone()[0],
        "non_adult_movies": connection.execute("SELECT COUNT(*) FROM titles WHERE type='movie' AND is_adult=0").fetchone()[0],
        "missing_runtime_movies": connection.execute("""SELECT COUNT(*) FROM titles WHERE type='movie'
            AND is_adult=0 AND (runtime_minutes IS NULL OR CAST(runtime_minutes AS TEXT)='\\N')""").fetchone()[0],
        "missing_genre_movies": connection.execute("""SELECT COUNT(*) FROM titles WHERE type='movie'
            AND is_adult=0 AND (genres IS NULL OR genres='' OR genres='\\N')""").fetchone()[0],
        "movies_without_rating": connection.execute("""SELECT COUNT(*) FROM titles t LEFT JOIN ratings r USING(title_id)
            WHERE t.type='movie' AND t.is_adult=0 AND r.rating IS NULL""").fetchone()[0],
        "orphan_rating_rows": connection.execute("""SELECT COUNT(*) FROM ratings r LEFT JOIN titles t USING(title_id)
            WHERE t.title_id IS NULL""").fetchone()[0],
    }


def write_csv(path, records, fields):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(records)


def run(connection, output, dataset_kind, year=2010, genres=("Drama", "Comedy", "Action", "Documentary")):
    validate_database(connection)
    runtime = runtime_by_genre(connection, genres)
    coverage = genre_coverage(connection, genres)
    shortlist = top_movies(connection, year)
    sensitivity = vote_sensitivity(connection, year)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output/"runtime_bins.csv", runtime, ["genre","runtime_bin_start","title_count","mean_title_rating","minimum_title_rating","maximum_title_rating"])
    write_csv(output/"genre_coverage.csv", coverage, ["genre","decade","genre_titles","eligible_movies","catalogue_share","window_start_year","window_end_year"])
    write_csv(output/"top_movies.csv", shortlist, ["title_id","primary_title","genres","premiered","runtime_minutes","rating","votes"])
    write_csv(output/"vote_sensitivity.csv", sensitivity, ["year","minimum_votes","eligible_titles","returned_titles","retained_from_baseline","jaccard_with_baseline","baseline_retention_share"])
    summary = {"author": "Grace Ngo", "dataset_kind": dataset_kind, "year": year, "profile": profile_database(connection),
               "parameters": {"genres": list(genres), "runtime_interval": "[40,200)", "bin_width": 10,
                              "min_votes_runtime": 200, "min_titles_per_bin": 2, "coverage_years": [1920,2019],
                              "ranking_min_votes": 5000, "top_n": 25, "vote_thresholds": [200,5000,50000]},
               "vote_sensitivity": sensitivity, "sqlite_version": sqlite3.sqlite_version,
               "interpretation": "Fictional software demonstration; not IMDb findings." if dataset_kind == "synthetic_fixture" else
                                 "Descriptive catalogue diagnostics; no causal runtime effect, viewership or revenue claim."}
    (output/"summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n")
    create_figures(runtime, sensitivity, output, dataset_kind)
    return summary


def create_figures(runtime, sensitivity, output, dataset_kind):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import math
    label = "Fictional demonstration data" if dataset_kind == "synthetic_fixture" else "Local database results"
    genres = list(dict.fromkeys(r["genre"] for r in runtime))
    columns = 1 if len(genres) <= 1 else 2 if len(genres) <= 4 else 3
    rows = max(1, math.ceil(len(genres)/columns))
    fig, axes = plt.subplots(rows, columns, figsize=(4.1*columns, 3.5*rows), squeeze=False)
    for ax, genre in zip(axes.flat, genres):
        data = [r for r in runtime if r["genre"] == genre]
        ax.scatter([r["runtime_bin_start"]+5 for r in data], [r["mean_title_rating"] for r in data],
                   s=[25+12*r["title_count"] for r in data], color="#772c44", alpha=.8)
        for r in data:
            ax.annotate(f'n={r["title_count"]}', (r["runtime_bin_start"]+5,r["mean_title_rating"]), xytext=(0,7),
                        textcoords="offset points", ha="center", fontsize=8)
        ax.set(title=genre, xlabel="10-minute bin midpoint", ylabel="Mean title rating", xlim=(40,200), ylim=(0,10))
        ax.grid(alpha=.15)
    for ax in list(axes.flat)[len(genres):]: ax.set_visible(False)
    if not genres:
        axes[0,0].set_visible(True); axes[0,0].text(.5,.5,"No supported runtime bins",ha="center"); axes[0,0].set_axis_off()
    fig.suptitle("Runtime-bin rating summaries | "+label, fontsize=12)
    fig.tight_layout(rect=[0,0,1,.94]); fig.savefig(output/"runtime_bins.png",dpi=160); plt.close(fig)
    fig, ax = plt.subplots(figsize=(8,4.3))
    ax.bar([str(r["minimum_votes"]) for r in sensitivity], [r["eligible_titles"] for r in sensitivity], color="#285d70")
    ax.set(title="Vote-floor sensitivity | "+label, xlabel="Minimum recorded votes", ylabel="Eligible movies in selected year")
    ax.grid(axis="y",alpha=.15); fig.tight_layout();fig.savefig(output/"vote_sensitivity.png",dpi=160);plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--database", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--year", type=int, default=2010)
    args = parser.parse_args()
    output = args.output or Path("reports/demo" if args.demo else "outputs/local")
    connection = demo_connection() if args.demo else read_only_connection(args.database)
    try:
        summary = run(connection, output, "synthetic_fixture" if args.demo else "local_database", args.year)
    finally:
        connection.close()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__": main()
