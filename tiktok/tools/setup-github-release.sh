#!/usr/bin/env bash
# One-shot setup: upload the 31 videos as a GitHub Release asset and
# register VIDEOS_BUNDLE_URL as a repository variable so the daily
# workflow can download it.
#
# Two ways to provide the videos:
#
#   1. Build from local mp4s (default):
#        bash tiktok/tools/setup-github-release.sh
#      requires tiktok/output/final/*.mp4 to exist on disk.
#
#   2. Use an already-built ZIP (e.g. one received from Claude):
#        ZIP_PATH=~/Downloads/ex_gambler_kazuki_videos.zip \
#            bash tiktok/tools/setup-github-release.sh
#      Skips repacking; uploads the file as-is.
#
# Prereqs:
#   - gh CLI authenticated: `gh auth login`
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

# --- 2. Resolve the ZIP: use provided one, else build from mp4s ---
if [ -f "$ZIP_PATH" ]; then
  echo "==> Using existing ZIP at $ZIP_PATH"
else
  videos_dir="$TIKTOK_DIR/output/final"
  if [ ! -d "$videos_dir" ]; then
    cat >&2 <<EOF
ERROR: video source not found.
  Looked for an existing ZIP at: $ZIP_PATH
  And mp4 files under:            $videos_dir

Either:
  - Place the ZIP at $ZIP_PATH, or set ZIP_PATH=/path/to/zip and re-run, or
  - Place all 31 mp4 files under $videos_dir and re-run.
EOF
    exit 1
  fi
  count=$(find "$videos_dir" -maxdepth 1 -name '*.mp4' | wc -l | tr -d ' ')
  if [ "$count" -lt 31 ]; then
    echo "ERROR: expected 31 mp4 files in $videos_dir, found $count" >&2
    exit 1
  fi
  echo "==> Found $count mp4 files in $videos_dir"
  echo "==> Packing zip -> $ZIP_PATH"
  rm -f "$ZIP_PATH"
  ( cd "$videos_dir" && zip -j -q "$ZIP_PATH" ./*.mp4 )
fi

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
ASSET_BASENAME="$(basename "$ZIP_PATH")"
ASSET_URL=$(gh release view "$TAG" --repo "$REPO_SLUG" --json assets \
    --jq ".assets[] | select(.name==\"$ASSET_BASENAME\") | .url")
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
