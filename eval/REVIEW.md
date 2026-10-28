# Evaluation set review sheet

Approve, edit or reject each reference query. Results are from the real database.

## D01 (dev, aggregation): How many questions were asked in total?

**reference** (1 rows, 0.0s)
```sql
SELECT COUNT(*) AS n FROM posts_questions
```

| n |
|---|
| 174131 |

## D02 (dev, aggregation): What is the average reputation of users?

**reference** (1 rows, 0.0s)
```sql
SELECT AVG(reputation) AS avg_reputation FROM users
```

| avg_reputation |
|---|
| 2013.1188 |

## D03 (dev, aggregation): How many distinct users have posted at least one answer?

**reference** (1 rows, 0.0s)
```sql
SELECT COUNT(DISTINCT user_id) AS n FROM posts_answers
```

| n |
|---|
| 86363 |

## D04 (dev, join): Which 10 tags have the most comments on their questions?

**reference** (10 rows, 5.3s)
```sql
SELECT t.tag_name, COUNT(c.comment_id) AS comment_count FROM tags t JOIN post_tags pt ON pt.tag_id = t.tag_id JOIN comments c ON c.post_id = pt.post_id GROUP BY t.tag_id, t.tag_name ORDER BY comment_count DESC, t.tag_name LIMIT 10
```

| tag_name | comment_count |
|---|---|
| python | 89853 |
| javascript | 66674 |
| java | 37625 |
| c# | 36377 |
| c++ | 32950 |

*Note: Counts comments on the question itself, not on its answers.*

## D05 (dev, join): What are the 10 most common tags on questions asked by users with reputation over 10,000?

**reference** (10 rows, 2.3s)
```sql
SELECT t.tag_name, COUNT(*) AS n FROM posts_questions q JOIN users u ON u.user_id = q.user_id JOIN post_tags pt ON pt.post_id = q.post_id JOIN tags t ON t.tag_id = pt.tag_id WHERE u.reputation > 10000 GROUP BY t.tag_id, t.tag_name ORDER BY n DESC, t.tag_name LIMIT 10
```

| tag_name | n |
|---|---|
| javascript | 788 |
| python | 759 |
| c# | 474 |
| java | 402 |
| typescript | 359 |

## D06 (dev, absence): How many questions have received no answers at all?

**reference** (1 rows, 0.2s)
```sql
SELECT COUNT(*) AS n FROM posts_questions WHERE answer_count = 0
```

| n |
|---|
| 42669 |

*Note: Uses the question's answer_count field only. Counting questions with no loaded answer rows gives a different number (43,217 vs 42,669) and is not accepted.*

## D07 (dev, absence): How many users have asked a question but never posted an answer?

**reference** (1 rows, 0.8s)
```sql
SELECT COUNT(*) AS n FROM users u WHERE EXISTS (SELECT 1 FROM posts_questions q WHERE q.user_id = u.user_id) AND NOT EXISTS (SELECT 1 FROM posts_answers a WHERE a.user_id = u.user_id)
```

| n |
|---|
| 121418 |

## D08 (dev, date): On average, how many days pass between a user creating their account and asking their first question?

**reference** (1 rows, 1.8s)
```sql
SELECT AVG(julianday(fq.first_q) - julianday(u.creation_date)) AS avg_days FROM users u JOIN (SELECT user_id, MIN(creation_date) AS first_q FROM posts_questions GROUP BY user_id) fq ON fq.user_id = u.user_id
```

| avg_days |
|---|
| 951.3401 |

## D09 (dev, date): What is the average number of hours until the first answer for questions tagged python?

**reference** (1 rows, 0.9s)
```sql
SELECT AVG((julianday(fa.first_a) - julianday(q.creation_date)) * 24) AS avg_hours FROM posts_questions q JOIN (SELECT parent_id, MIN(creation_date) AS first_a FROM posts_answers GROUP BY parent_id) fa ON fa.parent_id = q.post_id WHERE q.post_id IN (SELECT pt.post_id FROM post_tags pt JOIN tags t ON t.tag_id = pt.tag_id WHERE t.tag_name = 'python')
```

