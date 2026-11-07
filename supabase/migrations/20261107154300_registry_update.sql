-- registry_state sha256: 8a76ab28afcf4110498094df8f8cf928a04dc8cdf5c0feef42c76e1819445a43

ALTER TABLE ops.etl_run_log ADD COLUMN column_changes jsonb;
