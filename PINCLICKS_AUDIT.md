# PinClicks Login & Analysis — Full System Audit

> Scope: `New app/` folder only. All file paths are relative to `New app/`.

---

## 1. Overview — What PinFlow Does

PinFlow is a **Pinterest-to-WordPress automation pipeline** with three modules:

| Module | Command | What it does |
|--------|---------|-------------|
| **Spy** (Module 1) | `python pinflow.py spy --account cooking-family` | Keyword research: scrapes Pinterest, expands with LLM, analyzes in PinClicks, scores & selects |
| **Content** (Module 2) | `python pinflow.py content --account cooking-family` | Article generation via DeepSeek LLM, Midjourney images, WordPress publishing |
| **Pins** (Module 3) | `python pinflow.py pins --account cooking-family` | LLM-optimized pin titles/descriptions, Pinterest bulk-upload CSV export |
| **Full** | `python pinflow.py full --account cooking-family --auto` | Runs all 3 modules sequentially |

**Entry point:** `pinflow.py` — CLI with argparse subcommands.

**Tech stack:** Python 3.13, Playwright (async), DeepSeek LLM (OpenAI-compatible), SQLite, Pillow, Midjourney/Discord, WordPress REST API.

---

## 2. Brave Browser Integration

**File:** `utils/browser.py` — `BrowserManager` class

### Why Brave?

Brave is used as a **real browser with persistent profile** to bypass bot detection. Instead of launching a generic Chromium instance (which Pinterest and PinClicks can fingerprint), PinFlow launches the actual Brave executable with a dedicated `PinFlow` user data directory. This means the browser has real cookies, real history, and a real fingerprint.

### How It Works

```python
# utils/browser.py — BrowserManager.__init__
class BrowserManager:
    def __init__(self, headless=True, delay_min=2, delay_max=5, use_real_profile=False):
        self.use_real_profile = use_real_profile  # <-- key flag
```

When `use_real_profile=True` (which is how Spy always calls it):

```python
# modules/spy.py line 98-103
self.browser = BrowserManager(
    headless=self.headless,
    delay_min=self.delay_min,
    delay_max=self.delay_max,
    use_real_profile=True,   # Always uses real Brave profile
)
```

### Brave Executable Detection

`_find_brave_path()` checks these paths in order:

| OS | Paths checked |
|----|--------------|
| **Windows** | `%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe` |
| | `%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe` |
| | `%PROGRAMFILES(X86)%\BraveSoftware\Brave-Browser\Application\brave.exe` |
| **Linux** | `/usr/bin/brave-browser`, `/usr/bin/brave` |
| **macOS** | `/Applications/Brave Browser.app/Contents/MacOS/Brave Browser` |

### Brave Profile Directory Detection

`_find_brave_profile_dir()` checks:

| OS | Path |
|----|------|
| **Windows** | `%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data` |
| **Linux** | `~/.config/BraveSoftware/Brave-Browser` |
| **macOS** | `~/Library/Application Support/BraveSoftware/Brave-Browser` |

### Launching the Browser

```python
# utils/browser.py — start() method
self._context = await self._playwright.chromium.launch_persistent_context(
    user_data_dir=os.path.join(brave_profile, "PinFlow"),  # Separate profile to avoid lock conflicts
    executable_path=brave_path,
    headless=self.headless,
    viewport={"width": 1366, "height": 768},
    args=[
        "--disable-blink-features=AutomationControlled",  # Hide automation marker
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ],
)
```

Key details:
- Uses `launch_persistent_context()` — NOT `launch()` + `new_context()`. This means the browser profile persists between runs.
- Profile is stored in a `PinFlow` subdirectory inside Brave's User Data, separate from the Default profile to avoid lock conflicts.
- Viewport is fixed at **1366x768** (common laptop resolution).

### Cookie Copying

On first run, `_copy_cookies_if_needed()` attempts to initialize the PinFlow profile. It creates a marker file `_pinflow_cookies_copied` so it only runs once. Note: Chrome's cookies are encrypted, so the persistent context will prompt login once and then remember it.

### Fallback to Default Chromium

If Brave is not installed, the manager falls back to a standard Chromium launch:

