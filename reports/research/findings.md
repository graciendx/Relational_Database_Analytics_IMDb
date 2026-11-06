# IMDb vote-floor sensitivity

Question: how does requiring more audience votes change a movie-review pool and its apparent quality?

Scope: non-adult IMDb movies released 2000–2024; joined to observed ratings. Snapshot metadata and hashes are in source_manifest.json.

| Minimum votes | Titles | Retained vs 100 votes | Mean title rating | Median rating | Top-50 retained |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 88,601 | 100.0% | 5.789 | 6.00 | 50 / 50 |
| 1,000 | 30,977 | 35.0% | 6.101 | 6.30 | 3 / 50 |
| 10,000 | 8,323 | 9.4% | 6.449 | 6.50 | 0 / 50 |
| 100,000 | 2,008 | 2.3% | 6.849 | 6.90 | 0 / 50 |

## Findings

Increasing the vote floor from 100 to 10,000 retains 9.4% of the baseline pool (8,323 of 88,601 movies). The mean of title-level ratings changes from 5.789 to 6.449. This is selection, not an improvement in the films or a causal effect of voting.
The top-50 shortlist retains 0 of 50 baseline titles and introduces 50 replacements. Ranking is rating descending, votes descending, title ID ascending.

Largest genre-share shifts at 10,000 versus 100 votes:
- Action: 12.8% to 26.2% (+13.4 percentage points).
- Crime: 10.3% to 20.4% (+10.2 percentage points).
- Adventure: 6.8% to 16.7% (+10.0 percentage points).
- Documentary: 12.5% to 2.8% (-9.7 percentage points).
- Drama: 49.8% to 57.4% (+7.6 percentage points).

Holding release-year weights at the baseline distribution, the mean-rating difference is +0.650 points.

## Recommendation

Display vote eligibility alongside a shortlist and compare genre mix before adopting a high threshold. A high vote floor is a support rule; it also changes coverage. For discovery, keep a separate lower-vote review lane instead of silently excluding it. These findings do not identify an optimal threshold or establish commercial demand.

## Definitions and limits

Each title receives equal weight in the reported mean. IMDb averageRating is itself a provider-weighted user-rating measure. Votes are cumulative participation as of the snapshot, not unique viewers, sales, or revenue. Genre shares overlap because movies may have up to three tags; unknown genres remain in the denominator. Runtime is not required for inclusion. Release-year standardization compares within-year mean differences using fixed baseline-year weights; it does not remove language, geography, survival or audience-selection bias. The predeclared 100/1,000/10,000/100,000 vote floors are sensitivity scenarios, not optimized cutoffs.

Source datasets and the SQLite database remain local and are not redistributed. The original missing classroom database has not been reconstructed; this is a new, documented official-data extension. Aggregate numerical outputs are reconciled independently against the imported records.

Source: https://data.imdb.com/non-commercial-datasets/
