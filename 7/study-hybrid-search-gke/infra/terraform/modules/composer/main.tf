# =========================================================================
# Cloud Composer (Managed Airflow Gen 3) — Phase 7 canonical orchestrator.
#
# 本 module は Phase 7 の **本線 orchestration** を提供する (= 親
# README §「Cloud Composer の位置づけ」 / docs/architecture/01_仕様と設計.md
# §3 が canonical と謳う Composer DAG 経路の実体)。Phase 7 を canonical 起点
# とし、Phase 6 への引き算反映は別 phase 作業で行う (= ユーザ訂正 2026-05-02:
# 「Phase 7 で作った教材コード完成版を引き算して Phase 6 を後日修正する」)。
#
# 学習用 dev (mlops-dev-a) の PDCA サイクル前提で **Composer Gen 3 SMALL**
# を選ぶ。Gen 3 image (`composer-3-airflow-2.10.5`) は Autopilot worker で
# 動き、scheduler / web_server / worker の cpu/memory を細かく指定できる。
#
# Cost (Gen 3 DCU-hour 課金、12 DCU × ~$0.06/DCU-hour ≒ ~$0.72/h ≒ ~¥115/h、
# 為替 ¥160/$):
# - Stage 3 1 回 verify (50-65 min) → 約 ¥120-300 (数百円レベル)
# - destroy 漏れで 1 日放置 (24h) → 約 ¥2,800
# - 数日放置 → 約 ¥8,000-19,000、月常時稼働 → 約 ¥84,000
#
# 真のリスクは **destroy 漏れ**。1 回の verify そのものは安い。
# `make destroy-all` で連鎖 destroy するか、`enable_composer=false` で
# provisioning 自体 skip する運用が前提。ストレージ / DB / ネットワーク /
# Monitoring を含めても 1 時間 verify は数百円レベル。
# =========================================================================

resource "google_composer_environment" "this" {
  count    = var.enable_composer ? 1 : 0
  name     = var.environment_name
  region   = var.region
  project  = var.project_id
  provider = google-beta

  config {
    software_config {
      image_version = "composer-3-airflow-2.10.5-build.2"

      # DAG 内では Airflow Variable / Connection ではなく env 経由で値を受ける。
      # Variable.get(...) を使うと Airflow metadata DB に依存し、PDCA
      # destroy → re-create で値が消えるが、env_variables なら terraform
      # output からの再注入で済む。
      #
      # 予約変数禁止 (2026-05-03 incident): Composer Gen 3 は `PROJECT_ID` /
      # `GCP_PROJECT` / `AIRFLOW_*` / `PATH` / `PYTHONPATH` 等を予約しており、
      # ユーザー側で env_variables に含めると HTTP 400 `Environment variables
      # may not be overridden` で create が拒否される。`PROJECT_ID` は
      # Composer が自動で `GCP_PROJECT` に値を入れるため、DAG は
      # `os.environ["GCP_PROJECT"]` で参照する。
      env_variables = {
        REGION                                   = var.region
        VERTEX_LOCATION                          = var.vertex_location
        PIPELINE_ROOT_BUCKET                     = var.pipeline_root_bucket_name
        PIPELINE_TEMPLATE_GCS_PATH               = var.pipeline_template_gcs_path
        VERTEX_VECTOR_SEARCH_INDEX_RESOURCE_NAME = var.vector_search_index_resource_name
        VERTEX_FEATURE_ONLINE_STORE_ID           = var.feature_online_store_id
        VERTEX_FEATURE_VIEW_ID                   = var.feature_view_id
        API_EXTERNAL_URL                         = var.api_external_url
        SLO_AVAILABILITY_GOAL                    = tostring(var.slo_availability_goal)
        # V5 fix (2026-05-03、§4.1): KubernetesPodOperator が起動する
        # `composer-runner` image URI を DAG (`pipeline/dags/_pod.py`) に
        # 注入する。空ならば DAG 側 fallback (project + region + repo から
        # 組み立て、`composer-runner:latest`) を使う。
        COMPOSER_RUNNER_IMAGE = var.composer_runner_image
        # V5 fix Run 2 fail postmortem (2026-05-03 晩): scripts/_common.py の
        # `resolve_api_target()` は明示 `API_URL` パスでは default `verify_tls=True`
        # / `host_header=None` になり、GKE Gateway の自己署名 TLS + HTTPRoute
        # hostname mismatch で fail する。Composer Pod から正常に
        # `/jobs/check-retrain` を呼べるよう、TARGET=gcp パスと同じ挙動を
        # env で明示注入する (Pod では kubectl による gateway_url() resolve が
        # 出来ないため、明示 URL + 補助 env でカバーする)。
        API_HOST_HEADER   = "search-api.example.com"
        API_INSECURE_TLS  = "true"
      }
    }

    node_config {
      service_account = var.composer_service_account_email
    }

    workloads_config {
      scheduler {
        cpu        = 0.5
        memory_gb  = 2
        storage_gb = 1
        count      = 1
      }
      web_server {
        cpu        = 0.5
        memory_gb  = 2
        storage_gb = 1
      }
      worker {
        cpu        = 0.5
        memory_gb  = 2
        storage_gb = 1
        min_count  = 1
        max_count  = 3
      }
    }

    environment_size = "ENVIRONMENT_SIZE_SMALL"
  }

  # Composer 環境 の create / destroy は GCP 側で 15-25 min / 8-12 min
  # かかるので、provider 側 timeout を明示する (default は 30 min で短い)。
  timeouts {
    create = "60m"
    update = "60m"
    delete = "30m"
  }
}
