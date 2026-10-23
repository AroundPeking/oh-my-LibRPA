# NAO Translation-Projector Band Unfolding Design

## Goal

Move the validated exact-supercell NAO unfolding code into Oh-My-LibRPA as a
reusable post-processing module. The module assigns primitive-momentum spectral
weights to ABACUS complex-LCAO states and can attach those weights by point and
band index to diagonal LibRPA GW quasiparticle energies.

## Method

For a diagonal supercell with factors \(f=(f_1,f_2,f_3)\), enumerate the finite
translation group

\[
  t_n=(n_1/f_1,n_2/f_2,n_3/f_3),\qquad 0\le n_i<f_i.
\]

The supercell structure defines each translation matrix. For source atom
\(a\), find the unique same-species target atom \(p_n(a)\) and supercell lattice
shift \(L_{a,n}\) satisfying

\[
  x_a+t_n=x_{p_n(a)}+L_{a,n}.
\]

In the atom-contiguous NAO basis, the translated coefficient block is

\[
  [T_n C]_{p_n(a)}
  =e^{-2\pi i K\cdot L_{a,n}}C_a .
\]

For a primitive momentum \(k\) folded onto supercell momentum \(K\), use the
finite-group character projector

\[
  P_k=\frac{1}{N_t}\sum_n e^{2\pi i k\cdot n}T_n,\qquad
  w_{mk}=
  \frac{C_{mK}^\dagger S(K)P_kC_{mK}}
       {C_{mK}^\dagger S(K)C_{mK}}.
\]

The overlap matrix is Fourier transformed from ABACUS srs1_nao.csr with its
positive phase convention. The implementation reports norm, sector-sum,
projector-weight, and overlap-Hermiticity diagnostics.

## Scope And Failure Boundary

The first reusable version intentionally supports only:

- diagonal positive integer supercell factors;
- an exact periodic replication whose primitive translations give unique
  same-species atom permutations;
- a single chemical species with the same number and ordering of contiguous
  NAOs on every atom;
- Direct-coordinate STRU and KPT.info;
- nonmagnetic nspin=1, no SOC, complex-LCAO ABACUS wavefunction binaries;
- diagonal GW quasiparticle corrections, so KS-state weights are associated
  with GW energies by unchanged point and band identity.

It does not support a general integer \(3\times3\) supercell matrix,
multi-element systems, defects, relaxed/disordered supercells, atom-dependent
NAO slices, spin-polarized or spinor wavefunctions, or off-diagonal
quasiparticle-state rotations. Unsupported inputs that can be identified from
the available files must fail rather than silently produce weights.

## Placement

The implementation belongs in oml_mcp.band_unfolding, not the LibRPA response
kernel. It consumes ABACUS state/overlap output and supplies post-processing
weights for PBE, EXX, or GW energy tables.

PyATB's BANDUNFOLDING remains an independent comparison backend. PyATB uses
plane-wave projections with an explicit cutoff and supports a broader
supercell interface. The OML finite-translation projector is preferable for
exact supercell-equivalence tests because it is cutoff-free inside the NAO
space and uses the ABACUS overlap metric directly. Future generalization should
borrow PyATB's general transformation-matrix, spin/SOC, band-window, and output
interfaces without replacing the validated projector for its current scope.

## Validation

Unit tests must cover inverse folding, atom permutations, boundary Bloch
phases, projector sector selection and completeness, ABACUS CSR Fourier phase,
binary wavefunction parsing, and explicit rejection of unsupported structures.
The original C sc444 diagnostic remains the numerical provenance test.