| avg_hours |
|---|
| 163.4517 |

## D10 (dev, date): Which month of 2021 had the most answers posted?

**reference** (1 rows, 0.2s)
```sql
SELECT strftime('%Y-%m', creation_date) AS month, COUNT(*) AS n FROM posts_answers WHERE strftime('%Y', creation_date) = '2021' GROUP BY month ORDER BY n DESC, month LIMIT 1
```

| month | n |
|---|---|
| 2021-03 | 5993 |

## D11 (dev, rate): What is the average answer score for accepted answers compared with answers that were not accepted?

**reference** (2 rows, 0.3s)
```sql
SELECT is_accepted, AVG(score) AS avg_score FROM posts_answers GROUP BY is_accepted ORDER BY is_accepted
```

| is_accepted | avg_score |
|---|---|
| 0 | 0.6675 |
| 1 | 1.5261 |

## D12 (dev, rate): What percentage of questions have at least one answer with a score above 10?

**reference** (1 rows, 0.2s)
```sql
SELECT 100.0 * COUNT(DISTINCT a.parent_id) / (SELECT COUNT(*) FROM posts_questions) AS pct FROM posts_answers a WHERE a.score > 10
```

| pct |
|---|
| 0.456 |

*Note: Denominator is all questions.*

## D13 (dev, rate): For each year, what fraction of questions got an accepted answer?

**reference** (3 rows, 0.4s)
```sql
SELECT strftime('%Y', creation_date) AS year, AVG(accepted_answer_id IS NOT NULL) AS fraction FROM posts_questions GROUP BY year ORDER BY year
```

| year | fraction |
|---|---|
| 2020 | 0.4579 |
| 2021 | 0.4196 |
| 2022 | 0.3256 |

## D14 (dev, window): For each of the 5 tags with the most questions, what is the highest-scoring answer?

**reference** (5 rows, 1.4s)
```sql
WITH top_tags AS (SELECT tag_id, COUNT(*) AS n FROM post_tags GROUP BY tag_id ORDER BY n DESC, tag_id LIMIT 5), ranked AS (SELECT tt.tag_id, a.post_id, a.score, ROW_NUMBER() OVER (PARTITION BY tt.tag_id ORDER BY a.score DESC, a.post_id) AS rn FROM top_tags tt JOIN post_tags pt ON pt.tag_id = tt.tag_id JOIN posts_answers a ON a.parent_id = pt.post_id) SELECT t.tag_name, r.post_id, r.score FROM ranked r JOIN tags t ON t.tag_id = r.tag_id WHERE r.rn = 1 ORDER BY r.score DESC
```

| tag_name | post_id | score |
|---|---|---|
| java | 63851895 | 561 |
| reactjs | 64304122 | 502 |
| javascript | 60242323 | 445 |
| python | 64698899 | 283 |
| c# | 69919694 | 210 |

## D15 (dev, window): What is the running total of questions asked per month during 2021?

**reference** (12 rows, 0.2s)
```sql
WITH m AS (SELECT strftime('%Y-%m', creation_date) AS month, COUNT(*) AS n FROM posts_questions WHERE strftime('%Y', creation_date) = '2021' GROUP BY month) SELECT month, n, SUM(n) OVER (ORDER BY month) AS running_total FROM m ORDER BY month
```

| month | n | running_total |
|---|---|---|
| 2021-01 | 5172 | 5172 |
| 2021-02 | 4906 | 10078 |
| 2021-03 | 5451 | 15529 |
| 2021-04 | 5092 | 20621 |
| 2021-05 | 4878 | 25499 |

## D16 (dev, window): What was the most popular tag in each year?

