"""Build eval/questions.json (the evaluation set) and eval/REVIEW.md (a review sheet).

Every reference query is executed against stackoverflow.db so the review sheet
shows real results. Run from the repo root: python eval/build_eval_set.py
"""
import json
import re
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "stackoverflow.db"

# Shared fragments
PY_QS = "(SELECT pt.post_id FROM post_tags pt JOIN tags t ON t.tag_id = pt.tag_id WHERE t.tag_name = '{tag}')"
FIRST_ANS = "(SELECT parent_id, MIN(creation_date) AS first_a FROM posts_answers GROUP BY parent_id)"

# (id, split, category, question, reference_sql, alt_sqls, notes)
# category: aggregation, join, absence, date, rate, window, ambiguous, unanswerable
Q = []


def add(id_, split, cat, question, sql, alts=(), notes=""):
    Q.append(dict(id=id_, split=split, category=cat, question=question,
                  reference_sql=sql, alt_sqls=list(alts), notes=notes))


# ---------------------------------------------------------------- DEV (20)
add("D01", "dev", "aggregation", "How many questions were asked in total?",
    "SELECT COUNT(*) AS n FROM posts_questions")
add("D02", "dev", "aggregation", "What is the average reputation of users?",
    "SELECT AVG(reputation) AS avg_reputation FROM users")
add("D03", "dev", "aggregation", "How many distinct users have posted at least one answer?",
    "SELECT COUNT(DISTINCT user_id) AS n FROM posts_answers")
add("D04", "dev", "join", "Which 10 tags have the most comments on their questions?",
    "SELECT t.tag_name, COUNT(c.comment_id) AS comment_count FROM tags t "
    "JOIN post_tags pt ON pt.tag_id = t.tag_id JOIN comments c ON c.post_id = pt.post_id "
    "GROUP BY t.tag_id, t.tag_name ORDER BY comment_count DESC, t.tag_name LIMIT 10",
    notes="Counts comments on the question itself, not on its answers.")
add("D05", "dev", "join", "What are the 10 most common tags on questions asked by users with reputation over 10,000?",
    "SELECT t.tag_name, COUNT(*) AS n FROM posts_questions q JOIN users u ON u.user_id = q.user_id "
    "JOIN post_tags pt ON pt.post_id = q.post_id JOIN tags t ON t.tag_id = pt.tag_id "
    "WHERE u.reputation > 10000 GROUP BY t.tag_id, t.tag_name ORDER BY n DESC, t.tag_name LIMIT 10")
add("D06", "dev", "absence", "How many questions have received no answers at all?",
    "SELECT COUNT(*) AS n FROM posts_questions WHERE answer_count = 0",
    notes="Uses the question's answer_count field only. Counting questions with no loaded answer rows gives a different "
          "number (43,217 vs 42,669) and is not accepted.")
add("D07", "dev", "absence", "How many users have asked a question but never posted an answer?",
    "SELECT COUNT(*) AS n FROM users u WHERE EXISTS (SELECT 1 FROM posts_questions q WHERE q.user_id = u.user_id) "
    "AND NOT EXISTS (SELECT 1 FROM posts_answers a WHERE a.user_id = u.user_id)")
add("D08", "dev", "date", "On average, how many days pass between a user creating their account and asking their first question?",
    "SELECT AVG(julianday(fq.first_q) - julianday(u.creation_date)) AS avg_days FROM users u "
    "JOIN (SELECT user_id, MIN(creation_date) AS first_q FROM posts_questions GROUP BY user_id) fq "
    "ON fq.user_id = u.user_id")
add("D09", "dev", "date", "What is the average number of hours until the first answer for questions tagged python?",
    "SELECT AVG((julianday(fa.first_a) - julianday(q.creation_date)) * 24) AS avg_hours FROM posts_questions q "
    f"JOIN {FIRST_ANS} fa ON fa.parent_id = q.post_id WHERE q.post_id IN {PY_QS.format(tag='python')}")
