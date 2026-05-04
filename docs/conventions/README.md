# docs/conventions/ — 規約・配置・命名の正本セット

`study-gcp-mlops` 全 phase 横断の **規約・配置・命名** ドキュメントを集約するディレクトリ。各 phase の `CLAUDE.md` / `docs/01_仕様と設計.md` 等から参照される。

## 各ファイルの目的

| ファイル | 役割 | 行数目安 | メンテ形式 |
|---|---|---|---|
| [`命名規約.md`](命名規約.md) | 命名規約 (なぜその名前か) — `ml/<機能>/...` / `pipeline/<verb>_job/` / `scripts/{setup,deploy,ops,ci,sql}` 等の命名思想 | 149 | 手動 |
| [`フォルダ-ファイル.md`](フォルダ-ファイル.md) | 構造索引 (どこに何があるか) — Phase 7 最大集合 + Phase ごとの差分 + 各要素の役割と実装形態 | 490 | 手動 |
| [`スクリプト規約.md`](スクリプト規約.md) | scripts 命名標準 — Make target = 公開 API、scripts = 内部実装、移行方針 | 170 | 手動 |
| [`Makefile規約.md`](Makefile規約.md) | Make Command Matrix — Canonical Vocabulary + Phase Support Matrix | 208 | **自動生成** (`tools/generate_makefile_md.sh`) |
| [`Docker配置規約.md`](Docker配置規約.md) | Docker 配置標準 — `infra/run/{services,jobs}/<name>/Dockerfile` の固定配置 | 50 | 手動 (検証は `tools/check_docker_layout.py`) |

## 読む順 (Claude Code 視点)

1. **新規セッションで規約を確認したい** → `命名規約.md` (なぜ) → `フォルダ-ファイル.md` (どこに)
2. **新しい Make target を足す** → `スクリプト規約.md` (命名規則) → `Makefile規約.md` (既存語彙確認)
3. **Dockerfile を新規追加** → `Docker配置規約.md`
4. **特定 Phase の構造把握** → `フォルダ-ファイル.md` の「Phase ごとの差分」節

## 親 docs / phase docs との関係

- **権威順位** (`命名規約.md §優先順位`): 各 phase の `CLAUDE.md` > この `命名規約.md` > 同階層 (`スクリプト規約.md` / `Makefile規約.md` / `フォルダ-ファイル.md` / `Docker配置規約.md`) > 対象 phase の `README.md` / `docs/`
- 各 phase の `docs/{01_仕様と設計, 02_移行ロードマップ, 03_実装カタログ, 04_運用}.md` は phase 個別仕様、本 dir は **phase を跨ぐ共通規約**
- 命名衝突や規約改訂は本 dir の `命名規約.md` に集約 (各 phase 個別 docs に書かない)

## 編集ガイド

- `Makefile規約.md` は **手で編集しない**。`tools/generate_makefile_md.sh` を再実行して再生成する (出力先は `docs/conventions/Makefile規約.md`)
- 他 4 ファイルは手動編集。変更時は **権威順位** を意識し、上位 (CLAUDE.md / phase docs) と矛盾していないか確認
- 新規規約ファイルを追加するなら本 dir に配置し、本 README の表にも追記する
