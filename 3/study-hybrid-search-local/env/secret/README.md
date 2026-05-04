# env/secret/

Phase 3 のローカル開発で使うクレデンシャル置き場。

- 実体ファイル (`credential.yaml`) は **git にコミットしない**。`.gitignore` で除外済。
- サンプルは [`credential.yaml.example`](credential.yaml.example) を参照。
- `cp credential.yaml.example credential.yaml` してから値を編集する。

Phase 4 以降は Secret Manager → Cloud Run secret injection に差し替える。Phase 3 では
docker compose の `environment:` に渡される (master key / postgres password)。
