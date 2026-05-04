# Docker 配置規約（整理版）

## 目的

- フェーズ間で Dockerfile の置き場所を揃える
- CI / 運用スクリプトの参照先を固定する
- 旧形式の混在を抑える

---

## 標準配置

- Service 用: `infra/run/services/<service_name>/Dockerfile`
- Job 用: `infra/run/jobs/<job_name>/Dockerfile`

`<service_name>` / `<job_name>` は `snake_case` を使う。

---

## 命名ルール

- ファイル名は原則 `Dockerfile` 固定
- `Dockerfile.<suffix>` は legacy 扱い
- legacy を使う場合は、対象フェーズと理由を明記する

---

## フェーズ別の扱い

- Phase 2 以降は標準配置を基本とする
- Phase 1 は教材互換のため legacy が残っていても可

---

## チェック

ルートで以下を実行:

```bash
python3 tools/check_docker_layout.py
```

実際の required パスや例外ルールは、上記スクリプト実装を正とする。

---

## 運用メモ

- フェーズ再編（番号変更・移設）が発生したら、まず `tools/check_docker_layout.py` を更新
- この文書は原則「方針のみ」を保持し、詳細な移行履歴は別ファイルに切り出す