**reference** (3 rows, 2.0s)
```sql
WITH c AS (SELECT strftime('%Y', q.creation_date) AS yr, pt.tag_id, COUNT(*) AS n FROM posts_questions q JOIN post_tags pt ON pt.post_id = q.post_id GROUP BY yr, pt.tag_id), r AS (SELECT yr, tag_id, n, RANK() OVER (PARTITION BY yr ORDER BY n DESC) AS rk FROM c) SELECT r.yr, t.tag_name, r.n FROM r JOIN tags t ON t.tag_id = r.tag_id WHERE r.rk = 1 ORDER BY r.yr
```

| yr | tag_name | n |
|---|---|---|
| 2020 | python | 17293 |
| 2021 | python | 16039 |
| 2022 | python | 12555 |

*Note: 'Popular' read as number of questions.*

## D17 (dev, ambiguous): Who is the most active user?

**reference** (1 rows, 0.3s)
```sql
SELECT u.display_name, x.total FROM (SELECT user_id, SUM(n) AS total FROM (SELECT user_id, COUNT(*) AS n FROM posts_questions GROUP BY user_id UNION ALL SELECT user_id, COUNT(*) FROM posts_answers GROUP BY user_id) GROUP BY user_id ORDER BY total DESC, user_id LIMIT 1) x JOIN users u ON u.user_id = x.user_id
```

| display_name | total |
|---|---|
| Gordon Linoff | 1295 |

**alt 1** (1 rows, 0.2s)
```sql
SELECT u.display_name, COUNT(*) AS n FROM posts_answers a JOIN users u ON u.user_id = a.user_id GROUP BY u.user_id, u.display_name ORDER BY n DESC, u.user_id LIMIT 1
```

| display_name | n |
|---|---|
| Gordon Linoff | 1295 |

*Note: Ambiguous. Primary: questions + answers. Also accepted: answers only. Questions only is not accepted.*

## D18 (dev, ambiguous): What is the most popular tag?

**reference** (1 rows, 0.1s)
```sql
SELECT t.tag_name, COUNT(*) AS n FROM post_tags pt JOIN tags t ON t.tag_id = pt.tag_id GROUP BY t.tag_id, t.tag_name ORDER BY n DESC, t.tag_name LIMIT 1
```

| tag_name | n |
|---|---|
| python | 45887 |

**alt 1** (1 rows, 2.0s)
```sql
SELECT t.tag_name, SUM(q.view_count) AS views FROM post_tags pt JOIN tags t ON t.tag_id = pt.tag_id JOIN posts_questions q ON q.post_id = pt.post_id GROUP BY t.tag_id, t.tag_name ORDER BY views DESC, t.tag_name LIMIT 1
```

| tag_name | views |
|---|---|
| python | 17888144 |

*Note: Ambiguous. Primary: most questions. Also accepted: most total views.*

## D19 (dev, unanswerable): Which user cast the most upvotes?

*Unanswerable.* Voters are anonymized: votes.user_id is always NULL. Expected: no result that names users.

## D20 (dev, unanswerable): What is the average salary of the users?

*Unanswerable.* No salary data exists. Expected: the query fails or returns nothing; fail if it substitutes another column.

## T01 (test, aggregation): How many users have a reputation above 100,000?

**reference** (1 rows, 0.0s)
```sql
SELECT COUNT(*) AS n FROM users WHERE reputation > 100000
```

| n |
|---|
| 625 |

## T02 (test, aggregation): What is the average view count of a question?

**reference** (1 rows, 0.2s)
```sql
SELECT AVG(view_count) AS avg_views FROM posts_questions
```

| avg_views |
|---|
| 441.6646 |

## T03 (test, aggregation): How many answers have a negative score?

**reference** (1 rows, 0.2s)
```sql
SELECT COUNT(*) AS n FROM posts_answers WHERE score < 0
```

| n |
|---|
| 4515 |

## T04 (test, aggregation): What is the total number of comments posted?

**reference** (1 rows, 0.0s)
```sql
SELECT COUNT(*) AS n FROM comments
```

| n |
|---|
| 572119 |

