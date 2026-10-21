# pipeline

Turns a CSV file of transactions into per-group totals.

1. `importer`: reads the CSV; header names are normalized (`"Unit Price"` becomes
   `unit_price`) and cells are trimmed.
2. `validation`: rows missing a required value, or with a numeric column that does not
   parse, are set aside with a `RowError` each.
3. `cleaning`: amounts become floats rounded to the cent and group labels get one
   spelling.
4. `aggregate`: count, total, mean, minimum and maximum per group.
5. `cache`: a folder of JSON files so an unchanged file is not processed twice.
6. `export`: the summaries go to SQLite (in memory by default) or to a CSV file.

`runner.run_pipeline(PipelineConfig(...))` runs steps 1 to 5 for one job;
`runner.export` does step 6.

Run the tests with `python -m pytest`.
