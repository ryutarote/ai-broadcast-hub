# TikTok 自動投稿 — @ex_gambler_kazuki

`output/final/` の31本の動画を **1本目から1日1本** 順に `@ex_gambler_kazuki` へ
投稿するための運用システム。

```
posts.json + captions.md
        │
        ▼
posting/state.json (queue / posted / history)
        │
        ▼  毎日 21:00 JST
posting/run.py  ─┬─ mode=manual:  動画 + キャプションを Discord に投げる
                 │                 → 運営者が手動投稿
                 │
                 └─ mode=auto:    tiktok-uploader が直接投稿
                                   (Cookies必須・TikTok UI変更で壊れやすい)
```

## モード選択

| モード | 安全性 | 自動度 | 推奨ケース |
|---|---|---|---|
| **manual**（デフォルト）| ◎ | △ 通知のみ | アカウント保護優先・手動の数分は許容できる |
| **auto** | △ TikTok ToS 微妙 / BAN リスク | ◎ 完全自動 | 検証アカウント or リスク許容できる場合 |

最初の **2週間は manual** で運用して、Discord 通知から「動画 + キャプション」を
コピペで投稿することを強く推奨。シリーズが軌道に乗って投稿フローが安定したら
`auto` への切り替えを検討。

---

## ローカル運用（cron / systemd timer）

最も信頼できる構成。動画は自分のマシンに既にあるので、追加ストレージ不要。

### 1. 初期セットアップ

```bash
cd ai-broadcast-hub/tiktok
bash tools/setup.sh                # venv / ffmpeg / engine
cp .env.example .env               # 設定編集
```

`.env` に追記:

```
# 投稿先アカウント
TIKTOK_USERNAME=ex_gambler_kazuki

# manual = 通知のみ / auto = tiktok-uploader 起動
POSTING_MODE=manual

# Discord 通知（推奨）
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# 初回投稿に 000（イントロ）を含めるか
INCLUDE_INTRO=true
```

### 2. cron 登録（毎日 21:00 JST）

```bash
crontab -e
# ↓ を追記
0 21 * * * /home/user/ai-broadcast-hub/tiktok/tools/cron-daily.sh
```

スクリプトが state.json を更新し、Discord に通知します。

### 3. 手動操作

```bash
# 今日の投稿候補を見るだけ（実投稿しない）
python -m posting.run --dry-run

# 強制的に特定の話を投稿（再試行など）
python -m posting.run --id 003

# キューを最初から組み直す（履歴は保持される）
python -m posting.run --reset

# 投稿状況を確認
cat posting/state.json | python -m json.tool
```

---

## auto モード（tiktok-uploader）の準備

### Cookies 取得

