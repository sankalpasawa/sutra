# Fixture — Picture Desk

A labelled test fixture for the pictures the reader draws from a document's words (D459). No live data.

## Users

**Team lead** runs the desk each morning.
"When the day starts, I want the urgent items first, so that nothing waits."

**Support agent** answers what the lead hands over.

## Approach

The desk reads new mail, sorts it and gives the lead one summary.

## Key flows

**Morning summary**

1. The schedule starts the run at 9:00.
2. The desk reads the new mail since the last run.
3. The lead gets one summary, urgent items first.

If the inbox cannot be read: the summary says so and never says "nothing to do".

## Dependencies

| Needed | From | State |
|---|---|---|
| Inbox access | Mail admin | not yet verified |
| Chat account | IT | available |

## Components

- **C1** Mail reader (tool): reads new mail. Covers R1.
- **C2** Sorter (model): sorts each message. Covers R2.
- **C3** Summary writer (code): writes the summary. Covers R3.

## Data flow

1. Mail (read-only) to C1: new messages only.
2. C1 to C2: one message at a time.
3. C2 to C3 to Chat: the sorted items, then the summary.
