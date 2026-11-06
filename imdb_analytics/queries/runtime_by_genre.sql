-- One row per runtime bin. Every statistic is explicitly aggregated.
SELECT CAST(t.runtime_minutes / :bin_width AS INTEGER) * :bin_width AS runtime_bin_start,
       COUNT(*) AS title_count, AVG(r.rating) AS mean_title_rating,
       MIN(r.rating) AS minimum_title_rating, MAX(r.rating) AS maximum_title_rating
FROM titles AS t JOIN ratings AS r ON r.title_id = t.title_id
WHERE t.type = 'movie' AND t.is_adult = 0
  AND t.runtime_minutes >= :min_runtime AND t.runtime_minutes < :max_runtime
  AND r.rating BETWEEN 0 AND 10 AND r.votes >= :min_votes
  AND instr(',' || replace(coalesce(t.genres, ''), ' ', '') || ',', ',' || :genre || ',') > 0
GROUP BY runtime_bin_start
HAVING COUNT(*) >= :min_titles
ORDER BY runtime_bin_start;