## T05 (test, aggregation): How many distinct tags have been used?

**reference** (1 rows, 0.0s)
```sql
SELECT COUNT(DISTINCT tag_id) AS n FROM post_tags
```

| n |
|---|
| 19607 |

*Note: 'Used' means attached to at least one question. The tags table lists 63,653 tags, so counting rows in it instead is wrong.*

## T06 (test, aggregation): What is the highest score any question has received?

**reference** (1 rows, 0.2s)
```sql
SELECT MAX(score) AS max_score FROM posts_questions
```

| max_score |
|---|
| 283 |

## T07 (test, join): What are the 10 most frequently used tags on questions that have an accepted answer?

**reference** (10 rows, 1.3s)
```sql
SELECT t.tag_name, COUNT(*) AS n FROM posts_questions q JOIN post_tags pt ON pt.post_id = q.post_id JOIN tags t ON t.tag_id = pt.tag_id WHERE q.accepted_answer_id IS NOT NULL GROUP BY t.tag_id, t.tag_name ORDER BY n DESC, t.tag_name LIMIT 10
```

| tag_name | n |
|---|---|
| python | 19727 |
| javascript | 13777 |
| java | 6109 |
| reactjs | 5762 |
| c# | 5263 |

## T08 (test, join): Which 5 users have the highest total score across all their answers?

**reference** (5 rows, 2.0s)
```sql
SELECT u.display_name, SUM(a.score) AS total_score FROM posts_answers a JOIN users u ON u.user_id = a.user_id GROUP BY u.user_id, u.display_name ORDER BY total_score DESC, u.user_id LIMIT 5
```

| display_name | total_score |
|---|---|
| Gordon Linoff | 1062 |
| jezrael | 994 |
| jcalz | 674 |
| CertainPerformance | 647 |
| GMB | 589 |

## T09 (test, join): What is the average number of comments on javascript questions, counting questions with no comments?

**reference** (1 rows, 0.2s)
```sql
SELECT AVG(cnt) AS avg_comments FROM (SELECT q.post_id, (SELECT COUNT(*) FROM comments c WHERE c.post_id = q.post_id) AS cnt FROM posts_questions q WHERE q.post_id IN (SELECT pt.post_id FROM post_tags pt JOIN tags t ON t.tag_id = pt.tag_id WHERE t.tag_name = 'javascript'))
```

| avg_comments |
|---|
| 2.0263 |

## T10 (test, join): Which 10 users have written the most comments?

**reference** (10 rows, 0.3s)
```sql
SELECT u.display_name, COUNT(*) AS n FROM comments c JOIN users u ON u.user_id = c.user_id GROUP BY u.user_id, u.display_name ORDER BY n DESC, u.user_id LIMIT 10
```

| display_name | n |
|---|---|
| Barmar | 2759 |
| Community | 2449 |
| furas | 1273 |
| Gordon Linoff | 1209 |
| Bergi | 1111 |

## T11 (test, join): What are the 5 most common tags on questions with a score of 10 or more?

**reference** (5 rows, 0.8s)
```sql
SELECT t.tag_name, COUNT(*) AS n FROM posts_questions q JOIN post_tags pt ON pt.post_id = q.post_id JOIN tags t ON t.tag_id = pt.tag_id WHERE q.score >= 10 GROUP BY t.tag_id, t.tag_name ORDER BY n DESC, t.tag_name LIMIT 5
```

| tag_name | n |
|---|---|
| python | 111 |
| javascript | 103 |
| reactjs | 98 |
| c++ | 63 |
| typescript | 52 |

## T12 (test, join): Which tag has the highest average question view count, among tags with at least 100 questions?

**reference** (1 rows, 1.9s)
```sql
SELECT t.tag_name, AVG(q.view_count) AS avg_views FROM tags t JOIN post_tags pt ON pt.tag_id = t.tag_id JOIN posts_questions q ON q.post_id = pt.post_id GROUP BY t.tag_id, t.tag_name HAVING COUNT(*) >= 100 ORDER BY avg_views DESC LIMIT 1
```

