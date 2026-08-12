# Upstream Parameter Audit: 2026-08-12

This audit defines the source-backed compatibility contract for the first
read-only Oh-My-LibRPA MCP implementation.

## Pinned Sources

| Component | Ref | Revision |
| --- | --- | --- |
| ABACUS | `AroundPeking/abacus-develop:master_ghj` | `3efad9ed5ca066aee1d1b2214e43f92a2d2a567e` |
| LibRPA | `Srlive1201/LibRPA:v0.7.0` | `dd169fa11fa920d580d4f39dc11e218a7f17f7b5` |
| PyATB | `AroundPeking/pyatb:enable_head_wing` | `9fb9028c59b1dbaf9cf66965280961fc2225d9eb` |

Branch and tag names are update channels. OML records and checks the full SHA
for every approved profile and run.

## Confirmed Corrections

1. ABACUS registers `out_librpa_reader_version` with source default `0` and
   accepts only `0` or `1`. OML production input must write
   `out_librpa_reader_version 1` explicitly.
2. LibRPA 0.7.0 defaults `version_coul_reader` and `version_lri_reader` to
   `-1` auto-detection. OML production input must write both as `1` to prevent
   accidental legacy/v1 mixing.
3. LibRPA 0.7.0 parses `use_symmetry_exx`, `use_symmetry_gw`, and
   `use_symmetry_rpa`. The old OML spellings `use_input_exx_symmetry` and
   `use_input_gw_symmetry` are not aliases in the parser and can be silently
   ignored. OML must reject them and propose the canonical names.
4. `task = g0w0_band` remains accepted by LibRPA 0.7.0 but is documented as a
   deprecated alias of `task = g0w0`. New OML inputs use `g0w0`.
5. With ABACUS spatial symmetry enabled, `stru_out` appends `n_symops row`,
   followed by nine integer rotation entries and three translation values for
   every operation. LibRPA reads this tail and rebuilds its symmetry context.
   The old `irreducible_sector.txt` and `symrot_*.txt` files are not required.
6. The pinned PyATB branch exposes eigenvector and velocity-matrix calculation.
   It does not define LibRPA reader-v1 output parameters. OML's
   `output_librpa.py` adapter writes the handoff files, so the adapter and the
   PyATB calculation are validated as separate components.

## Reader-v1 Handoff

The canonical LibRPA names are:

- `prefix_coul_full = v1_coulomb_full_iq_`
- `prefix_coul_cut = v1_coulomb_cut_iq_`
- `prefix_lri_coeff = v1_Cs_data_`
- `prefix_lri_coeff_shrink = v1_Cs_shrinked_data_`
- `prefix_shrink_sinvS = v1_shrink_sinvS_`
- `fn_basis_wfc = basis_wfc_out`
- `fn_basis_aux = basis_aux_out`
- `fn_basis_aux_shrink = basis_aux_shrink_out`
- `version_coul_reader = 1`
- `version_lri_reader = 1`

The PyATB adapter eigenvector header is marker `-12345679`, kind `28`. The
velocity header is marker `-12345680`, kind `29`, with three Cartesian
components. Both formats use native-endian fixed-width integers and packed
complex double payloads.

## Reproduce The Audit

Run `scripts/audit_upstream_contract.py` with local checkouts of the three
pinned revisions. The audit checks every checkout SHA and the exact source
locations used for the contract above. A moving branch tip is rejected until a
new profile and regression result are reviewed.
