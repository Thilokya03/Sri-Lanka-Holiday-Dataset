import calendar
import datetime as dt
import io
import pathlib
import re
import shutil
from dataclasses import dataclass

import pandas as pd
import pymupdf
import pytesseract
import requests
from PIL import Image, ImageOps
from pypdf import PdfReader


# =========================================================
# SETTINGS
# =========================================================

BASE_URL = "https://documents.gov.lk/view/cdr/{year}/{year}_E.pdf"
CSV_PATH = pathlib.Path("csv") / "Document_gov_holidays.csv"
DEBUG_FOLDER = pathlib.Path("debug_ocr")

START_YEAR = 2005
END_YEAR = dt.datetime.now().year

# True removes the old CSV before the run. This is recommended once,
# because the old CSV may already contain incorrect rows.
REBUILD_CSV = True

# Bad years are not written to the CSV.
MIN_ACCEPTED_ROWS = 20
MIN_ACCEPTED_POYAS = 11
MIN_ACCEPTED_MONTHS = 10

OCR_DPI = 350

TESSERACT_LOCATIONS = [
    pathlib.Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    pathlib.Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
]

# The layout changes between years. The script tries several page areas.
# Values are: left, top, right, bottom as proportions of the page.
OCR_STRATEGIES = [
    ("centre", (0.22, 0.00, 0.78, 0.78), 4),
    ("wide", (0.08, 0.00, 0.92, 0.84), 4),
    ("left", (0.00, 0.00, 0.68, 0.84), 4),
    ("right", (0.32, 0.00, 1.00, 0.84), 4),
    ("upper_full", (0.00, 0.00, 1.00, 0.90), 11),
    ("full", (0.00, 0.00, 1.00, 1.00), 11),
]

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

WEEKDAYS = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]

MONTH_NUMBERS = {name: number for number, name in enumerate(MONTHS, start=1)}
MONTH_PATTERN = "|".join(MONTHS)
WEEKDAY_PATTERN = "|".join(WEEKDAYS)


# =========================================================
# DATA CLASSES
# =========================================================

@dataclass
class CandidateResult:
    name: str
    rows: list[list]
    score: int
    accepted: bool
    poya_count: int
    month_count: int
    fixed_date_errors: int
    text: str

# =========================================================
# MANUALLY REVIEWED CALENDARS
# =========================================================

