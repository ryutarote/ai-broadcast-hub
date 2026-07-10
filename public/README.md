# 卒業計画 動画素材 (Public)

`@ex_gambler_kazuki` の TikTok 投稿に使う 31 本の縦型動画 (1080×1920 / mp4)。

## アクセス URL

GitHub Pages 経由（推奨・公開）:

- 一覧: `https://ryutarote.github.io/ai-broadcast-hub/public/videos/`
- 第N話: `https://ryutarote.github.io/ai-broadcast-hub/public/videos/NNN.mp4`
  - 例: `000.mp4`（イントロ）, `001.mp4`〜`030.mp4`

Raw URL（リポジトリから直接）:

- `https://github.com/ryutarote/ai-broadcast-hub/raw/main/public/videos/NNN.mp4`

## ファイル一覧

| ID | 話数 | 尺 | 説明 |
|---|---|---|---|
| 000 | イントロ | 63s | 借金420万→0円。3年で完済した話 |
| 001 | 第1話 | 45s | 卒業1247日目、コンビニで思い出した |
| 002 | 第2話 | 56s | 借金420万→0円、最初の30日 |
| 003 | 第3話 | 64s | 180日目に再発した夜 |
| 004 | 第4話 | 52s | 嫁に告白した夜 |
| 005 | 第5話 | 56s | 親に頭下げた日のメモ |
| 006 | 第6話 | 58s | 100人に聞いた共通点 |
| 007 | 第7話 | 56s | 仕組みで降りた4つ |
| 008 | 第8話 | 54s | 駐車場で1時間動けなかった |
| 009 | 第9話 | 54s | 給料明細を嫁に見せた日 |
| 010 | 第10話 | 47s | 卒業1000日達成の朝 |
| 011 | 第11話 | 59s | あと1回が終わらない数学的理由 |
| 012 | 第12話 | 53s | ジャグラー勝って24万損 |
| 013 | 第13話 | 54s | 給料日に必ず負ける脳内 |
| 014 | 第14話 | 61s | 副業始める奴との違い |
| 015 | 第15話 | 59s | ドーパミンの置換 |
| 016 | 第16話 | 65s | 借金を返す発想で詰む理由 |
| 017 | 第17話 | 57s | 期待値が得意なお前ら |
| 018 | 第18話 | 58s | 次で取り返すの脳内 |
| 019 | 第19話 | 68s | 負ける脳と稼ぐ脳の回路 |
| 020 | 第20話 | 63s | 嫁9割気づいてる |
| 021 | 第21話 | 52s | 給料日朝の3作業 |
| 022 | 第22話 | 74s | 給料50%自動送金の手順 |
| 023 | 第23話 | 60s | ホールを避けるルート |
| 024 | 第24話 | 77s | ホール代替10選 |
| 025 | 第25話 | 61s | 家族告白3行台本 |
| 026 | 第26話 | 61s | 借金返済シミュレーター |
| 027 | 第27話 | 67s | 副業90日ルート |
| 028 | 第28話 | 81s | 再発前兆10サイン |
| 029 | 第29話 | 61s | 仲間を切る順番 |
| 030 | 第30話 | 79s | Discord中身を見せる ⟨完結⟩ |

## 一括ダウンロード

curl でまとめて取得:

```bash
mkdir -p ~/Downloads/ex_gambler_kazuki
for i in $(printf "%03d\n" {0..30}); do
  curl -fsSL -o "$HOME/Downloads/ex_gambler_kazuki/${i}.mp4" \
    "https://ryutarote.github.io/ai-broadcast-hub/public/videos/${i}.mp4"
  echo "downloaded ${i}.mp4"
done
```

または GitHub Web UI から個別にダウンロード（各ファイルの "Download raw file" ボタン）。

## 仕様

- 解像度: 1080×1920 (vertical 9:16)
- 動画: H.264 / AAC mono 44.1kHz / 30fps
- 容量: 5〜9 MB 各、合計 217 MB

## 関連

- 投稿運用: [`/tiktok/POSTING.md`](../tiktok/POSTING.md)
- キャプション集: [`/tiktok/captions.md`](../tiktok/captions.md)
- 生成パイプライン: [`/tiktok/README.md`](../tiktok/README.md)
