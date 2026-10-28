"""Independent check of the evaluation set's reference SQL.

Recomputes every answerable question in pandas from the raw CSVs in data/ (no
SQLite involved) and compares the result with the reference query's result from
stackoverflow.db. Run from the repo root: python eval/crosscheck.py
"""
import json
import math
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def load(name, dates=()):
    df = pd.read_csv(D / f"{name}.csv", keep_default_na=False, na_values=[""])
    for c in dates:
        df[c] = pd.to_datetime(df[c], utc=True, format="ISO8601")
    return df


u = load("users", ["creation_date"])
tg = load("tags")
q = load("posts_questions", ["creation_date"])
a = load("posts_answers", ["creation_date"])
c = load("comments", ["creation_date"])
v = load("votes", ["creation_date"])

# tag links, rebuilt from the pipe-delimited tags column
name_to_id = dict(zip(tg.tag_name, tg.tag_id))
pt = (q[["post_id", "tags"]].assign(tag_name=lambda d: d.tags.fillna("").str.split("|"))
      .explode("tag_name"))
pt = pt[pt.tag_name.isin(name_to_id)].assign(tag_id=lambda d: d.tag_name.map(name_to_id))
pt = pt[["post_id", "tag_id"]].drop_duplicates()
tagname = dict(zip(tg.tag_id, tg.tag_name))
uname = dict(zip(u.user_id, u.display_name))

q["yr"] = q.creation_date.dt.strftime("%Y")
q["ym"] = q.creation_date.dt.strftime("%Y-%m")
a["yr"] = a.creation_date.dt.strftime("%Y")
a["ym"] = a.creation_date.dt.strftime("%Y-%m")
first_ans = a.groupby("parent_id").creation_date.min().rename("first_a")
qf = q.merge(first_ans, left_on="post_id", right_index=True, how="left")
qf["hours"] = (qf.first_a - qf.creation_date).dt.total_seconds() / 3600
ptq = pt.merge(q, on="post_id")  # one row per (question, tag)


def tagset(name):
    return set(pt[pt.tag_id == name_to_id[name]].post_id)


def top(df, by, asc, n):
    return df.sort_values(by, ascending=asc, kind="mergesort").head(n)


def rows(df):
    return [tuple(r) for r in df.itertuples(index=False)]


def tag_counts(frame):
    g = frame.groupby("tag_id").size().rename("n").reset_index()
    g["tag_name"] = g.tag_id.map(tagname)
    return g


R = {}  # id -> list of acceptable pandas results (each a list of tuples)


def scalar(x):
    return [(x,)]


