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
  datasets now include Stack Overflow Q&A," Google Cloud / Medium, 2017.

## Tools & Libraries

- **Anthropic Claude API** — natural-language-to-SQL generation.
  https://docs.anthropic.com/
- **SQLite** — embedded analytical database.
- **Streamlit** — chat interface.
- **pandas / pyarrow** — data movement and CSV/parquet I/O.

## Attribution note

Per the CC BY-SA 4.0 license, any StackOverflow question/answer/comment text
surfaced in this app's UI is attributable to the original Stack Exchange
contributors and Stack Exchange Inc., not to this project. This tool
displays derived analytics (counts, rankings, aggregates) over that content;
it does not republish original post bodies as standalone content.