| tag_name | avg_views |
|---|---|
| create-react-app | 2829.0205 |

## T13 (test, join): How many questions were asked in the same calendar year that the asker's account was created?

**reference** (1 rows, 1.6s)
```sql
SELECT COUNT(*) AS n FROM posts_questions q JOIN users u ON u.user_id = q.user_id WHERE strftime('%Y', q.creation_date) = strftime('%Y', u.creation_date)
```

| n |
|---|
| 56742 |

## T14 (test, join): Which 5 users have the most accepted answers on javascript questions?

**reference** (5 rows, 0.4s)
```sql
SELECT u.display_name, COUNT(*) AS n FROM posts_answers a JOIN users u ON u.user_id = a.user_id WHERE a.is_accepted = 1 AND a.parent_id IN (SELECT pt.post_id FROM post_tags pt JOIN tags t ON t.tag_id = pt.tag_id WHERE t.tag_name = 'javascript') GROUP BY u.user_id, u.display_name ORDER BY n DESC, u.user_id LIMIT 5
```

| display_name | n |
|---|---|
| CertainPerformance | 171 |
| T.J. Crowder | 109 |
| Quentin | 96 |
| Barmar | 88 |
| Nina Scholz | 87 |

## T15 (test, absence): How many users have never asked a question?

**reference** (1 rows, 0.2s)
```sql
SELECT COUNT(*) AS n FROM users u WHERE NOT EXISTS (SELECT 1 FROM posts_questions q WHERE q.user_id = u.user_id)
```

| n |
|---|
| 83069 |

## T16 (test, absence): How many answers have never received a comment?

**reference** (1 rows, 0.1s)
```sql
SELECT COUNT(*) AS n FROM posts_answers a WHERE NOT EXISTS (SELECT 1 FROM comments c WHERE c.post_id = a.post_id)
```

| n |
|---|
| 107588 |

## T17 (test, absence): Which 5 tags have the highest share of questions without an accepted answer, among tags with at least 200 questions?

**reference** (5 rows, 2.1s)
```sql
SELECT t.tag_name, AVG(q.accepted_answer_id IS NULL) AS share_no_accepted FROM tags t JOIN post_tags pt ON pt.tag_id = t.tag_id JOIN posts_questions q ON q.post_id = pt.post_id GROUP BY t.tag_id, t.tag_name HAVING COUNT(*) >= 200 ORDER BY share_no_accepted DESC, t.tag_name LIMIT 5
```

| tag_name | share_no_accepted |
|---|---|
| google-chrome | 0.7875 |
| anaconda | 0.7851 |
| iframe | 0.7736 |
| expo | 0.7665 |
| audio | 0.7659 |

## T18 (test, absence): How many answers were posted by users who have never asked a question?

**reference** (1 rows, 0.1s)
```sql
SELECT COUNT(*) AS n FROM posts_answers a WHERE NOT EXISTS (SELECT 1 FROM posts_questions q WHERE q.user_id = a.user_id)
```

| n |
|---|
| 143985 |

## T19 (test, absence): How many users have a badge count of zero?

**reference** (1 rows, 0.0s)
```sql
SELECT COUNT(*) AS n FROM users WHERE badge_count = 0
```

| n |
|---|
| 11057 |

## T20 (test, date): How many questions were asked in March 2021?

**reference** (1 rows, 0.1s)
```sql
SELECT COUNT(*) AS n FROM posts_questions WHERE strftime('%Y-%m', creation_date) = '2021-03'
```

| n |
|---|
| 5451 |

## T21 (test, date): What was the average time in hours to the first answer for questions asked in 2020 versus 2021?