R["D01"] = [scalar(len(q))]
R["D02"] = [scalar(u.reputation.mean())]
R["D03"] = [scalar(a.user_id.nunique())]
cq = c.merge(pt, on="post_id")
R["D04"] = [rows(top(tag_counts(cq), ["n", "tag_name"], [False, True], 10)[["tag_name", "n"]])]
big = set(u[u.reputation > 10000].user_id)
R["D05"] = [rows(top(tag_counts(ptq[ptq.user_id.isin(big)]), ["n", "tag_name"], [False, True], 10)[["tag_name", "n"]])]
R["D06"] = [scalar(int((q.answer_count == 0).sum()))]
R["D07"] = [scalar(len((set(q.user_id) - set(a.user_id)) & set(u.user_id)))]
fq = q.groupby("user_id").creation_date.min().rename("first_q")
m = u.merge(fq, left_on="user_id", right_index=True)
R["D08"] = [scalar(((m.first_q - m.creation_date).dt.total_seconds() / 86400).mean())]
R["D09"] = [scalar(qf[qf.post_id.isin(tagset("python"))].hours.mean())]
mo = a[a.yr == "2021"].groupby("ym").size().rename("n").reset_index()
t1 = top(mo, ["n", "ym"], [False, True], 1)
R["D10"] = [rows(t1[["ym", "n"]])]
R["D11"] = [rows(a.groupby("is_accepted").score.mean().reset_index())]
R["D12"] = [scalar(100.0 * a[a.score > 10].parent_id.nunique() / len(q))]
R["D13"] = [rows(q.assign(f=q.accepted_answer_id.notna()).groupby("yr").f.mean().reset_index())]
top5 = top(pt.groupby("tag_id").size().rename("n").reset_index(), ["n", "tag_id"], [False, True], 5).tag_id
ans_by_tag = pt[pt.tag_id.isin(top5)].merge(a, left_on="post_id", right_on="parent_id", suffixes=("_q", ""))
best = top(ans_by_tag, ["score", "post_id"], [False, True], len(ans_by_tag)).groupby("tag_id").head(1)
best = best.assign(tag_name=best.tag_id.map(tagname))[["tag_name", "post_id", "score"]]
R["D14"] = [rows(top(best, ["score"], [False], 5))]
mq = q[q.yr == "2021"].groupby("ym").size().rename("n").reset_index()
mq["running_total"] = mq.n.cumsum()
R["D15"] = [rows(mq.sort_values("ym"))]
yt = ptq.groupby(["yr", "tag_id"]).size().rename("n").reset_index()
win = yt[yt.n == yt.groupby("yr").n.transform("max")]
R["D16"] = [rows(win.assign(t=win.tag_id.map(tagname)).sort_values(["yr", "t"])[["yr", "t", "n"]])]
both = pd.concat([q.user_id, a.user_id]).value_counts().rename("total").reset_index()
both.columns = ["user_id", "total"]
t = top(both, ["total", "user_id"], [False, True], 1)
r_both = [(uname[t.user_id.iloc[0]], t.total.iloc[0])]
ta = top(a.user_id.value_counts().rename("n").reset_index().set_axis(["user_id", "n"], axis=1), ["n", "user_id"], [False, True], 1)
tq = top(q.user_id.value_counts().rename("n").reset_index().set_axis(["user_id", "n"], axis=1), ["n", "user_id"], [False, True], 1)
R["D17"] = [r_both, [(uname[ta.user_id.iloc[0]], ta.n.iloc[0])]]
tc = top(tag_counts(pt), ["n", "tag_name"], [False, True], 1)
tv = ptq.groupby("tag_id").view_count.sum().rename("v").reset_index()
tv["tag_name"] = tv.tag_id.map(tagname)
tvt = top(tv, ["v", "tag_name"], [False, True], 1)
R["D18"] = [rows(tc[["tag_name", "n"]]), rows(tvt[["tag_name", "v"]])]

