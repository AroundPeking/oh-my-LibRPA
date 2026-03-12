# ABACUS GW PP / NAO / ABFS Library

A curated library of tested pseudopotentials (`.upf`), numerical atomic orbitals (`.orb`), and auxiliary basis files (`.abfs`) for **ABACUS + LibRPA GW workflows**.

This library is meant to be used as a **practical workflow reference** rather than a generic file dump. Its value is not only that the files are collected here, but that many of them have already been used in tested GW-oriented combinations.

---

## Purpose

For different materials, the most reliable PP / NAO / ABFS choice is not always the same.

For example:

- `AlAs` works well with the `sg15` family for both Al and As.
- `AlSb` uses `gth` for both Al and Sb, because the available `sg15` Sb setup was not accurate enough in that case.
- Some elements appear in more than one family because the best practical choice depends on the target system.

So the goal of this library is **consistency with experience**:

- reuse tested combinations when they already exist,
- otherwise assemble a new setup from element-level entries in a controlled way.

---

## What the library contains

Each element directory may contain one or more PP families, for example:

- `sg15`
- `gth`
- `dojo`
- `dojo_2`
- `dojo_3`

Inside a family directory, you will typically find:

- pseudopotentials: `*.upf`
- NAO basis files: `*.orb`
- auxiliary basis files: `*.abfs`

So this library can be used in **two complementary ways**:

1. **System-level reference**  
   If a tested material already appears in the table below, use that setup directly.

2. **Element-level asset pool**  
   If the target material is new, select files by element name and assemble the workflow case element by element.

---

## Recommended selection strategy

When preparing a new GW case, use the following priority:

1. **Exact system match first**  
   If the target system is listed in the tested table below, use that combination directly.

2. **Otherwise select by element**  
   If the system is not listed, choose the needed `.upf`, `.orb`, and `.abfs` files from the corresponding element directories.

3. **Prefer internal consistency**  
   When possible, keep the PP family consistent across the system.

4. **Allow deliberate mixing when necessary**  
   If a mixed-family setup is needed, do it intentionally and record why.

5. **Treat this library as a tested starting point**  
   The listed choices are practical GW-oriented references, not a guarantee of globally optimal accuracy for every new system.

6. **If an element is missing, ask the user for files**  
   If the needed element is not covered by this library, do not guess a replacement. Ask the user to provide the missing PP / NAO / ABFS files.

7. **Keep PP / NAO / ABFS strictly matched**  
   Pseudopotential, atomic basis, and auxiliary basis must correspond to each other. Do not mix them casually across unrelated families, because the basis sets are generated from the chosen pseudopotential.

8. **SOC pseudopotentials are not included yet**  
   SOC-ready pseudopotentials are not yet bundled in this library. They may be added later. Before that, if a SOC case needs missing PP assets, ask the user to upload them.

9. **SOC calculations must use SOC pseudopotentials**  
   If SOC is enabled, SOC pseudopotentials are mandatory. Do not use non-SOC pseudopotentials for a SOC workflow.

---

## Tested system-level recommendations

The `Gap (eV)` column records the band gap associated with the tested setup.

| System | Gap (eV) | Recommended setup |
|---|---:|---|
| AlAs | 2.008 | Al: `sg15`, As: `sg15` |
| AlSb | 1.576 | Al: `gth`, Sb: `gth` |
| AlP | 2.374 | Al: `sg15`, P: `sg15` |
| BAs | 1.762 | B: `sg15`, As: `sg15` |
| BN | 6.324 | B: `sg15`, N: `sg15` |
| BP | 2.030 | B: `sg15`, P: `sg15` |
| C | 5.549 | C: `sg15` (`1e-7`) |
| Si | 1.060 | Si: `sg15` |
| SiC | 2.255 | Si: `sg15`, C: `sg15` (`1e-6`) |
| GaAs | 1.378 | Ga: `dojo_3`, As: `dojo` |
| GaN | 2.857 | Ga: `dojo`, N: `dojo` |
| GaP | 2.245 | Ga: `dojo_2`, P: `dojo` |
| MgO | 7.392 | Mg: `sg15`, O: `sg15_10au` |
| NaCl | 7.832 | Na: `sg15`, Cl: `sg15` |
| CdS | 2.076 | Cd: `dojo`, S: `dojo` |
| CaO | 6.368 | Ca: `sg15`, O: `sg15_8au` |
| LiF | 14.000 | Li: `sg15`, F: `sg15` |

---

## Practical interpretation

A good way to read this table is:

- if your system is exactly listed, treat the entry as the **default recommended setup**;
- if your system is not listed, treat the element directories as the **search space for a new setup**;
- if the same element appears in multiple families, use prior system experience as guidance rather than choosing blindly.

In other words, this repository is both:

- a **tested-material lookup table**, and
- an **element-indexed resource library**.

---

## Maintenance notes

If you add a new tested system, update this README together with the files.

For each new entry, record at least:

- system name
- reported gap
- selected PP family for each element
- any special note explaining why the setup was chosen

This keeps the library readable, searchable, and reusable for future GW preparation.