```python
# utils/browser.py — _launch_default()
if brave_path and brave_profile:
    # ... launch Brave
else:
    print("Warning: Brave not found. Using default Chromium.")
    await self._launch_default()
```

---

## 3. Anti-Detection Measures

All anti-detection lives in `utils/browser.py`.

### Brave Persistent Mode (Primary)

When using real Brave profile:
- `--disable-blink-features=AutomationControlled` — Removes the `navigator.webdriver=true` flag that Playwright normally sets
- Real browser executable (not headless Chromium)
- Persistent user profile with real cookies and history
- Fixed viewport matching real devices (1366x768)

### Default Chromium Mode (Fallback)

When Brave is not available, additional anti-detection is injected:

```python
# utils/browser.py — _launch_default()
self._context = await self._browser.new_context(
    viewport={"width": 1366, "height": 768},
    user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    locale="en-US",
)

# JavaScript injection to remove automation markers
await self._context.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
""")
```

This does three things:
1. **Removes `navigator.webdriver`** — Playwright normally sets this to `true`, which is the #1 bot detection signal
2. **Sets `navigator.languages`** — Real browsers have this; headless Chromium sometimes doesn't
3. **Fakes `navigator.plugins`** — Real browsers have browser plugins; headless ones have an empty array

### Human-Like Delays

```python
# utils/browser.py
async def random_delay(self, min_override=None, max_override=None):
    low = min_override or self.delay_min    # default: 2s
    high = max_override or self.delay_max   # default: 5s
    delay = random.uniform(low, high)
    await asyncio.sleep(delay)
```

Delays are used:
- **2-5s** between page navigations (configurable via `config.json`)
- **0.3-0.8s** after filling form fields
- **0.5-1.5s** after clicking buttons
- **1-3s** after page loads
- **3-5s** after Pinterest searches
- **4-7s** after PinClicks login

### Retry Logic

All browser interactions use safe wrappers with exponential backoff:

```python
# utils/browser.py
async def safe_goto(self, page, url, retries=3, timeout=30000):
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            await self.random_delay(1, 3)
            return True
        except Exception:
            if attempt == retries:
                return False
            await asyncio.sleep(2 * attempt)  # 2s, 4s backoff

async def safe_click(self, page, selector, retries=3, timeout=10000):
    # Similar pattern with 1s between retries

async def safe_fill(self, page, selector, text, retries=3, timeout=10000):
    # Similar pattern with 1s between retries
```

---

## 4. Pinterest Login Flow

**File:** `modules/spy.py` — `SpyModule._login_to_pinterest()` (lines 148-191)

### Credentials

```python
# From .env:
PINTEREST_EMAIL=your@email.com
PINTEREST_PASSWORD=your_password
```

Loaded via `get_env("PINTEREST_EMAIL", required=False)`. If either is missing, the module continues as a **guest user** (no login).

### Login Steps

1. Open a new page
2. Navigate to `https://www.pinterest.com/login/` (timeout: 20s)
3. Wait random delay (2-4s)
4. Fill email — tries these selectors in order:
   - `input[name="id"]`
   - `input[type="email"]`
   - `#email`
5. Fill password — tries these selectors in order:
   - `input[name="password"]`
   - `input[type="password"]`
   - `#password`
6. Click submit — tries these selectors in order:
   - `button[type="submit"]`
   - `div[data-test-id="registerFormSubmitButton"]`
   - `button:has-text("Log in")`
7. Wait random delay (5-8s)
8. Check if URL still contains "login" — if yes, login probably failed
9. Close the page (login cookies persist in the browser context)

### Fallback

If login fails or credentials are missing, the module **does not abort**. It continues searching Pinterest as a guest. This means keyword discovery still works, but may get fewer results or hit rate limits sooner.

---

## 5. PinClicks Login & Analysis

**File:** `modules/spy.py` — `SpyModule._enrich_with_pinclicks()` (lines 520-685)

PinClicks login happens during **Step 4** of the Spy pipeline. It is separate from the Pinterest login.

### Credentials

```python
# utils/config.py
def get_pinclicks_credentials() -> dict:
    return {
        "email": get_env("PINCLICKS_EMAIL"),
        "password": get_env("PINCLICKS_PASSWORD"),
    }
```