# ---- test split
R["T01"] = [scalar(int((u.reputation > 100000).sum()))]
R["T02"] = [scalar(q.view_count.mean())]
R["T03"] = [scalar(int((a.score < 0).sum()))]
R["T04"] = [scalar(len(c))]
R["T05"] = [scalar(pt.tag_id.nunique())]
R["T06"] = [scalar(q.score.max())]
R["T07"] = [rows(top(tag_counts(ptq[ptq.accepted_answer_id.notna()]), ["n", "tag_name"], [False, True], 10)[["tag_name", "n"]])]
s = a.groupby("user_id").score.sum().rename("total").reset_index()
s = top(s, ["total", "user_id"], [False, True], 5)
R["T08"] = [[(uname[r.user_id], r.total) for r in s.itertuples()]]
cnt = c.groupby("post_id").size()
js = sorted(tagset("javascript"))
R["T09"] = [scalar(cnt.reindex(js).fillna(0).mean())]
cc = c.groupby("user_id").size().rename("n").reset_index()
cc = top(cc, ["n", "user_id"], [False, True], 10)
R["T10"] = [[(uname[r.user_id], r.n) for r in cc.itertuples()]]
R["T11"] = [rows(top(tag_counts(ptq[ptq.score >= 10]), ["n", "tag_name"], [False, True], 5)[["tag_name", "n"]])]
av = ptq.groupby("tag_id").agg(avg_views=("view_count", "mean"), n=("post_id", "size")).reset_index()
av = av[av.n >= 100].assign(tag_name=lambda d: d.tag_id.map(tagname))
R["T12"] = [rows(top(av, ["avg_views"], [False], 1)[["tag_name", "avg_views"]])]
qu = q.merge(u[["user_id", "creation_date"]], on="user_id", suffixes=("", "_u"))
R["T13"] = [scalar(int((qu.creation_date.dt.year == qu.creation_date_u.dt.year).sum()))]
acc = a[(a.is_accepted == 1) & a.parent_id.isin(tagset("javascript"))]
ac = top(acc.groupby("user_id").size().rename("n").reset_index(), ["n", "user_id"], [False, True], 5)
R["T14"] = [[(uname[r.user_id], r.n) for r in ac.itertuples()]]
R["T15"] = [scalar(len(set(u.user_id) - set(q.user_id)))]
R["T16"] = [scalar(int((~a.post_id.isin(set(c.post_id))).sum()))]
sh = ptq.assign(no=ptq.accepted_answer_id.isna()).groupby("tag_id").agg(share=("no", "mean"), n=("post_id", "size")).reset_index()
sh = sh[sh.n >= 200].assign(tag_name=lambda d: d.tag_id.map(tagname))
R["T17"] = [rows(top(sh, ["share", "tag_name"], [False, True], 5)[["tag_name", "share"]])]
R["T18"] = [scalar(int((~a.user_id.isin(set(q.user_id))).sum()))]
R["T19"] = [scalar(int((u.badge_count == 0).sum()))]
R["T20"] = [scalar(int((q.ym == "2021-03").sum()))]
yy = qf[qf.yr.isin(["2020", "2021"])].groupby("yr").hours.mean().reset_index()
R["T21"] = [rows(yy)]
within = (qf.hours <= 24).sum()
R["T22"] = [scalar(100.0 * within / len(q))]
mm = q.creation_date.dt.month.value_counts().rename("n").reset_index().set_axis(["month", "n"], axis=1)
mm = top(mm, ["n", "month"], [False, True], 1)
R["T23"] = [[(MONTHS[int(mm.month.iloc[0]) - 1], int(mm.n.iloc[0]))]]
R["T24"] = [rows(u.assign(yr=u.creation_date.dt.strftime("%Y")).groupby("yr").size().rename("n").reset_index())]
R["T25"] = [scalar(int((q.creation_date.dt.dayofweek >= 5).sum()))]
R["T26"] = [scalar(a[a.yr == "2021"].is_accepted.mean())]
aq = a.merge(q[["post_id", "score"]], left_on="parent_id", right_on="post_id", suffixes=("", "_q"))
R["T27"] = [scalar(100.0 * (aq.score > aq.score_q).mean())]
aa = a.sort_values(["parent_id", "creation_date", "post_id"], kind="mergesort")
aa["rn"] = aa.groupby("parent_id").cumcount()
aa["kind"] = aa.rn.map(lambda x: "first" if x == 0 else "later")
R["T28"] = [rows(aa.groupby("kind").score.mean().reset_index())]
R["T29"] = [scalar(q[q.post_id.isin(tagset("python"))].accepted_answer_id.notna().mean())]
pu = a.groupby("user_id").agg(rate=("is_accepted", "mean"), n=("post_id", "size"))
R["T30"] = [scalar(pu[pu.n >= 10].rate.mean())]
down = (v.vote_type == "DownMod").sum()
R["T31"] = [scalar(100.0 * down / len(v)), scalar(100.0 * down / v.vote_type.isin(["UpMod", "DownMod"]).sum())]
ay = a.groupby(["yr", "user_id"]).size().rename("n").reset_index()
ay = ay.sort_values(["yr", "n", "user_id"], ascending=[True, False, True], kind="mergesort").groupby("yr").head(1)
R["T32"] = [[(r.yr, uname[r.user_id], r.n) for r in ay.itertuples()]]
tm = ptq.groupby(["tag_id", "ym"]).size().rename("n").reset_index()
tm = tm[tm.tag_id.isin(top5)].sort_values(["tag_id", "n", "ym"], ascending=[True, False, True], kind="mergesort").groupby("tag_id").head(1)
tm = tm.assign(tag_name=tm.tag_id.map(tagname)).sort_values("tag_name")
R["T33"] = [rows(tm[["tag_name", "ym", "n"]])]
cm = a.groupby("ym").size().rename("n").reset_index()
cm["running_total"] = cm.n.cumsum()
R["T34"] = [rows(cm.sort_values("ym"))]
gp = a.groupby("parent_id").score.agg(lambda s: s.max() - s.min()).rename("gap").reset_index()
R["T35"] = [rows(top(gp, ["gap", "parent_id"], [False, True], 10))]
ty = ptq[ptq.yr.isin(["2020", "2021"])].groupby(["tag_id", "yr"]).size().unstack(fill_value=0)
ty["inc"] = ty.get("2021", 0) - ty.get("2020", 0)
ty = ty.reset_index().assign(tag_name=lambda d: d.tag_id.map(tagname))
R["T36"] = [rows(top(ty, ["inc", "tag_name"], [False, True], 3)[["tag_name", "inc"]])]
R["T37"] = [rows(top(tag_counts(ptq[ptq.yr == "2022"]), ["n", "tag_name"], [False, True], 5)[["tag_name", "n"]])]
bd = q.creation_date.dt.strftime("%Y-%m-%d").value_counts().rename("n").reset_index().set_axis(["day", "n"], axis=1)
bd = top(bd, ["n", "day"], [False, True], 1)
wd = q.creation_date.dt.strftime("%w").value_counts().rename("n").reset_index().set_axis(["wd", "n"], axis=1)
wd = top(wd, ["n", "wd"], [False, True], 1)
R["T38"] = [rows(bd), rows(wd)]


