"""Convert an image, preview its art, and optionally type it into League chat."""

import argparse
from pathlib import Path
import sys

from art_converter import ConversionOptions, convert_image
from sender import SendAborted, SendOptions, WindowsKeyboard, estimated_seconds, send_rows


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("image", type=Path, help="PNG, JPEG, WebP or BMP image path")
    result.add_argument("--width", type=int, default=50, help="maximum columns (default: 50)")
    result.add_argument("--max-rows", type=int, default=12, help="maximum chat messages (default: 12)")
    result.add_argument("--aspect", type=float, default=4, help="vertical font correction (default: 4)")
    result.add_argument("--contrast", type=float, default=1, help="positive contrast factor (default: 1)")
    result.add_argument("--threshold", type=int, default=128, help="dark/light cutoff, 0-255 (default: 128)")
    result.add_argument("--invert", action="store_true", help="swap l and .")
    result.add_argument("--channel", choices=("all", "team"), default="all")
    result.add_argument("--start-delay", type=float, default=2, help="seconds after F8 release (default: 2)")
    result.add_argument("--char-delay", type=float, default=0.01, help="seconds between characters (default: 0.01)")
    result.add_argument("--line-delay", type=float, default=1.5, help="seconds between messages (default: 1.5)")
    result.add_argument("--preview-only", action="store_true", help="print art and exit without keyboard access")
    result.add_argument("--output", type=Path, help="export art to a new text file; existing files are preserved")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        conversion = ConversionOptions(width=args.width, max_rows=args.max_rows,
            aspect=args.aspect, contrast=args.contrast, threshold=args.threshold, invert=args.invert)
        sending = SendOptions(channel=args.channel, start_delay=args.start_delay,
            char_delay=args.char_delay, line_delay=args.line_delay)
        rows = convert_image(args.image, conversion)
        art = "\n".join(rows)
        if args.output is not None:
            # Exclusive creation also prevents accidentally overwriting the input.
            with args.output.open("x", encoding="utf-8", newline="\n") as output:
                output.write(art + "\n")
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(art)
    print(f"\n{len(rows[0])} columns | {len(rows)} messages | channel: {sending.channel}")
    print(f"Estimated time after F8: {estimated_seconds(rows, sending):.1f}s (plus key release and OS overhead)")
    if args.output is not None:
        print(f"Text exported to: {args.output.resolve()}")
    if args.preview_only:
        print("Preview only. No keyboard input was sent.")
        return 0

    try:
        backend = WindowsKeyboard()
        print("\nClose League chat, turn Caps Lock off, release modifiers, switch to the match, then press and release F8.")
        print("Esc or a primary-screen mouse corner cancels. Focus loss cancels without resuming.", flush=True)
        attempted = send_rows(rows, sending, backend, on_start=lambda: print(
            f"Starting in {sending.start_delay:g}s...", flush=True))
        print(f"Finished: {attempted} row submissions attempted. In-game delivery is not verified.")
        return 0
    except SendAborted as exc:
        print(f"Stopped: {exc} {exc.attempted_rows} row submissions attempted. Delivery is not verified.", file=sys.stderr)
        print("A partial chat draft may remain; inspect and clear it yourself.", file=sys.stderr)
        return 130
    except (RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
