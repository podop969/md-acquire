# NSFC Downloader - Troubleshooting

## Browser Issues

### Chrome fails to start
- **Check**: Is `CHROME_PATH` correct in `config.py`?
- **Fix**: Run `chrome.exe` directly to verify the path
- **Alternative**: Try `export NSFC_CHROME_PATH="/path/to/chrome"`

### Cannot connect to CDP
- **Check**: Is another Chrome instance using port 9222?
- **Fix**: Close all Chrome windows and re-run

### CDP connection lost during download
- **Cause**: Chrome crashed or closed
- **Fix**: Re-launch with `start-chrome.py`, re-login, re-run `download.py`

## Login Issues

### Login timeout
- **Cause**: User did not complete login within 120s window
- **Fix**: Re-run `download.py`, ensure you have completed login (including captcha/MFA)

### Token expired mid-session
- **Symptom**: API returns 401 or empty responses
- **Fix**: The downloader auto-refreshes token every 50 downloads. If it fails:
  1. Re-open Chrome with `start-chrome.py`
  2. Log in again
  3. Re-run `download.py`

## Search Issues

### Search returns 0 results
- **Check**: Is the keyword spelled correctly?
- **Check**: Has the NSFC site changed its Vue component structure?
- **Fix**: Try `search-rerun.py` to restart Chrome and retry
- **Fix**: Check if `finalSearchList` Vue component name still exists on the page

### Missing results (some projects not found)
- **Cause**: The 100-result limit combined with too-broad filters
- **Fix**: Reduce `MAX_RESULTS_THRESHOLD` in config.py (e.g., to 50)
- **Fix**: Add more specific sub-keywords

## Download Issues

### "No images retrieved" error
- **Check**: Does this project actually have a report? Check on the NSFC website
- **Check**: Has the token expired? Re-login and retry

### 503 Service Unavailable
- **Cause**: NSFC rate limiting
- **Fix**: Already handled by built-in retries with backoff
- **Fix**: Increase `REQUEST_DELAY` in config.py (e.g., to 5.0)

### PDF generation fails
- **Check**: Is Pillow installed? `pip install Pillow`
- **Check**: Are images downloading but corrupt? Check the NSFC website directly

### Download incomplete (only some pages)
- **Cause**: Report has fewer pages than expected, or API truncation
- **Fix**: Verify on the NSFC website directly
- **Note**: The tool downloads pages 1-200 sequentially until the API returns empty

## Configuration Issues

### Config not loading
- **Check**: Did you create `config.py` from `templates/config-example.py`?
- **Check**: Is `config.py` in the project root directory?
- **Fix**: Run `cp templates/config-example.py config.py`

### Wrong download directory
- **Check**: Does `DOWNLOAD_DIR` exist or is it writable?
- **Fix**: The tool creates the directory if it doesn't exist
- **Fix**: Set `NSFC_DOWNLOAD_DIR` environment variable to override

## Platform-Specific

### Windows
- Chrome path: `C:\Program Files\Google\Chrome\Application\chrome.exe`
- Path separators in config.py
- Anti-virus may block WebSocket connections — add exception for port 9222

### macOS
- Chrome path: `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- May need to allow Chrome remote debugging in System Preferences

### Linux
- Chrome path: `/usr/bin/google-chrome` or `/usr/bin/google-chrome-stable`
- May need `--no-sandbox` flag for certain environments