def same(x, y):
    if isinstance(x, (int, float)) and isinstance(y, (int, float)) and not isinstance(x, bool):
        return math.isclose(float(x), float(y), rel_tol=1e-6, abs_tol=1e-9)
    return str(x) == str(y)


def table_equal(p, s, ordered=True):
    if len(p) != len(s):
        return False
    if not ordered:
        key = lambda r: tuple(str(round(x, 6)) if isinstance(x, float) else str(x) for x in r)
        p, s = sorted(p, key=key), sorted(s, key=key)
    return all(len(x) == len(y) and all(same(i, j) for i, j in zip(x, y)) for x, y in zip(p, s))


def main():
    conn = sqlite3.connect(f"file:{(ROOT / 'stackoverflow.db').as_posix()}?mode=ro", uri=True)
    db_pt = conn.execute("SELECT COUNT(*) FROM post_tags").fetchone()[0]
    print(f"post_tags rebuilt from CSV: {len(pt):,}; in database: {db_pt:,}; match: {len(pt) == db_pt}")
    qs = [x for x in json.load(open(ROOT / "eval" / "questions.json")) if x["reference_sql"]]
    bad = 0
    for item in qs:
        sql_variants = [item["reference_sql"]] + item["alt_sqls"]
        sql_results = [conn.execute(s).fetchall() for s in sql_variants]
        pd_results = R.get(item["id"])
        if pd_results is None:
            print(f"{item['id']}: NO PANDAS VERSION")
            bad += 1
            continue
        status = []
        for i, s in enumerate(sql_results):
            ok = any(table_equal(p, s) for p in pd_results)
            ok_unordered = any(table_equal(p, s, ordered=False) for p in pd_results)
            status.append("match" if ok else ("order only" if ok_unordered else "MISMATCH"))
        label = "ok" if status[0] == "match" and all(x != "MISMATCH" for x in status) else "CHECK"
        if label == "CHECK":
            bad += 1
            print(f"{item['id']}: {status}")
            print("   sql   :", sql_results[0][:4])
            print("   pandas:", pd_results[0][:4])
    print(f"\n{len(qs) - bad} of {len(qs)} reference queries agree with the independent pandas result")


if __name__ == "__main__":
    main()
