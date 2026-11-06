-- Parameters are defined before reviewing outputs. One row is one title.
WITH floors(vote_floor) AS (VALUES (100),(1000),(10000),(100000)),
eligible AS (
 SELECT t.title_id, t.premiered, t.runtime_minutes, t.genres, r.rating, r.votes
 FROM titles t JOIN ratings r USING(title_id)
 WHERE t.type='movie' AND t.is_adult=0
 AND t.premiered BETWEEN :start_year AND :end_year
), groups AS (
 SELECT f.vote_floor, e.*,
 ROW_NUMBER() OVER(PARTITION BY f.vote_floor ORDER BY e.rating,e.title_id) AS rating_rank,
 COUNT(*) OVER(PARTITION BY f.vote_floor) AS group_n
 FROM floors f JOIN eligible e ON e.votes >= f.vote_floor
)
SELECT vote_floor, COUNT(*) AS n_titles, AVG(rating) AS mean_title_rating,
 AVG(CASE WHEN rating_rank IN ((group_n+1)/2,(group_n+2)/2) THEN rating END) AS median_title_rating,
 AVG(premiered) AS mean_release_year,
 SUM(runtime_minutes IS NULL) AS missing_runtime,
 SUM(genres IS NULL OR genres='' OR genres='\N') AS missing_genres,
 AVG(CASE WHEN rating >= 8 THEN 1.0 ELSE 0 END) AS share_rating_at_least_8
FROM groups GROUP BY vote_floor ORDER BY vote_floor;
