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

FONT_PATH       = "DejaVuSans-Bold.ttf"
TEXT_COLOR      = (15, 40, 90)   # dark navy — matches DonorFlow brand
FONT_SIZE_RATIO = 0.068          # slightly larger so quoted text reads boldly
LINE_GAP_RATIO  = 0.022
SIDE_MARGIN_RATIO = 0.10         # keeps text away from template edges


def overlay_text(img: Image.Image, text: str) -> Image.Image:
    img = img.convert("RGB")
    w, h = img.size

    font_size     = max(int(w * FONT_SIZE_RATIO), 28)
    line_gap      = int(h * LINE_GAP_RATIO)
    side_margin   = int(w * SIDE_MARGIN_RATIO)
    max_text_width = w - (2 * side_margin)

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

    # Measure each line
    line_heights, line_widths = [], []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    total_h = sum(line_heights) + (len(lines) - 1) * line_gap

    # Vertically centered in the usable image area (top 75% — avoid bottom pill/logo zone)
    usable_h = h * 0.72
    y = max((usable_h - total_h) / 2, side_margin)

    # Draw dark navy text — no outline, no backdrop
    for i, line in enumerate(lines):
        x = (w - line_widths[i]) / 2
        draw.text((x, y), line, font=font, fill=TEXT_COLOR)
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
