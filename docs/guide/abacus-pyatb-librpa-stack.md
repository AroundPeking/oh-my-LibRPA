# Fresh Ubuntu/WSL Stack for ABACUS + PYATB + LibRPA

This guide is the project-side reference for bootstrapping a fresh `ABACUS + PYATB + LibRPA` environment that `oh-my-LibRPA` can later drive through natural-language interaction.

It follows the maintained Ubuntu/WSL installation note and keeps the project's current split intact:

- `skills-core/` remains the only source of truth for project skills
- `platform/` remains separate and agent-specific
- stack bootstrap and diagnosis are provided as project assets plus one dedicated core skill

## Supported Reference Profile

Primary reference profile:

- Ubuntu `24.04` on `WSL`
- Intel oneAPI `2025.1+`
- Python venv for `PYATB`
- out-of-source CMake builds

This is a reproducible baseline, not a claim that other profiles are unsupported.

## What This Stack Must Cover

Core programs:

- `ABACUS`
- `LibRPA`
- `PYATB`

Auxiliary dependencies commonly needed in practice:

- Intel oneAPI compiler + MPI + MKL
- `Eigen`
- `ELPA`
- `Libxc`
- Python packages: `pybind11`, `mpi4py`, `numpy`, `scipy`, `matplotlib`
- LibRPA third-party subtree: `LibRI`, `LibComm`, `cereal`

## Build Order

Keep this order unless there is a strong reason not to:

1. system packages
2. oneAPI
3. Python venv
4. LibRPA
5. Eigen
6. PYATB
7. optional custom GCC for ABACUS
8. ELPA
9. Libxc
10. ABACUS
11. environment export script
12. smoke validation

## 1) Base System Packages

```bash
sudo apt update
sudo apt install -y git cmake python3-dev python3-pip python3-venv wget
```

Notes:

- On Ubuntu `23+`, prefer venv over system `pip` because of externally-managed Python rules.
- VS Code usage is optional for this repo; it is not required by the stack itself.

## 2) Intel oneAPI

Reference commands:

```bash
wget -qO- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | sudo gpg --dearmor --output /usr/share/keyrings/oneapi-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" | sudo tee /etc/apt/sources.list.d/oneAPI.list
sudo apt update
sudo apt install -y intel-basekit intel-hpckit
```

Add to shell startup:

```bash
source /opt/intel/oneapi/setvars.sh > /dev/null
```

Compiler rename reminder:

- `icpc -> icpx`
- `ifort -> ifx`
- `mpiicpc -> mpiicpx`
- `mpiifort -> mpiifx`

## 3) Python venv For PYATB

```bash
python3 -m venv ~/.venvs/pyatb
source ~/.venvs/pyatb/bin/activate
pip install --upgrade pip setuptools wheel
pip install pybind11 mpi4py numpy scipy matplotlib
```

If mirror access is needed, switch to a local mirror instead of forcing system Python.

## 4) LibRPA

Reference checkout from the maintained note:

```bash
git clone -b qsgw git@github.com:bhjia-phys/LibRPA.git
cd LibRPA
```

Compiler-related CMake adjustments from the note:

```cmake
set(CMAKE_CXX_COMPILER "mpiicpx" CACHE STRING "" FORCE)
set(CMAKE_Fortran_COMPILER "ifx" CACHE STRING "" FORCE)
```

Update submodules before building:

```bash
cd thirdparty/LibComm
git submodule init
git submodule update --recursive
cd ../../
```

Known source-level fix to remember when this branch still carries it:

- `LibRPA/thirdparty/LibRI/include/RI/physics/RPA.hpp`
- replace `this->period` with `this->lri.period`

Build with the repository's preferred protocol:

```bash
cmake -B build
cmake --build build -j$(nproc)
```

## 5) Eigen For PYATB

Reference flow:

```bash
wget https://gitlab.com/libeigen/eigen/-/archive/3.4.0/eigen-3.4.0.tar.bz2
tar xvf eigen-3.4.0.tar.bz2
cd eigen-3.4.0
cmake -B build -DCMAKE_INSTALL_PREFIX=$HOME/software/eigen-3.4.0
cmake --build build -j$(nproc)
cmake --install build
```

## 6) PYATB

Reference checkout from the maintained note:

```bash
git clone -b enable_head_wing git@github.com:AroundPeking/pyatb.git
cd pyatb
```

`siteconfig.py` should use the LLVM compiler names and real oneAPI/Eigen paths:

```python
compiler = 'icpx'
mkl_include_dir = '/opt/intel/oneapi/mkl/2025.1/include'
mkl_library_dir = '/opt/intel/oneapi/mkl/2025.1/lib'
eigen_include_dir = '/home/<user>/software/eigen-3.4.0/include/eigen3'
```

