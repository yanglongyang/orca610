# Photophysics Consistency Checklist

This file is the compact review checklist used before accepting a photophysical result.

## Energy-cycle check

For geometries R0 (S0 minimum) and R1 (S1 minimum), construct all final energies at one consistent energy level:

- E0(R0)
- E1(R0)
- E0(R1)
- E1(R1)

Derived quantities:

- Eabs = E1(R0) - E0(R0)
- Eem = E1(R1) - E0(R1)
- Ead = E1(R1) - E0(R0)
- lambda_e = E1(R0) - E1(R1)
- lambda_g = E0(R1) - E0(R0)
- E00 = Ead + ZPE(S1,R1) - ZPE(S0,R0)

Expected sanity relations in the ordinary two-surface picture:

- Eabs >= Ead >= Eem
- Eabs - Eem = lambda_e + lambda_g
- lambda_e >= 0 and lambda_g >= 0

If these fail substantially, inspect method mixing, state mixing, sign convention, geometry identity, and solvent regime before interpreting the spectrum.

## State-identity check

- Root number is not state identity.
- Compare NTOs / leading configurations at R0 and R1.
- Use FOLLOWIROOT for likely crossings.
- When comparing TD-DFT and STEOM, match state composition rather than ordinal root.

## Controlled comparison check

Before claiming an effect belongs to TDA, basis set, functional, or solvent:

- same geometry?
- same state?
- same method except the tested variable?
- same solvent regime?

If more than one answer is no, call the result a protocol difference, not a single-variable effect.

## ESD(IC) check

- input geometry = S0 geometry matching GSHessian
- both GS and ES Hessians available for AH calculation
- NACME true
- ETF true
- full TDDFT (`TDA false`) preferred by ORCA 6.1 manual for IC NACME
- no silent S0-Hessian-as-S1-Hessian substitution

## Quantum-yield check

General:

Phi_F = kr / (kr + kIC + kISC + knr,other + ...)

If only kr and kIC are present, label the result `Phi_F(two-channel)` and state the missing pathways.
