-- registry_state sha256: f26e6b1dc71a2efdd8a87e15dba090af7afe1749ba82d08bdbfcaed00b82cef9

ALTER TABLE ops.dim_fantrax_crosswalk_override DROP CONSTRAINT dim_fantrax_crosswalk_override_chk_ae6113e7;

ALTER TABLE ops.dim_fantrax_crosswalk_override ADD CONSTRAINT dim_fantrax_crosswalk_override_chk_6c176b09 CHECK (origin IN ('csv', 'apply_script', 'form'));
