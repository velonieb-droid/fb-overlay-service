"""
Image Text Overlay Microservice
Deploy to Render, Railway, or any host with Python.
n8n (cloud) calls this via HTTP Request node using multipart/form-data.

POST /overlay
Form fields:
  image : binary file (the photo from Google Drive)
  text  : string (the ChatGPT-generated caption)
Response: PNG image bytes (binary)
"""

import io
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw, ImageFont

app = FastAPI()

FONT_PATH         = "DejaVuSans-Bold.ttf"
TEXT_COLOR        = (15, 40, 90)   # dark navy
FONT_SIZE_RATIO   = 0.068
LINE_GAP_RATIO    = 0.025

# MY SNW template has an angled/hex safe-zone (narrower at top and bottom
# than the full canvas width) — wider side margin keeps wrapped lines off
# the diagonal red/gold borders regardless of exact line count.
SIDE_MARGIN_RATIO = 0.16

# Text block lives between 38% and 68% of image height — this is the band
# where the white hex panel is at (or near) full width in this template.
TOP_ZONE    = 0.30
BOTTOM_ZONE = 0.60


def overlay_text(img: Image.Image, text: str) -> Image.Image:
    img = img.convert("RGB")
    w, h = img.size

    font_size      = max(int(w * FONT_SIZE_RATIO), 28)
    line_gap       = int(h * LINE_GAP_RATIO)
    side_margin    = int(w * SIDE_MARGIN_RATIO)
    max_text_width = w - (2 * side_margin)

    # Ensure quote marks are present
    text = text.strip().strip('"').strip('\u201c\u201d')
    text = f'\u201c{text}\u201d'   # wrap in proper curly quotes " … "

    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except OSError:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(img)

    # Pixel-accurate word wrap
    words = text.split()
    lines = []
    current = ""
    for word in words:
        trial = (current + " " + word).strip()
        bbox  = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_text_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    # Measure lines — capture left/top bearing offsets so we can
    # center the VISIBLE glyph box, not PIL's raw anchor point
    line_heights, line_widths, line_offsets = [], [], []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])
        line_offsets.append((bbox[0], bbox[1]))  # (left_bearing, top_bearing)

    total_h = sum(line_heights) + (len(lines) - 1) * line_gap

    # Center the block within the safe zone (TOP_ZONE to BOTTOM_ZONE)
    zone_top    = h * TOP_ZONE
    zone_bottom = h * BOTTOM_ZONE
    zone_h      = zone_bottom - zone_top
    y = zone_top + (zone_h - total_h) / 2

    # Draw dark navy text, each line centered on canvas width (w),
    # correcting for glyph bearing so the visible text — not the
    # font's internal anchor box — sits on the true center line
    for i, line in enumerate(lines):
        off_x, off_y = line_offsets[i]
        x = (w - line_widths[i]) / 2 - off_x
        draw.text((x, y - off_y), line, font=font, fill=TEXT_COLOR)
        y += line_heights[i] + line_gap

    return img


@app.post("/overlay")
async def overlay(image: UploadFile = File(...), text: str = Form(...)):
    try:
        contents = await image.read()
        img = Image.open(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read image: {e}")

    result_img = overlay_text(img, text)

    buf = io.BytesIO()
    result_img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok"}
