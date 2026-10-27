# weatherlog

Collects readings from a network of weather stations. Stations send JSON
payloads in metric or imperial units; `weatherlog.ingest` converts them to
metric, refuses readings outside the plausible ranges in
`weatherlog.validation` and keeps the rest. `weatherlog.aggregate` builds daily
summaries (minimum, maximum and mean temperature, rain total, strongest wind),
`weatherlog.alerts` runs alert rules such as frost, gale and heavy rain, and
`weatherlog.export` writes CSV files into an export folder that is synced to a
public file share.
