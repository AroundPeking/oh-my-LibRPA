# NAO Translation-Projector Band Unfolding

## Purpose

The OML band-unfolding module assigns primitive-cell momentum weights to
ABACUS supercell LCAO states. Its first scope is a controlled primitive-cell
versus exact-supercell equivalence test for PBE, EXX, and diagonal LibRPA GW
energies.

Run it as:

~~~bash
python -m oml_mcp.band_unfolding \
  --path-table path.csv \
  --stru STRU \
  --overlap OUT.ABACUS/srs1_nao.csr \
  --wfc-dir OUT.ABACUS \
  --kpt-info OUT.ABACUS/KPT.info \
  --factors 4 4 4 \
  --orbitals-per-atom 22 \
  --output unfolded_weights.csv \
  --summary unfolding_summary.json
~~~

The module computes spectral weights. It does not rerun ABACUS, PyATB, or
LibRPA and does not alter GW energies.

## How The Translation Matrices Are Obtained

The translation matrices are reconstructed from the supercell structure; they
are not read from LibRPA or PyATB.

For diagonal supercell factors \(f=(f_1,f_2,f_3)\), OML enumerates

\[
  n=(n_1,n_2,n_3),\qquad 0\le n_i<f_i,
\]

and the corresponding supercell-fractional primitive translation

\[
  t_n=(n_1/f_1,n_2/f_2,n_3/f_3).
\]

For each source atom \(a\), OML searches the STRU coordinates for the unique
same-species atom \(p_n(a)\) satisfying

\[
  x_a+t_n=x_{p_n(a)}+L_{a,n},
\]

where \(L_{a,n}\) is an integer supercell lattice vector. The atom permutation
\(p_n\) and the boundary shift \(L_{a,n}\) completely define the translation
in an atom-contiguous equal-size NAO basis:

\[
  [T_n C]_{p_n(a)}
  =\exp[-2\pi iK\cdot L_{a,n}]\,C_a .
\]

The phase is required when an orbital crosses the supercell boundary. It also
gives the finite-group relation \(T_i^{f_i}=\exp(-2\pi iK_i)\).

### Software And NAO Locality

This implementation is local in two distinct senses.

First, it is a read-only OML post-processor. It does not modify the ABACUS
Hamiltonian, the LibRPA response kernel, the screened interaction, or the GW
self-energy. The unfolding weights can therefore be regenerated from archived
ABACUS wavefunctions and overlaps without rerunning either electronic-structure
code.

Second, each translation is a sparse block permutation in the current NAO
representation. If \(\alpha\) and \(\beta\) label the equally ordered orbitals
on each atom, its only nonzero matrix elements are

\[
  (T_n)_{(p_n(a),\alpha),(a,\beta)}
  =\delta_{\alpha\beta}
   \exp[-2\pi iK\cdot L_{a,n}].
\]

Thus applying \(T_n\) requires only moving each atom's coefficient block and
multiplying it by the boundary phase. It does not construct a dense translation
matrix, evaluate another real-space integral, rotate angular functions, or mix
radial/orbital indices on the translated atom. This locality is exact only
because the current scope requires an exact repetition with the same ordered
NAO block on every atom.

The final spectral weight is not an on-site observable. The overlap matrix
\(S(K)\) contains interatomic overlaps, and the projector sums every primitive
translation. "Local" therefore describes the representation and application
of each \(T_n\), not the spatial extent of \(P_k\) or of the unfolded state.

## Projector And Nonorthogonal Metric

The primitive points folded onto one supercell point are

\[
  k_s=(K+s)/f\pmod 1,\qquad 0\le s_i<f_i.
\]

The character projector for one primitive sector is

\[
  P_k=\frac{1}{N_t}\sum_n
      \exp(2\pi ik\cdot n)T_n ,
  \qquad N_t=f_1f_2f_3 .
\]

Because ABACUS NAOs are nonorthogonal, the weight of supercell state \(m\) is

\[
  w_{mk}=
  \frac{C_{mK}^{\dagger}S(K)P_kC_{mK}}
       {C_{mK}^{\dagger}S(K)C_{mK}}.
\]

OML constructs \(S(K)\) from ABACUS srs1_nao.csr using

