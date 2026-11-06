SELECT COUNT(*) AS eligible_titles
FROM titles AS t JOIN ratings AS r ON r.title_id = t.title_id
WHERE t.type = 'movie' AND t.is_adult = 0 AND t.premiered = :year
  AND r.rating BETWEEN 0 AND 10 AND r.votes >= :min_votes;
