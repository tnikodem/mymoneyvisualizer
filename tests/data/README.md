Test data
=========

All data is made up.

`characterization/`
: A synthetic data set (two accounts, Jan 2022 - Aug 2024, taggers incl. an overlapping and an invalid one,
  a one-time tag) and the outputs of the analysis of version 0.1 (incl. the "recurring" work in progress):
  `golden_*.csv/json`. `tests/test_characterization.py` checks that the current code reproduces them.
  The golden files were generated once with the old code and must not be regenerated with the new code.
  Intentional changes of behaviour (bug fixes) are covered by separate tests.

`legacy_v0_1/`
: `config/` is a data directory and `mmv_backup.zip` a "Save Project" backup, both written by version 0.1
  (`git show 284b451`). Used to test the migration to the current format.
