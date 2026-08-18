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
import math

import cv2
import numpy as np
from PIL import Image

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


def grid_images_onto_page(images: list[Image.Image], grid_size: tuple[int, int] = (2, 2), bg_color=(255, 255, 255)) -> Image.Image:
    """
    Arranges a list of PIL Images into a single grid image.
    grid_size: (cols, rows) e.g., (2, 2) for 4 slides per page.
    """
    cols, rows = grid_size
    if not images:
        return None

    # Determine individual tile size based on the first image aspect ratio
    single_w, single_h = images[0].size

    canvas_w = single_w * cols
    canvas_h = single_h * rows

    # Create a blank white page
    canvas = Image.new("RGB", (canvas_w, canvas_h), bg_color)

    for idx, img in enumerate(images):
        if idx >= cols * rows:
            break

        # Calculate row and column index
        r = idx // cols
        c = idx % cols

        x = c * single_w
        y = r * single_h

        # Resize image if it doesn't match standard dimensions
        if img.size != (single_w, single_h):
            img = img.resize((single_w, single_h), Image.Resampling.LANCZOS)

        canvas.paste(img, (x, y))

    return canvas


def get_grid_dimensions(n_slides: int) -> tuple[int, int]:
    """Helper to auto-calculate optimal (cols, rows) for a target number of slides."""
    if n_slides <= 1:
        return (1, 1)
    elif n_slides == 2:
        return (1, 2)
    elif n_slides <= 4:
        return (2, 2)
    elif n_slides <= 6:
        return (2, 3)
    elif n_slides <= 9:
        return (3, 3)
    else:
        cols = math.ceil(math.sqrt(n_slides))
        rows = math.ceil(n_slides / cols)
        return (cols, rows)

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
                dpi: int = 150, n_bands: int = 40, slides_per_page: int = 4) -> None:
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    src = fitz.open(input_path)
    dst = fitz.open()
    total = len(src)

    cols, rows = get_grid_dimensions(slides_per_page)
    max_per_page = cols * rows

    print(f"Processing {total} page(s) at {dpi} DPI ({slides_per_page} slides per output page: {cols}x{rows} grid) …")

    batch = []

    for page_num, page in enumerate(src, start=1):
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        png_bytes = pix.tobytes("png")
        pix = None

        with Image.open(io.BytesIO(png_bytes)) as img:
            processed = smart_invert(img, n_bands)
            final_output = normalize_page_to_white(processed)
            batch.append(final_output)

        # When batch is full or on the last slide, compile into a grid page
        if len(batch) == max_per_page or page_num == total:
            grid_img = grid_images_onto_page(batch, grid_size=(cols, rows))

            buf = io.BytesIO()
            grid_img.save(buf, format="PNG", optimize=False)

            # Insert combined grid into destination PDF
            new_page = dst.new_page(width=grid_img.width, height=grid_img.height)
            new_page.insert_image(new_page.rect, stream=buf.getvalue())

            batch.clear()
            print(f"  Processed up to input page {page_num}/{total} ✓")

    dst.save(output_path, garbage=4, deflate=True)
    dst.close()
    src.close()
    print(f"\nDone → {output_path}")

def normalize_page_to_white(pil_img: Image.Image) -> Image.Image:
    """
    Takes a PIL image and normalizes its background to pure white while
    preserving handwritten notes, text, and colored diagrams.
    """
    # 1. Convert PIL Image to OpenCV format (BGR)
    img = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)

    # 2. Convert to Grayscale to estimate background illumination
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 3. Use Morphological Closing with a large kernel to extract background illumination
    # Adjust kernel size (e.g., 21x21 to 51x51) depending on DPI/text thickness
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (35, 35))
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)

    # Avoid division by zero
    background = np.maximum(background, 1)

    # 4. Divide image channels by the estimated background to remove dark regions & shadows
    # Normalize channels back to 0-255 scale
    channels = cv2.split(img)
    normalized_channels = []
    for ch in channels:
        norm_ch = cv2.divide(ch, background, scale=255)
        normalized_channels.append(norm_ch)

    normalized_img = cv2.merge(normalized_channels)

    # 5. Contrast stretch: force near-white pixels to pure 255 white
    # Maps pixel intensities [0, 225] to [0, 255], clipping values > 225 to pure white
    normalized_img = np.clip((normalized_img.astype(np.float32) - 0) * (255.0 / 225.0), 0, 255).astype(np.uint8)

    # 6. Convert back to RGB PIL Image
    return Image.fromarray(cv2.cvtColor(normalized_img, cv2.COLOR_BGR2RGB))

def main():
    parser = argparse.ArgumentParser(
        description="Smart PDF inversion & grid layout — only inverts dark bands and formats slides."
    )
    parser.add_argument("input",   help="Source PDF")
    parser.add_argument("output",  help="Output PDF")
    parser.add_argument("--dpi",   type=int, default=150,
                        help="Render DPI (default 150)")
    parser.add_argument("--bands", type=int, default=40,
                        help="Horizontal analysis bands (default 40)")
    parser.add_argument("--slides", type=int, default=4,
                        help="Number of slides per page in output PDF (default 4)")
    args = parser.parse_args()
    convert_pdf(args.input, args.output, dpi=args.dpi, n_bands=args.bands, slides_per_page=args.slides)


if __name__ == "__main__":
    main()