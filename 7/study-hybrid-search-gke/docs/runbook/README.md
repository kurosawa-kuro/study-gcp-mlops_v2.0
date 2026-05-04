# runbook/ — 検証ゲート + 運用手順

Phase 7 の検証・運用・PDCA loop を集約。`make deploy-all` / `make destroy-all` 周辺の手順はここ。

## 収録ファイル

| ファイル | 役割 | いつ読むか |
|---|---|---|
| [`04_検証.md`](04_検証.md) | 検証ゲート定義 + 「OK」判定基準 + 検証シナリオ (ローカル / GCP ゲート) | 検証実施時 / 「これで通ったと言えるか?」の判定時 |
| [`05_運用.md`](05_運用.md) | PDCA loop (`make deploy-all` / `destroy-all`) + 定常運用 + インシデント対応 | デプロイ・運用・PDCA 周回時 |

## 棲み分け

- **`04_検証.md` = ゲート (判定基準)**。「OK か NG か」を決める。
- **`05_運用.md` = 実行 (手順書)**。「どうやって動かすか」を書く。

検証で通ったら運用に進む、という前後関係。

## 関連

- 設計根拠: [`../architecture/01_仕様と設計.md`](../architecture/01_仕様と設計.md)
- 実装場所: [`../architecture/03_実装カタログ.md`](../architecture/03_実装カタログ.md)
- current sprint: [`../tasks/TASKS.md`](../tasks/TASKS.md)
- 過去判断: [`../decisions/`](../decisions/) (ADR 0001〜0008)
