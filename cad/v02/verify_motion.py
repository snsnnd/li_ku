"""Sampled exact-solid motion verification. Not continuous collision detection or FEA."""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path

from asrs_v02 import OUT, bbox, build_model, overlaps, source_sha256


def check_pose(model, dx, dz, q, lift, target=None, bin_q=None):
    fixed, moving = [], []
    for i in model.items:
        if target and i.name == f"stored_bin_{target[0]}_{target[1]}":
            continue
        # Entirely fixed pairs and rigid intra-group pairs were checked in static validation.
        s = i.located(dx, dz, q, lift, bin_q)
        (fixed if i.group == "fixed" else moving).append((i, s, bbox(s)))
    failures = []
    candidates = 0
    for ai, (a, sa, ba) in enumerate(moving):
        pairs = fixed + moving[ai+1:]
        for b, sb, bb in pairs:
            if a.group == b.group:
                continue
            if not overlaps(ba, bb):
                continue
            candidates += 1
            v = sa.intersect(sb).Volume()
            if v > .02 and tuple(sorted((a.name, b.name))) not in model.allowed:
                failures.append({"a": a.name, "b": b.name, "volume_mm3": round(v, 4)})
    return failures, candidates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=float, default=11, help="Y sample interval mm")
    args = ap.parse_args()
    verifier_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if args.step <= 0:
        raise ValueError("step must be positive")
    m = build_model()
    n = math.ceil(m.d.transfer/args.step)
    qs = [m.d.transfer*j/n for j in range(n+1)]
    backlash = (6.2-4)/2
    nc = math.ceil(m.d.transfer/11)
    compensation_points = [m.d.transfer*j/nc for j in range(nc+1)]
    poses = []
    # Each target is empty during retrieval/deposit; every other stored box remains present.
    for c, xx in enumerate(m.d.x_positions):
        for r, zz in enumerate(m.d.decks):
            for q in qs:
                poses.append(("transfer", xx-m.x, zz-m.deck, q, 0, (c, r), None))
                poses.append(("released_reach_or_withdraw", xx-m.x, zz-m.deck, q,
                              7*(1-math.cos(math.radians(165))), (c, r), m.d.transfer))
            for bq in compensation_points:
                poses.append(("push_with_pin_clearance", xx-m.x, zz-m.deck, bq+backlash, 0, (c, r), bq))
                poses.append(("pull_with_pin_clearance", xx-m.x, zz-m.deck, bq-backlash, 0, (c, r), bq))
            for tq in (-backlash, 0, backlash):
                poses.append(("clearance_take_up", xx-m.x, zz-m.deck, tq, 0, (c, r), 0))
    # X and Z traverse with Y FULLY RETRACTED, mandatory control interlock.
    for j in range(31):
        xx = m.d.x_positions[0]+(m.d.x_positions[-1]-m.d.x_positions[0])*j/30
        poses.append(("x_traverse", xx-m.x, m.d.first_deck-m.deck, -backlash, 0, None, 0))
    for c, xx in enumerate(m.d.x_positions):
        for j in range(39):
            zz = m.d.first_deck+(m.d.decks[-1]-m.d.first_deck)*j/38
            poses.append(("z_traverse", xx-m.x, zz-m.deck, -backlash, 0, None, 0))
    for q in (0, m.d.transfer):
        for angle in range(0, 181, 10):
            lift = 7*(1-math.cos(math.radians(angle)))
            poses.append(("latch", 0, 0, q, lift, (1, 2), None))
    failures, candidates = [], 0
    start = time.monotonic()
    for k, (phase, dx, dz, q, lift, target, bin_q) in enumerate(poses, 1):
        bad, count = check_pose(m, dx, dz, q, lift, target, bin_q)
        candidates += count
        if bad:
            failures.append({"phase": phase, "dx": dx, "dz": dz, "q": q,
                             "pin_lift": lift, "target": target, "bin_q": bin_q, "collisions": bad})
        if k % 40 == 0:
            print(f"POSE {k}/{len(poses)} failing_poses={len(failures)} elapsed={time.monotonic()-start:.1f}s", flush=True)
    report = {"generator_sha256": source_sha256(),
              "verifier_sha256": verifier_sha,
              "method": "OCCT B-rep intersection at discrete poses, volume tolerance 0.02 mm3",
              "continuous_collision_detection": False, "pose_count": len(poses),
              "y_sample_interval_mm": m.d.transfer/n, "x_sample_interval_mm": 15,
              "pin_clearance_compensation_mm_each_direction": backlash,
              "clearance_compensated_sample_interval_mm": m.d.transfer/nc,
              "clearance_compensated_y_rail_end_margin_min_mm": 8.05-backlash,
              "clearance_compensated_y_stop_gap_min_mm": 4.05-backlash,
              "z_sample_interval_mm": 10, "latch_angle_interval_deg": 10,
              "boolean_pair_tests": candidates, "failures": failures,
              "geometry_sample_pass": not failures, "hardware_accepted": False,
              "requirements": ["X/Z only move when Y retracted", "Target cell must be empty for deposit",
                               "Latch physical feedback before horizontal pull", "All gaps need tolerance verification"],
              "elapsed_seconds": round(time.monotonic()-start, 2)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"motion_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"poses": len(poses), "failing_pose_count": len(failures),
                      "first_failures": failures[:5], "elapsed": report["elapsed_seconds"]}, indent=2), flush=True)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
