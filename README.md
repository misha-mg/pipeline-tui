# pipeline-tui

A terminal dashboard for an agent ticket pipeline that runs tickets in batches on a server: what
the batch is doing now, how the runs went, the server's health, and every run's reports. Built
with [Textual](https://textual.textualize.io/). It only reads; it never starts, stops or changes a
run.

## Run

Needs [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/misha-mg/pipeline-tui && cd pipeline-tui
uv run pipeline-tui /path/to/webui/.pipeline-runs
```

Keys: `a` all runs · `Enter` open · `Esc` back · `r` reload · `q` quit. Screens reload every 5 s.
In all runs, `f` steps the filter through the outcomes and `/` searches tickets and summaries;
`Esc` clears the search, then the filter.

## Screens

- **Home** — the current batch with its progress, statistics for the last day, week and all time
  (outcomes, review and app-test quality, runs per day), the server's disk, worktrees and device
  mock, and the runs that need a look.
- **All runs** — every run grouped by day: ticket summary, start, duration, verdict, PR.
- **A run** — its `state.md` and each stage's report.

## What it reads

- `.pipeline-runs/<TICKET>/run-<N>/` — `00-assignment.md` (its `- Summary:` line names the
  ticket), `<NN>-<stage>.md`, `state.md`
- `.pipeline-runs/batch-*/summary.tsv` and the tmux session `pipeline`
- `.claude/worktrees/` next to `.pipeline-runs`, and the mock at `https://127.0.0.1:8888`

## Develop

```bash
uv run pytest
```
