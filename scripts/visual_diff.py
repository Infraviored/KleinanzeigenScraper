#!/usr/bin/env python3
"""Compare screenshots against committed baselines via pixel diff.

Usage:
    python scripts/visual_diff.py <baseline-dir> <current-dir> [--threshold 0.1]

Compares every .png in <current-dir> against the matching .png in <baseline-dir>.
Exits 0 if all diffs are below the threshold, exits 1 if any exceed it or if a
new screenshot has no baseline (prints a notice but does not fail for new shots).

Requires only Pillow — no heavyweight visual regression service.
"""

import argparse
import os
import sys


def pixel_diff_ratio(img_a, img_b):
    """Return the fraction of pixels that differ between two images."""
    from PIL import Image

    a = Image.open(img_a).convert("RGB")
    b = Image.open(img_b).convert("RGB")

    # Resize to the smaller common size so dimension changes don't produce 100% diff
    w = min(a.width, b.width)
    h = min(a.height, b.height)
    a = a.resize((w, h))
    b = b.resize((w, h))

    a_pixels = list(a.getdata())
    b_pixels = list(b.getdata())

    total = len(a_pixels)
    if total == 0:
        return 0.0

    # Count pixels whose RGB distance exceeds a per-pixel threshold
    # (small antialiasing shifts shouldn't count as diffs)
    per_pixel_threshold = 30  # per-channel Manhattan distance
    diffs = 0
    for pa, pb in zip(a_pixels, b_pixels):
        channel_diff = abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) + abs(pa[2] - pb[2])
        if channel_diff > per_pixel_threshold:
            diffs += 1

    return diffs / total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_dir", help="Directory containing baseline .png files")
    parser.add_argument("current_dir", help="Directory containing current .png files")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.1,
        help="Maximum allowed diff ratio (0.0–1.0). Default: 0.1 (10%%)",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.current_dir):
        print(f"Current dir does not exist: {args.current_dir}")
        sys.exit(1)

    current_files = sorted(
        f for f in os.listdir(args.current_dir) if f.endswith(".png")
    )
    if not current_files:
        print("No .png files found in current dir.")
        sys.exit(0)

    has_baselines = os.path.isdir(args.baseline_dir)
    failures = []
    results = []

    for fname in current_files:
        current_path = os.path.join(args.current_dir, fname)
        baseline_path = (
            os.path.join(args.baseline_dir, fname) if has_baselines else None
        )

        if not baseline_path or not os.path.exists(baseline_path):
            results.append((fname, None, "NEW"))
            continue

        try:
            ratio = pixel_diff_ratio(baseline_path, current_path)
            status = "PASS" if ratio <= args.threshold else "FAIL"
            results.append((fname, ratio, status))
            if status == "FAIL":
                failures.append((fname, ratio))
        except Exception as e:
            results.append((fname, None, f"ERROR: {e}"))
            failures.append((fname, None))

    # Print results table
    print(f"\n{'File':<40} {'Diff':>8}  {'Status'}")
    print("-" * 60)
    for fname, ratio, status in results:
        diff_str = f"{ratio:.2%}" if ratio is not None else "—"
        print(f"{fname:<40} {diff_str:>8}  {status}")

    print(f"\nThreshold: {args.threshold:.1%}")

    if failures:
        print(f"\n{len(failures)} screenshot(s) exceeded the visual diff threshold.")
        sys.exit(1)
    else:
        print("\nAll screenshots within threshold.")
        sys.exit(0)


if __name__ == "__main__":
    main()