add("D10", "dev", "date", "Which month of 2021 had the most answers posted?",
    "SELECT strftime('%Y-%m', creation_date) AS month, COUNT(*) AS n FROM posts_answers "
    "WHERE strftime('%Y', creation_date) = '2021' GROUP BY month ORDER BY n DESC, month LIMIT 1")
add("D11", "dev", "rate", "What is the average answer score for accepted answers compared with answers that were not accepted?",
    "SELECT is_accepted, AVG(score) AS avg_score FROM posts_answers GROUP BY is_accepted ORDER BY is_accepted")
add("D12", "dev", "rate", "What percentage of questions have at least one answer with a score above 10?",
    "SELECT 100.0 * COUNT(DISTINCT a.parent_id) / (SELECT COUNT(*) FROM posts_questions) AS pct "
    "FROM posts_answers a WHERE a.score > 10",
    notes="Denominator is all questions.")
add("D13", "dev", "rate", "For each year, what fraction of questions got an accepted answer?",
    "SELECT strftime('%Y', creation_date) AS year, AVG(accepted_answer_id IS NOT NULL) AS fraction "
    "FROM posts_questions GROUP BY year ORDER BY year")
add("D14", "dev", "window", "For each of the 5 tags with the most questions, what is the highest-scoring answer?",
    "WITH top_tags AS (SELECT tag_id, COUNT(*) AS n FROM post_tags GROUP BY tag_id ORDER BY n DESC, tag_id LIMIT 5), "
    "ranked AS (SELECT tt.tag_id, a.post_id, a.score, ROW_NUMBER() OVER (PARTITION BY tt.tag_id "
    "ORDER BY a.score DESC, a.post_id) AS rn FROM top_tags tt JOIN post_tags pt ON pt.tag_id = tt.tag_id "
    "JOIN posts_answers a ON a.parent_id = pt.post_id) "
    "SELECT t.tag_name, r.post_id, r.score FROM ranked r JOIN tags t ON t.tag_id = r.tag_id WHERE r.rn = 1 "
    "ORDER BY r.score DESC")
add("D15", "dev", "window", "What is the running total of questions asked per month during 2021?",
    "WITH m AS (SELECT strftime('%Y-%m', creation_date) AS month, COUNT(*) AS n FROM posts_questions "
    "WHERE strftime('%Y', creation_date) = '2021' GROUP BY month) "
    "SELECT month, n, SUM(n) OVER (ORDER BY month) AS running_total FROM m ORDER BY month")
add("D16", "dev", "window", "What was the most popular tag in each year?",
    "WITH c AS (SELECT strftime('%Y', q.creation_date) AS yr, pt.tag_id, COUNT(*) AS n FROM posts_questions q "
    "JOIN post_tags pt ON pt.post_id = q.post_id GROUP BY yr, pt.tag_id), "
    "r AS (SELECT yr, tag_id, n, RANK() OVER (PARTITION BY yr ORDER BY n DESC) AS rk FROM c) "
    "SELECT r.yr, t.tag_name, r.n FROM r JOIN tags t ON t.tag_id = r.tag_id WHERE r.rk = 1 ORDER BY r.yr",
    notes="'Popular' read as number of questions.")
