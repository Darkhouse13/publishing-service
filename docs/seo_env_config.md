# SEO Environment Config

This project uses two JSON environment variables for SEO link automation during publish.

## `CROSS_BLOG_LINK_MAP_JSON`

Purpose:
- Trigger phrase to sibling-blog URL mapping for cross-blog internal backlinks.

Shape:
```json
{
  "dark mode desk setup": "https://yourmidnightdesk.com/dark-mode-desk-setup-guide",
  "patio furniture": "https://yoursundaypatio.com/patio-furniture-layout-ideas",
  "weekend routine": "https://theweekendfolio.com/weekend-routine-template"
}
```

Rules:
- Top-level object.
- Keys are trigger phrases.
- Values are absolute `http://` or `https://` URLs.
- First match per trigger only, capped total backlinks per post.
- Same-domain targets are skipped to keep links truly cross-blog.
- If trigger replacement inserts no sibling-blog link, publish flow appends one deterministic fallback sibling backlink when at least one eligible sibling URL exists.

## `SEO_EXTERNAL_SOURCES_JSON`

Purpose:
- Trusted authority sources used when a generated post has no external link.

Shape:
```json
{
  "default": [
    {"anchor": "official guidance", "url": "https://www.consumerreports.org/"}
  ],
  "THE_SUNDAY_PATIO": [
    {"anchor": "USDA planting guidance", "url": "https://planthardiness.ars.usda.gov/"}
  ],
  "YOUR_MIDNIGHT_DESK": [
    {"anchor": "ergonomics reference", "url": "https://www.osha.gov/ergonomics"}
  ],
  "THE_WEEKEND_FOLIO": [
    {"anchor": "public travel advisory", "url": "https://travel.state.gov/"}
  ]
}
```

Rules:
- Top-level object.
- Optional blog-suffix keys plus optional `default`.
- Each key maps to a list of objects.
- Each object must include `url` (absolute `http/https`).
- `anchor` is optional and defaults to `official guidance`.

## Publish Warnings You May See

- Missing or invalid `CROSS_BLOG_LINK_MAP_JSON`: cross-blog trigger injection skipped.
- Valid map but only same-domain targets: no sibling fallback can be added; same-domain entries are ignored.
- Same-domain cross-blog target: skipped to avoid non-sibling linking.
- Missing or invalid `SEO_EXTERNAL_SOURCES_JSON`: external authority link not auto-added.
- Malformed authority URL: skipped.
- Category lookup failure / missing category slug: internal link falls back to homepage.
