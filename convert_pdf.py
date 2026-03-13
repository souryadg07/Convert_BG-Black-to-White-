#!/usr/bin/env python3
"""
convert_pdf.py — Smart PDF color inversion.

Problem solved:
  Lecture-screenshot PDFs often have pure-black letterbox bars (top/bottom)
  surrounding a light content area. A naive full-page invert turns the content
  dark and the bars white — the opposite of what we want.

Strategy:
  1. Slice the page into horizontal bands.
  2. Classify each band as "dark" or "light".
  3. Only invert bands that are genuinely dark (background luminance < threshold).
  4. Leave light bands unchanged.
  5. Stitch the bands back together and embed into the output PDF.

Usage:
    python convert_pdf.py input.pdf output.pdf [--dpi 150] [--bands 40]
"""

import sys
import argparse
import io

try:
    import fitz
except ImportError:
    sys.exit("PyMuPDF not found. Run:  pip install PyMuPDF")

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Pillow not found. Run:  pip install Pillow")

try:
    import numpy as np
except ImportError:
    sys.exit("NumPy not found. Run:  pip install numpy")

# A band whose average luminance (0-1) is below this is treated as "dark"
DARK_THRESHOLD = 0.35

# Minimum fraction of page height a dark run must occupy to be inverted
MIN_DARK_FRACTION = 0.02


def band_luminance(gray_arr, y0: int, y1: int) -> float:
    strip = gray_arr[y0:y1]
    if strip.size == 0:
        return 1.0
    return float(strip.mean()) / 255.0


def smart_invert(pil_img: Image.Image, n_bands: int) -> Image.Image:
    """
    Invert only horizontal bands that are dark.
    Light bands (white/light content areas) are left unchanged.
    """
    width, height = pil_img.size
    gray_arr = np.array(pil_img.convert("L"))   # (H, W) uint8

    band_h = max(1, height // n_bands)

    # Build list of contiguous dark runs
    dark_runs = []
    in_dark = False
    run_start = 0

    for b in range(n_bands + 1):
        y0 = b * band_h
        y1 = min(y0 + band_h, height)
        lum = band_luminance(gray_arr, y0, y1)
        is_dark = lum < DARK_THRESHOLD

        if is_dark and not in_dark:
            run_start = y0
            in_dark = True
        elif not is_dark and in_dark:
            dark_runs.append((run_start, y0))
            in_dark = False

    if in_dark:
        dark_runs.append((run_start, height))

    # Drop tiny dark runs (thin dividers, single-pixel artifacts)
    dark_runs = [
        (y0, y1) for y0, y1 in dark_runs
        if (y1 - y0) / height >= MIN_DARK_FRACTION
    ]

    if not dark_runs:
        # Whole page is already light — return a clean RGB copy
        return pil_img.convert("RGB")

    # If >= 85% of the page is dark, do a simple full-page invert
    total_dark_px = sum(y1 - y0 for y0, y1 in dark_runs)
    if total_dark_px >= 0.85 * height:
        return ImageOps.invert(pil_img.convert("RGB"))

    # Partial invert: only flip the dark strips
    result_arr = np.array(pil_img.convert("RGB"))   # (H, W, 3) uint8
    for y0, y1 in dark_runs:
        result_arr[y0:y1] = 255 - result_arr[y0:y1]

    return Image.fromarray(result_arr, mode="RGB")


def convert_pdf(input_path: str, output_path: str,
                dpi: int = 150, n_bands: int = 40) -> None:
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    src = fitz.open(input_path)
    dst = fitz.open()
    total = len(src)
    print(f"Processing {total} page(s) at {dpi} DPI …")

    for page_num, page in enumerate(src, start=1):
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        png_bytes = pix.tobytes("png")
        pix = None  # free immediately

        with Image.open(io.BytesIO(png_bytes)) as img:
            processed = smart_invert(img, n_bands)

        buf = io.BytesIO()
        processed.save(buf, format="PNG", optimize=False)

        rect = page.rect
        new_page = dst.new_page(width=rect.width, height=rect.height)
        new_page.insert_image(rect, stream=buf.getvalue())

        print(f"  Page {page_num}/{total} ✓")

    dst.save(output_path, garbage=4, deflate=True)
    dst.close()
    src.close()
    print(f"\nDone → {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Smart PDF inversion — only inverts dark bands, leaves light content alone."
    )
    parser.add_argument("input",  help="Source PDF")
    parser.add_argument("output", help="Output PDF")
    parser.add_argument("--dpi",   type=int, default=150,
                        help="Render DPI (default 150)")
    parser.add_argument("--bands", type=int, default=40,
                        help="Horizontal analysis bands (default 40)")
    args = parser.parse_args()
    convert_pdf(args.input, args.output, dpi=args.dpi, n_bands=args.bands)


if __name__ == "__main__":
    main()