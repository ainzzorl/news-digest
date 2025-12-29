# Playwright Integration for Chess Player Scraping

## Summary

This document describes the implementation of Playwright with fallback to requests for fetching chess player data from 365chess.com.

## Changes Made

### 1. Updated Dependencies (`pyproject.toml`)
- Added `playwright (>=1.48.0,<2.0.0)` to the project dependencies

### 2. Modified `chess_players.py`

#### Converted to Async/Await
All main functions have been converted to async to properly support Playwright's async API:
- `gen_chess_players_digest()` - now async
- `_gen_player_digest()` - now async
- `_get_player_info()` - now async
- `_fetch_with_playwright()` - now async

#### New Function: `_fetch_with_playwright()`
A new async helper function that uses Playwright to fetch player pages with JavaScript rendering support.

**Features:**
- Uses Playwright's async API (required when called from async context)
- Uses Chromium in headless mode
- Sets realistic user agent to avoid detection
- **Progressive loading strategy** with multiple fallback options:
  1. `domcontentloaded` (45s timeout) - Fast, waits for DOM
  2. `load` (60s timeout) - Slower, waits for all resources
  3. Current content - Gets whatever is available as last resort
- Waits for critical content (table elements) to appear
- Proper cleanup of browser resources
- Comprehensive error handling with detailed logging

**Location:** Lines 373-456 in `chess_players.py`

#### Modified Function: `_get_player_info()`
Enhanced the existing function to try Playwright first, then fallback to requests.

**Behavior:**
1. Checks local cache first (unchanged)
2. Attempts to fetch using Playwright (async)
3. If Playwright fails, falls back to requests method
4. If both fail, raises an exception with details from both attempts
5. Saves to local cache in non-production mode (unchanged)

**Location:** Lines 429-474 in `chess_players.py`

### 3. Modified `handler.py`
- Updated call to `gen_chess_players_digest()` to use `await` since it's now async

### 4. Updated Documentation

#### README.md
Added installation instructions for Playwright browsers:
```bash
poetry run playwright install chromium
```

With a note about the fallback mechanism.

### 4. Created Test Script

`test_playwright_fallback.py` - A standalone test script to verify the functionality.

## Installation Instructions

### For Development:

```bash
# 1. Install project dependencies
poetry install

# 2. Install Playwright browsers (for chess player scraping)
poetry run playwright install chromium
```

### For AWS Lambda Deployment:

The Playwright library and browsers need special handling for Lambda:
- Consider using `playwright-aws-lambda` package for Lambda-optimized setup
- Or use the requests fallback (which will be automatic if Playwright is unavailable)
- Alternatively, package only the chromium binary needed for Lambda

## Usage

The changes are transparent to existing code. The function is now async:

```python
from news_digest.core.chess_players import gen_chess_players_digest

# This is already called with await in the handler
digest = await gen_chess_players_digest(config, source_options, global_config)
```

## Fallback Strategy

The implementation uses a robust fallback strategy:

1. **Playwright (Primary):** Handles JavaScript-rendered content, better for dynamic sites
2. **Requests (Fallback):** Lighter weight, works for static content, no browser needed
3. **Local Cache:** Reduces API calls during development

## Error Handling

- If Playwright is not installed, it raises a clear error with installation instructions
- If Playwright fails (timeout, browser issue, etc.), it logs the error and tries requests
- If both methods fail, it raises an exception with details from both attempts
- All errors are logged for debugging

## Benefits

1. **Better Scraping:** Playwright can handle JavaScript-rendered content
2. **Reliability:** Fallback ensures the system keeps working even if Playwright fails
3. **Development Friendly:** Local caching speeds up development
4. **Production Ready:** Graceful degradation in Lambda or restricted environments
5. **Maintainability:** Clear error messages and logging

## Testing

Run the test script to verify the implementation:

```bash
poetry run python test_playwright_fallback.py
```

This will test fetching data for Magnus Carlsen and verify both the Playwright and fallback mechanisms.

## Performance Considerations

- **Playwright:** Slower (~5-10 seconds per page with progressive loading) but more reliable for JavaScript content
- **Requests:** Faster (~1 second per page) but may miss dynamically loaded content
- **Caching:** Both methods benefit from local caching in development
- **Progressive Loading:** Multiple strategies ensure pages load even if slow or problematic

### Loading Strategy Details

The Playwright implementation uses a progressive loading approach:

1. **First Try - `domcontentloaded` (45s):**
   - Fastest option
   - Waits for DOM to be parsed but not all resources
   - Sufficient for most pages
   - Adds 2-second buffer for dynamic content

2. **Second Try - `load` (60s):**
   - Used if first strategy times out
   - Waits for all resources (images, scripts, etc.)
   - More reliable but slower

3. **Last Resort - Current Content:**
   - If all else fails, gets whatever content is available
   - Better to have partial data than complete failure
   - Still falls back to requests if content is too short

This approach ensures maximum reliability while maintaining reasonable performance.

## Technical Details

### Async/Await Architecture

The implementation uses Python's async/await pattern to properly integrate Playwright's async API:

1. **Why Async?** Playwright's sync API cannot be used inside an existing asyncio event loop (which the main handler uses). The error "It looks like you are using Playwright Sync API inside the asyncio loop" occurs when trying to use sync Playwright in an async context.

2. **Solution:** Convert all related functions to async and use Playwright's `async_api` instead of `sync_api`:
   - `from playwright.async_api import async_playwright` (not sync_playwright)
   - `async with async_playwright()` 
   - `await` all Playwright operations (launch, goto, content, close, etc.)

3. **Benefits:**
   - Properly integrates with the existing async architecture
   - Allows for better concurrency in the future
   - Avoids event loop conflicts

## Future Improvements

1. Add configuration option to prefer one method over the other
2. Implement browser pooling/reuse for better Playwright performance
3. Add retry logic with exponential backoff
4. Add metrics to track which method is used more often
5. Consider parallel player fetching using asyncio.gather() for better performance

