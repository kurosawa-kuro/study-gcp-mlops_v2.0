# env/secret/

ローカル開発用クレデンシャル置き場。`setting.yaml` との役割分離の一覧は [`../README.md`](../README.md)。

**このディレクトリは `.gitignore` 対象。** README.md のみコミットする。

## ファイル

| ファイル | 用途 | 参照箇所 |
|---|---|---|
| `credential.yaml` | flat YAML でローカル用シークレットを集約（`meili_master_key` など） | `ml.common.config.BaseAppSettings` と local dev helper が読む |

非クレデンシャル設定（project_id, region, secret ID, service 名, local port 等）は `env/config/setting.yaml`。

## 本番環境との関係

本番は **Secret Manager** を正本とする。

- Cloud Run `meili-search`: Secret Manager を直接参照
- GKE `search-api`: External Secrets Operator が Secret Manager から K8s Secret `meili-master-key` を自動生成

`credential.yaml` はローカル開発でのみ使われる。

役割分担:

- **Secret Manager**: 本番の正本。実値を持つ
- **`env/config/setting.yaml`**: 非秘密の参照情報。`meili_master_key_secret_id` のような secret ID もここ
- **`env/secret/credential.yaml`**: ローカル override。開発者が手元で実値を置きたい場合のみ使う

## 形式

```yaml
# flat key: value のみ。ネスト・リスト非対応。
meili_master_key: "<your-meilisearch-master-key>"
```

値は `BaseAppSettings` の対応フィールド名と **小文字キーで一致** させる
（pydantic-settings が大文字小文字を区別せずに解決）。

## 新しいシークレット追加手順

1. **実値が秘密かどうか** を判断する
2. 秘密なら `BaseAppSettings` または派生 Settings に `secret_name: SecretStr = SecretStr("")` を追加
3. `credential.yaml` に同名キーを flat YAML で追加
4. その secret の **ID / 参照先** は `setting.yaml` に追加する
5. 本番で必要なら `infra/terraform/modules/data/main.tf` に `google_secret_manager_secret` を追加し、
   deploy workflow の `--set-secrets` または ExternalSecret manifest に追記する
