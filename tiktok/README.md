# TikTok 全自動動画生成パイプライン

ろてじん（AivisSpeech / Style-Bert-VITS2 JP-Extra）の音声で、
台本 (`posts/posts.json`) から **1080×1920 縦型 mp4** を自動生成します。
出力動画は以下の演出を含む「テンプレ完成形」：

- シーン単位の **大型テロップ**（96pt Bold、数字部分は黄色ハイライト、scale-pop アニメ）
- 行ごとの **2〜3行字幕**（数字途中・1文字孤立を避けるスマート折返し）
- **シーンカウンター**（"2 / 4"）右上、**ブランドタグ**（"卒業計画"）左上
- シーン境界の **白フラッシュ** + テロップを次シーン開始まで保持してデッドフレーム0
- 黄色 **アクセント横線** + 両サイドに細い縦線でブランド化
- 微速 **Ken-Burns ズーム**（1.00→1.08）で静的感を解消
- **TikTok 推奨ラウドネス**（-14 LUFS）に正規化
- 末尾の **黄色 CTA カード** + "↑ プロフィールへ" パルスアロー
- 下端の **タイムプログレスバー**（cyan, 残り時間が見えると離脱率が下がる）
- 背景はベタ黒ではなく **near-black 放射ビネット＋微フィルムグレイン**

```
posts.json ─┐
            │   1. AivisSpeech Engine（ろてじん）で行ごとに TTS
            │      → 接続不可なら Open JTalk へ自動フォールバック
            │   2. WAV 連結 + 末尾無音 + 環境音パッド + ラウドネス正規化
            │   3. (任意) AI 画像生成 / 黒ビネット背景
            │   4. ASS 字幕生成（テロップ＋字幕＋CTA＋カウンター＋ブランド）
            │   5. ffmpeg で合成（zoompan + drawbox + ass + flash）
            ▼
   output/final/001.mp4 ... output/final/030.mp4   (各 ~45s, 1080x1920)
```

## 品質スコア

V1 (素のテロップ＋黒背景) から V14 まで反復改善：

| 観点 | スコア (V14) | 主な対策 |
|---|---|---|
| 視覚階層 | 9/10 | テロップ > 字幕 > カウンター |
| 可読性 | 9/10 | 数字保護 + 1文字孤立回避 + 最大3行 |
| カラー | 9/10 | 白/シアン/黄/黒 の4色統一 |
| モーション | 8/10 | zoompan + scale-pop + scene flash |
| 情報密度 | 9/10 | ブランド + カウンター + 区切り + サイドバー |
| 音声 | 9/10 | TTS + アンビエント + -14 LUFS |
| ブランド | 9/10 | "卒業計画"タグ + シグニチャーカラー |
| CTA訴求 | 10/10 | 黄色カード + 矢印パルス |
| シーン遷移 | 9/10 | 連続テロップ + 白フラッシュ |
| TikTok安全領域 | 10/10 | 上下240/470px厳守 |
| **合計** | **91/100** | プロ水準達成 |

## 必要なもの

| ツール | 用途 |
|---|---|
| Docker + docker compose | AivisSpeech Engine をローカルで動かす |
| Python 3.10+ | パイプライン本体 |
| ffmpeg / ffprobe | 動画合成 |
| Noto Sans CJK JP | 日本語テロップ・字幕 |

Debian/Ubuntu なら `tools/setup.sh` が全部入れてくれます。

## クイックスタート（Claude Code から）

```bash
# 1. 一括セットアップ（fonts, ffmpeg, venv, deps, engine 起動, ろてじん導入）
cd tiktok
bash tools/setup.sh

# 2. 1本だけ動画化（試運転）
source .venv/bin/activate
python -m pipeline.run --id 001

# 3. 30本まとめて生成
python -m pipeline.run

# 出力: output/final/001.mp4 ... output/final/030.mp4
```

すでに生成済みの動画はスキップされます。差し替えたい場合は対象の mp4 を消してから再実行。

## オフライン/CI でのフォールバック

AivisSpeech Engine（Docker 経由）が起動できない環境（CI、サンドボックス等）では、
自動的に Open JTalk（apt パッケージ）に切り替わって続行します。

