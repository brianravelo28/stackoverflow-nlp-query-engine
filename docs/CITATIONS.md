# Citations & Data Sources

## Data

- **Stack Exchange Data Dump** — the underlying source of all StackOverflow
  content used here (questions, answers, comments, tags, votes, user
  metadata). Licensed under
  [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
  Official archive: https://archive.org/details/stackexchange
- **`bigquery-public-data.stackoverflow`** — Google BigQuery's public mirror
  of the data dump, queried via a Kaggle Notebook (free-tier BigQuery access,
  no local GCP billing setup). Dataset listing:
  https://www.kaggle.com/datasets/stackoverflow/stackoverflow
- Announcement of the BigQuery mirror: Felipe Hoffa, "Google BigQuery public
  datasets now include Stack Overflow Q&A," Google Cloud Community / Medium.

## Tools & Libraries

- **Anthropic Claude API** — natural-language-to-SQL generation.
  https://docs.anthropic.com/
- **SQLite** — embedded analytical database.
- **Streamlit** — chat interface.
- **pandas** — data loading and query results (`pyarrow` is optional, dev only).
- **Render** — hosting; **GitHub Releases** — hosting for the database file.

## License and attribution

- **Code** in this repository is MIT licensed (see `LICENSE`).
- **Data** is Stack Exchange content under CC BY-SA 4.0. The prebuilt database
  published as the `data-v1` release asset contains question titles, post
  bodies (truncated to 500 characters), and comments, so that file is a
  derivative of CC BY-SA content and is shared under the same license, with
  attribution to the Stack Exchange contributors and Stack Exchange Inc. Text
  the app displays (titles, answer excerpts, aggregates) likewise belongs to
  its original authors. User display names are included in the data.