**reference** (2 rows, 1.1s)
```sql
SELECT strftime('%Y', q.creation_date) AS year, AVG((julianday(fa.first_a) - julianday(q.creation_date)) * 24) AS avg_hours FROM posts_questions q JOIN (SELECT parent_id, MIN(creation_date) AS first_a FROM posts_answers GROUP BY parent_id) fa ON fa.parent_id = q.post_id WHERE strftime('%Y', q.creation_date) IN ('2020', '2021') GROUP BY year ORDER BY year
```

| year | avg_hours |
|---|---|
| 2020 | 248.2326 |
| 2021 | 161.8201 |

## T22 (test, date): What percentage of questions receive an answer within 24 hours?

**reference** (1 rows, 1.1s)
```sql
SELECT 100.0 * SUM(CASE WHEN fa.first_a IS NOT NULL AND (julianday(fa.first_a) - julianday(q.creation_date)) * 24 <= 24 THEN 1 ELSE 0 END) / COUNT(*) AS pct FROM posts_questions q LEFT JOIN (SELECT parent_id, MIN(creation_date) AS first_a FROM posts_answers GROUP BY parent_id) fa ON fa.parent_id = q.post_id
```

| pct |
|---|
| 64.7639 |

*Note: Denominator is all questions; unanswered questions count as not answered within 24 hours. Using answered questions only gives a different number (86.1% vs 64.8%) and is not accepted.*

## T23 (test, date): Which calendar month, across all years combined, has the most questions?

**reference** (1 rows, 0.2s)
```sql
SELECT CASE strftime('%m', creation_date) WHEN '01' THEN 'January' WHEN '02' THEN 'February' WHEN '03' THEN 'March' WHEN '04' THEN 'April' WHEN '05' THEN 'May' WHEN '06' THEN 'June' WHEN '07' THEN 'July' WHEN '08' THEN 'August' WHEN '09' THEN 'September' WHEN '10' THEN 'October' WHEN '11' THEN 'November' ELSE 'December' END AS month_name, COUNT(*) AS n FROM posts_questions GROUP BY strftime('%m', creation_date) ORDER BY n DESC, strftime('%m', creation_date) LIMIT 1
```

| month_name | n |
|---|---|
| April | 17100 |

*Note: Data covers Jan 2020 to Sep 2022, so Jan-Sep appear three times and Oct-Dec twice. Answer is a month name; a model returning the month number (04) is graded as equivalent.*

## T24 (test, date): How many users joined in each year?

**reference** (15 rows, 0.2s)
```sql
SELECT strftime('%Y', creation_date) AS year, COUNT(*) AS n FROM users GROUP BY year ORDER BY year
```

| year | n |
|---|---|
| 2008 | 991 |
| 2009 | 2679 |
| 2010 | 4116 |
| 2011 | 6999 |
| 2012 | 9959 |

*Note: Users loaded are authors of sampled posts, so account years go back before 2020.*

## T25 (test, date): How many questions were asked on weekends?

**reference** (1 rows, 0.1s)
```sql
SELECT COUNT(*) AS n FROM posts_questions WHERE strftime('%w', creation_date) IN ('0', '6')
```

| n |
|---|
| 34779 |

*Note: Dates are UTC as stored.*

## T26 (test, rate): What was the answer acceptance rate for answers posted in 2021?

**reference** (1 rows, 0.3s)
```sql
SELECT AVG(is_accepted) AS acceptance_rate FROM posts_answers WHERE strftime('%Y', creation_date) = '2021'
```

| acceptance_rate |
|---|
| 0.3843 |

*Note: Fraction; a percentage (x100) is treated as equivalent.*

## T27 (test, rate): What percentage of answers have a higher score than the question they answer?

**reference** (1 rows, 0.6s)
```sql
SELECT 100.0 * AVG(a.score > q.score) AS pct FROM posts_answers a JOIN posts_questions q ON q.post_id = a.parent_id
```

| pct |
|---|
| 41.0025 |

## T28 (test, rate): What is the average score of the first answer to each question compared with later answers?