\[
  S(K)=\sum_R e^{2\pi iK\cdot R}S(R).
\]

For an exact periodic supercell, the weights over all folded primitive sectors
sum to one for each state.

## Input Contract

The path CSV must contain:

| Column | Meaning |
| --- | --- |
| distance | Plot coordinate along the primitive path |
| kx, ky, kz | Target primitive reciprocal-fractional momentum |
| Kx, Ky, Kz | Corresponding supercell reciprocal-fractional momentum |

The ABACUS output directory must contain one complex-LCAO wavefunction file per
path point, named wfs1kN_nao.dat or the legacy wfkN_nao.dat, plus KPT.info.
Both names for the same point are rejected because their provenance is
ambiguous.

The caller must supply orbitals-per-atom explicitly. OML verifies that both the
overlap and wavefunction dimensions equal

\[
  N_{\rm atom}N_{\rm NAO/atom}.
\]

## Output Contract

The CSV contains one row per path point and supercell band:

| Field | Meaning |
| --- | --- |
| point, distance, band | Stable state identity |
| energy_eV, occupation | ABACUS mean-field values from the wavefunction file |
| target_weight | Weight at the requested primitive momentum |
| weight_sum | Sum over every folded primitive sector |
| norm | \(C^\dagger S C\) |
| strongest_sector, strongest_weight | Largest folded-sector assignment |

The JSON summary reports maximum norm error, sector-sum error, overlap
anti-Hermiticity, and the minimum and maximum projector weights.

To display LibRPA GW bands, join these weights to GW_band_spin_1.dat by point
and original band index. Do not sort occupied and empty energies independently
and do not rematch states by energy. This association assumes the diagonal GW
approximation used by the current LibRPA band output, so the KS eigenvector
identity is unchanged.

## Primitive/Supercell Numerical Comparison

Band unfolding only assigns primitive momenta to an already computed supercell
state. It cannot remove a difference caused by using different RPA/GW numerical
quadratures. PBE and EXX energies do not depend on the LibRPA minimax grid, but
RPA correlation energies and the correlation part of GW do.

For an exact primitive/supercell equivalence test, use the same frequency-grid
definition in both calculations:

~~~text
nfreq              16
tfgrids_type        minimax
minimax_emin        <common positive lower transition energy>
minimax_emax        <common positive upper transition energy>
~~~

The exact number of points is a convergence choice; 16 is the value used in the
documented C/Si controls, not a universal requirement. In current LibRPA,
non-positive `minimax_emin` or `minimax_emax` requests an automatic value from
the mean-field transition-energy window. Exact folded primitive and supercell
spectra should give the same automatic window when the state subspace,
occupations, and band cutoffs are also equivalent, but this should be verified
from the output rather than assumed.

It is therefore **not necessary to run the primitive cell first**. There are
two valid controlled procedures:

1. Let both calculations determine the window automatically, then require the
   printed `Minimax energy window` and every `Frequency node & weight` entry to
   agree within the comparison tolerance.
2. Select one common window in advance and set the same positive
   `minimax_emin`, `minimax_emax`, and `nfreq` in both calculations. A primitive
   run can supply candidate bounds, but the final common interval must cover
   the transitions retained in both calculations.

For a production supercell calculation with no primitive reference, converge
the window and `nfreq` directly; a primitive calculation is not an algorithmic
dependency. For the documented current-stack Si primitive/sc2 comparison, both
runs used the automatic window and the printed frequency nodes and weights
already agreed to about \(1.8\times10^{-10}\) and \(2.2\times10^{-10}\),
respectively. That particular primitive/supercell difference was therefore not
caused by the minimax grid.

Besides the frequency grid, an equivalence claim must keep the occupations,
included state subspace, k/q sampling, auxiliary basis and shrink definition,
symmetry controls, head/wing option, analytic continuation, and quasiparticle
solver fixed. In particular, integer occupations remain a separate prerequisite
for the insulating RPA/GW tests discussed here.

## Current Applicability

This version is valid only when all of the following hold:

- the supercell matrix is diagonal with positive integer factors;
- the structure is an exact periodic replication;
- every primitive translation maps each atom uniquely to a same-species atom;
- the structure contains one chemical species, with the same number and
  ordering of contiguous NAOs on every atom;
