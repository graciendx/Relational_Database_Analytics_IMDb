"""Build a local, non-adult-movie SQLite subset from authorized IMDb TSV files."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

from .fixture import SCHEMA


def rows(path, required):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t", quoting=csv.QUOTE_NONE)
        if len(reader.fieldnames or []) != len(set(reader.fieldnames or [])) or not required.issubset(reader.fieldnames or []):
            raise ValueError(f"{path.name}: unexpected TSV headers")
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f"{path.name}: malformed TSV row")
            yield row


def number(value, kind=int):
    return None if value in ("\\N", "") else kind(value)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b""): h.update(chunk)
    return h.hexdigest()


def build_database(basics, ratings, output):
    if output.exists():
        raise FileExistsError("Destination exists; choose a new database path")
    output.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(prefix="imdb-import-", suffix=".tmp", dir=output.parent, delete=False)
    temp = Path(handle.name); handle.close()
    connection = None
    try:
        connection = sqlite3.connect(temp)
        connection.executescript(SCHEMA)
        for row in rows(basics, {"tconst","titleType","primaryTitle","isAdult","startYear","runtimeMinutes","genres"}):
            if row["titleType"] != "movie" or row["isAdult"] != "0": continue
            year, runtime = number(row["startYear"]), number(row["runtimeMinutes"])
            if not row["tconst"] or year is not None and not 1800 <= year <= 2200 or runtime is not None and runtime < 0:
                raise ValueError("Invalid title identifier, year or runtime")
            connection.execute("INSERT INTO titles VALUES (?,?,?,?,?,?,?)", (
                row["tconst"], row["titleType"], row["primaryTitle"], 0, year, runtime,
                None if row["genres"] == "\\N" else row["genres"]))
        for row in rows(ratings, {"tconst","averageRating","numVotes"}):
            rating, votes = number(row["averageRating"], float), number(row["numVotes"])
            if rating is None or not 0 <= rating <= 10 or votes is None or votes < 0:
                raise ValueError("Invalid rating or vote count")
            connection.execute("""INSERT INTO ratings SELECT ?,?,?
                WHERE EXISTS (SELECT 1 FROM titles WHERE title_id=?)""", (row["tconst"],rating,votes,row["tconst"]))
        connection.execute("CREATE INDEX movie_year ON titles(type,is_adult,premiered)")
        connection.execute("CREATE TABLE import_metadata (key TEXT PRIMARY KEY, value TEXT)")
        metadata = {"scope":"non-adult movies only", "basics_sha256":digest(basics), "ratings_sha256":digest(ratings)}
        connection.executemany("INSERT INTO import_metadata VALUES (?,?)", metadata.items())
        connection.commit(); connection.close(); connection = None
        # Hard-link publication is atomic and refuses an existing destination.
        output.hardlink_to(temp)
        return metadata
    finally:
        if connection is not None: connection.close()
        temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--basics", type=Path, required=True)
    parser.add_argument("--ratings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_database(args.basics,args.ratings,args.output),indent=2))


if __name__ == "__main__": main()
