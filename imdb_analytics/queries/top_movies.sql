SELECT t.title_id, t.primary_title, t.genres, t.premiered, t.runtime_minutes,
       r.rating, r.votes
FROM titles AS t JOIN ratings AS r ON r.title_id = t.title_id
WHERE t.type = 'movie' AND t.is_adult = 0 AND t.premiered = :year
  AND r.rating BETWEEN 0 AND 10 AND r.votes >= :min_votes
ORDER BY r.rating DESC, r.votes DESC, t.title_id ASC
LIMIT :top_n;
