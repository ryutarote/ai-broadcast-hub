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

`.github/workflows/tiktok-daily-post.yml` が同梱。
**初回投稿: 2026-05-24 18:00 JST**、以降毎日同時刻（09:00 UTC）。

その日が来るまでスケジュールトリガーは `precheck` ジョブで自動 no-op します
（workflow_dispatch + `bypass_launch_gate=yes` で先行テスト可能）。

### ワンショットセットアップ

リポジトリのオーナーが **1 度だけ** 実行:

```bash
# gh CLI を認証
gh auth login

# 動画 ZIP → GitHub Release → リポジトリ変数 VIDEOS_BUNDLE_URL まで一括
bash tiktok/tools/setup-github-release.sh
```

このスクリプトが行うこと:
1. `tiktok/output/final/*.mp4` を `/tmp/ex_gambler_kazuki_videos.zip` に圧縮
2. リポジトリの Release `v1.0-videos` に asset アップロード（既存なら上書き）
3. asset の直 URL をリポジトリ変数 `VIDEOS_BUNDLE_URL` に登録
4. 設定後の値を表示

### 残りの手動設定

リポジトリ **Settings → Secrets and variables → Actions** で:

| 種別 | 名前 | 内容 | 必須？ |
|---|---|---|---|
| Variable | `VIDEOS_BUNDLE_URL` | スクリプトが自動設定 | ✅ |
| Variable | `POSTING_MODE` | `manual` or `auto`（未設定なら manual） | 任意 |
| Secret | `TIKTOK_COOKIES_TXT` | cookies.txt の中身全文 | auto時のみ |
| Secret | `DISCORD_WEBHOOK_URL` | 通知 Webhook URL | 強推奨 |

### 投稿スケジュール

- **初回**: 2026-05-24 18:00 JST に 第0話（イントロ）を投稿
- **以降**: 毎日 18:00 JST に第N話を1本ずつ
- **完了**: 2026-06-23 頃に第30話で完結
- **時間変更**: workflow ファイルの `cron: "0 9 * * *"` を編集（UTC 表記）

### 手動実行

- 通常: **Actions タブ → "TikTok daily post" → Run workflow** → 空欄で実行
  → 次のキューを投稿
- 特定話を強制: `force_id` に `005` などを入れて実行
- 発射日前のスモークテスト: `bypass_launch_gate` に `yes` を入れて実行

### 動画 ZIP の作り直し

台本を修正して `posts.json` を変えたら、`pipeline.run` で再生成 → 同じ
スクリプトを再実行すれば Release asset と変数が更新される（冪等）。

```bash
cd tiktok
source .venv/bin/activate
python -m pipeline.run        # 必要な動画だけ再生成
bash tools/setup-github-release.sh
```

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
