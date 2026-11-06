"""Fictional records for executable examples; never a sample of IMDb."""
import sqlite3

SCHEMA = """
CREATE TABLE titles (
 title_id TEXT PRIMARY KEY, type TEXT NOT NULL, primary_title TEXT NOT NULL,
 is_adult INTEGER, premiered INTEGER, runtime_minutes REAL, genres TEXT
);
CREATE TABLE ratings (title_id TEXT PRIMARY KEY, rating REAL, votes INTEGER);
"""


def demo_connection():
    connection = sqlite3.connect(":memory:")
    connection.executescript(SCHEMA)
    genres = ["Action,Drama", "Comedy", "Drama,Comedy", "Documentary", "Action", "Drama"]
    for i in range(36):
        title_id = f"demo-{i:03}"
        year = [1985, 1995, 2005, 2010, 2010, 2010][i % 6]
        connection.execute("INSERT INTO titles VALUES (?,?,?,?,?,?,?)", (
            title_id, "movie", f"Fictional Film {i+1:02}", 0, year,
            [91, 99, 102, 118, 125, 150][i % 6], genres[i % 6]))
        connection.execute("INSERT INTO ratings VALUES (?,?,?)", (
            title_id, 5.0 + (i % 10) * .4, [200, 1000, 5000, 10000, 50000, 100000][i % 6]))
    connection.executemany("INSERT INTO titles VALUES (?,?,?,?,?,?,?)", [
        ("demo-adult", "movie", "Excluded adult example", 1, 2010, 95, "Drama"),
        ("demo-tv", "tvEpisode", "Excluded television example", 0, 2010, 95, "Drama"),
        ("demo-missing", "movie", "Missing runtime example", 0, 2010, None, "Drama"),
        ("demo-unknown", "movie", "Unknown genre example", 0, 2010, 95, "\\N"),
        ("demo-token", "movie", "Exact token example", 0, 2010, 95, "Live-Action"),
    ])
    connection.executemany("INSERT INTO ratings VALUES (?,?,?)", [
        ("demo-adult", 10, 100000), ("demo-tv", 10, 100000),
        ("demo-missing", 7, 100), ("demo-unknown", 7, 100), ("demo-token", 7, 100),
    ])
    connection.commit()
    return connection