add("D17", "dev", "ambiguous", "Who is the most active user?",
    "SELECT u.display_name, x.total FROM (SELECT user_id, SUM(n) AS total FROM "
    "(SELECT user_id, COUNT(*) AS n FROM posts_questions GROUP BY user_id UNION ALL "
    "SELECT user_id, COUNT(*) FROM posts_answers GROUP BY user_id) GROUP BY user_id "
    "ORDER BY total DESC, user_id LIMIT 1) x JOIN users u ON u.user_id = x.user_id",
    alts=["SELECT u.display_name, COUNT(*) AS n FROM posts_answers a JOIN users u ON u.user_id = a.user_id "
          "GROUP BY u.user_id, u.display_name ORDER BY n DESC, u.user_id LIMIT 1",
          "SELECT u.display_name, x.total FROM (SELECT user_id, SUM(n) AS total FROM "
          "(SELECT user_id, COUNT(*) AS n FROM posts_questions GROUP BY user_id UNION ALL "
          "SELECT user_id, COUNT(*) FROM posts_answers GROUP BY user_id UNION ALL "
          "SELECT user_id, COUNT(*) FROM comments GROUP BY user_id) GROUP BY user_id "
          "ORDER BY total DESC, user_id LIMIT 1) x JOIN users u ON u.user_id = x.user_id"],
    notes="Ambiguous. Primary: questions + answers. Also accepted: answers only; questions + answers + comments. "
          "Questions only is not accepted.")
add("D18", "dev", "ambiguous", "What is the most popular tag?",
    "SELECT t.tag_name, COUNT(*) AS n FROM post_tags pt JOIN tags t ON t.tag_id = pt.tag_id "
    "GROUP BY t.tag_id, t.tag_name ORDER BY n DESC, t.tag_name LIMIT 1",
    alts=["SELECT t.tag_name, SUM(q.view_count) AS views FROM post_tags pt JOIN tags t ON t.tag_id = pt.tag_id "
          "JOIN posts_questions q ON q.post_id = pt.post_id GROUP BY t.tag_id, t.tag_name "
          "ORDER BY views DESC, t.tag_name LIMIT 1"],
    notes="Ambiguous. Primary: most questions. Also accepted: most total views.")
add("D19", "dev", "unanswerable", "Which user cast the most upvotes?", None,
    notes="Voters are anonymized: votes.user_id is always NULL. Expected: no result that names users.")
add("D20", "dev", "unanswerable", "What is the average salary of the users?", None,
    notes="No salary data exists. Expected: the query fails or returns nothing; fail if it substitutes another column.")

# --------------------------------------------------------------- TEST (40)
add("T01", "test", "aggregation", "How many users have a reputation above 100,000?",
    "SELECT COUNT(*) AS n FROM users WHERE reputation > 100000")
add("T02", "test", "aggregation", "What is the average view count of a question?",
    "SELECT AVG(view_count) AS avg_views FROM posts_questions")
add("T03", "test", "aggregation", "How many answers have a negative score?",
    "SELECT COUNT(*) AS n FROM posts_answers WHERE score < 0")
add("T04", "test", "aggregation", "What is the total number of comments posted?",
    "SELECT COUNT(*) AS n FROM comments")
add("T05", "test", "aggregation", "How many distinct tags have been used?",
    "SELECT COUNT(DISTINCT tag_id) AS n FROM post_tags",
    notes="'Used' means attached to at least one question. The tags table lists 63,653 tags, "
          "so counting rows in it instead is wrong.")
add("T06", "test", "aggregation", "What is the highest score any question has received?",
    "SELECT MAX(score) AS max_score FROM posts_questions")
add("T07", "test", "join", "What are the 10 most frequently used tags on questions that have an accepted answer?",
    "SELECT t.tag_name, COUNT(*) AS n FROM posts_questions q JOIN post_tags pt ON pt.post_id = q.post_id "
    "JOIN tags t ON t.tag_id = pt.tag_id WHERE q.accepted_answer_id IS NOT NULL "
    "GROUP BY t.tag_id, t.tag_name ORDER BY n DESC, t.tag_name LIMIT 10")
add("T08", "test", "join", "Which 5 users have the highest total score across all their answers?",
    "SELECT u.display_name, SUM(a.score) AS total_score FROM posts_answers a JOIN users u ON u.user_id = a.user_id "
    "GROUP BY u.user_id, u.display_name ORDER BY total_score DESC, u.user_id LIMIT 5")
