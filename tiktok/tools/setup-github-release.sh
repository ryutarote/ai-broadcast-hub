#!/usr/bin/env bash
# One-shot setup: upload the 31 videos as a GitHub Release asset and
# register VIDEOS_BUNDLE_URL as a repository variable so the daily
# workflow can download it.
#
# Prereqs:
#   - gh CLI authenticated: `gh auth login`
#   - The mp4 files exist under tiktok/output/final/
#   - This script runs from the repo root or anywhere; it auto-locates
#     the repo via the script's own path.
#
# Usage:
#   bash tiktok/tools/setup-github-release.sh
#
# Idempotent: re-running replaces the release asset and updates the
# variable. The release tag (v1.0-videos) is reused.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIKTOK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$TIKTOK_DIR/.." && pwd)"
cd "$REPO_ROOT"

REPO_SLUG="${GITHUB_REPO:-ryutarote/ai-broadcast-hub}"
TAG="${VIDEOS_TAG:-v1.0-videos}"
ZIP_PATH="${ZIP_PATH:-/tmp/ex_gambler_kazuki_videos.zip}"

# --- 1. Sanity checks ---
if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: gh CLI not installed. https://cli.github.com/" >&2
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: gh not authenticated. Run: gh auth login" >&2
  exit 1
fi

videos_dir="$TIKTOK_DIR/output/final"
count=$(find "$videos_dir" -maxdepth 1 -name '*.mp4' | wc -l)
if [ "$count" -lt 31 ]; then
  echo "ERROR: expected 31 mp4 files in $videos_dir, found $count" >&2
  exit 1
fi
echo "==> Found $count mp4 files in $videos_dir"

# --- 2. Build zip ---
echo "==> Packing zip -> $ZIP_PATH"
rm -f "$ZIP_PATH"
( cd "$videos_dir" && zip -j -q "$ZIP_PATH" ./*.mp4 )
zip_size=$(du -h "$ZIP_PATH" | cut -f1)
echo "    zip size: $zip_size"

# --- 3. Create or update the release ---
if gh release view "$TAG" --repo "$REPO_SLUG" >/dev/null 2>&1; then
  echo "==> Release $TAG already exists; replacing asset"
  gh release upload "$TAG" "$ZIP_PATH" --clobber --repo "$REPO_SLUG"
else
  echo "==> Creating release $TAG"
  gh release create "$TAG" "$ZIP_PATH" \
      --repo "$REPO_SLUG" \
      --title "卒業計画 動画素材 (31本)" \
      --notes "Auto-uploaded video bundle for the @ex_gambler_kazuki daily posting workflow. Re-uploaded by tiktok/tools/setup-github-release.sh."
fi

# --- 4. Resolve the asset download URL ---
ASSET_URL=$(gh release view "$TAG" --repo "$REPO_SLUG" --json assets \
    --jq '.assets[] | select(.name=="'"$(basename "$ZIP_PATH")"'") | .url')
if [ -z "$ASSET_URL" ]; then
  echo "ERROR: failed to resolve asset URL from release $TAG" >&2
  exit 1
fi
echo "==> Asset URL: $ASSET_URL"

# --- 5. Register the repo variable ---
echo "==> Setting repository variable VIDEOS_BUNDLE_URL"
gh variable set VIDEOS_BUNDLE_URL --body "$ASSET_URL" --repo "$REPO_SLUG"

# --- 6. Sanity: print current variable ---
gh variable get VIDEOS_BUNDLE_URL --repo "$REPO_SLUG" || true

echo ""
echo "✅ Done."
echo "   Next scheduled post: 2026-05-24 18:00 JST (09:00 UTC)"
echo "   To smoke-test before launch:"
echo "     gh workflow run tiktok-daily-post.yml -f bypass_launch_gate=yes --repo $REPO_SLUG"