Also update legacy compiler names inside `setup.py` if present:

- replace `icpc` with `icpx`

Then install in the venv:

```bash
source ~/.venvs/pyatb/bin/activate
pip install .
```

## 7) Optional Custom GCC For ABACUS

Only do this if the target ABACUS build truly requires it.

Important rule from the installation note:

```bash
export CC=
export CXX=
export FC=
export LIBS=
export CFLAGS=
```

Clear oneAPI contamination before configuring GCC.

## 8) ELPA

Use the configured MPI/oneAPI toolchain consistently. The maintained note uses:

- `FC="mpiifx"`
- `CC="mpiicx"`
- MKL-backed ScaLAPACK link flags

After install, ensure the expected include symlink exists so ABACUS can find ELPA headers.

## 9) Libxc

Install with CMake so that `share/cmake/Libxc/*.cmake` is generated:

```bash
cmake -H. -Bobjdir -DCMAKE_C_COMPILER=mpiicx -DCMAKE_INSTALL_PREFIX=$HOME/software/libxc-6.2.2-build
cmake --build objdir -j$(nproc)
cmake --install objdir
```

## 10) ABACUS

Keep ABACUS on out-of-source CMake builds as well.

Typical dependency wiring from the maintained note includes:

- `CEREAL_DIR`
- `CEREAL_INCLUDE_DIR`
- `ELPA_DIR`
- `LIBRI_DIR`
- `LIBCOMM_DIR`
- `Libxc_DIR`

When ELPA / Libxc linkage misses Intel runtime math libraries, add the required compiler runtime libraries explicitly in the CMake logic.

Build/install shape:

```bash
cmake -B build
cmake --build build -j$(nproc)
cmake --install build
```

## 11) Environment Export Script

Create a shell file based on:

- `templates/env/abacus-pyatb-librpa.env.sh.template`

At minimum, expose:

- oneAPI environment
- `ABACUS` bin path
- `LibRPA` bin/lib paths
- `ELPA` / `Libxc` library paths
- `~/.local/bin`
- the PYATB venv or its launcher path

Then source it before running `oh-my-LibRPA` stack tests.

## 12) Stack Validation

### Doctor

Run the environment doctor first:

```bash
bash oh-my-librpa/scripts/stack_env_doctor.sh --env-script <your-env.sh>
```

### Smoke test

Run the stack smoke helper on a real case directory:

```bash
bash oh-my-librpa/scripts/stack_smoke_test.sh \
  --case-dir <case_dir> \
  --env-script <your-env.sh> \
  --abacus-bin <abacus-bin> \
  --librpa-bin <chi0_main.exe>
```

Interpretation:

- if only `ABACUS -> PYATB` is validated on the active case and `LibRPA` is validated on an exported `input_librpa` bundle, call the result a `stack smoke test`
- reserve `full end-to-end GW chain passed` for runs that truly cover `SCF -> PYATB -> NSCF -> preprocess -> LibRPA`

## Common Failures And Minimal Fixes

### `pip` blocked by externally-managed Python

- root cause: Ubuntu system Python policy
- minimal fix: use venv and install there
- verify: `python -c 'import numpy, scipy, mpi4py'`

### `pyatb` command exists but import fails in `python3`

- root cause: wrapper points to a different venv/interpreter
- minimal fix: use the wrapper's interpreter or activate the correct venv
- verify: `head -n 1 $(command -v pyatb)` then run that Python with `import pyatb`

### `chi0_main.exe`: `libqsgw.so` not found

- root cause: runtime library path mismatch
- minimal fix: export matching `LD_LIBRARY_PATH` or use a consistent install/build tree
- verify: `ldd <chi0_main.exe> | grep -i qsgw`

### oneAPI compiler names rejected

- root cause: legacy `icpc/ifort` names still hardcoded
- minimal fix: switch to `icpx/ifx/mpiicpx/mpiifx`
- verify: `command -v icpx ifx mpiicpx mpiifx`

### ABACUS fails to link with ELPA / Libxc

- root cause: missing Intel runtime math libraries during final link
- minimal fix: add the needed oneAPI runtime libraries in the ABACUS CMake link logic
- verify: rerun the final link stage with verbose build output

## Natural-Language Entry Prompts

After the repo is installed into an agent home, users can start with prompts like:

- `Help me bootstrap a fresh Ubuntu WSL environment for ABACUS + PYATB + LibRPA.`
- `Audit this machine and tell me the minimum steps still missing before GW smoke tests.`
- `My chi0_main.exe says libqsgw.so is missing. Diagnose it and give me the smallest fix.`
- `Use the current BN case to smoke-test ABACUS, PYATB, and LibRPA locally.`