add("T09", "test", "join", "What is the average number of comments on javascript questions, counting questions with no comments?",
    "SELECT AVG(cnt) AS avg_comments FROM (SELECT q.post_id, (SELECT COUNT(*) FROM comments c WHERE c.post_id = q.post_id) AS cnt "
    f"FROM posts_questions q WHERE q.post_id IN {PY_QS.format(tag='javascript')})")
add("T10", "test", "join", "Which 10 users have written the most comments?",
    "SELECT u.display_name, COUNT(*) AS n FROM comments c JOIN users u ON u.user_id = c.user_id "
    "GROUP BY u.user_id, u.display_name ORDER BY n DESC, u.user_id LIMIT 10")
add("T11", "test", "join", "What are the 5 most common tags on questions with a score of 10 or more?",
    "SELECT t.tag_name, COUNT(*) AS n FROM posts_questions q JOIN post_tags pt ON pt.post_id = q.post_id "
    "JOIN tags t ON t.tag_id = pt.tag_id WHERE q.score >= 10 GROUP BY t.tag_id, t.tag_name "
    "ORDER BY n DESC, t.tag_name LIMIT 5")
add("T12", "test", "join", "Which tag has the highest average question view count, among tags with at least 100 questions?",
    "SELECT t.tag_name, AVG(q.view_count) AS avg_views FROM tags t JOIN post_tags pt ON pt.tag_id = t.tag_id "
    "JOIN posts_questions q ON q.post_id = pt.post_id GROUP BY t.tag_id, t.tag_name HAVING COUNT(*) >= 100 "
    "ORDER BY avg_views DESC LIMIT 1")
add("T13", "test", "join", "How many questions were asked in the same calendar year that the asker's account was created?",
    "SELECT COUNT(*) AS n FROM posts_questions q JOIN users u ON u.user_id = q.user_id "
    "WHERE strftime('%Y', q.creation_date) = strftime('%Y', u.creation_date)")
add("T14", "test", "join", "Which 5 users have the most accepted answers on javascript questions?",
    "SELECT u.display_name, COUNT(*) AS n FROM posts_answers a JOIN users u ON u.user_id = a.user_id "
    f"WHERE a.is_accepted = 1 AND a.parent_id IN {PY_QS.format(tag='javascript')} "
    "GROUP BY u.user_id, u.display_name ORDER BY n DESC, u.user_id LIMIT 5")
add("T15", "test", "absence", "How many users have never asked a question?",
    "SELECT COUNT(*) AS n FROM users u WHERE NOT EXISTS (SELECT 1 FROM posts_questions q WHERE q.user_id = u.user_id)")
add("T16", "test", "absence", "How many answers have never received a comment?",
    "SELECT COUNT(*) AS n FROM posts_answers a WHERE NOT EXISTS (SELECT 1 FROM comments c WHERE c.post_id = a.post_id)")
add("T17", "test", "absence", "Which 5 tags have the highest share of questions without an accepted answer, among tags with at least 200 questions?",
    "SELECT t.tag_name, AVG(q.accepted_answer_id IS NULL) AS share_no_accepted FROM tags t "
    "JOIN post_tags pt ON pt.tag_id = t.tag_id JOIN posts_questions q ON q.post_id = pt.post_id "
    "GROUP BY t.tag_id, t.tag_name HAVING COUNT(*) >= 200 ORDER BY share_no_accepted DESC, t.tag_name LIMIT 5")
add("T18", "test", "absence", "How many answers were posted by users who have never asked a question?",
    "SELECT COUNT(*) AS n FROM posts_answers a WHERE NOT EXISTS (SELECT 1 FROM posts_questions q WHERE q.user_id = a.user_id)")
add("T19", "test", "absence", "How many users have a badge count of zero?",
    "SELECT COUNT(*) AS n FROM users WHERE badge_count = 0")
add("T20", "test", "date", "How many questions were asked in March 2021?",
    "SELECT COUNT(*) AS n FROM posts_questions WHERE strftime('%Y-%m', creation_date) = '2021-03'")
