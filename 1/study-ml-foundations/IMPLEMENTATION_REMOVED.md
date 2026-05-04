# Phase 1 実装データは削除済 (2026-05-02)

本 phase (`1/study-ml-foundations/`) の **実装データ (コード)** は
2026-05-02 に削除された。残っているのは:

- `README.md` — phase 概要 (教育資料)
- `CLAUDE.md` — phase 別作業ガイド
- `docs/` — 仕様書 / 移行ロードマップ / 実装カタログ / 運用 / 教育資料 / `architecture/` / `decisions/` / `images/` / `operations/`

## なぜ削除したか

Phase 7 (`7/study-hybrid-search-gke/`) が **educational code 完成版の到達ゴール** であり、
Phase 1 / 3-6 は Phase 7 から **引き算で派生** する関係。Phase 1 (ML 基礎 / 回帰タスク) と
Phase 3-6 (検索ドメイン段階移行) の実装を別実装として維持すると、Phase 7 と
doc / 仕様の整合確認のたびに複数 phase を比較するコストが発生し、
token / 認知負荷が増大していた。

教育上の意味は **docs/ (仕様書 / 教育資料)** がすべて残っているため失われない。
学習者は Phase 7 の実装を読み、各 phase の docs/ で「この phase では何を
引き算したか」を比較する形で学べる。

## 復元方法

git tag `pre-phase1-impl-removal` が削除直前の HEAD をマークしている:

```bash
# Phase 1 全体を復元
git checkout pre-phase1-impl-removal -- 1/study-ml-foundations/

# 特定ディレクトリだけ復元
git checkout pre-phase1-impl-removal -- 1/study-ml-foundations/ml/

# tag の中身を確認
git show pre-phase1-impl-removal --stat
```

詳細は親リポ [`README.md`](../README.md) を参照。

## 関連 tag

- `pre-phase1-impl-removal` — 本 phase 削除直前 (本ファイル参照)
- `pre-phase3to6-impl-removal` — Phase 3-6 削除直前 (別コミットで作成)