**reference** (2 rows, 1.0s)
```sql
WITH r AS (SELECT a.score, ROW_NUMBER() OVER (PARTITION BY a.parent_id ORDER BY a.creation_date, a.post_id) AS rn FROM posts_answers a) SELECT CASE WHEN rn = 1 THEN 'first' ELSE 'later' END AS kind, AVG(score) AS avg_score FROM r GROUP BY kind ORDER BY kind
```

| kind | avg_score |
|---|---|
| first | 0.9978 |
| later | 0.9874 |

## T29 (test, rate): What fraction of python questions have an accepted answer?

**reference** (1 rows, 0.2s)
```sql
SELECT AVG(q.accepted_answer_id IS NOT NULL) AS fraction FROM posts_questions q WHERE q.post_id IN (SELECT pt.post_id FROM post_tags pt JOIN tags t ON t.tag_id = pt.tag_id WHERE t.tag_name = 'python')
```

| fraction |
|---|
| 0.4299 |

## T30 (test, rate): Among users with at least 10 answers, what is the average of each user's acceptance rate?

**reference** (1 rows, 1.8s)
```sql
SELECT AVG(rate) AS avg_rate FROM (SELECT AVG(is_accepted) AS rate FROM posts_answers GROUP BY user_id HAVING COUNT(*) >= 10)
```

| avg_rate |
|---|
| 0.466 |

*Note: Unweighted average of per-user rates.*

## T31 (test, rate): What share of all votes are downvotes?

**reference** (1 rows, 0.1s)
```sql
SELECT 100.0 * SUM(vote_type = 'DownMod') / COUNT(*) AS pct FROM votes
```

| pct |
|---|
| 11.0588 |

**alt 1** (1 rows, 0.2s)
```sql
SELECT 100.0 * SUM(vote_type = 'DownMod') / SUM(vote_type IN ('UpMod', 'DownMod')) AS pct FROM votes
```

| pct |
|---|
| 14.3801 |

*Note: Primary: share of all votes. Also accepted: share of up+down votes.*

## T32 (test, window): Which user wrote the most answers in each year?

**reference** (3 rows, 0.9s)
```sql
WITH c AS (SELECT strftime('%Y', creation_date) AS yr, user_id, COUNT(*) AS n FROM posts_answers GROUP BY yr, user_id), r AS (SELECT yr, user_id, n, ROW_NUMBER() OVER (PARTITION BY yr ORDER BY n DESC, user_id) AS rk FROM c) SELECT r.yr, u.display_name, r.n FROM r JOIN users u ON u.user_id = r.user_id WHERE r.rk = 1 ORDER BY r.yr
```

| yr | display_name | n |
|---|---|---|
| 2020 | Gordon Linoff | 764 |
| 2021 | Gordon Linoff | 531 |
| 2022 | mozway | 295 |

## T33 (test, window): For each of the 5 tags with the most questions, which month had the most questions?

**reference** (5 rows, 8.6s)
```sql
WITH c AS (SELECT pt.tag_id, strftime('%Y-%m', q.creation_date) AS month, COUNT(*) AS n FROM post_tags pt JOIN posts_questions q ON q.post_id = pt.post_id GROUP BY pt.tag_id, month), top AS (SELECT tag_id FROM post_tags GROUP BY tag_id ORDER BY COUNT(*) DESC, tag_id LIMIT 5), r AS (SELECT c.tag_id, c.month, c.n, ROW_NUMBER() OVER (PARTITION BY c.tag_id ORDER BY c.n DESC, c.month) AS rk FROM c JOIN top ON top.tag_id = c.tag_id) SELECT t.tag_name, r.month, r.n FROM r JOIN tags t ON t.tag_id = r.tag_id WHERE r.rk = 1 ORDER BY t.tag_name
```

| tag_name | month | n |
|---|---|---|
| c# | 2020-04 | 527 |
| java | 2020-04 | 756 |
| javascript | 2020-04 | 1295 |
| python | 2020-05 | 1778 |
| reactjs | 2022-08 | 547 |

## T34 (test, window): What is the cumulative number of answers posted, month by month?