add("T21", "test", "date", "What was the average time in hours to the first answer for questions asked in 2020 versus 2021?",
    "SELECT strftime('%Y', q.creation_date) AS year, AVG((julianday(fa.first_a) - julianday(q.creation_date)) * 24) AS avg_hours "
    f"FROM posts_questions q JOIN {FIRST_ANS} fa ON fa.parent_id = q.post_id "
    "WHERE strftime('%Y', q.creation_date) IN ('2020', '2021') GROUP BY year ORDER BY year")
add("T22", "test", "date", "What percentage of questions receive an answer within 24 hours?",
    "SELECT 100.0 * SUM(CASE WHEN fa.first_a IS NOT NULL AND (julianday(fa.first_a) - julianday(q.creation_date)) * 24 <= 24 "
    f"THEN 1 ELSE 0 END) / COUNT(*) AS pct FROM posts_questions q LEFT JOIN {FIRST_ANS} fa ON fa.parent_id = q.post_id",
    notes="Denominator is all questions; unanswered questions count as not answered within 24 hours. "
          "Using answered questions only gives a different number (86.1% vs 64.8%) and is not accepted.")
add("T23", "test", "date", "Which calendar month, across all years combined, has the most questions?",
    "SELECT CASE strftime('%m', creation_date) WHEN '01' THEN 'January' WHEN '02' THEN 'February' "
    "WHEN '03' THEN 'March' WHEN '04' THEN 'April' WHEN '05' THEN 'May' WHEN '06' THEN 'June' "
    "WHEN '07' THEN 'July' WHEN '08' THEN 'August' WHEN '09' THEN 'September' WHEN '10' THEN 'October' "
    "WHEN '11' THEN 'November' ELSE 'December' END AS month_name, COUNT(*) AS n FROM posts_questions "
    "GROUP BY strftime('%m', creation_date) ORDER BY n DESC, strftime('%m', creation_date) LIMIT 1",
    notes="Data covers Jan 2020 to Sep 2022, so Jan-Sep appear three times and Oct-Dec twice. "
          "Answer is a month name; a model returning the month number (04) is graded as equivalent.")
add("T24", "test", "date", "How many users joined in each year?",
    "SELECT strftime('%Y', creation_date) AS year, COUNT(*) AS n FROM users GROUP BY year ORDER BY year",
    notes="Users loaded are authors of sampled posts, so account years go back before 2020.")
add("T25", "test", "date", "How many questions were asked on weekends?",
    "SELECT COUNT(*) AS n FROM posts_questions WHERE strftime('%w', creation_date) IN ('0', '6')",
    notes="Dates are UTC as stored.")
add("T26", "test", "rate", "What was the answer acceptance rate for answers posted in 2021?",
    "SELECT AVG(is_accepted) AS acceptance_rate FROM posts_answers WHERE strftime('%Y', creation_date) = '2021'",
    notes="Fraction; a percentage (x100) is treated as equivalent.")
add("T27", "test", "rate", "What percentage of answers have a higher score than the question they answer?",
    "SELECT 100.0 * AVG(a.score > q.score) AS pct FROM posts_answers a JOIN posts_questions q ON q.post_id = a.parent_id")
add("T28", "test", "rate", "What is the average score of the first answer to each question compared with later answers?",
    "WITH r AS (SELECT a.score, ROW_NUMBER() OVER (PARTITION BY a.parent_id ORDER BY a.creation_date, a.post_id) AS rn FROM posts_answers a) "
    "SELECT CASE WHEN rn = 1 THEN 'first' ELSE 'later' END AS kind, AVG(score) AS avg_score FROM r GROUP BY kind ORDER BY kind")
add("T29", "test", "rate", "What fraction of python questions have an accepted answer?",
    "SELECT AVG(q.accepted_answer_id IS NOT NULL) AS fraction FROM posts_questions q "
    f"WHERE q.post_id IN {PY_QS.format(tag='python')}")
