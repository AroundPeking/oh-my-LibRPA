# Example: Si GW chat flow (`k = 4x4x4`)

This example shows the **conversation form** that `oh-my-librpa` should encourage.

It focuses on three things only:

1. what the user should say
2. what the agent should ask back
3. how the workflow should progress to a final result

---

## 1. User request

```text
Run a Si GW calculation on ks_ghj_3.
Use ~/gw/Si/AI/ as the source directory.
The basis, ABFS, pseudopotential, and KPT_nscf are already there.
Use lattice constant 5.431 Å.
Use SCF KPT = 4 4 4.
ABACUS executable: /path/to/abacus
LibRPA executable: /path/to/chi0_main.exe
Please check first and then submit.
```

This is a good first message because it already provides:

- server
- source directory
- structure information
- KPT mesh
- `KPT_nscf` availability
- basis / ABFS / pseudopotential availability
- ABACUS executable path
- LibRPA executable path
- desired execution style

---

## 2. Agent follow-up

The agent should ask only for what is still missing.

A good follow-up can be this short:

```text
Before I proceed, please confirm:
1. Is VPN / remote access already ready?
2. May I create a fresh run subdirectory?
3. Are those ABACUS and LibRPA executable paths final for this run?
```

---

## 3. Pre-submit summary

After preflight, the agent should summarize the final setup clearly.

```text
Pre-submit summary
- server: ks_ghj_3
- fresh run directory: ~/gw/Si/AI/si_gw_k444_xxxxx
- system: Si solid
- lattice constant: 5.431 Å
- KPT: 4 4 4
- KPT_nscf: user-provided
- ABACUS executable: /path/to/abacus
- LibRPA executable: /path/to/chi0_main.exe
- task: g0w0_band
- nfreq: 16

If this looks right, I will submit.
```

---

## 4. Stage-by-stage flow

The expected workflow is:

1. connect to the remote machine
2. inspect the source directory
3. create a fresh run directory
4. run preflight / consistency checks
5. submit the job
6. report progress stage by stage

A concise progress update should always use:

- what was done
- what was observed
- what is next

---

## 5. Final user request for plotting

After the calculation succeeds, the user should be able to say:

```text
Plot the GW band structure from GW_band_spin_* and the band path.
Use Python.
Make it look like a paper figure.
```

That should be enough for the agent to continue.

The default paper-style plotting behavior should also choose the y-axis automatically from the near-gap manifold, instead of using a fixed upper bound that can clip the CBM region.

---

## 6. Example final result

The final result should not just be numbers or logs.
It should also include a clean figure.

![Si GW band figure](../../docs/assets/si-gw-band-paper.png)

This figure is an example of the expected final presentation quality for a successful periodic GW workflow.