From `.env`:
```
PINCLICKS_EMAIL=your@email.com
PINCLICKS_PASSWORD=your_password
```

If credentials are missing, PinClicks analysis is **skipped entirely** (keywords are returned without PinClicks enrichment).

### Login Steps

1. Open a new page
2. Navigate to `https://app.pinclicks.com/login` (timeout: 25s)
3. Wait random delay (2-4s)
4. **Dismiss popups** — calls `_dismiss_pinclicks_popups(page)` (see Section 7)
5. Fill email — tries these selectors in order:
   - `input[type="email"]`
   - `input[name="email"]`
   - `#email`
   - `input[placeholder*="email" i]`
6. Fill password — tries these selectors in order:
   - `input[type="password"]`
   - `input[name="password"]`
   - `#password`
   - `input[placeholder*="password" i]`
7. Click submit — tries these selectors in order:
   - `button[type="submit"]`
   - `button:has-text("Log in")`
   - `button:has-text("Sign in")`
   - `button:has-text("Login")`
8. Wait random delay (4-7s)
9. Check URL — if still contains "login", take a screenshot and abort PinClicks
10. Navigate to `https://app.pinclicks.com/pins` (the Top Pins page)

### Per-Keyword Search Loop

After login, the module loops through each keyword (up to `keywords_per_batch * 2` keywords, sorted by relevance score):

```python
for i, kw_data in enumerate(keywords_to_analyze):
    keyword = kw_data["keyword"]

    # 1. Dismiss popups
    await self._dismiss_pinclicks_popups(page)

    # 2. Find search input
    search_input = await page.query_selector(
        'input[placeholder*="Search any keyword"],'
        'input[placeholder*="keyword or topic"],'
        'input[placeholder*="search" i],'
        'input[type="search"],'
        'input[type="text"]'
    )

    # 3. Clear and type keyword
    await search_input.click()
    await search_input.click(click_count=3)  # Triple-click to select all
    await search_input.fill(keyword)

    # 4. Press Enter to search
    await page.keyboard.press("Enter")

    # 5. Wait for loading (up to 20 seconds polling)
    for wait_attempt in range(20):
        body_text = await page.inner_text('body')
        if 'Loading...' not in body_text:
            break
        await asyncio.sleep(1)

    # 6. Dismiss popups again
    await self._dismiss_pinclicks_popups(page)

    # 7. Extract data
    pinclicks_result = await self._extract_pinclicks_data(page)
```

If the search input is not found, it **reloads the page** once and tries again. If still not found, it aborts the entire PinClicks loop.

---

## 6. PinClicks Data Extraction

**File:** `modules/spy.py` — `SpyModule._extract_pinclicks_data()` (lines 687-856)

### PinClicks Table Structure

The PinClicks top-pins table has 12 columns:

| Index | Column | What's extracted |
|-------|--------|-----------------|
| 0 | Checkbox | (skipped) |
| 1 | Pin | Title, pin URL (`pinterest.com/pin/...`), destination URL (from `link-explorer`) |
| 2 | Pin Score | Numeric 0-100 (competition score) |
| 3 | Position | Ranking position |
| 4 | Created At | Date string |
| 5 | Appearances | Count |
| 6 | Saves | Count |
| 7 | Repins | Count |
| 8 | Reactions | Count |
| 9 | Comments | Count |
| 10 | Is Repin | Tags |
| 11 | Row Actions | (skipped) |

### Volume Extraction

```python
# Primary: bold large number element
vol_el = await page.query_selector('div.text-3xl.font-bold')

# Fallback: regex from body text
vol_match = re.search(r'Volume\s*(\d[\d,]*)', body_text)
```

### Pin Title Extraction

```python
# Primary: structured path in column 1
title_link = await cells[1].query_selector('div.flex-col a')

# Fallback: first <a> with meaningful text
links = await cells[1].query_selector_all('a[target="_blank"]')
```

### Pin URL Extraction

```python
# Pinterest pin link
img_link = await cells[1].query_selector('a[href*="pinterest.com/pin/"]')
```

### Destination URL Extraction