add("T30", "test", "rate", "Among users with at least 10 answers, what is the average of each user's acceptance rate?",
    "SELECT AVG(rate) AS avg_rate FROM (SELECT AVG(is_accepted) AS rate FROM posts_answers GROUP BY user_id HAVING COUNT(*) >= 10)",
    notes="Unweighted average of per-user rates.")
add("T31", "test", "rate", "What share of all votes are downvotes?",
    "SELECT 100.0 * SUM(vote_type = 'DownMod') / COUNT(*) AS pct FROM votes",
    alts=["SELECT 100.0 * SUM(vote_type = 'DownMod') / SUM(vote_type IN ('UpMod', 'DownMod')) AS pct FROM votes"],
    notes="Primary: share of all votes. Also accepted: share of up+down votes.")
add("T32", "test", "window", "Which user wrote the most answers in each year?",
    "WITH c AS (SELECT strftime('%Y', creation_date) AS yr, user_id, COUNT(*) AS n FROM posts_answers GROUP BY yr, user_id), "
    "r AS (SELECT yr, user_id, n, ROW_NUMBER() OVER (PARTITION BY yr ORDER BY n DESC, user_id) AS rk FROM c) "
    "SELECT r.yr, u.display_name, r.n FROM r JOIN users u ON u.user_id = r.user_id WHERE r.rk = 1 ORDER BY r.yr")
add("T33", "test", "window", "For each of the 5 tags with the most questions, which month had the most questions?",
    "WITH c AS (SELECT pt.tag_id, strftime('%Y-%m', q.creation_date) AS month, COUNT(*) AS n FROM post_tags pt "
    "JOIN posts_questions q ON q.post_id = pt.post_id GROUP BY pt.tag_id, month), "
    "top AS (SELECT tag_id FROM post_tags GROUP BY tag_id ORDER BY COUNT(*) DESC, tag_id LIMIT 5), "
    "r AS (SELECT c.tag_id, c.month, c.n, ROW_NUMBER() OVER (PARTITION BY c.tag_id ORDER BY c.n DESC, c.month) AS rk "
    "FROM c JOIN top ON top.tag_id = c.tag_id) "
    "SELECT t.tag_name, r.month, r.n FROM r JOIN tags t ON t.tag_id = r.tag_id WHERE r.rk = 1 ORDER BY t.tag_name")
add("T34", "test", "window", "What is the cumulative number of answers posted, month by month?",
    "WITH m AS (SELECT strftime('%Y-%m', creation_date) AS month, COUNT(*) AS n FROM posts_answers GROUP BY month) "
    "SELECT month, n, SUM(n) OVER (ORDER BY month) AS running_total FROM m ORDER BY month")
add("T35", "test", "window", "Which 10 questions have the largest gap between their highest and lowest answer score?",
    "SELECT q.post_id, MAX(a.score) - MIN(a.score) AS gap FROM posts_questions q JOIN posts_answers a ON a.parent_id = q.post_id "
    "GROUP BY q.post_id ORDER BY gap DESC, q.post_id LIMIT 10")
add("T36", "test", "window", "Which 3 tags had the largest increase in question count from 2020 to 2021?",
    "WITH y AS (SELECT pt.tag_id, strftime('%Y', q.creation_date) AS yr, COUNT(*) AS n FROM post_tags pt "
    "JOIN posts_questions q ON q.post_id = pt.post_id WHERE strftime('%Y', q.creation_date) IN ('2020', '2021') GROUP BY pt.tag_id, yr) "
    "SELECT t.tag_name, SUM(CASE WHEN yr = '2021' THEN n ELSE 0 END) - SUM(CASE WHEN yr = '2020' THEN n ELSE 0 END) AS increase "
    "FROM y JOIN tags t ON t.tag_id = y.tag_id GROUP BY t.tag_id, t.tag_name ORDER BY increase DESC, t.tag_name LIMIT 3")