# These rows were manually checked against the uploaded calendar images.
# They bypass OCR and normal PDF extraction because these layouts are
# scanned, rotated, or contain multiple columns that can confuse parsing.
#
# Years listed below were manually verified against official calendar pages.
MANUAL_REVIEWED_HOLIDAYS: dict[int, list[list]] = {2006: [[2006, 'January', 11, 'Wednesday', 'Id-Ul-Alha (Hadji Festival Day)', True, True, False],
        [2006, 'January', 13, 'Friday', 'Duruthu Full Moon Poya Day', True, True, False],
        [2006, 'January', 14, 'Saturday', 'Tamil Thai Pongal Day', True, True, True],
        [2006, 'February', 4, 'Saturday', 'Independence Day', True, True, True],
        [2006, 'February', 12, 'Sunday', 'Navam Full Moon Poya Day', True, True, False],
        [2006, 'February', 26, 'Sunday', 'Maha Sivarathri Day', True, True, False],
        [2006, 'March', 14, 'Tuesday', 'Medin Full Moon Poya Day', True, True, False],
        [2006, 'April', 11, 'Tuesday', "Milad-Un-Nabi (Holy Prophet's Birthday)", True, True, True],
        [2006, 'April', 13, 'Thursday', 'Bak Full Moon Poya Day', True, True, False],
        [2006, 'April', 13, 'Thursday', 'Day prior to Sinhala and Tamil New Year Day', True, True, True],
        [2006, 'April', 14, 'Friday', 'Sinhala and Tamil New Year Day', True, True, True],
        [2006, 'April', 14, 'Friday', 'Good Friday', True, True, False],
        [2006, 'May', 1, 'Monday', 'May Day', True, True, True],
        [2006, 'May', 12, 'Friday', 'Vesak Full Moon Poya Day', True, True, False],
        [2006, 'May', 13, 'Saturday', 'Day following Vesak Full Moon Poya Day', True, True, True],
        [2006, 'June', 11, 'Sunday', 'Poson Full Moon Poya Day', True, True, False],
        [2006, 'July', 10, 'Monday', 'Esala Full Moon Poya Day', True, True, False],
        [2006, 'August', 9, 'Wednesday', 'Nikini Full Moon Poya Day', True, True, False],
        [2006, 'September', 7, 'Thursday', 'Binara Full Moon Poya Day', True, True, False],
        [2006, 'October', 6, 'Friday', 'Vap Full Moon Poya Day', True, True, False],
        [2006, 'October', 21, 'Saturday', 'Deepavali Festival Day', True, True, False],
        [2006, 'October', 24, 'Tuesday', 'Id-Ul-Fitr (Ramazan Festival Day)', True, True, False],
        [2006, 'November', 5, 'Sunday', 'Il Full Moon Poya Day', True, True, False],
        [2006, 'December', 4, 'Monday', 'Unduvap Full Moon Poya Day', True, True, False],
        [2006, 'December', 25, 'Monday', 'Christmas Day', True, True, True],
        [2006, 'December', 31, 'Sunday', 'Id-Ul-Alha (Hadji Festival Day)', True, True, False]],
 2007: [[2007, 'January', 3, 'Wednesday', 'Duruthu Full Moon Poya Day', True, True, False],
        [2007, 'January', 15, 'Monday', 'Tamil Thai Pongal Day', True, True, True],
        [2007, 'February', 1, 'Thursday', 'Navam Full Moon Poya Day', True, True, False],
        [2007, 'February', 4, 'Sunday', 'Independence Day', True, True, True],
        [2007, 'February', 5, 'Monday', 'Additional Bank Holiday', False, True, False],
        [2007, 'February', 16, 'Friday', 'Maha Sivarathri Day', True, True, False],
        [2007, 'March', 3, 'Saturday', 'Medin Full Moon Poya Day', True, True, False],
        [2007, 'April', 1, 'Sunday', "Milad-Un-Nabi (Holy Prophet's Birthday)", True, True, True],
        [2007, 'April', 2, 'Monday', 'Bak Full Moon Poya Day', True, True, False],
        [2007, 'April', 3, 'Tuesday', 'Additional Bank Holiday', False, True, False],
        [2007, 'April', 6, 'Friday', 'Good Friday', True, True, False],
        [2007, 'April', 13, 'Friday', 'Day prior to Sinhala and Tamil New Year Day', True, True, True],
        [2007, 'April', 14, 'Saturday', 'Sinhala and Tamil New Year Day', True, True, True],
        [2007, 'May', 1, 'Tuesday', 'May Day', True, True, True],
        [2007, 'May', 1, 'Tuesday', 'Vesak Full Moon Poya Day', True, True, False],
        [2007, 'May', 2, 'Wednesday', 'Day following Vesak Full Moon Poya Day', True, True, True],
        [2007, 'May', 31, 'Thursday', 'Adhi Poson Full Moon Poya Day', True, True, False],
        [2007, 'June', 30, 'Saturday', 'Poson Full Moon Poya Day', True, True, False],
        [2007, 'July', 29, 'Sunday', 'Esala Full Moon Poya Day', True, True, False],
        [2007, 'August', 28, 'Tuesday', 'Nikini Full Moon Poya Day', True, True, False],
        [2007, 'September', 26, 'Wednesday', 'Binara Full Moon Poya Day', True, True, False],
        [2007, 'October', 13, 'Saturday', 'Id-Ul-Fitr (Ramazan Festival Day)', True, True, False],
        [2007, 'October', 25, 'Thursday', 'Vap Full Moon Poya Day', True, True, False],
        [2007, 'November', 8, 'Thursday', 'Deepavali Festival Day', True, True, False],
        [2007, 'November', 24, 'Saturday', 'Il Full Moon Poya Day', True, True, False],
        [2007, 'December', 21, 'Friday', 'Id-Ul-Alha (Hadji Festival Day)', True, True, False],
        [2007, 'December', 23, 'Sunday', 'Unduvap Full Moon Poya Day', True, True, False],
        [2007, 'December', 25, 'Tuesday', 'Christmas Day', True, True, True]],
 2008: [[2008, 'January', 15, 'Tuesday', 'Tamil Thai Pongal Day', True, True, True],
        [2008, 'January', 22, 'Tuesday', 'Duruthu Full Moon Poya Day', True, True, False],
        [2008, 'February', 4, 'Monday', 'Independence Day', True, True, True],
        [2008, 'February', 20, 'Wednesday', 'Navam Full Moon Poya Day', True, True, False],
        [2008, 'March', 6, 'Thursday', 'Maha Sivarathri Day', True, True, False],
        [2008, 'March', 20, 'Thursday', "Milad-Un-Nabi (Holy Prophet's Birthday)", True, True, True],
        [2008, 'March', 21, 'Friday', 'Medin Full Moon Poya Day', True, True, False],
        [2008, 'March', 21, 'Friday', 'Good Friday', True, True, False],
        [2008, 'April', 12, 'Saturday', 'Day prior to Sinhala and Tamil New Year Day', True, True, True],
        [2008, 'April', 13, 'Sunday', 'Sinhala and Tamil New Year Day', True, True, True],
        [2008, 'April', 18, 'Friday', 'Additional Bank Holiday', False, True, False],
        [2008, 'April', 19, 'Saturday', 'Bak Full Moon Poya Day', True, True, False],
        [2008, 'May', 1, 'Thursday', 'May Day', True, True, True],
        [2008, 'May', 19, 'Monday', 'Vesak Full Moon Poya Day', True, True, False],
        [2008, 'May', 20, 'Tuesday', 'Day following Vesak Full Moon Poya Day', True, True, True],
        [2008, 'June', 18, 'Wednesday', 'Poson Full Moon Poya Day', True, True, False],
        [2008, 'July', 17, 'Thursday', 'Esala Full Moon Poya Day', True, True, False],
        [2008, 'August', 16, 'Saturday', 'Nikini Full Moon Poya Day', True, True, False],
        [2008, 'September', 14, 'Sunday', 'Binara Full Moon Poya Day', True, True, False],
        [2008, 'October', 1, 'Wednesday', 'Id-Ul-Fitr (Ramazan Festival Day)', True, True, False],
        [2008, 'October', 14, 'Tuesday', 'Vap Full Moon Poya Day', True, True, False],
        [2008, 'October', 27, 'Monday', 'Deepavali Festival Day', True, True, False],
        [2008, 'November', 12, 'Wednesday', 'Il Full Moon Poya Day', True, True, False],
        [2008, 'December', 9, 'Tuesday', 'Id-Ul-Alha (Hadji Festival Day)', True, True, False],
        [2008, 'December', 12, 'Friday', 'Unduvap Full Moon Poya Day', True, True, False],
        [2008, 'December', 25, 'Thursday', 'Christmas Day', True, True, True]],
 2014: [[2014, 'January', 14, 'Tuesday', 'Tamil Thai Pongal Day', True, True, True],
        [2014, 'January', 14, 'Tuesday', "Milad-Un-Nabi (Holy Prophet's Birthday)", True, True, True],
        [2014, 'January', 15, 'Wednesday', 'Duruthu Full Moon Poya Day', True, True, False],
        [2014, 'February', 4, 'Tuesday', 'Independence Day', True, True, True],
        [2014, 'February', 14, 'Friday', 'Navam Full Moon Poya Day', True, True, False],
        [2014, 'February', 27, 'Thursday', 'Maha Sivarathri Day', True, True, False],
        [2014, 'March', 16, 'Sunday', 'Medin Full Moon Poya Day', True, True, False],
        [2014, 'April', 13, 'Sunday', 'Day prior to Sinhala and Tamil New Year Day', True, True, True],
        [2014, 'April', 14, 'Monday', 'Sinhala and Tamil New Year Day', True, True, True],
        [2014, 'April', 14, 'Monday', 'Bak Full Moon Poya Day', True, True, False],
        [2014, 'April', 15, 'Tuesday', 'Special Bank Holiday', False, True, False],
        [2014, 'April', 18, 'Friday', 'Good Friday', True, True, False],
        [2014, 'May', 1, 'Thursday', 'May Day', True, True, True],
        [2014, 'May', 14, 'Wednesday', 'Vesak Full Moon Poya Day', True, True, False],
        [2014, 'May', 15, 'Thursday', 'Day following Vesak Full Moon Poya Day', True, True, True],
        [2014, 'June', 12, 'Thursday', 'Poson Full Moon Poya Day', True, True, False],
        [2014, 'July', 12, 'Saturday', 'Esala Full Moon Poya Day', True, True, False],
        [2014, 'July', 29, 'Tuesday', 'Id-Ul-Fitr (Ramazan Festival Day)', True, True, False],
        [2014, 'August', 10, 'Sunday', 'Nikini Full Moon Poya Day', True, True, False],
        [2014, 'September', 8, 'Monday', 'Binara Full Moon Poya Day', True, True, False],
        [2014, 'October', 5, 'Sunday', 'Id-Ul-Alha (Hadji Festival Day)', True, True, False],
        [2014, 'October', 8, 'Wednesday', 'Vap Full Moon Poya Day', True, True, False],
        [2014, 'October', 22, 'Wednesday', 'Deepavali Festival Day', True, True, False],
        [2014, 'November', 6, 'Thursday', 'Il Full Moon Poya Day', True, True, False],
        [2014, 'December', 6, 'Saturday', 'Unduvap Full Moon Poya Day', True, True, False],
        [2014, 'December', 25, 'Thursday', 'Christmas Day', True, True, True]],
 2015: [[2015, 'January', 4, 'Sunday', 'Duruthu Full Moon Poya Day', True, True, False],
        [2015, 'January', 4, 'Sunday', "Milad-Un-Nabi (Holy Prophet's Birthday)", True, True, True],
        [2015, 'January', 5, 'Monday', 'Special Bank Holiday', False, True, False],
        [2015, 'January', 15, 'Thursday', 'Tamil Thai Pongal Day', True, True, True],
        [2015, 'February', 3, 'Tuesday', 'Navam Full Moon Poya Day', True, True, False],
        [2015, 'February', 4, 'Wednesday', 'Independence Day', True, True, True],
        [2015, 'February', 17, 'Tuesday', 'Maha Sivarathri Day', True, True, False],
        [2015, 'March', 5, 'Thursday', 'Medin Full Moon Poya Day', True, True, False],
        [2015, 'April', 3, 'Friday', 'Bak Full Moon Poya Day', True, True, False],
        [2015, 'April', 3, 'Friday', 'Good Friday', True, True, False],
        [2015, 'April', 13, 'Monday', 'Day prior to Sinhala and Tamil New Year Day', True, True, True],
        [2015, 'April', 14, 'Tuesday', 'Sinhala and Tamil New Year Day', True, True, True],
        [2015, 'May', 1, 'Friday', 'May Day', True, True, True],
        [2015, 'May', 3, 'Sunday', 'Vesak Full Moon Poya Day', True, True, False],
        [2015, 'May', 4, 'Monday', 'Day following Vesak Full Moon Poya Day', True, True, True],
        [2015, 'June', 2, 'Tuesday', 'Poson Full Moon Poya Day', True, True, False],
        [2015, 'July', 1, 'Wednesday', 'Adhi Esala Full Moon Poya Day', True, True, False],
        [2015, 'July', 18, 'Saturday', 'Id-Ul-Fitr (Ramazan Festival Day)', True, True, False],
        [2015, 'July', 31, 'Friday', 'Esala Full Moon Poya Day', True, True, False],
        [2015, 'August', 29, 'Saturday', 'Nikini Full Moon Poya Day', True, True, False],
        [2015, 'September', 24, 'Thursday', 'Id-Ul-Alha (Hadji Festival Day)', True, True, False],
        [2015, 'September', 27, 'Sunday', 'Binara Full Moon Poya Day', True, True, False],
        [2015, 'October', 27, 'Tuesday', 'Vap Full Moon Poya Day', True, True, False],
        [2015, 'November', 10, 'Tuesday', 'Deepavali Festival Day', True, True, False],
        [2015, 'November', 25, 'Wednesday', 'Il Full Moon Poya Day', True, True, False],
        [2015, 'December', 24, 'Thursday', 'Unduvap Full Moon Poya Day', True, True, False],
        [2015, 'December', 25, 'Friday', 'Christmas Day', True, True, True]],
 2018: [[2018, 'January', 1, 'Monday', 'Duruthu Full Moon Poya Day', True, True, False],
        [2018, 'January', 14, 'Sunday', 'Tamil Thai Pongal Day', True, True, True],
        [2018, 'January', 15, 'Monday', 'Special Bank Holiday', False, True, False],
        [2018, 'January', 31, 'Wednesday', 'Navam Full Moon Poya Day', True, True, False],
        [2018, 'February', 4, 'Sunday', 'Independence Day', True, True, True],
        [2018, 'February', 5, 'Monday', 'Special Bank Holiday', False, True, False],
        [2018, 'February', 13, 'Tuesday', 'Maha Sivarathri Day', True, True, False],
        [2018, 'March', 1, 'Thursday', 'Medin Full Moon Poya Day', True, True, False],
        [2018, 'March', 30, 'Friday', 'Good Friday', True, True, False],
        [2018, 'March', 31, 'Saturday', 'Bak Full Moon Poya Day', True, True, False],
        [2018, 'April', 13, 'Friday', 'Day prior to Sinhala and Tamil New Year Day', True, True, True],
        [2018, 'April', 14, 'Saturday', 'Sinhala and Tamil New Year Day', True, True, True],
        [2018, 'April', 29, 'Sunday', 'Vesak Full Moon Poya Day', True, True, False],
        [2018, 'April', 30, 'Monday', 'Day following Vesak Full Moon Poya Day', True, True, True],
        [2018, 'May', 1, 'Tuesday', 'May Day', True, True, True],
        [2018, 'May', 29, 'Tuesday', 'Adhi Poson Full Moon Poya Day', True, True, False],
        [2018, 'June', 15, 'Friday', 'Id-Ul-Fitr (Ramazan Festival Day)', True, True, False],
        [2018, 'June', 27, 'Wednesday', 'Poson Full Moon Poya Day', True, True, False],
        [2018, 'July', 27, 'Friday', 'Esala Full Moon Poya Day', True, True, False],
        [2018, 'August', 22, 'Wednesday', 'Id-Ul-Alha (Hadji Festival Day)', True, True, False],
        [2018, 'August', 25, 'Saturday', 'Nikini Full Moon Poya Day', True, True, False],
        [2018, 'September', 24, 'Monday', 'Binara Full Moon Poya Day', True, True, False],
        [2018, 'October', 24, 'Wednesday', 'Vap Full Moon Poya Day', True, True, False],
        [2018, 'November', 6, 'Tuesday', 'Deepavali Festival Day', True, True, False],
        [2018, 'November', 20, 'Tuesday', "Milad-Un-Nabi (Holy Prophet's Birthday)", True, True, True],
        [2018, 'November', 22, 'Thursday', 'Il Full Moon Poya Day', True, True, False],
        [2018, 'December', 22, 'Saturday', 'Unduvap Full Moon Poya Day', True, True, False],
        [2018, 'December', 25, 'Tuesday', 'Christmas Day', True, True, True]]}


