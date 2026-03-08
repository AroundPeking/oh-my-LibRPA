# Chat Guidance

This guide is for human users.

The goal is simple: describe your GW / RPA / debug task in plain English, and let the agent turn it into a safe workflow.

---

## 1. What the user should provide

For a solid-state GW task, the user should provide the key runtime information directly in chat.

### Minimum information

- remote server or compute target
- working directory
- system type (`molecule`, `solid`, or `2D`)
- structure information (for example lattice constant or prepared structure file)
- SCF `KPT` mesh
- whether `KPT_nscf` is already prepared
- whether basis / ABFS / pseudopotential files are already in the directory
- **ABACUS executable path**
- **LibRPA executable path**
- whether the agent should only check first or submit immediately

If executable paths are fixed for a given server, the guidance should still make them explicit instead of leaving them implicit.

---

## 2. Recommended first message

A good periodic GW request can look like this:

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

---

## 3. What the agent should ask back

The agent should ask only for missing information.

A good follow-up is short and concrete.

Example:

```text
I have the server, directory, structure, and KPT mesh.
Please confirm three things before I proceed:
1. Is VPN / remote access already ready?
2. May I create a fresh run subdirectory?
3. Are the ABACUS and LibRPA executable paths final for this run?
```

That is enough.
A good agent should not turn intake into a long questionnaire.

---

## 4. Expected dialogue flow

A good dialogue usually follows this order:

1. **User request**
2. **Minimal clarification**
3. **Preflight / consistency check**
4. **Pre-submit summary**
5. **Submission**
6. **Stage-by-stage updates**
7. **Final result**
8. **Postprocessing request**, such as plotting

---

## 5. Pre-submit summary template

Before submission, the agent should summarize the resolved setup in chat.

Example:

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

## 6. Stage update style

Each stage update should stay short.

Use exactly these three parts:

- what was done
- what was observed
- what is next

Example:

```text
what was done
- submitted the job and checked the live outputs

what was observed
- SCF has converged and OUT.ABACUS is present

what is next
- monitor pyatb, NSCF, preprocess, and LibRPA in sequence
```

---

## 7. Plotting request

After a successful GW run, the user should be able to ask for the final figure in plain language.

Example:

```text
Plot the GW band structure from GW_band_spin_* and the band path.
Use Python.
Make it look like a paper figure.
```

A good agent should automatically find the needed files and produce:

- a clean PNG
- a clean PDF
- a reusable plotting script
- a y-axis range chosen automatically from the near-gap bands, with enough headroom above the CBM instead of a hard-coded top limit

---

## 8. One realistic example

For one compact end-to-end conversation example, see:

- `examples/si-k444-gw/README.md`
