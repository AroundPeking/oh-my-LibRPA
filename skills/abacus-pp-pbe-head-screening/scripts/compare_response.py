#!/usr/bin/env python3
"""Compare definition-matched imaginary-frequency in-plane response tensors."""
import argparse
import json
from pathlib import Path

import numpy as np

COMPONENTS = ("xx", "xy", "yx", "yy")
IDENTITY = np.array([1.0, 0.0, 0.0, 1.0])


def validate(w, a):
    if w.ndim != 1 or len(w) < 2 or a.shape != (len(w), 4):
        raise ValueError("Need at least two frequencies and four tensor components")
    if not np.all(np.isfinite(w)) or not np.all(np.isfinite(a)):
        raise ValueError("Nonfinite frequency or tensor component")
    if np.any(w <= 0) or np.any(np.diff(w) <= 0):
        raise ValueError("Frequencies must be positive and strictly increasing")


def read_csv(path):
    data = np.atleast_1d(np.genfromtxt(path, delimiter=",", names=True))
    if not set(("omega_ha",) + COMPONENTS).issubset(data.dtype.names or ()):
        raise ValueError("CSV requires omega_ha,xx,xy,yx,yy")
    w = data["omega_ha"]
    a = np.column_stack([data[c] for c in COMPONENTS])
    validate(w, a)
    return w, a


def to_alpha(head, height):
    if not np.isfinite(height) or height <= 0:
        raise ValueError("Perpendicular cell height must be positive in bohr")
    return (head - IDENTITY) * height / (4 * np.pi)


def metrics(w, ae, pp, low, reference=None):
    ref = ae if reference is None else reference
    diff = pp - ae
    norm2 = lambda x: np.sum(x*x, axis=1)
    denominator = np.trapz(norm2(ref), w)
    numerator = np.trapz(norm2(diff), w)
    low_den = np.sqrt(norm2(ae[low]))
    low_num = np.sqrt(norm2(diff[low]))
    return {
        "relative_l2": float(np.sqrt(numerator/denominator)) if denominator > 0 else None,
        "relative_low_max": float(np.max(low_num/low_den)) if np.all(low_den > 0) else None,
        "absolute_max": float(np.max(np.sqrt(norm2(diff)))),
    }


def compare(wa, ae, wp, pp, omega_min=None, omega_max=None, low_max=0.1,
            head_metric=False):
    validate(wa, ae)
    validate(wp, pp)
    start, stop = max(wa[0], wp[0]), min(wa[-1], wp[-1])
    start = start if omega_min is None else omega_min
    stop = stop if omega_max is None else omega_max
    if not (np.isfinite(start) and np.isfinite(stop) and np.isfinite(low_max)):
        raise ValueError("Frequency bounds must be finite")
    if start < max(wa[0], wp[0]) or stop > min(wa[-1], wp[-1]) or start >= stop:
        raise ValueError("No valid common interval; extrapolation is forbidden")
    if start >= min(low_max, stop):
        raise ValueError("No low-frequency interval; do not report a zero low error")
    w = np.unique(np.concatenate(([start, stop, min(low_max, stop)], wa, wp)))
    w = w[(w >= start) & (w <= stop)]
    interp = lambda oldw, a: np.column_stack([
        np.interp(np.log(w), np.log(oldw), a[:, i]) for i in range(4)])
    ae, pp = interp(wa, ae), interp(wp, pp)
    low = w <= low_max
    reference = ae - IDENTITY if head_metric else ae
    result = metrics(w, ae, pp, low, reference)
    result.update({"omega_min_ha": float(start), "omega_max_ha": float(stop),
                   "low_max_used_ha": float(min(low_max, stop)), "nodes": len(w),
                   "interpolation": "linear in log(omega)", "integration_measure": "domega"})
    result["directions"] = {
        name: metrics(w, ae[:, i:i+1], pp[:, i:i+1], low, reference[:, i:i+1])
        for i, name in enumerate(COMPONENTS)
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ae", type=Path, required=True)
    parser.add_argument("--pp", type=Path, required=True)
    parser.add_argument("--quantity", choices=("alpha2d", "head3d"), required=True)
    parser.add_argument("--ae-height-bohr", type=float)
    parser.add_argument("--pp-height-bohr", type=float)
    parser.add_argument("--omega-min", type=float)
    parser.add_argument("--omega-max", type=float)
    parser.add_argument("--low-max", type=float, default=0.1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    wa, ae = read_csv(args.ae)
    wp, pp = read_csv(args.pp)
    bounds = dict(omega_min=args.omega_min, omega_max=args.omega_max, low_max=args.low_max)
    result = {"ae": str(args.ae.resolve()), "pp": str(args.pp.resolve()),
              "input_quantity": args.quantity, "physical_acceptance": "not_determined"}
    if args.quantity == "head3d":
        if args.ae_height_bohr is None or args.pp_height_bohr is None:
            parser.error("head3d requires both perpendicular heights in bohr")
        if args.ae_height_bohr == args.pp_height_bohr:
            result["epsilon_head_metrics"] = compare(wa, ae, wp, pp, head_metric=True, **bounds)
        else:
            result["epsilon_head_metrics"] = "not compared: unequal vacuum heights"
        ae, pp = to_alpha(ae, args.ae_height_bohr), to_alpha(pp, args.pp_height_bohr)
    result["alpha2d_metrics"] = compare(wa, ae, wp, pp, **bounds)
    result["units"] = "alpha2d input must use one common length unit; converted head3d uses bohr"
    encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
