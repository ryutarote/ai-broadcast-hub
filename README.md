# AI系発信ハブ Codex Automations

Codex Thread automationで運用する「AI系発信ハブ」のセットアップ一式。

## 使い方

1. Codexで新しいThreadを作る。
2. `thread_seed_prompt.md` の内容を最初のメッセージとして送る。
3. Thread automationを作成し、スケジュールを毎日 08:00 に設定する。
4. automationのプロンプトに `daily_thread_automation_prompt.md` を貼る。
5. 週次レビューが必要な場合は、別ThreadまたはStandalone automationに `weekly_standalone_review_prompt.md` を貼る。

## Codex AutomationsのX投稿ワークフロー

Codex Automationsそのものを発信テーマにする場合は、以下を使う。

1. `codex_automations_x_workflow.md` で運用設計を確認する。
2. Thread automationまたはStandalone automationを作成する。
3. automationのプロンプトに `x_codex_automations_daily_prompt.md` を貼る。
4. 出力されたX案を確認し、採用/不採用と反応を `material_bank_sources.md` に追記する。
5. 週次で `weekly_standalone_review_prompt.md` を使い、反応がよい切り口を翌週の条件に戻す。

## X API連携用URL

GitHub Pagesで公開するX API申請・OAuth設定用の静的ページ。

- Website URL: `https://ryutarote.github.io/ai-broadcast-hub/`
- Callback URI / Redirect URL: `https://ryutarote.github.io/ai-broadcast-hub/api/auth/x/callback/`

`index.html` はX Developer PortalのWebsite URL用、`api/auth/x/callback/index.html` はOAuth Callback URL用。

## 運用対象

- 発信先: X、note/ブログ
- 読者: 非エンジニア、AI活用に関心がある事業側・企画側・個人
- 役割: AI翻訳役。技術ニュースを「自分の仕事や生活にどう効くか」へ翻訳する
- 日次成果物: 切り口3案、X投稿ドラフト2案、note/ブログ骨子1案、Triage向け要約
- 週次成果物: 投稿傾向レビュー、反応仮説、翌週の配分方針

## 会話でのフィードバック例

- `2案目の方向で、もう少し失敗談を入れて`
- `最近Anthropic系のネタが多いから、今週はOpenAI/Google系に寄せて`
- `専門用語が多いので、たとえ話を増やして`
- `Xは短く刺す。noteは実務寄りに厚くして`

フィードバックは同じThreadに残す。翌日のautomationは過去2週間の発信履歴と直近フィードバックを読み、切り口やトーンに反映する。

## 素材バンク連携

Notion、Gmail、Slack、Microsoft Suiteなどのプラグインが使える環境では、`material_bank_sources.md` の参照先を実際のページ名・チャンネル名・フォルダ名に置き換える。

プラグインが未接続の場合は、同ファイルに手動で素材メモを追記して代替する。

## TikTok 全自動動画生成

`tiktok/` 配下に、ろてじん（AivisSpeech / Style-Bert-VITS2 JP-Extra）で
30本の縦型 mp4 を全自動生成するパイプラインを同梱。

```bash
cd tiktok
bash tools/setup.sh                                # 初回のみ
source .venv/bin/activate
python -m pipeline.run --id 001                    # 1本テスト
python -m pipeline.run                             # 30本一括
```

詳細は `tiktok/README.md` を参照。
