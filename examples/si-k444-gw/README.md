# Example: Si periodic GW on a remote server (`k = 4x4x4`)

This is a realistic example of how `oh-my-librpa` should be used in chat.

It is intentionally not a toy example.
It includes:

- a natural-language user request
- the minimal clarifications that were actually needed
- a real failure / repair loop on HPC
- final GW success
- postprocessing into a paper-style band plot

---

## 1. Initial user request

A good real-world request looked like this:

```text
在 ks_ghj_3 服务器上做一个 Si 的 k444 的 gw 计算，
计算目录使用 ~/gw/Si/AI/,
使用的基组、辅助基和赝势都在计算目录里面了，
Si 的晶格常数设为 5.431 埃
```

This is already good because it contains:

- target server
- target directory
- system identity
- important assets already prepared
- lattice constant

---

## 2. The right follow-up questions

The agent did **not** need to ask 20 things.
It only needed the missing pieces:

1. is VPN already connected?
2. is it allowed to create a fresh subdirectory?
3. is `KPT_nscf` already present in `~/gw/Si/AI/`?

This is the style we want:

- ask little
- ask the right things
- unblock the workflow quickly

---

## 3. What the workflow should do next

Once those answers are confirmed, the workflow should:

1. connect to the remote machine
2. inspect the directory contents
3. create a **fresh** run directory
4. materialize the workflow there
5. run intake / consistency checks
6. report key parameters back to the user
7. submit only after confirmation

For this case, the final successful run directory was:

```text
/mnt/sg001/home/ks_iopcas_ghj/gw/Si/AI/si_gw_k444_fixenv3_20260308_141111
```

---

## 4. What went wrong in reality

This case is useful because several real HPC problems showed up.

### Problem A: executable paths were not explicitly confirmed

The template paths happened to be correct, but that was luck.
A mature workflow should not rely on luck.

### Problem B: batch environment did not match interactive shell

The batch job did not automatically inherit the expected runtime environment.

### Problem C: `python` vs `python3`

The compute nodes had `/usr/bin/python` (python2), but no system `python3`.
The real Python 3 was:

```text
/mnt/sg001/opt/anaconda3/2022.10/bin/python3
```

### Problem D: `srun` was the wrong launcher for this host profile

A direct `srun` route produced PMI2 errors.
A small probe showed that `mpirun` was the correct launcher for this machine.

### Problem E: fail-fast was missing in the early script

When the first stage failed, the script still tried to continue, which polluted the logs.

---

## 5. What the successful repair looked like

The eventual successful workflow did four important things:

1. explicit batch environment initialization
2. explicit `python3` path
3. explicit `mpirun` launcher
4. fail-fast behavior

After those repairs, the job ran successfully:

- **job id**: `867184`
- **state**: `COMPLETED`
- **elapsed**: `00:34:41`

Success markers included:

- SCF converged
- `OUT.ABACUS/vxc_out.dat` present
- `band_out`, `KS_eigenvector_*`, `coulomb_cut_*` present
- NSCF succeeded
- preprocess succeeded
- `GW_band_spin_1.dat` generated

---

## 6. What the user should be able to say next

The next prompt was also natural language:

```text
根据输出的 GW_band_spin_* 和能带路径用 python 画能带图，要求论文画风，清晰好看
```

A good `oh-my-librpa` should treat this as part of the workflow, not as an unrelated manual task.

It should know to use:

- `GW_band_spin_*`
- `band_out`
- `band_kpath_info`
- `KPT_nscf`

and generate:

- paper-style PNG
- paper-style PDF
- a reusable plotting script

---

## 7. What this example should teach the project

This case should influence the project at three levels.

### README level

Show users what a good natural-language request looks like.

### Guide level

Explain the expected conversation flow:

- request
- clarification
- preflight
- submit
- stage reports
- postprocessing

### Rule-card level

Teach the agent:

- what to ask for periodic GW intake
- what not to guess blindly
- how to react when batch environment and login shell differ

---

## 8. One-sentence takeaway

A strong `oh-my-librpa` user experience is not just “generate inputs”.
It is:

> natural-language request → minimal clarification → stable remote execution → durable stage reporting → clean postprocessing
