# Develop/

開発中のプロジェクト群を配置するルート。`main` ブランチの既存資産（X API 連携など）と切り分けて、新規プロジェクトはこのディレクトリ配下に置く。

## プロジェクト一覧

| プロジェクト | パス | 概要 | ステータス |
|---|---|---|---|
| **Aegis** | [Aegis/](./Aegis/) | Claude Code時代の中小企業向けマネージドAIオペレーションサービス | MVP実装中（テスト16/16通過） |

## Aegis 構成

```
Develop/Aegis/
├── apps/
│   └── control-plane/        FastAPI + SQLite + バニラJS UI
│       ├── src/aegis/        Pythonバックエンド
│       ├── tests/            pytest（16テスト）
│       └── README.md         起動手順
└── docs/                     設計・運用ドキュメント
    ├── PRD.md
    ├── basic-design.md
    ├── data-flow.md
    ├── legal/                利用規約・PP・SLA・DPA・OSSコンプラ
    ├── infra/                AWS設計・コスト試算・Terraformスケルトン
    └── pii-masking/          Presidio拡張（日本語PII9種）+ テスト
```

## クイックスタート（Aegis Control Plane）

```bash
cd Develop/Aegis/apps/control-plane
pip install fastapi 'uvicorn[standard]' 'sqlalchemy>=2' 'pydantic[email]' python-multipart
AEGIS_ADMIN_TOKEN=dev-admin-token PYTHONPATH=src python -m uvicorn aegis.main:app --port 8000
```

UI: http://localhost:8000/

テスト:
```bash
cd Develop/Aegis/apps/control-plane
python -m pytest tests/ -v
```