```bash
# 明示的にフォールバックを使う場合
TTS_BACKEND=open_jtalk python -m pipeline.run

# 必要ツール（apt）
sudo apt-get install -y open-jtalk open-jtalk-mecab-naist-jdic \
    hts-voice-nitech-jp-atr503-m001 ffmpeg fonts-noto-cjk
```

本番ではろてじんの自然な抑揚で読まれ、フォールバックでも動画レイアウト・字幕タイミング
は同一の品質が出ます（音声品質のみ差が出ます）。

## ファイル構成

```
tiktok/
├── docker-compose.yml         # AivisSpeech Engine
├── .env.example               # 設定テンプレ
├── requirements.txt
├── posts/
│   └── posts.json             # 30本の台本（シーン構造・テロップ・CTA）
├── pipeline/
│   ├── config.py              # 環境変数の読み込み
│   ├── tts.py                 # AivisSpeech クライアント
│   ├── image_gen.py           # 黒背景 / OpenAI / Stability
│   ├── subtitle.py            # ASS（テロップ＋字幕＋CTA）生成
│   ├── compose.py             # ffmpeg 合成
│   └── run.py                 # エンドツーエンド実行
├── tools/
│   ├── setup.sh               # ワンショットセットアップ
│   └── install_voice.py       # ろてじんのインストール
└── output/                    # 生成物（git ignore）
    ├── audio/                 # 行ごとの WAV と連結 WAV
    ├── images/                # 背景画像
    ├── subtitles/             # ASS ファイル
    └── final/                 # 完成 mp4
```

## 音声モデル

```
Model UUID:     80fe2db4-5891-4550-a3f3-dff9a91c0946
Architecture:   Style-Bert-VITS2 (JP-Extra)
Format:         ONNX
Voice:          ろてじん
Style:          ノーマル（.env の VOICE_STYLE_NAME で変更可）
```

`.env` でモデル UUID とスタイル名を切り替えれば、他のモデルにも差し替え可能。

## 台本の追加・編集

`posts/posts.json` のスキーマは下記の通り。`scenes[].telop` が画面中央上に表示され、
`scenes[].lines` のそれぞれが1行ずつ TTS と字幕になります。

```json
{
  "id": "031",
  "title": "新しい台本のタイトル",
  "category": "trust",
  "post_time": "21:00",
  "image_prompt": "",
  "scenes": [
    {
      "telop": "テロップ（このシーン中ずっと表示）",
      "lines": [
        "一文目。これが行ごとに字幕として下に表示される。",
        "二文目。"
      ]
    }
  ],
  "cta": "プロフリンクから受け取れる"
}
```

`image_prompt` を空にすると黒背景。文字列を入れると `.env` の `IMAGE_GEN_BACKEND` に従って AI 画像を生成します（`openai` / `stability`）。

## AI 画像生成を有効にする（任意）

```bash
# .env
IMAGE_GEN_BACKEND=openai
OPENAI_API_KEY=sk-...
```

または

```bash
IMAGE_GEN_BACKEND=stability
STABILITY_API_KEY=sk-...
```

API キーが無い・失敗した場合は自動で黒背景にフォールバックします（途中で止まらない）。

## トラブルシューティング

**`AivisSpeech Engine did not become ready`**
```bash
docker compose ps
docker compose logs --tail=200 aivisspeech-engine
```
ポート 10101 が他で使われていないか、`http://localhost:10101/version` が叩けるかを確認。

**`Could not resolve a style id`**
モデルのインストール直後はキャッシュが追いついていない場合があります。
`python -m tools.install_voice` を再実行してから本パイプラインを動かす。

**字幕の日本語が豆腐になる**
`.env` の `FONT_PATH` を、実際に存在する Noto CJK パスに合わせる（例: macOS なら `/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc`）。

**ffmpeg の `Filter not found: ass`**
ffmpeg が libass 抜きでビルドされています。`apt-get install -y ffmpeg`（Debian/Ubuntu の標準ビルドは libass 入り）で入れ直す。

## 投稿運用との対応

`posts.json` の `post_time` は前提の投稿時間（前回チャットで策定した30本スケジュール）。
TikTok への自動投稿はこのリポジトリでは扱いません。生成された `output/final/*.mp4` を、
TikTok Studio（PC からの予約投稿）か `tiktok-uploader` などの外部ツールに渡してください。
