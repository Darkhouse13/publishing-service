#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost}"

echo "=== Publishing Service Smoke Test ==="
echo "Target: $BASE_URL"
echo ""

# 1. Health check
echo -n "Health check... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/v1/health")
if [ "$STATUS" = "200" ]; then
    echo "✓ OK ($STATUS)"
else
    echo "✗ FAILED ($STATUS)"
    exit 1
fi

# 2. Frontend loads
echo -n "Frontend loads... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/dashboard")
if [ "$STATUS" = "200" ]; then
    echo "✓ OK ($STATUS)"
else
    echo "✗ FAILED ($STATUS)"
    exit 1
fi

# 3. Blogs API
echo -n "GET /api/v1/blogs... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/v1/blogs")
if [ "$STATUS" = "200" ]; then
    echo "✓ OK ($STATUS)"
else
    echo "✗ FAILED ($STATUS)"
    exit 1
fi

# 4. Create a test blog
echo -n "POST /api/v1/blogs (create)... "
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/api/v1/blogs" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "Smoke Test Blog",
        "url": "https://example.com",
        "wp_username": "test",
        "wp_application_password": "test-password"
    }')
BODY=$(echo "$RESPONSE" | head -n -1)
STATUS=$(echo "$RESPONSE" | tail -1)
if [ "$STATUS" = "201" ]; then
    BLOG_ID=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
    echo "✓ OK ($STATUS) id=$BLOG_ID"
else
    echo "✗ FAILED ($STATUS)"
    echo "$BODY"
    exit 1
fi

# 5. Get credentials API
echo -n "GET /api/v1/credentials... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/v1/credentials")
if [ "$STATUS" = "200" ]; then
    echo "✓ OK ($STATUS)"
else
    echo "✗ FAILED ($STATUS)"
    exit 1
fi

# 6. Runs API
echo -n "GET /api/v1/runs... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/v1/runs")
if [ "$STATUS" = "200" ]; then
    echo "✓ OK ($STATUS)"
else
    echo "✗ FAILED ($STATUS)"
    exit 1
fi

# 7. Articles API
echo -n "GET /api/v1/articles... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/api/v1/articles")
if [ "$STATUS" = "200" ]; then
    echo "✓ OK ($STATUS)"
else
    echo "✗ FAILED ($STATUS)"
    exit 1
fi

# 8. Cleanup — delete test blog
if [ -n "${BLOG_ID:-}" ]; then
    echo -n "DELETE /api/v1/blogs/$BLOG_ID (cleanup)... "
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE_URL/api/v1/blogs/$BLOG_ID")
    if [ "$STATUS" = "204" ]; then
        echo "✓ OK ($STATUS)"
    else
        echo "⚠ Cleanup returned $STATUS (non-fatal)"
    fi
fi

echo ""
echo "=== All checks passed ==="
