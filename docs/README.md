# docs

ルート `docs/` は、全フェーズ共通の方針・移行作業・補助資料を管理するディレクトリ。
`architecture/01_仕様と設計.md` / `architecture/03_実装カタログ.md` / `runbook/04_運用.md` は **Phase 横断ハブ** として各フェーズ正本へ案内する。
トップ入口は `../README.md`。

## まず読むファイル

- [`conventions/`](conventions/README.md) — 規約・配置・命名の正本セット (5 ファイル + 索引 README)
  - `conventions/命名規約.md` — フォルダ名・ファイル名・役割の共通規約
  - `conventions/フォルダ-ファイル.md` — Phase 1-7 を 1 枚で見る構造索引
  - `conventions/スクリプト規約.md` — scripts 命名標準
  - `conventions/Makefile規約.md` — Make Command Matrix (auto-generated)
  - `conventions/Docker配置規約.md` — Dockerfile / compose 関連の共通ルール
- `05_問題点.md`
  - 全体課題メモ
- `archive/README.md`
  - 過去ログの退避方針
- `phases/README.md`
  - Phase 1〜5 の docs 入口（phase サブフォルダ）

## 位置付け

- 各フェーズの正本仕様は、**フェーズ配下の `README.md` / `CLAUDE.md` / `docs/`**
- ルート `docs/` は、フェーズ横断の管理情報を置く場所
- 実装詳細の参照先は、必ず対象フェーズ配下を優先する
- Phase 3/4/5 のハイブリッド検索は **LightGBM + multilingual-e5 + Meilisearch** を必須構成とする

## 補助資料

- [`conventions/フォルダ-ファイル.md`](conventions/フォルダ-ファイル.md) — Phase 1-7 構造索引 + 各要素の役割と実装形態 (旧 `パイプラインとジョブ.md` を統合)
- `archive/パイプラインとジョブ.md` — 旧版 (2026-04-26 archived、`conventions/フォルダ-ファイル.md` の前身)
