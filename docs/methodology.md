# Analytical decisions and source review

## Correct the statistic before interpreting the chart

The supplied runtime function selected `r.rating` and `t.runtime_minutes` while grouping by a runtime-bin expression. Neither selected column was aggregated. SQLite permits bare result columns in grouped queries; they do not establish a bin mean. The accompanying narrative described averages and runtime guidance that the code did not compute.

The reviewed query returns explicit mean, minimum and maximum title ratings plus `COUNT(*)`. Unsupported bins are omitted according to a declared minimum title count. The figure shows bin summaries and support, not fictitious raw-title scatter points or a fitted trendline. Integer bin starts and half-open filters make boundaries reproducible.

## Define catalogue coverage honestly

The original heatmap was called popularity and production volume. It counted catalogue records, including overlapping tags, and the requested 1920-2020 interval included only one year of the 2020s. The corrected workflow calls this genre coverage, tokenizes genres exactly, deduplicates memberships and reports each decade's denominator and requested year window. Unknown genres remain in the denominator. The default window ends in 2019.

Coverage is an attribute of the catalogue snapshot, not attendance, streaming demand or a complete census of film production. Metadata availability and surviving historical records can affect trends.

## Treat ranking as a parameterized view

A minimum vote count changes which films qualify; it does not prove statistical precision or establish viewership. The sensitivity table reports pool size and shortlist overlap across three declared floors. Ties are resolved by title ID after rating and votes. All genre labels are retained, rather than calling the first token the primary genre.

The same non-adult-movie scope applies to runtime, coverage and shortlist queries. Missing fields have question-specific effects. A missing runtime does not exclude a title from ranking if year, rating and votes are available.

## Keep verification separate from empirical findings

The original `imdb.db` is absent. Saved screenshots and text do not substitute for running corrected SQL against it. Published outputs use fictional records with controlled properties. Tests compare query results with independent expected values, including the mean of two different ratings in one bin.

The original exploration notebook reports 8,802,474 titles and 1,228,987 ratings in saved output. These are historical cached counts, not a newly verified run, a performance benchmark or the size of the demonstration. The first 50,000 source rows were not a random sample and cannot establish full-database null rates.

The source notebooks and README contained classroom prompts and speculative example findings. The current notebooks remove those prompts and unsupported interpretations. Earlier repository versions remain recoverable in Git history.
