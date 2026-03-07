# smoke-abacus-pyatb-librpa

This example documents the intended stack-level smoke validation shape.

Use it when you already have a real ABACUS/LibRPA case directory and want to validate that the software stack is usable.

## Doctor first

```bash
bash ../../scripts/stack_env_doctor.sh --env-script <your-env.sh> --case-dir <case_dir>
```

## Stack smoke test

```bash
bash ../../scripts/stack_smoke_test.sh \
  --case-dir <case_dir> \
  --env-script <your-env.sh> \
  --abacus-bin <abacus-bin> \
  --librpa-bin <chi0_main.exe>
```

## Interpretation

- `ABACUS` stage validates SCF runtime markers
- `PYATB` stage validates the `ABACUS -> PYATB` interface through `get_diel.py`
- `LibRPA` stage validates runtime on either:
  - the active run directory when it already contains LibRPA-ready inputs, or
  - an exported `input_librpa` bundle in the same case directory

This is a stack smoke path.

Do not describe it as a full end-to-end GW reproduction unless the run truly covers:

- `SCF -> PYATB -> NSCF -> preprocess -> LibRPA`
