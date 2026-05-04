# CLAUDE.md

Phase 2 (`study-ml-app-pipeline`) の作業ガイド。正本は [docs/02_移行ロードマップ.md](docs/02_移行ロードマップ.md)。

## 最初に読むもの

1. [docs/02_移行ロードマップ.md](docs/02_移行ロードマップ.md)
2. [docs/01_仕様と設計.md](docs/01_仕様と設計.md)
3. [README.md](README.md)

## 不変ルール

- 題材は California Housing 回帰
- ML コアは LightGBM 回帰
- Phase 2 は App / Pipeline / Port-Adapter を学ぶフェーズ
- 検索ドメインやクラウド責務は持ち込まない

## Phase 2 の対象

- FastAPI
- lifespan DI
- Port-Adapter
- job 分離
- container 配線

## 実装ルール

- Phase 1 の ML コアは維持する
- 入口と依存方向だけ整理する
- まず差分修正を優先し、E2E / CI/CD 検証は後段へ回す
