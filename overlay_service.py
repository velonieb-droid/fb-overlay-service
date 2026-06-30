"""
Image Text Overlay Microservice
Deploy to Render, Railway, or any host with Python.
n8n (cloud) calls this via HTTP Request node using multipart/form-data,
since Drive files are private and can't be fetched by URL.

POST /overlay
Form fields:
  image : binary file (the photo from Google Drive)
  text  : string (the ChatGPT-generated caption)

Response: PNG image bytes (binary)
"""

import io
import textwrap

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw, ImageFont

app = FastAPI()

FONT_PATH = "DejaVuSans-Bold.ttf"  # bundle this font file alongside the script (see notes below)

# Sized relative to the image so it looks right at any resolution.
FONT_SIZE_RATIO = 0.055       # font size = 5.5% of image width
LINE_GAP_RATIO = 0.018        # gap between wrapped lines
BOTTOM_MARGIN_RATIO = 0.12    # keep clear of bottom 12% (avoids logos/CTAs/pills)
SIDE_MARGIN_RATIO = 0.08      # horizontal safe margin on each side
BACKDROP_PADDING_RATIO = 0.025


def overlay_text(img: Image.Image, text: str) -> Image.Image:
    img = img.convert("RGBA")
    w, h = img.size

    font_size = max(int(w * FONT_SIZE_RATIO), 24)
    line_gap = int(h * LINE_GAP_RATIO)
    bottom_margin = int(h * BOTTOM_MARGIN_RATIO)
    side_margin = int(w * SIDE_MARGIN_RATIO)
    backdrop_pad = int(h * BACKDROP_PADDING_RATIO)
    max_text_width = w - (2 * side_margin)

    try:
        font = ImageFont.truetype(FONT_PATH, font_size)
    except OSError:
        font = ImageFont.load_default()

    draw = ImageDraw.Draw(img)

    # Wrap based on actual pixel width, not a fixed character count.
    words = text.split()
    lines = []
    current = ""
    for word in words:
        trial = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_text_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    total_h = sum(line_heights) + (len(lines) - 1) * line_gap

    block_bottom = h - bottom_margin
    block_top = block_bottom - total_h
    y = max(block_top, side_margin)

    max_line_width = max(line_widths) if line_widths else 0
    backdrop_box = [
        (w - max_line_width) / 2 - backdrop_pad * 2,
        y - backdrop_pad,
        (w + max_line_width) / 2 + backdrop_pad * 2,
        y + total_h + backdrop_pad,
    ]
    overlay_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay_layer)
    overlay_draw.rounded_rectangle(backdrop_box, radius=backdrop_pad, fill=(0, 0, 0, 110))
    img = Image.alpha_composite(img, overlay_layer)
    draw = ImageDraw.Draw(img)

    for i, line in enumerate(lines):
        x = (w - line_widths[i]) / 2
        outline_w = max(font_size // 28, 1)
        for dx in range(-outline_w, outline_w + 1):
            for dy in range(-outline_w, outline_w + 1):
                if dx or dy:
                    draw.text((x + dx, y + dy), line, font=font, fill="black")
        draw.text((x, y), line, font=font, fill="white")
        y += line_heights[i] + line_gap

    return img.convert("RGB")


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


@app.get("/health")
def health():
    return {"status": "ok"}