def get_manual_reviewed_candidate(year: int) -> CandidateResult | None:
    rows = MANUAL_REVIEWED_HOLIDAYS.get(year)
    if not rows:
        return None

    # Return copies so later processing cannot modify the source table.
    copied_rows = [row.copy() for row in rows]
    return CandidateResult(
        name="manual_reviewed_calendar",
        rows=copied_rows,
        score=1000,
        accepted=True,
        poya_count=sum("Full Moon Poya Day" in row[4] for row in copied_rows),
        month_count=len({row[1] for row in copied_rows}),
        fixed_date_errors=0,
        text=f"Manually reviewed calendar rows for {year}.",
    )


# =========================================================
# TESSERACT AND PDF HELPERS
# =========================================================

def configure_tesseract() -> None:
    for location in TESSERACT_LOCATIONS:
        if location.exists():
            pytesseract.pytesseract.tesseract_cmd = str(location)
            return

    detected = shutil.which("tesseract")
    if detected:
        pytesseract.pytesseract.tesseract_cmd = detected
        return

    raise FileNotFoundError(
        "Tesseract OCR was not found. Expected it at "
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )


def download_pdf(year: int) -> bytes | None:
    url = BASE_URL.format(year=year)
    print(f"\nDownloading the {year} PDF...")

    try:
        response = requests.get(
            url,
            timeout=60,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"Failed to download {year}: {error}")
        return None

    if not response.content:
        print(f"The {year} response was empty.")
        return None

    print(f"Downloaded {len(response.content)} bytes.")
    return response.content


