-- Normalize genre tokens after restricting the title population.
WITH RECURSIVE eligible AS (
    SELECT title_id, CAST(premiered / 10 AS INTEGER) * 10 AS decade, genres
    FROM titles
    WHERE type = 'movie' AND is_adult = 0 AND premiered BETWEEN :start_year AND :end_year
), tokens(title_id, decade, genre, remaining) AS (
    SELECT title_id, decade, '', coalesce(NULLIF(genres, '\N'), '') || ',' FROM eligible
    UNION ALL
    SELECT title_id, decade, trim(substr(remaining, 1, instr(remaining, ',') - 1)),
           substr(remaining, instr(remaining, ',') + 1)
    FROM tokens WHERE remaining <> ''
), memberships AS (
    SELECT DISTINCT title_id, decade, genre FROM tokens WHERE genre <> ''
), denominators AS (
    SELECT decade, COUNT(*) AS eligible_movies FROM eligible GROUP BY decade
)
SELECT m.genre, m.decade, COUNT(*) AS genre_titles, d.eligible_movies,
       1.0 * COUNT(*) / d.eligible_movies AS catalogue_share
FROM memberships AS m JOIN denominators AS d ON d.decade = m.decade
GROUP BY m.genre, m.decade, d.eligible_movies
ORDER BY m.genre, m.decade;
