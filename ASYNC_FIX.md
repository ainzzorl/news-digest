# Async Fix for Playwright Integration

## Problems and Solutions

### Problem 1: Event Loop Conflict

**Error:**
```
Playwright fetch failed: It looks like you are using Playwright Sync API inside the asyncio loop.
```

**Cause:** Using Playwright's sync API inside an existing asyncio event loop

**Solution:** Converted to async API (see below)

### Problem 2: Page Load Timeout

**Error:**
```
Playwright fetch failed: Page.goto: Timeout 30000ms exceeded.
```

**Cause:** 
- The `wait_until="networkidle"` strategy was too strict (waits for 500ms of no network activity)
- 30-second timeout was too short for slow-loading pages
- Some pages never reach "networkidle" due to continuous background requests

**Solution:** Implemented progressive timeout strategy with fallbacks

## Solutions Implemented

### 1. Async API Conversion

1. **Function Signatures** - Made async:
   - `gen_chess_players_digest()` → `async def gen_chess_players_digest()`
   - `_gen_player_digest()` → `async def _gen_player_digest()`
   - `_get_player_info()` → `async def _get_player_info()`
   - `_fetch_with_playwright()` → `async def _fetch_with_playwright()`

2. **Playwright API** - Switched to async:
   ```python
   # Before (sync)
   from playwright.sync_api import sync_playwright
   with sync_playwright() as p:
       browser = p.chromium.launch(headless=True)
       # ... etc
   
   # After (async)
   from playwright.async_api import async_playwright
   async with async_playwright() as p:
       browser = await p.chromium.launch(headless=True)
       # ... await all operations
   ```

3. **All Playwright Operations** - Added await:
   - `await p.chromium.launch(headless=True)`
   - `await browser.new_context(...)`
   - `await context.new_page()`
   - `await page.goto(...)`
   - `await page.wait_for_selector(...)`
   - `await page.content()`
   - `await context.close()`
   - `await browser.close()`

4. **Function Calls** - Added await:
   - `await _fetch_with_playwright(url, player)`
   - `await _get_player_info(player)`
   - `await _gen_player_digest(...)`
   - In handler.py: `await gen_chess_players_digest(...)`

5. **Test Script** - Updated:
   - Made test functions async
   - Used `asyncio.run(main())` to run the async test

### 2. Progressive Loading Strategy

Implemented a multi-tier loading strategy to handle slow or problematic pages:

**Strategy 1: `domcontentloaded` (Fast)**
```python
await page.goto(url, wait_until="domcontentloaded", timeout=45000)
await page.wait_for_timeout(2000)  # Wait for dynamic content
```
- Faster, less strict
- Waits for DOM to be parsed, but not all resources
- 45-second timeout

**Strategy 2: `load` (Fallback)**
```python
await page.goto(url, wait_until="load", timeout=60000)
```
- Waits for the `load` event (all resources loaded)
- 60-second timeout
- Used if Strategy 1 times out

**Strategy 3: Get Current Content (Last Resort)**
```python
html_content = await page.content()
```
- If even `load` times out, get whatever content is available
- Better to get partial content than fail completely

### 3. Better Error Handling

- Proper browser cleanup even on errors
- Validates content length
- Detailed logging at each step
- Graceful degradation to requests if Playwright fails

## Why Multiple Strategies?

Different pages load differently:
- **networkidle**: Too strict, many pages never achieve 500ms of no network activity
- **domcontentloaded**: Good balance, fast and usually sufficient
- **load**: Slower but more reliable for complex pages
- **Current content**: Last resort, better than total failure

## Files Modified:

1. `/home/lacungus/dev/news-digest/news_digest/core/chess_players.py`
   - Made 4 functions async
   - Switched to Playwright async API
   - Added await to all async calls

2. `/home/lacungus/dev/news-digest/news_digest/core/handler.py`
   - Updated call to `await gen_chess_players_digest(...)`

3. `/home/lacungus/dev/news-digest/test_playwright_fallback.py`
   - Made test functions async
   - Added `asyncio.run()` in main

4. `/home/lacungus/dev/news-digest/PLAYWRIGHT_INTEGRATION.md`
   - Updated documentation to reflect async architecture
   - Added technical details about async/await

## Testing

Run the test script to verify:
```bash
poetry run python test_playwright_fallback.py
```

Or test the full digest generation through the main script.

## Why This Approach?

1. **Correct Integration**: Playwright's async API is designed to work within async contexts
2. **Better Architecture**: Aligns with the existing async architecture in the codebase
3. **Future Ready**: Enables potential concurrent fetching of multiple players using `asyncio.gather()`
4. **No Event Loop Conflicts**: Avoids trying to create nested event loops

## Fallback Still Works

The fallback to requests still works as before - requests is a synchronous library that can be called from async functions without issues.

