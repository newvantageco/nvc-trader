#!/bin/bash
# NVC Trader — Fly.io deployment script
# Run AFTER: fly auth login
# Usage: ./deploy-fly.sh

set -e

APP_NAME="nvc-trader-engine"
REGION="lhr"  # London

echo "=== NVC Trader — Fly.io Deploy ==="
echo ""

# 1. Create app if it doesn't exist
echo "[1/6] Creating Fly app..."
fly apps create $APP_NAME --org personal 2>/dev/null || echo "App already exists, continuing..."

# 2. Create persistent volume for model cache (FinBERT ~1.5GB)
echo "[2/6] Creating persistent volume for model cache..."
fly volumes create nvc_model_cache \
  --app $APP_NAME \
  --region $REGION \
  --size 5 \
  2>/dev/null || echo "Volume already exists, continuing..."

# 3. Set secrets (REQUIRED — fill these in first!)
echo "[3/6] Setting secrets..."
echo ""
echo "  ⚠️  You must set your API keys. Edit this script or run these manually:"
echo ""
echo "  fly secrets set ANTHROPIC_API_KEY=sk-ant-..."
echo "  fly secrets set OANDA_API_KEY=your-oanda-key"
echo "  fly secrets set OANDA_ACCOUNT_ID=001-001-XXXXXXX-001"
echo "  fly secrets set OANDA_LIVE=false"
echo "  fly secrets set SUPABASE_URL=https://xxx.supabase.co"
echo "  fly secrets set SUPABASE_SERVICE_ROLE_KEY=eyJ..."
echo "  fly secrets set NEWS_API_KEY=your-newsapi-key"
echo ""

# Check if ANTHROPIC_API_KEY is set
if [ -n "$ANTHROPIC_API_KEY" ]; then
  fly secrets set \
    ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
    OANDA_API_KEY="${OANDA_API_KEY:-}" \
    OANDA_ACCOUNT_ID="${OANDA_ACCOUNT_ID:-}" \
    OANDA_LIVE="${OANDA_LIVE:-false}" \
    SUPABASE_URL="${SUPABASE_URL:-}" \
    SUPABASE_SERVICE_ROLE_KEY="${SUPABASE_SERVICE_ROLE_KEY:-}" \
    NEWS_API_KEY="${NEWS_API_KEY:-}" \
    MAX_RISK_PER_TRADE_PCT="${MAX_RISK_PER_TRADE_PCT:-1.0}" \
    MAX_DAILY_DRAWDOWN_PCT="${MAX_DAILY_DRAWDOWN_PCT:-3.0}" \
    --app $APP_NAME
  echo "  ✓ Secrets set from environment"
else
  echo "  ℹ️  Skipping auto-set (ANTHROPIC_API_KEY not in environment)"
fi

# 4. Deploy
echo "[4/6] Building and deploying (this takes ~5 minutes for first build)..."
fly deploy --app $APP_NAME --dockerfile Dockerfile.fly --remote-only

# 5. Scale to 1 machine (always on)
echo "[5/6] Ensuring machine is always running..."
fly scale count 1 --app $APP_NAME

# 6. Show status
echo "[6/6] Deployment complete!"
echo ""
fly status --app $APP_NAME
echo ""
echo "=== DONE ==="
echo ""
echo "Dashboard:  https://dashboard-nvc-labs.vercel.app"
echo "API:        https://$APP_NAME.fly.dev"
echo "Health:     https://$APP_NAME.fly.dev/health"
echo "Logs:       fly logs --app $APP_NAME"
echo ""
echo "Trigger a manual agent cycle:"
echo "  curl -X POST https://$APP_NAME.fly.dev/agent/run"