```python
# PinClicks wraps destination URLs in link-explorer
dest_link = await cells[1].query_selector('a[href*="link-explorer"]')
# Extract actual URL: /link-explorer?search=https://...
url_match = re.search(r'search=(https?://[^\s&]+)', href)
```

### Output Format

```python
{
    "volume": 12500,           # Monthly search volume (or None)
    "top_score": 85,           # Highest pin score = competition level
    "pins": [
        {
            "title": "Quick Garlic Butter Chicken",
            "score": 85,
            "position": 1,
            "created_at": "2024-01-15",
            "appearances": 450,
            "saves": 12000,
            "repins": 3400,
            "reactions": 89,
            "comments": 23,
            "pin_url": "https://pinterest.com/pin/123...",
            "dest_url": "https://example.com/recipe/...",
        },
        # ... up to 10 pins
    ]
}
```

### Debug Screenshots

If no data is extracted (empty pins and no volume), the module takes a timestamped screenshot for debugging:

```python
if not result["pins"] and result["volume"] is None:
    await self.browser.screenshot(page, f"pinclicks_empty_{timestamp}.png")
```

---

## 7. Captcha & Popup Workaround

**File:** `modules/spy.py` — `SpyModule._dismiss_pinclicks_popups()` (lines 487-518)

### Strategy: Prevention, Not Solving

The `New app/` does **NOT** have a traditional CAPTCHA solving mechanism. Instead, the entire anti-captcha strategy is **prevention** through:

1. **Real Brave browser with persistent profile** — appears as a real user to Cloudflare and PinClicks
2. **Human-like delays** — no instant page loads or rapid clicking
3. **JavaScript popup removal** — dismisses PinClicks application-level popups that could block interaction

### The Popup Dismissal Script

PinClicks uses **Livewire** (a Laravel real-time framework) which sometimes throws error overlays that block the page. The dismissal function injects JavaScript to remove these:

```python
async def _dismiss_pinclicks_popups(self, page):
    await page.evaluate('''() => {
        // 1. Remove Livewire error overlay (the main blocker)
        const lwError = document.getElementById("livewire-error");
        if (lwError) lwError.remove();

        // 2. Remove any Livewire overlay containers with error text
        document.querySelectorAll('[wire\\\\:id]').forEach(el => {
            if (el.style && (el.style.position === 'fixed' || el.style.position === 'absolute')) {
                const text = (el.innerText || '').toLowerCase();
                if (text.includes('error') || text.includes('went wrong') || text.includes('page expired')) {
                    el.remove();
                }
            }
        });

        // 3. Remove modal backdrops
        document.querySelectorAll('.modal-backdrop, .overlay, [class*="livewire-error"]')
            .forEach(el => el.remove());

        // 4. Auto-click dismiss buttons
        document.querySelectorAll('button').forEach(btn => {
            const txt = (btn.innerText || '').toLowerCase().trim();
            if (['ok', 'dismiss', 'close', 'got it', 'retry'].includes(txt)) {
                const rect = btn.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) btn.click();
            }
        });
    }''')
```

This function is called:
- **Before login** — after the login page loads
- **After login** — after the post-login delay
- **After navigating to /pins** — before starting keyword searches
- **Before each keyword search** — before interacting with the search input
- **After each keyword search** — after results load, before data extraction

### Why There's No CAPTCHA Solver