def extract_normal_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_texts = []

    for page in reader.pages:
        page_texts.append(page.extract_text() or "")

    return "\n".join(page_texts)


def render_pdf_pages(pdf_bytes: bytes) -> list[Image.Image]:
    document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    images: list[Image.Image] = []

    try:
        for page in document:
            pixmap = page.get_pixmap(dpi=OCR_DPI, alpha=False)
            image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")
            images.append(image.copy())
    finally:
        document.close()

    return images


def crop_image(image: Image.Image, ratios: tuple[float, float, float, float]) -> Image.Image:
    width, height = image.size
    left, top, right, bottom = ratios

    box = (
        int(width * left),
        int(height * top),
        int(width * right),
        int(height * bottom),
    )

    cropped = image.crop(box)
    cropped = ImageOps.grayscale(cropped)
    cropped = ImageOps.autocontrast(cropped)
    return cropped


def ocr_strategy_text(
    pages: list[Image.Image],
    year: int,
    strategy_name: str,
    ratios: tuple[float, float, float, float],
    psm: int,
) -> str:
    DEBUG_FOLDER.mkdir(parents=True, exist_ok=True)
    texts: list[str] = []

    for page_index, page_image in enumerate(pages, start=1):
        prepared = crop_image(page_image, ratios)

        image_path = DEBUG_FOLDER / f"{year}_{strategy_name}_page_{page_index}.png"
        prepared.save(image_path)

        text = pytesseract.image_to_string(
            prepared,
            lang="eng",
            config=(
                f"--oem 3 --psm {psm} "
                "-c preserve_interword_spaces=1"
            ),
        )
        texts.append(text)

    combined = "\n".join(texts)
    text_path = DEBUG_FOLDER / f"{year}_{strategy_name}_ocr.txt"
    text_path.write_text(combined, encoding="utf-8")
    return combined


