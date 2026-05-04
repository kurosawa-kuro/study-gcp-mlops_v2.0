# env/ — 設定とクレデンシャルの分離（設計の前提）

このリポジトリでは **非秘密と秘密をファイルで分ける**。混同するとエージェント・人間とも設計を破る。

| 場所 | 置くもの | Git |
|---|---|---|
| **`config/setting.yaml`** | **非クレデンシャルのみ**（`project_id`、`region`、Secret の **ID** など参照情報） | コミットする |
| **`secret/credential.yaml`** | **ローカル用クレデンシャル**（例: Meilisearch マスターキーの実値） | **`env/secret/` ごと gitignore** |

## エージェント向け（必読）

1. **`setting.yaml` にパスワード・鍵・トークンの実体を書かない** — そもそもその設計ではない。実値は **`secret/credential.yaml`**（ローカル）または **Secret Manager**（本番）。
2. 「setting を直せば live が直る」とは限らない。**Composer / GKE の正本は Terraform の env と Composer 注入の環境変数**（`docs/tasks/TASKS.md` / `CLAUDE.md` 参照）。
3. 詳細は **`env/secret/README.md`**（秘密側の運用）と各ファイル先頭コメント。
