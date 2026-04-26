# Luzahorro Bot

Luzahorro Bot is a Telegram bot that compares fixed-price electricity tariffs using data stored in Google Sheets.

## Features

- Lets users choose between Valencian, Spanish, and Russian.
- Collects contracted power and monthly consumption from Telegram chat.
- Calculates an estimated monthly total for each tariff.
- Sorts plans from cheapest to most expensive.
- Reads tariff data directly from a Google Sheets worksheet.

## How It Works

The bot loads tariff rows from the `Luz` spreadsheet and the `bot` worksheet. For every tariff, it calculates:

- Energy cost based on monthly consumption.
- Power cost based on the selected contracted power.
- Additional charges and taxes from the sheet.
- Final monthly total including VAT.

## Project Structure

```text
.
|-- luzahorro_bot.py
|-- languages/
|   |-- russian.json
|   |-- spanish.json
|   `-- valencian.json
`-- LICENSE
```

## Requirements

- Python 3.10+
- A Telegram bot token
- A Google service account JSON key with access to the target spreadsheet

Install dependencies:

```bash
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file with:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GOOGLE_CREDENTIALS=path/to/service-account.json
```

## Run

```bash
python luzahorro_bot.py
```

## Notes

- The bot expects a spreadsheet named `Luz` and a worksheet named `bot`.
- Tariff values are maintained in Google Sheets, so no code changes are needed when tariffs change.
- A local `bot_start_count.txt` file is used to store the number of `/start` runs.

## License

MIT