- STRU and KPT.info use Direct coordinates;
- the calculation is nonmagnetic nspin=1 without SOC;
- ABACUS writes complex-LCAO wavefunction binaries and srs1_nao.csr;
- GW uses diagonal quasiparticle corrections with unchanged state indices.

It must not be used for a general integer transformation matrix, multi-element
systems, defects, relaxed or disordered supercells, atom-dependent NAO slices,
nspin=2, spinors, SOC, or off-diagonal quasiparticle-state rotations. The
implementation rejects multi-element structures and other unsupported
conditions that it can identify, but it cannot infer nspin or SOC from the
wavefunction binary alone. The caller must therefore preserve and verify those
input conditions.

## Relation To PyATB

PyATB BANDUNFOLDING and OML target the same primitive momentum-resolved
spectral measure but use different representations.

The comparison here is pinned to PyATB commit
`80f7c2d89aaa8a736e4145f67a6e1d30c783be2d`: see its
[BANDUNFOLDING documentation](https://github.com/pyatb/pyatb/blob/80f7c2d89aaa8a736e4145f67a6e1d30c783be2d/doc/source/functions/bandunfolding.md)
and
[solver implementation](https://github.com/pyatb/pyatb/blob/80f7c2d89aaa8a736e4145f67a6e1d30c783be2d/src/cpp/core/bandunfolding_solver.cpp).

PyATB expands the supercell tight-binding eigenstate in plane waves. In compact
notation, its projection amplitude and spectral weight have the form

\[
  D_{Gm}(k)
  =\sum_\mu \langle k+G\mid\phi_{\mu K}\rangle C_{\mu m}(K),
  \qquad
  W_{mK}(k)=\sum_{G\in\mathcal G(E_{\rm cut})}|D_{Gm}(k)|^2,
\]

where \(K\) is the supercell momentum, \(k\) is a primitive momentum folded to
\(K\), and the sum contains primitive reciprocal vectors selected by a
plane-wave cutoff. The orbital Fourier transforms supply
\(\langle k+G\mid\phi_{\mu K}\rangle\). This construction does not require the
exact atom permutation used by OML, so its representation and interface are
more suitable for general supercell matrices and non-perfect supercells. Its
weights must, however, be checked with respect to the plane-wave cutoff.

| Property | OML translation projector | PyATB plane-wave projection |
| --- | --- | --- |
| Projection basis | Finite primitive translations in the NAO overlap metric | Truncated plane waves |
| Extra convergence parameter | None inside the fixed NAO space | Plane-wave cutoff |
| Best current use | Exact primitive/supercell equivalence and LibRPA GW post-processing | More general standalone TB/supercell unfolding |
| Main limitation | Requires exact translation permutations and current diagonal-factor scope | Requires orbital-to-plane-wave projection and cutoff convergence |

For the present exact C and Si supercell tests, the OML method is the more
direct method: it is cutoff-free within the ABACUS NAO space and attaches the
weights to the LibRPA GW state identity. PyATB is the better reference for a
future general interface. Its general transformation matrix, spin/SOC and
band-window handling should inform that extension, and a matched PBE
calculation should be retained as an independent cross-check.

A future general OML implementation should borrow the following interface ideas
without replacing the validated translation-projector kernel for exact
repetitions:

- accept a general integer primitive-to-supercell matrix and enumerate its
  translation cosets rather than requiring diagonal factors;
- read explicit per-atom AO slices so multi-element and atom-dependent basis
  layouts are unambiguous;
- support spin channels and spinors without changing state identity;
- expose band windows and stable output identifiers compatible with later PBE,
  EXX, and GW plotting;
- retain a matched PyATB/PBE calculation as an independent representation-level
  validation when extending beyond exact periodic repetitions.

## Provenance

The first validated production case is the diamond-C sc444 calculation
documented under AITP_project/rpa_headwing. It used 128 atoms, 22 NAOs per atom,
91 path points, and 512 bands. Its maximum norm error was
\(3.44\times10^{-9}\), the maximum sector-sum error was
\(2.59\times10^{-14}\), and the overlap anti-Hermiticity was
\(6.28\times10^{-16}\).
