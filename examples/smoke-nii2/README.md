# smoke-nii2

This directory is for a minimal smoke-test case.

Suggested flow:

1. Prepare `INPUT_scf`, `INPUT_nscf`, and `librpa.in` from one consistent workflow chain.
2. Run static checks:
   - `bash ../../scripts/check_consistency.sh .`
3. Decide whether to submit a remote small job.

Constraints:

- Always run in a newly created directory.
- Never overwrite original source-data directories.
