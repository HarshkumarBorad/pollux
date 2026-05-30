#!/bin/bash
#
# Pollux HuggingFace Spaces entrypoint.
#
# Lifecycle:
#   1. Create the data directory (parent of chroma_data + pollux.db).
#   2. Create DB tables (idempotent).
#   3. Ingest the bundled sample knowledge IF the collection is empty.
#   4. Start the REST API on internal port 8001 in the background.
#   5. Wait for the API to be healthy.
#   6. Exec into Streamlit on port 7860 (HF Spaces' public port).
#
# Sample-knowledge ingestion is gated on chunk count rather than a marker
# file — that way wake-from-sleep doesn't re-ingest, but a rebuild (which
# wipes the ephemeral filesystem) does.
#
set -euo pipefail

DATA_DIR="${POLLUX_DATA_DIR:-/home/user/app/data}"
mkdir -p "$DATA_DIR" "${CHROMA_PERSIST_PATH:-$DATA_DIR/chroma_data}"

echo "==> Pollux HF Space starting up"
echo "    DATA_DIR              = $DATA_DIR"
echo "    CHROMA_PERSIST_PATH   = ${CHROMA_PERSIST_PATH:-(unset)}"
echo "    DATABASE_URL          = ${DATABASE_URL:-(unset)}"
echo "    HF_TOKEN set          = $([ -n "${HF_TOKEN:-}" ] && echo yes || echo no)"
echo "    OPENAI_API_KEY set    = $([ -n "${OPENAI_API_KEY:-}" ] && echo yes || echo no)"

# 1. Create DB tables (idempotent).
echo "==> Initializing database..."
python -c "
import asyncio
from core.db.migrate import create_all_tables
asyncio.run(create_all_tables())
" || { echo "ERROR: DB migration failed"; exit 1; }

# 2. Check existing chunk count. If 0 → ingest sample knowledge.
echo "==> Checking knowledge collection..."
TOTAL_CHUNKS=$(python -c "
try:
    from core.knowledge.client import get_collection
    print(get_collection().count())
except Exception as exc:
    import sys
    print(0)
" 2>/dev/null || echo "0")

if [ "$TOTAL_CHUNKS" = "0" ]; then
    echo "==> Knowledge is empty — ingesting bundled sample docs..."
    python scripts/ingest_samples.py 2>&1 || {
        echo "WARN: ingest failed; UI will still start. Manual ingest via Tickets page is possible."
    }
else
    echo "==> Knowledge already populated ($TOTAL_CHUNKS chunks); skipping ingest."
fi

# 3. Start the REST API in the background (internal only).
echo "==> Starting REST API on http://127.0.0.1:8001 (internal)..."
python -m api.server --host 127.0.0.1 --port 8001 &
API_PID=$!

# 4. Wait up to 30s for /health to return 200.
echo "==> Waiting for API to become healthy..."
for i in $(seq 1 30); do
    if python -c "
import urllib.request, sys
try:
    urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=2).read()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
        echo "==> API is healthy after ${i}s."
        break
    fi
    sleep 1
done

# Defensive: if the API died before becoming healthy, surface its logs and
# bail rather than starting a UI that will only show errors.
if ! kill -0 "$API_PID" 2>/dev/null; then
    echo "ERROR: REST API failed to start; aborting."
    exit 1
fi

# 5. Start Streamlit on port 7860 (the public HF Spaces port).
#    XSRF/CORS disabled because HF Spaces reverse-proxies the connection
#    and the XSRF cookie can't round-trip (DocuMind lesson — file uploads
#    fail with 403 otherwise).
echo "==> Starting Streamlit UI on http://0.0.0.0:7860..."
exec streamlit run ui/home.py \
    --server.port 7860 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableXsrfProtection false \
    --server.enableCORS false \
    --server.fileWatcherType none \
    --browser.gatherUsageStats false