# =========================================================
# TEXT NORMALIZATION
# =========================================================

def normalize_text(text: str) -> str:
    if not text:
        return ""

    replacements = {
        "\xa0": " ",
        "\r\n": "\n",
        "\r": "\n",
        "\f": "\n",
        "—": "-",
        "–": "-",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    spelling_fixes = {
        r"\bSetember\b": "September",
        r"\bSepternber\b": "September",
        r"\bJ\s+anuary\b": "January",
        r"\bFebraury\b": "February",
        r"\bOctaber\b": "October",
        r"\bDecernber\b": "December",
        r"\bThureday\b": "Thursday",
        r"\bWednsday\b": "Wednesday",
        r"\bTusday\b": "Tuesday",
        r"\bPublicHolidays\b": "Public Holidays",
        r"\bBankHolidays\b": "Bank Holidays",
        r"\bMercantileHolidays\b": "Mercantile Holidays",
        r"\bPoyaDay\b": "Poya Day",
        r"\bFul+\s+Moon\b": "Full Moon",
        r"\bNationalDay\b": "National Day",
    }

    for pattern, replacement in spelling_fixes.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# =========================================================
# HOLIDAY NAME DETECTION
# =========================================================

# The earliest matching rule in each date entry is used. This prevents a later
# Poya name from replacing an earlier holiday when OCR joins two entries.
HOLIDAY_RULES: list[tuple[str, str]] = [
    (
        "Half a day Additional Bank Holiday",
        r"half\s+a\s+day\s+additional\s+bank\s+holiday",
    ),
    (
        "Day following Vesak Full Moon Poya Day",
        r"day\s+following\s+(?:vesak|wesak).*?full\s+moon\s+poya\s+day",
    ),
    (
        "Day prior to Sinhala and Tamil New Year Day",
        r"day\s+pr\s*ior\s+to\s+sinhala\s+and\s+t\s*amil\s+new\s+y\s*ear\s+day",
    ),
    (
        "Sinhala and Tamil New Year Day",
        r"sinhala\s+and\s+t\s*amil\s+new\s+y\s*ear\s+day",
    ),
    (
        "Milad-Un-Nabi (Holy Prophet's Birthday)",
        r"milad[-\s]*un[-\s]*nabi.*?(?:birth\s*day|birthday)",
    ),
    (
        "Id-Ul-Fitr (Ramazan Festival Day)",
        r"id[-\s]*u[li1][-\s]*fitr.*?ramazan.*?festival\s+day",
    ),
    (
        "Id-Ul-Alha (Hadji Festival Day)",
        r"id[-\s]*u[li1][-\s]*alha.*?hadji.*?festival\s+day",
    ),
    (
        "Tamil Thai Pongal Day",
        r"t\s*amil\s+thai\s+pongal\s+day",
    ),
    (
        "Independence Day",
        r"(?:independence|national)\s*day",
    ),
    (
        "Maha Sivarathri Day",
        r"maha\s*sivarath\w*\s+day",
    ),
    (
        "Good Friday",
        r"good\s+friday",
    ),
    (
        "May Day",
        r"\bmay\s+day\b",
    ),
    (
        "Christmas Day",
        r"christmas\s+day",
    ),
    (
        "Deepavali Festival Day",
        r"deepavali\s+festival\s+day",
    ),
    (
        "Special Bank Holiday",
        r"special\s+bank\s+holiday",
    ),
    (
        "Additional Bank Holiday",
        r"additional\s+bank\s+holiday",
    ),
    (
        "Duruthu Full Moon Poya Day",
        r"\bduruthu\b.*?full\s+moon\s+poya\s+day",
    ),
    (
        "Navam Full Moon Poya Day",
        r"\b(?:navam|nawam)\b.*?full\s+moon\s+poya\s+day",
    ),
    (
        "Medin Full Moon Poya Day",
        r"\b(?:medin|madin)\b.*?full\s+moon\s+poya\s+day",
    ),
    (
        "Bak Full Moon Poya Day",
        r"\bbak\b.*?full\s+moon\s+poya\s+day",
    ),
    (
        "Vesak Full Moon Poya Day",
        r"\b(?:vesak|wesak)\b.*?full\s+moon\s+poya\s+day",
    ),
    (
        "Poson Full Moon Poya Day",
        r"\bposon\b.*?full\s+moon\s+poya\s+day",
    ),
    (
        "Esala Full Moon Poya Day",
        r"\besala\b.*?full\s+moon\s+poya\s+day",
    ),
    (
        "Nikini Full Moon Poya Day",
        r"\bnikini\b.*?full\s+moon\s+poya\s+day",
    ),
    (
        "Binara Full Moon Poya Day",
        r"\bbinara\b.*?full\s+moon\s+poya\s+day",
    ),
    (
        "Unduvap Full Moon Poya Day",
        r"\bunduvap\b.*?full\s+moon\s+poya\s+day",
    ),
    (
        "Vap Full Moon Poya Day",
        r"\bvap\b.*?full\s+moon\s+poya\s+day",
    ),
    (
        "Il Full Moon Poya Day",
        r"\b(?:il|ii|ill)\b.*?full\s+moon\s+poya\s+day",
    ),
]

COMPILED_HOLIDAY_RULES = [
    (canonical, re.compile(pattern, flags=re.IGNORECASE | re.DOTALL))
    for canonical, pattern in HOLIDAY_RULES
]

ALL_THREE_TYPES = {
    "Tamil Thai Pongal Day",
    "Independence Day",
    "Milad-Un-Nabi (Holy Prophet's Birthday)",
    "Day prior to Sinhala and Tamil New Year Day",
    "Sinhala and Tamil New Year Day",
    "May Day",
    "Day following Vesak Full Moon Poya Day",
    "Christmas Day",
}


def detect_holiday_name(body: str, month: str) -> tuple[str, int, int] | None:
    matches: list[tuple[int, int, str]] = []

    for canonical, pattern in COMPILED_HOLIDAY_RULES:
        match = pattern.search(body)
        if match:
            matches.append((match.start(), match.end(), canonical))

    if not matches:
        return None

    # Earliest phrase wins. For the same start, prefer the longer phrase.
    start, end, canonical = min(matches, key=lambda item: (item[0], -(item[1] - item[0])))

    # Extra protection against a clipped or badly recognized December name.
    if month == "December" and canonical == "Vap Full Moon Poya Day":
        canonical = "Unduvap Full Moon Poya Day"

    return canonical, start, end


def infer_holiday_types(canonical_name: str, body: str, name_end: int) -> tuple[bool, bool, bool]:
    tail = body[name_end:name_end + 18]
    compact = re.sub(r"\s+", "", tail)

    # Exact symbols from selectable PDF text.
    if "†" in compact or "‡" in compact:
        return "*" in compact, "†" in compact, "‡" in compact

    # OCR often converts † and ‡ to t, f, + or #.
    marker_match = re.match(r"[*tTfF+#]{1,8}", compact)
    if marker_match:
        marker_text = marker_match.group()
        public = "*" in marker_text
        uncertain_count = sum(char in "tTfF+#" for char in marker_text)
        bank = uncertain_count >= 1
        mercantile = uncertain_count >= 2

        if public or bank or mercantile:
            return public, bank, mercantile

    # Reliable fallback based on the category of the recognized holiday.
    if "Bank Holiday" in canonical_name:
        return False, True, False

    if canonical_name in ALL_THREE_TYPES:
        return True, True, True

    return True, True, False


# =========================================================
# DATE PARSING AND VALIDATION
# =========================================================

def digit_difference(first: int, second: int) -> int:
    first_text = str(first)
    second_text = str(second)
    difference = abs(len(first_text) - len(second_text))

    for left, right in zip(first_text, second_text):
        if left != right:
            difference += 1

    return difference


def correct_ocr_day(year: int, month: str, raw_day: int, weekday: str) -> int | None:
    month_number = MONTH_NUMBERS[month]
    last_day = calendar.monthrange(year, month_number)[1]

    # Never change an in-range date merely because the weekday disagrees.
    # Such a row is usually a wrong date/name pairing, not a one-digit OCR error.
    if 1 <= raw_day <= last_day:
        actual_weekday = dt.date(year, month_number, raw_day).strftime("%A")
        return raw_day if actual_weekday.lower() == weekday.lower() else None

    # Correct impossible values such as 43 -> 13 only when the correction is safe.
    candidates: list[int] = []
    for possible_day in range(1, last_day + 1):
        possible_weekday = dt.date(year, month_number, possible_day).strftime("%A")
        if possible_weekday.lower() == weekday.lower():
            candidates.append(possible_day)

    if not candidates:
        return None

    best = min(candidates, key=lambda value: (digit_difference(raw_day, value), abs(raw_day - value)))
    if digit_difference(raw_day, best) <= 1:
        print(f"Corrected OCR date: {month} {raw_day} {weekday} -> {month} {best} {weekday}")
        return best

    return None


def easter_sunday(year: int) -> dt.date:
    # Anonymous Gregorian algorithm.
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def parse_holidays(text: str, year: int) -> list[list]:
    text = normalize_text(text)

    date_expression = (
        rf"\b(?P<month>{MONTH_PATTERN})\s+"
        rf"(?P<day>\d{{1,2}})[.,]?\s*"
        rf"(?P<weekday>{WEEKDAY_PATTERN})\b"
    )

    entry_pattern = re.compile(
        date_expression
        + rf"\s*(?:[-=]+\s*)?(?P<body>.*?)"
        + rf"(?={date_expression.replace('?P<month>', '?:').replace('?P<day>', '?:').replace('?P<weekday>', '?:')}|\Z)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    rows: list[list] = []
    seen: set[tuple] = set()

    for match in entry_pattern.finditer(text):
        month = match.group("month").title()
        raw_day = int(match.group("day"))
        weekday = match.group("weekday").title()
        body = re.sub(r"\s+", " ", match.group("body")).strip()

        detected = detect_holiday_name(body, month)
        if not detected:
            continue

        canonical_name, _name_start, name_end = detected
        corrected_day = correct_ocr_day(year, month, raw_day, weekday)
        if corrected_day is None:
            continue

        is_public, is_bank, is_mercantile = infer_holiday_types(
            canonical_name,
            body,
            name_end,
        )

        key = (year, month, corrected_day, canonical_name)
        if key in seen:
            continue

        seen.add(key)
        rows.append([
            year,
            month,
            corrected_day,
            weekday,
            canonical_name,
            is_public,
            is_bank,
            is_mercantile,
        ])

    rows.sort(key=lambda row: (row[0], MONTH_NUMBERS[row[1]], row[2], row[4]))
    return rows


# =========================================================
# CANDIDATE QUALITY
# =========================================================

def fixed_date_error_count(rows: list[list], year: int) -> int:
    errors = 0
    good_friday = easter_sunday(year) - dt.timedelta(days=2)

    for row in rows:
        _year, month, day, _weekday, name, *_types = row
        month_number = MONTH_NUMBERS[month]
        actual = dt.date(year, month_number, day)

        if name == "Christmas Day" and (month, day) != ("December", 25):
            errors += 1
        elif name == "Independence Day" and (month, day) != ("February", 4):
            errors += 1
        elif name == "May Day" and (month, day) != ("May", 1):
            errors += 1
        elif name == "Good Friday" and actual != good_friday:
            errors += 1
        elif name == "Tamil Thai Pongal Day" and not (
            month == "January" and day in {14, 15}
        ):
            errors += 1

    return errors


def evaluate_candidate(name: str, text: str, year: int) -> CandidateResult:
    rows = parse_holidays(text, year)
    poya_count = sum("Full Moon Poya Day" in row[4] for row in rows)
    month_count = len({row[1] for row in rows})
    fixed_errors = fixed_date_error_count(rows, year)

    score = len(rows) * 5 + poya_count * 4 + month_count * 3

    if MIN_ACCEPTED_ROWS <= len(rows) <= 32:
        score += 40
    else:
        score -= abs(MIN_ACCEPTED_ROWS - len(rows)) * 6

    if poya_count >= MIN_ACCEPTED_POYAS:
        score += 35
    else:
        score -= (MIN_ACCEPTED_POYAS - poya_count) * 8

    if month_count >= MIN_ACCEPTED_MONTHS:
        score += 25
    else:
        score -= (MIN_ACCEPTED_MONTHS - month_count) * 8

    score -= fixed_errors * 40

    accepted = (
        len(rows) >= MIN_ACCEPTED_ROWS
        and poya_count >= MIN_ACCEPTED_POYAS
        and month_count >= MIN_ACCEPTED_MONTHS
        and fixed_errors == 0
    )

    return CandidateResult(
        name=name,
        rows=rows,
        score=score,
        accepted=accepted,
        poya_count=poya_count,
        month_count=month_count,
        fixed_date_errors=fixed_errors,
        text=text,
    )


def write_candidate_report(year: int, candidates: list[CandidateResult]) -> None:
    DEBUG_FOLDER.mkdir(parents=True, exist_ok=True)

    report = pd.DataFrame([
        {
            "Year": year,
            "Candidate": candidate.name,
            "Rows": len(candidate.rows),
            "Poya_Count": candidate.poya_count,
            "Month_Count": candidate.month_count,
            "Fixed_Date_Errors": candidate.fixed_date_errors,
            "Score": candidate.score,
            "Accepted": candidate.accepted,
        }
        for candidate in candidates
    ])

    report.to_csv(DEBUG_FOLDER / f"{year}_candidate_report.csv", index=False)


# =========================================================
# CSV SAVING
# =========================================================

def save_year_rows(year: int, rows: list[list]) -> None:
    columns = [
        "Year",
        "Month",
        "Date",
        "Day",
        "Holiday_Name",
        "Is_Public_Holiday",
        "Is_Bank_Holiday",
        "Is_Mercantile_Holiday",
    ]

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_data = pd.DataFrame(rows, columns=columns)

    if CSV_PATH.exists() and CSV_PATH.stat().st_size > 0:
        old_data = pd.read_csv(CSV_PATH)

        # Remove the whole old year first. This prevents old incorrect rows
        # from surviving after a corrected rerun.
        old_data = old_data[old_data["Year"] != year]
        final_data = pd.concat([old_data, new_data], ignore_index=True)
    else:
        final_data = new_data

    final_data["_Month_Number"] = final_data["Month"].map(MONTH_NUMBERS)
    final_data = final_data.sort_values(
        ["Year", "_Month_Number", "Date", "Holiday_Name"]
    ).drop(columns=["_Month_Number"])

    final_data.to_csv(CSV_PATH, index=False)
    print(f"Saved {len(rows)} validated rows for {year}.")


# =========================================================
# YEAR PROCESSING
# =========================================================

def process_year(year: int) -> CandidateResult | None:
    manual_candidate = get_manual_reviewed_candidate(year)

    if manual_candidate:
        print(
            f"Using manually reviewed calendar data: "
            f"rows={len(manual_candidate.rows)}, "
            f"poyas={manual_candidate.poya_count}"
        )

        write_candidate_report(year, [manual_candidate])

        print(f"\n----- MANUALLY VERIFIED HOLIDAYS: {year} -----")
        for row in manual_candidate.rows:
            print(row)

        save_year_rows(year, manual_candidate.rows)
        return manual_candidate

    pdf_bytes = download_pdf(year)
    if not pdf_bytes:
        return None

    candidates: list[CandidateResult] = []

    try:
        normal_text = extract_normal_text(pdf_bytes)
        normal_candidate = evaluate_candidate("normal_pdf_text", normal_text, year)
        candidates.append(normal_candidate)

        print(
            f"Normal extraction: rows={len(normal_candidate.rows)}, "
            f"poyas={normal_candidate.poya_count}, "
            f"score={normal_candidate.score}, "
            f"accepted={normal_candidate.accepted}"
        )
    except Exception as error:
        print(f"Normal extraction failed for {year}: {error}")

    # OCR is used whenever normal extraction is incomplete or suspicious.
    if not candidates or not candidates[0].accepted:
        try:
            configure_tesseract()
            rendered_pages = render_pdf_pages(pdf_bytes)

            for strategy_name, ratios, psm in OCR_STRATEGIES:
                print(f"Trying OCR strategy: {strategy_name}")
                text = ocr_strategy_text(
                    rendered_pages,
                    year,
                    strategy_name,
                    ratios,
                    psm,
                )
                candidate = evaluate_candidate(f"ocr_{strategy_name}", text, year)
                candidates.append(candidate)

                print(
                    f"  rows={len(candidate.rows)}, "
                    f"poyas={candidate.poya_count}, "
                    f"months={candidate.month_count}, "
                    f"fixed_errors={candidate.fixed_date_errors}, "
                    f"score={candidate.score}, "
                    f"accepted={candidate.accepted}"
                )

                # Stop when a strong candidate has been found.
                if candidate.accepted and candidate.score >= 220:
                    break

        except Exception as error:
            print(f"OCR processing failed for {year}: {error}")

    if not candidates:
        return None

    write_candidate_report(year, candidates)
    best = max(candidates, key=lambda candidate: candidate.score)

    best_text_path = DEBUG_FOLDER / f"{year}_selected_{best.name}.txt"
    best_text_path.write_text(best.text, encoding="utf-8")

    print(
        f"Selected {best.name}: rows={len(best.rows)}, "
        f"poyas={best.poya_count}, score={best.score}"
    )

    if not best.accepted:
        print(
            f"WARNING: {year} did not pass validation. "
            "It will NOT be written to the CSV."
        )
        return best

    print(f"\n----- VALIDATED HOLIDAYS: {year} -----")
    for row in best.rows:
        print(row)

    save_year_rows(year, best.rows)
    return best


def main() -> None:
    DEBUG_FOLDER.mkdir(parents=True, exist_ok=True)

    if REBUILD_CSV and CSV_PATH.exists():
        CSV_PATH.unlink()
        print(f"Removed old CSV: {CSV_PATH}")

    failed_years: list[int] = []
    completed_years: list[int] = []

    for year in range(START_YEAR, END_YEAR + 1):
        print("\n" + "=" * 68)
        print(f"PROCESSING YEAR {year}")
        print("=" * 68)

        try:
            result = process_year(year)
        except Exception as error:
            print(f"Unexpected error for {year}: {error}")
            result = None

        if result and result.accepted:
            completed_years.append(year)
        else:
            failed_years.append(year)

    summary_path = DEBUG_FOLDER / "processing_summary.txt"
    summary_path.write_text(
        "Completed years: " + ", ".join(map(str, completed_years)) + "\n"
        + "Failed/manual-review years: " + ", ".join(map(str, failed_years)) + "\n",
        encoding="utf-8",
    )

    print("\n" + "=" * 68)
    print("PROCESSING COMPLETED")
    print(f"Validated years: {completed_years}")
    print(f"Manual-review years: {failed_years}")
    print(f"Summary: {summary_path}")
    print("=" * 68)


if __name__ == "__main__":
    main()