"""Handwriting reader service (optional, off by default): TrOCR on one text line at a time.

POST /read  (multipart `file`, an image)  ->  {"lines": [{"text", "box": [x0,y0,x1,y1]}], "model": "..."}
GET  /health

TrOCR reads a SINGLE line of text, so the page is cut into lines first (horizontal ink-projection profile). It is a second
reader for MediThread's own two-pass check: it never decides anything alone and its text is never written to a record.
Nothing is stored; the image is processed in memory and dropped."""
from __future__ import annotations

import io
import os

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, ImageOps

MODEL = os.getenv("HTR_MODEL", "microsoft/trocr-base-handwritten")
MAX_BYTES = 8 * 1024 * 1024
MAX_LINES = 40

app = FastAPI(title="MediThread HTR")
_proc = _model = None


def segment(gray: np.ndarray, min_h: int = 14, gap: int = 6) -> list[tuple[int, int]]:
    """Row ranges (y0, y1) that hold ink, found from the row sums of a binarised page. Pure numpy, unit tested."""
    h, w = gray.shape
    thresh = gray.mean() - 0.6 * gray.std()
    ink = (gray < thresh).sum(axis=1)
    on = ink > max(2, w * 0.004)
    rows, start, blank = [], None, 0
    for y in range(h):
        if on[y]:
            start = y if start is None else start
            blank = 0
        elif start is not None:
            blank += 1
            if blank > gap:
                if (y - blank + 1) - start >= min_h:
                    rows.append((start, y - blank + 1))  # end is exclusive
                start, blank = None, 0
    if start is not None and h - start >= min_h:
        rows.append((start, h))
    return rows[:MAX_LINES]


def _load():
    global _proc, _model
    if _model is None:
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        _proc = TrOCRProcessor.from_pretrained(MODEL)
        _model = VisionEncoderDecoderModel.from_pretrained(MODEL).eval()
    return _proc, _model


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL, "loaded": _model is not None}


@app.post("/read")
async def read(file: UploadFile = File(...)):
    data = await file.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(413, "image too large or empty")
    try:
        im = ImageOps.autocontrast(ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L"))
    except Exception:
        raise HTTPException(415, "not an image")
    if im.width > 2200:
        im = im.resize((2200, int(im.height * 2200 / im.width)))
    arr = np.asarray(im, dtype=np.float32)
    lines = []
    import torch
    proc, model = _load()
    for y0, y1 in segment(arr):
        pad = 4
        crop = im.crop((0, max(0, y0 - pad), im.width, min(im.height, y1 + pad))).convert("RGB")
        with torch.no_grad():
            ids = model.generate(proc(images=crop, return_tensors="pt").pixel_values, max_new_tokens=48)
        text = proc.batch_decode(ids, skip_special_tokens=True)[0].strip()
        if text:
            lines.append({"text": text, "box": [0, y0, im.width, y1]})
    return {"lines": lines, "model": MODEL}
