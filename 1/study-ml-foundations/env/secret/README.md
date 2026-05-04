# env/secret/

クレデンシャル（パスワード・APIキー等）置き場。

**このディレクトリは `.gitignore` 対象。** README.md のみコミットする。

## ファイル

| ファイル | 用途 | 参照箇所 |
|---|---|---|
| `credential.yaml` | flat YAML でシークレットを集約 (`postgres_password` / `pgadmin_default_password` など) | `scripts/compose.sh` が読み取り、キーを大文字化して env に export → `docker-compose.yml` の `${POSTGRES_PASSWORD}` / `${PGADMIN_DEFAULT_PASSWORD}` で補間 |

非クレデンシャル設定（ホスト・ポート・DB 名・モデル設定等）は `env/config/setting.yaml` に置く。

## 形式

```yaml
# flat key: value のみ。ネスト・リスト非対応。
postgres_password: <value>
pgadmin_default_password: <value>
```

## 新しいシークレット追加手順

1. `credential.yaml` にキーを追加（flat YAML）
2. docker-compose.yml から `${KEY_UPPERCASE}` で参照
3. Python から参照する場合は `docker-compose.yml` の `environment:` に転送するか、
   `scripts/compose.sh` 経由で shell に export された値を `os.getenv` で読む