1. Chromium / Brave で `https://www.tiktok.com/@ex_gambler_kazuki` にログイン
2. 拡張機能 [Cookie-Editor](https://cookie-editor.com/) などで `tiktok.com` の
   全 cookies を **Netscape 形式** でエクスポート
3. `tiktok/secrets/cookies.txt` に保存（パーミッション 600 推奨）

```bash
mkdir -p tiktok/secrets
chmod 700 tiktok/secrets
# cookies.txt をこの場所に配置
chmod 600 tiktok/secrets/cookies.txt
```

### auto モード有効化

`.env`:

```
POSTING_MODE=auto
TIKTOK_COOKIES_PATH=/home/user/ai-broadcast-hub/tiktok/secrets/cookies.txt
```

動作確認:

```bash
python -m posting.run --dry-run        # ← 投稿はしない、対象だけ確認
python -m posting.run --id 000         # ← 実投稿（イントロから）
```

トラブル時の典型対処:
- **cookies expired**: 同じ手順で取り直し
- **uploader フレーム検出失敗**: `tiktok-uploader` のバージョンを上げる
  (`pip install -U tiktok-uploader`)、それでもダメなら manual に切替
- **アカウント警告 / 一時停止**: 即 manual に戻す。Caps lock キー多用や
  超短時間連投はリスク高い

---

## GitHub Actions 運用（クラウド完全自動）

`.github/workflows/tiktok-daily-post.yml` が同梱されており、`main` ブランチに
マージするだけで毎日 12:00 UTC（21:00 JST）に動作します。

### 必要な Secrets / Variables 設定

リポジトリ **Settings → Secrets and variables → Actions**:

| 種別 | 名前 | 内容 |
|---|---|---|
| Secret | `TIKTOK_COOKIES_TXT` | cookies.txt の中身全文（auto モード時のみ必要）|
| Secret | `DISCORD_WEBHOOK_URL` | 通知用 Webhook URL（強推奨）|
| Variable | `POSTING_MODE` | `manual` or `auto`（未設定なら manual） |
| Variable | `VIDEOS_BUNDLE_URL` | 31本の mp4 を ZIP にまとめた URL（後述）|

### 動画ファイルの取り回し

`output/final/` は `.gitignore` に入っているので、CI ジョブは動画を手元に
持ちません。3 つの選択肢:

1. **`VIDEOS_BUNDLE_URL` で配信** — `output/final/` を zip にして GitHub
   Release / S3 / Dropbox / Google Drive の直リンクに置き、変数に URL を
   登録。Actions が毎回ダウンロードして展開。**推奨**。
2. **git-lfs で動画を版管理** — `output/` のうち `*.mp4` だけ LFS で追跡。
3. **クラウドストレージ from script** — 投稿スクリプトを拡張して S3 等から
   ダイレクトに取得。

最速なのは選択肢 1。

```bash
# zip を作って GitHub Release にアップ
cd tiktok
zip -j /tmp/ex_gambler_kazuki_videos.zip output/final/*.mp4
gh release create v1.0-videos /tmp/ex_gambler_kazuki_videos.zip \
  --title "卒業計画 動画素材" --notes "31本 / 1080x1920 / mp4"
# 出力されたアセット URL を VIDEOS_BUNDLE_URL に設定
```

### 手動実行

リポジトリ **Actions タブ → "TikTok daily post" → Run workflow**。
`force_id` を指定すれば任意の話を投稿可能。

---

## 公式 TikTok Content Posting API（理想形）

unofficial uploader より遥かに安全だが、TikTok for Developers での
**アプリ審査 + Login Kit 連携 + Sandbox → Production 移行** が必要なので
申請から最低 2〜3週間かかる。

### 移行手順サマリ

1. https://developers.tiktok.com/ でアプリ作成
2. **Content Posting API** スコープを申請
3. OAuth 2.0 で `video.upload` 権限のトークンを取得
4. `POST /v2/post/publish/inbox/video/init/` → アップロード URL を取得
5. mp4 をその URL に PUT
6. `POST /v2/post/publish/status/fetch/` でステータス確認

承認が下りたら `posting/uploader.py` に `official_upload()` を追加して
mode `official` を新設、Actions secret に `TIKTOK_ACCESS_TOKEN` を入れる
だけで切り替え可能な構造になっている。

---

## state.json の中身

```json
{
  "queue":  ["000", "001", "002", ..., "030"],
  "posted": ["000"],
  "history": [
    {"id": "000", "at": "2026-05-17T12:00:03Z",
     "status": "posted", "url": "", "note": "manual"}
  ]
}
```

- `queue`: 投稿順（最初の run で captions.md から自動構築）
- `posted`: 完了済み（次回は queue 内の未 posted を選ぶ）
- `history`: 全試行ログ（失敗 / 成功）

`--reset` で queue だけ作り直せる（posted/history は保持）。

---

## 監視

- Discord に成功/失敗が流れる（embed カラー: シアン=成功 / 赤=失敗）
- 失敗時は動画ファイル本体が Discord に添付される（手動投稿可能に）
- `posting/logs/YYYY-MM-DD.log` にも残る
- 連続 2 日失敗したら手動確認 → cookies 再発行 or manual に降格

---

## トラブルシュート

| 症状 | 原因 | 対処 |
|---|---|---|
| 「動画ファイルが見つからない」 | `output/final/{id}.mp4` 不在 | `python -m pipeline.run --id NNN` で再生成 |
| Discord に何も来ない | `DISCORD_WEBHOOK_URL` 未設定 | `.env` か Secret に追加 |
| auto モードが毎回失敗 | cookies 期限切れ / UI 変更 | 取り直し → ダメなら manual に戻す |
| 同じ話が 2 回投稿された | state.json が壊れた | `state.json` を直接編集 / `--reset` |
