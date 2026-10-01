"""Generate 3 test document images so the pipeline has stable input."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parents[1] / "test_docs"
OUT.mkdir(exist_ok=True)

try:
    FONT_BIG = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
    FONT = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
except Exception:
    FONT_BIG = ImageFont.load_default()
    FONT = ImageFont.load_default()


def _text_image(lines: list[tuple[str, bool]], w=900, h=1200) -> Image.Image:
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    y = 60
    for text, big in lines:
        d.text((50, y), text, fill="black", font=FONT_BIG if big else FONT)
        y += 48 if big else 36
    return img


PRESCRIPTION = [
    ("Sunrise Clinic, Kottayam", True),
    ("Dr Rahul Das, MBBS, General Physician", False),
    ("Date: 28/09/2026", False),
    ("", False),
    ("Patient: Ammini Varghese, 62 y, F", False),
    ("C/O: Cough and fever x 4 days.", False),
    ("Throat congested, no breathlessness.", False),
    ("", False),
    ("Rx", True),
    ("1. Tab Clarithromycin 500 mg - BD x 7 days (after food)", False),
    ("2. Tab Glycomet 500 mg - BD (continue)", False),
    ("3. Syp Ascoril 10 ml - TDS x 5 days", False),
    ("4. Tab Dolo 650 mg - SOS for fever", False),
    ("", False),
    ("Review after 5 days if fever persists.", False),
    ("", False),
    ("Dr Rahul Das", False),
]

LAB = [
    ("DDRC Agilus Diagnostics, Kottayam", True),
    ("Lab Report  -  Date: 26/09/2026", False),
    ("Patient: Ammini Varghese, 62 y, F", False),
    ("", False),
    ("TEST                  RESULT   UNIT   REFERENCE", False),
    ("HbA1c                 8.2      %      < 5.7 normal", False),
    ("Fasting glucose       168      mg/dL  70 - 100", False),
    ("LDL cholesterol       142      mg/dL  < 100", False),
    ("HDL cholesterol       44       mg/dL  > 40", False),
    ("Triglycerides         178      mg/dL  < 150", False),
    ("Creatinine            1.1      mg/dL  0.5 - 1.2", False),
    ("", False),
    ("Interpretation: Diabetes not controlled.", False),
    ("Discuss with your doctor.", False),
]


def main():
    _text_image(PRESCRIPTION).save(OUT / "sunrise_prescription.png")
    lab = _text_image(LAB)
    lab.save(OUT / "lab_report.png")

    blurry = lab.rotate(-6, resample=Image.BICUBIC, fillcolor="white").filter(ImageFilter.GaussianBlur(radius=1.2))
    blurry.save(OUT / "blurry_photo.png")
    print("Wrote:", *sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