**reference** (33 rows, 0.2s)
```sql
WITH m AS (SELECT strftime('%Y-%m', creation_date) AS month, COUNT(*) AS n FROM posts_answers GROUP BY month) SELECT month, n, SUM(n) OVER (ORDER BY month) AS running_total FROM m ORDER BY month
```

| month | n | running_total |
|---|---|---|
| 2020-01 | 5840 | 5840 |
| 2020-02 | 5951 | 11791 |
| 2020-03 | 6223 | 18014 |
| 2020-04 | 7611 | 25625 |
| 2020-05 | 7467 | 33092 |

## T35 (test, window): Which 10 questions have the largest gap between their highest and lowest answer score?

**reference** (10 rows, 0.8s)
```sql
SELECT q.post_id, MAX(a.score) - MIN(a.score) AS gap FROM posts_questions q JOIN posts_answers a ON a.parent_id = q.post_id GROUP BY q.post_id ORDER BY gap DESC, q.post_id LIMIT 10
```

| post_id | gap |
|---|---|
| 61023968 | 561 |
| 62059408 | 502 |
| 60234640 | 445 |
| 61339968 | 305 |
| 66993264 | 295 |

## T36 (test, window): Which 3 tags had the largest increase in question count from 2020 to 2021?

**reference** (3 rows, 8.2s)
```sql
WITH y AS (SELECT pt.tag_id, strftime('%Y', q.creation_date) AS yr, COUNT(*) AS n FROM post_tags pt JOIN posts_questions q ON q.post_id = pt.post_id WHERE strftime('%Y', q.creation_date) IN ('2020', '2021') GROUP BY pt.tag_id, yr) SELECT t.tag_name, SUM(CASE WHEN yr = '2021' THEN n ELSE 0 END) - SUM(CASE WHEN yr = '2020' THEN n ELSE 0 END) AS increase FROM y JOIN tags t ON t.tag_id = y.tag_id GROUP BY t.tag_id, t.tag_name ORDER BY increase DESC, t.tag_name LIMIT 3
```

| tag_name | increase |
|---|---|
| next.js | 216 |
| typescript | 120 |
| discord.py | 106 |

## T37 (test, ambiguous): What are the 5 most active tags this year?

**reference** (5 rows, 1.4s)
```sql
SELECT t.tag_name, COUNT(*) AS n FROM posts_questions q JOIN post_tags pt ON pt.post_id = q.post_id JOIN tags t ON t.tag_id = pt.tag_id WHERE strftime('%Y', q.creation_date) = '2022' GROUP BY t.tag_id, t.tag_name ORDER BY n DESC, t.tag_name LIMIT 5
```

| tag_name | n |
|---|---|
| python | 12555 |
| javascript | 8488 |
| reactjs | 4591 |
| java | 4098 |
| c# | 3461 |

*Note: 'This year' must resolve to 2022 (the data's last year), not today's date. 'Active' read as questions.*

## T38 (test, ambiguous): What was the busiest day for questions?

**reference** (1 rows, 0.2s)
```sql
SELECT date(creation_date) AS day, COUNT(*) AS n FROM posts_questions GROUP BY day ORDER BY n DESC, day LIMIT 1
```

| day | n |
|---|---|
| 2020-05-12 | 280 |

**alt 1** (1 rows, 0.2s)
```sql
SELECT strftime('%w', creation_date) AS weekday, COUNT(*) AS n FROM posts_questions GROUP BY weekday ORDER BY n DESC, weekday LIMIT 1
```

| weekday | n |
|---|---|
| 3 | 29143 |

*Note: Ambiguous. Primary: calendar date. Also accepted: day of the week.*

## T39 (test, unanswerable): Which users voted on the most posts?

*Unanswerable.* Voters are anonymized. Expected: no result that names users.

## T40 (test, unanswerable): How many times was each question edited?

*Unanswerable.* No edit history is loaded. Expected: the query fails or returns nothing; fail if it substitutes another column.