The combination of:
- Real Brave browser executable (not Chromium/Playwright's bundled browser)
- Persistent user profile with real cookies
- `--disable-blink-features=AutomationControlled`
- Human-like timing

...means Cloudflare and PinClicks generally don't trigger CAPTCHAs in the first place. The Brave browser already has `cf_clearance` cookies from normal browsing, so Cloudflare's bot detection considers it a legitimate user.

If a CAPTCHA does appear (e.g., after too many searches), the current behavior is that data extraction silently returns empty results and the module continues to the next keyword. There is no manual-solve prompt or exception — the module degrades gracefully.

---

## 8. Full Spy Pipeline (5 Steps)

**File:** `modules/spy.py` — `SpyModule.run()` (lines 92-143)

### Step 0: Pinterest Login

See Section 4. Opens a dedicated page, logs in, closes the page. Cookies persist in the browser context for subsequent pages.

### Step 1: Discover Keywords from Pinterest Search

**Method:** `_discover_keywords_from_search()` (lines 197-336)

Uses three discovery methods for each seed term:

**Method 1 — Related search guide pills:**
```python
guide_selectors = [
    '[data-test-id="search-guide"] a',
    '[data-test-id="search-guide"] button',
    '[data-test-id="searchGuide"] a',
    # ... 11 selectors total
]
```
Extracts text from Pinterest's suggestion pills/chips that appear above search results.

**Method 2 — Pin titles from search results:**
```python
pin_wrappers = await page.query_selector_all("div[data-test-id='pinWrapper']")
# Extract aria-label from pin links
# Extract alt text from pin images
```
Scrapes the first 25 pin titles and image alt texts from search results.

**Method 3 — Autocomplete suggestions (first 8 seeds only):**
```python
# Navigate to pinterest.com
# Click search input
# Type seed term character by character (50ms per char)
# Scrape autocomplete dropdown: [role="option"], [data-test-id*="typeahead"] li
```

**Seed terms** come from the account's Pinterest boards + niche-specific extras:

```python
# For "cooking" niche, adds:
"easy dinner recipes", "chicken recipes", "dessert ideas",
"healthy meals", "slow cooker recipes", "air fryer recipes",
"meal prep ideas", "pasta recipes", "soup recipes", "baking ideas",
# ... 20 total extras
```

### Step 2: Expand Keywords with LLM

**Method:** `_expand_keywords_with_llm()` (lines 374-411)

Sends discovered keywords to DeepSeek LLM with a prompt asking for 80 more specific keywords in the same niche. The LLM is told to generate keywords in the account's language (English or German).

### Step 3: Classify and Filter

**Method:** `_classify_and_filter()` (lines 417-481)

1. **Junk filtering** — removes keywords matching `JUNK_PATTERNS` (34 regex patterns):
   ```python
   JUNK_PATTERNS = [
       r"pin page", r"more actions", r"visit site", r"sponsored",
       r"\.com", r"\.net", r"\.org",
       r"shop now", r"learn more", r"sign up", r"log in",
       r"promoted", r"advertisement", r"loading", r"image of",
       # ...
   ]
   ```
   Also rejects keywords <4 chars or >8 words.

2. **LLM classification** — sends batches of 50 keywords to `classify_keywords()`:
   ```python
   # Returns per keyword:
   {
       "keyword": "honey garlic chicken",
       "keyword_type": "direct_recipe",     # or "roundup_listicle"
       "is_evergreen": true,
       "seasonal": null,                     # or "winter", "Q4", etc.
       "relevance_score": 85,
       "should_exclude": false
   }
   ```

3. **Filtering rules:**
   - Remove if `should_exclude=true`
   - Remove if `relevance_score < 30`
   - Remove if keyword type doesn't match config (`recipe-only`, `roundup-only`, or `all`)
   - Remove if already processed by this account
   - Remove if already used by another account in the same niche (cross-account dedup)

### Step 4: Enrich with PinClicks

See Sections 5 and 6. Logs into PinClicks, searches each keyword, extracts volume + top pin data.

### Step 5: Score and Select Final Batch

**Method:** `_score_and_select()` (lines 862-918)

1. **LLM scoring** — sends batches of 20 keywords to `score_keywords_with_pinclicks()`:
   ```python
   # Returns per keyword:
   {
       "keyword": "honey garlic chicken",
       "opportunity_score": 78,
       "reasoning": "High trending + medium competition (top pin score 65)"
   }
   ```
   Scoring criteria:
   - High trending + low competition (top pin scores <70) = highest score
   - Evergreen + medium competition = good score
   - High competition (top pin scores 85+) = lower score
   - Saturated with strong pins = lowest score

2. **Trending/Evergreen split:**
   ```python
   num_trending = int(keywords_per_batch * trends_pct / 100)
   num_evergreen = keywords_per_batch - num_trending

   selected = trending[:num_trending] + evergreen[:num_evergreen]
   ```
   Default: 30% trending / 70% evergreen (configurable per account).

3. **Save to database** via `add_keywords_to_bank()`

4. **Save JSON report** to `output/spy_report_{account_id}_{timestamp}.json`

---

## 9. Keyword Scoring Details

### Opportunity Score Formula

The opportunity score is **LLM-determined** (not a fixed formula). The LLM receives:
- Keyword text
- Keyword type (recipe vs roundup)
- Is evergreen?
- Relevance score (from classification step)
- PinClicks top score (competition level)
- Search volume

And returns a score 0-100 with reasoning.

### Junk Keyword Filtering

```python
def is_junk_keyword(text: str) -> bool:
    # 1. Check 34 regex patterns (UI artifacts, ads, short text, etc.)
    # 2. Reject if > 8 words
    # 3. Reject if < 4 characters
```

### Cross-Account Deduplication

```python
# utils/database.py
def is_keyword_used_by_other_account(keyword, current_account_id, same_niche=None):
    # Checks processed_keywords table for same keyword used by different account
    # Prevents both accounts from writing about the same topic
```

---

## 10. Content Module

**File:** `modules/content.py` — `ContentModule` class

### Pipeline per Keyword

1. **Generate article** — DeepSeek LLM with detailed SEO prompt (1000+ word recipe article)
   - Validates word count (min 1000) and keyword density (min 8 mentions)
   - Retries once if validation fails
   - Injects Table of Contents (TOC) with anchor links
2. **Generate images** — Midjourney via Discord bot (`utils/discord_mj.py`)
   - Sends `/imagine` prompt, polls for 5 min, downloads grid, crops into 4 images
3. **Create Pinterest pin** — Pillow-based 1000x1500 image (`utils/pin_builder.py`)
4. **Upload images to WordPress** — as WebP, including pin image
5. **Insert images into article HTML** — at strategic positions (after intro, before tips)
6. **Post to WordPress** — with RankMath SEO meta (focus keyword, title, description)
7. **Create recipe card** — WP Recipe Maker or Tasty Recipes shortcode
8. **Save locally** — JSON to `output/articles/`

### WordPress Integration

```python
# utils/config.py
def get_wp_credentials(account):
    prefix = account["wordpress"]["env_prefix"]  # e.g., "WP_FLAVORNEST"
    return {
        "url": get_env(f"{prefix}_URL"),
        "user": get_env(f"{prefix}_USER"),
        "app_password": get_env(f"{prefix}_APP_PASSWORD"),
    }
```

---

## 11. Pin Factory Module

**File:** `modules/pin_factory.py` — `PinFactoryModule` class

### Input Sources

1. **Spy report JSON** — `output/spy_report_{account_id}_{timestamp}.json`
2. **Database** — `keyword_bank` table (keywords with PinClicks data)

### LLM Pin Generation

For each keyword, sends PinClicks competitor data to DeepSeek:

```python
# Competitor context sent to LLM:
{
    "keyword": "honey garlic chicken",
    "top_pins": [
        "Quick Garlic Butter Chicken | score:85 | saves:12000 | repins:3400",
        "Easy Honey Garlic Chicken | score:72 | saves:8500 | repins:2100",
    ]
}
```

LLM generates per pin:
- `pin_title` — max 100 chars, inspired by top performers
- `pin_description` — 150-500 chars with keywords and CTA
- `overlay_text` — 2-5 words in ALL CAPS for pin image overlay
- `interests` — 4 Pinterest search terms
- `suggested_board` — matched against configured boards

### Scheduling

Pins are scheduled starting tomorrow, with configurable interval:

```python
# Default: every 4 hours starting at 08:00
slot_time = base_date + timedelta(hours=idx * self.schedule_interval)
pin["publish_date"] = slot_time.strftime("%m/%d/%y")
pin["publish_time"] = slot_time.strftime("%I:%M %p")
```

### CSV Export

Outputs Pinterest bulk-upload format:

| Column | Source |
|--------|--------|
| Title | LLM-generated pin title |
| Media URL | Pin image uploaded to WordPress |
| Pinterest board | Matched from config boards |
| Description | LLM-generated description |
| Link | Article URL from Module 2 |
| Publish date | Scheduled date |
| Keywords | 4 interest terms, comma-separated |

Skips pins with missing Media URL or article link.

---

## 12. Database Schema

**File:** `utils/database.py` — SQLite with WAL mode, auto-initialized on import.

**Location:** `data/pinflow.db`

### Tables

**keyword_bank** — All discovered keywords
```sql
CREATE TABLE keyword_bank (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    keyword TEXT NOT NULL,
    keyword_type TEXT DEFAULT 'direct_recipe',
    source TEXT DEFAULT 'trends',
    trend_direction TEXT,
    search_volume TEXT,
    seasonal TEXT,
    opportunity_score REAL DEFAULT 0,
    pinclicks_top_score REAL,
    pinclicks_data TEXT,          -- JSON blob with full PinClicks response
    competitor_count INTEGER DEFAULT 0,
    discovered_at TEXT NOT NULL,
    updated_at TEXT,
    UNIQUE(account_id, keyword)
);
```

**processed_keywords** — Keywords that went through Content module
```sql
CREATE TABLE processed_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    keyword TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    article_url TEXT,
    article_id INTEGER,
    pins_generated INTEGER DEFAULT 0,
    status TEXT DEFAULT 'completed',
    UNIQUE(account_id, keyword, batch_id)
);
```

**batch_history** — Run tracking
```sql
CREATE TABLE batch_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT UNIQUE NOT NULL,
    account_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    keywords_count INTEGER DEFAULT 0,
    articles_posted INTEGER DEFAULT 0,
    pins_generated INTEGER DEFAULT 0,
    csv_path TEXT,
    status TEXT DEFAULT 'running',
    settings TEXT                 -- JSON blob
);
```

**competitor_pins** — Scraped competitor pin data
```sql
CREATE TABLE competitor_pins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    competitor TEXT NOT NULL,
    pin_title TEXT,
    pin_description TEXT,
    pin_url TEXT,
    destination_url TEXT,
    board TEXT,
    keywords TEXT,               -- JSON array
    scraped_at TEXT NOT NULL
);
```

---

## 13. Configuration

**File:** `config.json` — Multi-account configuration

### Account Structure

```json
{
  "accounts": {
    "cookingfamilymeals": {
      "niche": "cooking",
      "niche_description": "easy homemade recipes for busy moms",
      "language": "en",
      "pinterest_username": "CookingFamilyMeals",
      "website_url": "https://theweekendfolio.com/",
      "website_name": "theweekendfolio.com",
      "boards": ["Chicken Recipes", "Easy Family Dinners", "..."],
      "exclude_terms": ["pork", "alcohol", "wine", "bacon", "..."],
      "midjourney_prompt": "professional food photography of {{keyword}}...",
      "spy_settings": {
        "keywords_per_batch": 25,
        "trends_percent": 30,
        "evergreen_percent": 70,
        "keyword_type": "recipe-only",
        "target_country": "US",
        "min_opportunity_score": 50
      },
      "scheduling": {
        "pins_per_day": 8,
        "schedule_days": 12,
        "first_pin_time": "08:00",
        "gap_hours": 2,
        "pins_per_keyword": 2
      },
      "wordpress": {
        "env_prefix": "WP_FLAVORNEST",
        "default_category": "Dinner",
        "author_id": 1
      },
      "pin_template": {
        "width": 1000,
        "height": 1500,
        "title_font": "playfair",
        "title_font_size": 70,
        "url_font": "lora-regular",
        "url_font_size": 35,
        "brand_text": "theweekendfolio.com"
      },
      "recipe_plugin": "tasty_recipes"
    }
  }
}
```

### Global Settings

```json
{
  "global_settings": {
    "openai_model": "deepseek-chat",
    "openai_base_url": "https://api.deepseek.com",
    "headless_browser": true,
    "scrape_delay_min": 2,
    "scrape_delay_max": 5,
    "retry_attempts": 3,
    "log_level": "INFO"
  }
}
```

### Current Accounts

| Account ID | Niche | Language | Website |
|-----------|-------|----------|---------|
| `cookingfamilymeals` | Easy homemade recipes for busy moms | English | theweekendfolio.com |
| `spoon-schmarrn` | Family-friendly cooking recipes | German | yourmidnightdesk.com |

---

## 14. Environment Variables Reference

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes | DeepSeek API key (used via OpenAI-compatible endpoint) |
| `PINTEREST_EMAIL` | No | Pinterest account email (optional — guest mode if missing) |
| `PINTEREST_PASSWORD` | No | Pinterest account password |
| `PINCLICKS_EMAIL` | No | PinClicks login email (PinClicks analysis skipped if missing) |
| `PINCLICKS_PASSWORD` | No | PinClicks login password |
| `WP_FLAVORNEST_URL` | For content | WordPress site URL (cookingfamilymeals account) |
| `WP_FLAVORNEST_USER` | For content | WordPress username |
| `WP_FLAVORNEST_APP_PASSWORD` | For content | WordPress Application Password |
| `WP_SPOONSCHMARRN_URL` | For content | WordPress site URL (spoon-schmarrn account) |
| `WP_SPOONSCHMARRN_USER` | For content | WordPress username |
| `WP_SPOONSCHMARRN_APP_PASSWORD` | For content | WordPress Application Password |
| `DISCORD_TOKEN` | For images | Discord user token for Midjourney bot |
| `DISCORD_SERVER_ID` | For images | Discord server ID |
| `DISCORD_CHANNEL_ID` | For images | Discord channel ID for `/imagine` commands |

---

## 15. Key File Paths

| File | Lines | Purpose |
|------|-------|---------|
| `pinflow.py` | 280 | CLI entry point with argparse |
| `modules/spy.py` | 989 | Spy module: Pinterest search, LLM expansion, PinClicks analysis, scoring |
| `modules/content.py` | 845 | Content module: article generation, image generation, WordPress publishing |
| `modules/pin_factory.py` | 746 | Pin factory: LLM pin optimization, board assignment, CSV export |
| `utils/browser.py` | 215 | BrowserManager: Brave integration, anti-detection, safe wrappers |
| `utils/config.py` | 76 | Configuration loader, credential accessors |
| `utils/llm.py` | 152 | DeepSeek LLM wrapper with retry logic |
| `utils/database.py` | 312 | SQLite schema, CRUD operations, cross-account dedup |
| `utils/wordpress.py` | — | WordPress REST API client |
| `utils/discord_mj.py` | — | Midjourney/Discord integration |
| `utils/pin_builder.py` | — | Pillow-based pin image renderer |
| `utils/logger.py` | — | Rich console logging |
| `config.json` | 164 | Multi-account configuration |
| `.env` | — | API keys and credentials |

---

## 16. Flow Diagram

```
python pinflow.py spy --account cookingfamilymeals --visible
                    |
                    v
        +-----------------------+
        |   BrowserManager      |
        |   (Brave, real profile)|
        +-----------+-----------+
                    |
        +-----------v-----------+
        | Step 0: Pinterest Login|  <-- PINTEREST_EMAIL/PASSWORD
        | pinterest.com/login/   |      (optional, guest mode fallback)
        +-----------+-----------+
                    |
        +-----------v-----------+
        | Step 1: Search Pinterest|
        | - Guide pills           |
        | - Pin titles/alt texts  |
        | - Autocomplete          |
        +-----------+-----------+
                    |
        +-----------v-----------+
        | Step 2: LLM Expansion  |  <-- DeepSeek: 80 more keywords
        +-----------+-----------+
                    |
        +-----------v-----------+
        | Step 3: Classify+Filter|  <-- DeepSeek: type, evergreen, score
        | - Junk patterns        |      + cross-account dedup
        | - Exclude terms        |
        +-----------+-----------+
                    |
        +-----------v-----------+
        | Step 4: PinClicks      |  <-- PINCLICKS_EMAIL/PASSWORD
        | - Login to app         |
        | - Search each keyword  |  <- _dismiss_pinclicks_popups()
        | - Extract volume+pins  |  <- _extract_pinclicks_data()
        +-----------+-----------+
                    |
        +-----------v-----------+
        | Step 5: Score+Select   |  <-- DeepSeek: opportunity_score 0-100
        | - Trending/evergreen   |
        | - Save to SQLite       |
        | - Export JSON report   |
        +-----------+-----------+
                    |
                    v
         output/spy_report_*.json
```
