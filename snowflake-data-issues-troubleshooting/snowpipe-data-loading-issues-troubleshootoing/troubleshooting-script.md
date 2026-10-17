# Snowflake Data Loading & Latency Troubleshooting (Snowpipe)

When a business user or an alert reports that a table has missed its SLA and the
table is loaded by Snowpipe, work through the steps below.

## Step 1: Identify the pipe loading the table

-- Real-time (no latency, last 14 days)
select distinct pipe_catalog_name || '.' || pipe_schema_name || '.' || pipe_name as snowpipe_name
from snowflake.account_usage.copy_history
where 
      date(last_load_time)>=current_date()-14 and 
      lower(table_catalog_name)='database_name' and 
      lower(table_schema_name) = 'schema_name' and 
      lower(table_name)='table_name'; 


-- Alternative: search pipe definitions
SELECT pipe_catalog || '.' || pipe_schema || '.' || pipe_name, definition
FROM snowflake.account_usage.pipes
WHERE deleted IS NULL AND definition ILIKE '%<table_name>%';

## Step 2: Check the pipe status

select system$pipe_status('<database_name>.<schema_name>.<pipe_name>');

Key fields: `executionState`, `pendingFileCount`, `lastIngestedTimestamp`,
`lastIngestedFilePath`, `notificationChannelName`, `lastReceivedMessageTimestamp`,
`lastForwardedMessageTimestamp`, `error`.

## Case 1: Pipe is RUNNING but data is late

1. Compare `lastIngestedFilePath` with the files in the external stage (Azure Blob):
   LIST @<stage>;
2. **No new files in storage** → the source isn't delivering. Escalate to the
   source/application team.
3. **New files exist but weren't loaded** → the event notification may have been
   missed. Check `lastReceivedMessageTimestamp` and the Event Grid subscription,
   then backfill:
   ALTER PIPE <db>.<schema>.<pipe> REFRESH;   -- files staged in the last 7 days only
4. **The file was re-sent with the same name** → Snowpipe skips files it loaded in
   the last 14 days. Rename the file or load it with a manual COPY ... FORCE = TRUE.

## Case 2: Pipe is PAUSED or STOPPED

- Find the cause: a manual pause, an ownership transfer, or a dropped stage,
  table or file format (`STOPPED_*` states).
- Fix the underlying issue, then resume:
  ALTER PIPE <database_name>.<schema_name>.<pipe_name> set pipe_execution_paused = FALSE;
- If it was paused for more than 14 days (stale):
  select SYSTEM$PIPE_FORCE_RESUME('<db>.<schema>.<pipe>', 'staleness_check_override');

## Case 3: Some files or records were not ingested

Snowpipe defaults to `ON_ERROR = SKIP_FILE`: a file with errors is skipped and the
rest of the queue keeps loading. If the pipe uses `ON_ERROR = CONTINUE`, bad rows
are skipped and the file shows as *Partially loaded*.

select file_name, stage_location, last_load_time, status,
       row_count, row_parsed, error_count,
       first_error_message, first_error_line_number, first_error_column_name
from snowflake.account_usage.copy_history
where 
      date(last_load_time)>=current_date()-14 and 
      lower(table_catalog_name)='database_name' and 
      lower(table_schema_name) = 'schema_name' and 
      lower(table_name)='table_name' and
      status in ('Load failed', 'Partially loaded')


-- Pipe-level errors, this will not work if snowpipe has any transformations in copy statement of that pipe
select * from table(validate_pipe_load(
       pipe_name => '<database_name>.<schema_name>.<pipe_name>',
       start_time => dateadd(hour, -24, current_timestamp())));

- One-off bad file: correct it and re-stage it under a new name, or load it manually.
- Recurring errors: send the source provider the error details so they fix the
  file at the source.

## Case 4: Invalid or non-UTF-8 characters

alter file format <ff> set replace_invalid_characters = true;  -- replaced with u+fffd (�)
-- or, if the source uses a different encoding:
alter file format <ff> set encoding = 'iso-8859-1';
