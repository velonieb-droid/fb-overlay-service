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
FONT_SIZE = 64
MAX_CHARS_PER_LINE = 28  # adjust based on font size / image width


def overlay_text(img: Image.Image, text: str) -> Image.Image:
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except OSError:
        font = ImageFont.load_default()

    # Wrap long captions so they don't run off the image
    lines = textwrap.wrap(text, width=MAX_CHARS_PER_LINE)

    # Measure total block height to vertically position near bottom
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    total_h = sum(line_heights) + (len(lines) - 1) * 12
    y = img.height - total_h - 80

    for i, line in enumerate(lines):
        x = (img.width - line_widths[i]) / 2
        # outline for readability
        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2), (-2, 2), (2, -2)]:
            draw.text((x + dx, y + dy), line, font=font, fill="black")
        draw.text((x, y), line, font=font, fill="white")
        y += line_heights[i] + 12

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


@app.get("/health")
def health():
    return {"status": "ok"}
