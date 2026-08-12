# SIAB First-Order Wavefunction Research Plan

This research route is separate from the current OML controlled periodic-GW executor. Its intended sequence is:

1. Implement atomic and molecular Sternheimer response on a uniform real-space grid, with the real-space cutoff matched to the plane-wave `Ecut` definition.
2. Implement atomic and molecular delta-Sternheimer response on the same uniform grid.
3. Obtain numerically exact first-order atomic and molecular wavefunctions under the matched cutoff and boundary conditions.
4. Replace the plane-wave reference used by SIAB `DPSI` with these first-order wavefunctions.

Each step should define its input convention, reference solution, measured error, acceptance threshold, and retained artifacts before the next step starts. The current MCP write tools do not execute this route; Delta-Sternheimer and SIAB remain on their reviewed research workflows until dedicated schemas and validators are implemented.
