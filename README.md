# Convert BG Black to White

Tools for cleaning up lecture-screenshot PDFs that have black letterbox bars around light content, and for compiling many single-slide pages into a compact grid layout.

## What it does

- Slices each page into horizontal bands and classifies each as dark or light.
- Inverts only the genuinely dark bands (e.g. black letterbox bars), leaving light content untouched.
- Normalizes the remaining background to pure white while preserving text, handwriting, and colored diagrams.
- Packs multiple processed slides onto each output page in a grid (e.g. 4-up, 6-up) to save paper/space.

## Requirements

```
pip install PyMuPDF Pillow numpy opencv-python
```

## Usage

Convert a single PDF:

```
python convert_pdf.py input.pdf output.pdf [--dpi 150] [--bands 40] [--slides 4]
```

- `--dpi`: render resolution (default 150)
- `--bands`: number of horizontal analysis bands used to detect dark regions (default 40)
- `--slides`: number of slides per output page, arranged in an auto-sized grid (default 4)

Convert every PDF in the current directory in parallel (writes `<name>_converted.pdf` next to each source file):

```
python loop.py
```