add("T37", "test", "ambiguous", "What are the 5 most active tags this year?",
    "SELECT t.tag_name, COUNT(*) AS n FROM posts_questions q JOIN post_tags pt ON pt.post_id = q.post_id "
    "JOIN tags t ON t.tag_id = pt.tag_id WHERE strftime('%Y', q.creation_date) = '2022' "
    "GROUP BY t.tag_id, t.tag_name ORDER BY n DESC, t.tag_name LIMIT 5",
    notes="'This year' must resolve to 2022 (the data's last year), not today's date. 'Active' read as questions.")
add("T38", "test", "ambiguous", "What was the busiest day for questions?",
    "SELECT date(creation_date) AS day, COUNT(*) AS n FROM posts_questions GROUP BY day ORDER BY n DESC, day LIMIT 1",
    alts=["SELECT strftime('%w', creation_date) AS weekday, COUNT(*) AS n FROM posts_questions GROUP BY weekday ORDER BY n DESC, weekday LIMIT 1"],
    notes="Ambiguous. Primary: calendar date. Also accepted: day of the week.")
add("T39", "test", "unanswerable", "Which users voted on the most posts?", None,
    notes="Voters are anonymized. Expected: no result that names users.")
add("T40", "test", "unanswerable", "How many times was each question edited?", None,
    notes="No edit history is loaded. Expected: the query fails or returns nothing; fail if it substitutes another column.")


def tie_at_boundary(conn, sql):
    m = re.search(r"LIMIT (\d+)\s*$", sql)
    ob = re.search(r"ORDER BY (\w+) DESC", sql)
    if not m or not ob:
        return None
    n = int(m.group(1))
    cur = conn.execute(re.sub(r"LIMIT \d+\s*$", f"LIMIT {n + 1}", sql))
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    if ob.group(1) not in cols or len(rows) <= n:
        return None
    i = cols.index(ob.group(1))
    return rows[n - 1][i] == rows[n][i]


def main():
    conn = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    lines = ["# Evaluation set review sheet", "",
             "Approve, edit or reject each reference query. Results are from the real database.", ""]
    problems = []
    for q in Q:
        entry = [f"## {q['id']} ({q['split']}, {q['category']}): {q['question']}", ""]
        if q["reference_sql"] is None:
            entry += [f"*Unanswerable.* {q['notes']}", ""]
            lines += entry
            continue
        for label, sql in [("reference", q["reference_sql"])] + [(f"alt {i+1}", s) for i, s in enumerate(q["alt_sqls"])]:
            t = time.time()
            cur = conn.execute(sql)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            secs = time.time() - t
            q.setdefault("_rows", len(rows)) if label == "reference" else None
            entry += [f"**{label}** ({len(rows)} rows, {secs:.1f}s)", "```sql", sql, "```"]
            shown = rows[:5]
            entry += ["", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
            for r in shown:
                entry.append("| " + " | ".join(str(round(v, 4)) if isinstance(v, float) else str(v) for v in r) + " |")
            entry.append("")
            if label == "reference":
                if len(rows) == 0:
                    problems.append(f"{q['id']}: reference returns no rows")
                if rows and all(v in (0, None) for v in rows[0]):
                    problems.append(f"{q['id']}: reference result is zero/NULL")
                tie = tie_at_boundary(conn, sql)
                if tie:
                    problems.append(f"{q['id']}: TIE at the LIMIT boundary")
                    entry.append("> Tie at the cutoff: scorer must compare metric values, not names.\n")
        if q["notes"]:
            entry += [f"*Note: {q['notes']}*", ""]
        lines += entry
    (ROOT / "eval" / "REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    out = [{k: v for k, v in q.items() if not k.startswith("_")} for q in Q]
    (ROOT / "eval" / "questions.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(len(Q), "questions;", sum(q["split"] == "dev" for q in Q), "dev,", sum(q["split"] == "test" for q in Q), "test")
    print("problems:" if problems else "no problems")
    for p in problems:
        print(" -", p)


if __name__ == "__main__":
    main()
