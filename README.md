
# Sri Lanka Holiday Dataset

This repository builds a structured holiday dataset for Sri Lanka by combining public holiday information from multiple sources and turning it into a full calendar dataset.

## What this project does

The workflow collects holiday data from:

- CBS bank holiday listings
- Official government document calendar PDFs
- A combined normalized holiday dataset
- A final daily calendar dataset for every date from 2005 onward

The scripts generate CSV files in the `csv/` folder so the data can be used for analysis, modeling, or reporting.

## Project structure

- `scripts/1.create_cbs_dataset.py` - Scrapes CBS bank holiday data and writes `CBS_holidays.csv`
- `scripts/2.create_document_dataset.py` - Downloads and processes government holiday PDFs using OCR and writes `Document_gov_holidays.csv`
- `scripts/3.combine_holidays.py` - Merges and normalizes the datasets into `Combined_holidays.csv`
- `scripts/4.create_final_dataset.py` - Expands the combined data into a full daily calendar dataset as `Sri_Lanka_all_dates.csv`
- `requirements.txt` - Python dependencies

## Requirements

This project requires Python 3 and the packages listed in `requirements.txt`.

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
# On Windows PowerShell:
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

> The OCR-based script also requires Tesseract OCR to be installed on your system.

## Running the pipeline

Run the scripts in order:

```bash
python scripts/1.create_cbs_dataset.py
python scripts/2.create_document_dataset.py
python scripts/3.combine_holidays.py
python scripts/4.create_final_dataset.py
```

## Output files

After running the pipeline, the following files are generated in the `csv/` directory:

- `csv/CBS_holidays.csv`
- `csv/Document_gov_holidays.csv`
- `csv/Combined_holidays.csv`
- `csv/Sri_Lanka_all_dates.csv`

## Notes

- The document-based extraction process can be sensitive to PDF layout changes and may require manual review for some years.
- Some scripts may take a few minutes to complete because they download and process historical documents.
- The final dataset includes flags such as public, bank, mercantile, poya, weekend, and holiday indicators.

## Licence

This repository uses separate licences for source code and dataset content.

### Source Code

The Python scripts, GitHub Actions workflows, validation logic, and other source code are licensed under the **MIT License**.

See [`LICENSE`](LICENSE).

### Dataset and Documentation

The processed CSV datasets, dataset structure, derived fields, metadata, and documentation are licensed under the **Creative Commons Attribution 4.0 International Licence — CC BY 4.0**, except for third-party source material.

See [`LICENSE-DATA.md`](LICENSE-DATA.md).

### Data Sources

The dataset was independently compiled and processed using publicly available holiday information from:

* The Central Bank of Sri Lanka
* The Department of Government Printing, Sri Lanka
* Relevant Government of Sri Lanka publications

The source institutions remain the authoritative providers of the original information. This project is independent and is not officially endorsed by those institutions.
