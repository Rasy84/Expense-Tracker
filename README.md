# Expense Tracker (Flask)

Track daily income and expenses, upload receipt images, and review yearly summaries.

## Quick start from GitHub

```bash
git clone https://github.com/Rasy84/Expense-Tracker.git
cd "Expense-Tracker"
```

## Setup

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

If you want receipt OCR:
- Install Tesseract OCR and add it to your PATH.
- On Windows, you can download the installer from the official repo.

## Run

```bash
python app.py
```

Open `http://127.0.0.1:5000` in your browser.

## Notes

- Receipt OCR is optional. If OCR libraries or Tesseract are missing, the upload still saves the receipt but won't extract amounts.
- Data is stored locally in `expense_tracker.db`.

## License

MIT
