# Academic Book Downloader

An automated Python script that searches and downloads academic books from multiple free sources including Anna's Archive, Internet Archive, OpenAlex, and Open Library.

## Features

- **Multi-Source Search**: Automatically searches 4 sources:
  - Anna's Archive (primary, with Playwright for bypassing anti-bot protections)
  - Internet Archive
  - OpenAlex
  - Open Library
  
- **Bot Protection Handling**: Uses Playwright with stealth configuration to bypass Anna's Archive countdown timers and CAPTCHA

- **Concurrent Downloads**: Downloads multiple books simultaneously (default: 2 workers)

- **Rate Limit Resilience**: Automatic retry with exponential backoff for 429 (Too Many Requests) errors

- **File Validation**: 
  - Ensures downloads are >50KB (filters out error pages)
  - Validates PDF/EPUB headers to detect encrypted files
  - Logs file sizes for verification

- **Download History**: Tracks successfully downloaded books to avoid re-downloading

- **Smart Fallbacks**: If primary source fails, automatically tries alternative sources

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/download_books.git
cd download_books
```

2. Create a virtual environment and install dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

3. Install Playwright browsers:
```bash
playwright install chromium
```

## Usage

1. Edit `download_script.py` and update the `books_to_download` list with your desired books:
```python
books_to_download = [
    "Your Book Title Author Year",
    "Another Book Title Author Year",
]
```

2. Run the script:
```bash
python download_script.py
```

3. Books will be downloaded to the `downloads/` folder

## How It Works

1. **Search Phase**: For each book, the script:
   - Searches Anna's Archive first (prioritized)
   - If not found or encrypted, tries fallback sources (IA, OpenAlex, Open Library)

2. **Anna's Archive Handling**:
   - Uses Playwright headless browser with stealth mode
   - Waits through the 24-second countdown timer
   - Extracts final download link
   - Downloads with retry logic for 429 errors

3. **Download & Validation**:
   - Streams file to disk
   - Validates file size (>50KB minimum)
   - Checks file headers to detect DRM/encryption
   - Saves to download history if successful

## Configuration

You can customize the script behavior by modifying these variables in `download_script.py`:

- `MAX_WORKERS`: Number of concurrent downloads (default: 2)
- `CONNECTION_TIMEOUT`: Timeout for HTTP requests (default: 15s)
- `DOWNLOAD_TIMEOUT`: Timeout for file downloads (default: 300s)
- `DOWNLOAD_DIR`: Directory for downloaded books (default: "downloads")

## Troubleshooting

**"No module named 'playwright'" error**:
```bash
pip install playwright
playwright install chromium
```

**Books showing as encrypted**:
Some files from Anna's Archive mirrors are DRM-protected. The script will automatically:
- Detect encrypted files via header validation
- Try alternative Anna's Archive mirrors
- Fall back to other sources

**Rate limiting (429 errors)**:
The script automatically handles rate limits with:
- Exponential backoff (waits 10-35 seconds between retries)
- Random delays (10-20 seconds) between requests
- Up to 3 retry attempts

## Limitations

- Some books may not be available from any free source
- Anna's Archive access may be temporarily blocked by ISPs (use VPN if needed)
- Download limits may apply (typically 10-20 books/day per source)
- Internet Archive books may require "borrowing" for some titles

## Legal Notice

This tool is for educational purposes. Users are responsible for ensuring their use complies with local copyright laws. Only download books that:
- Are in the public domain
- You have legal access to
- Are covered under fair use in your jurisdiction

## Project Structure

```
download_books/
├── download_script.py      # Main script with all provider classes
├── requirements.txt        # Python dependencies
├── .gitignore             # Git ignore rules
├── downloads/             # Downloaded books (excluded from git)
└── download_history.json  # Download tracking (excluded from git)
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - feel free to use and modify as needed.

## Acknowledgments

- Anna's Archive for preserving digital books
- Internet Archive for their digital library
- OpenAlex for open access to academic works
- Open Library for their book database
