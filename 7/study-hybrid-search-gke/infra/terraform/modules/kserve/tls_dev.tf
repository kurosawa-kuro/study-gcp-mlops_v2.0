# =========================================================================
# Self-signed TLS Secret bootstrap for the search-api Gateway listener.
#
# Why this lives in Terraform (not in `infra/manifests/`):
# 1. The Secret data must be generated, not committed (private key).
# 2. `destroy-all → deploy-all` is the PDCA dev loop: with TF-managed
#    state, `tfstate` carries the cert + key over re-apply (no churn) and
#    `destroy-all` cleanly removes them too.
# 3. Phase 7 Run 1 wedged at `Gateway PROGRAMMED=False` because the listener
#    referenced `Secret search/search-api-tls` that didn't exist. Bootstrapping
#    a self-signed cert here closes the gap so `make deploy-all` is one-shot.
#
# Production guidance: set `var.enable_self_signed_tls = false` and provision
# either GCP Managed Certificate (`google_compute_managed_ssl_certificate`)
# bound via FrontendConfig, or cert-manager + Let's Encrypt with the same
# Secret name. The current `gateway.yaml` references Secret name verbatim
# so no manifest change is needed when switching.
# =========================================================================

resource "tls_private_key" "search_api_dev" {
  count       = var.enable_self_signed_tls ? 1 : 0
  algorithm   = "RSA"
  rsa_bits    = 2048
}

resource "tls_self_signed_cert" "search_api_dev" {
  count           = var.enable_self_signed_tls ? 1 : 0
  private_key_pem = tls_private_key.search_api_dev[0].private_key_pem

  subject {
    common_name = var.tls_cn
  }

  dns_names = [var.tls_cn]

  validity_period_hours = 24 * 365
  early_renewal_hours   = 24 * 7

  allowed_uses = [
    "key_encipherment",
    "digital_signature",
    "server_auth",
  ]
}

resource "kubernetes_secret" "search_api_tls" {
  count = var.enable_self_signed_tls ? 1 : 0
  metadata {
    name      = "search-api-tls"
    namespace = kubernetes_namespace.search.metadata[0].name
  }
  type = "kubernetes.io/tls"
  data = {
    "tls.crt" = tls_self_signed_cert.search_api_dev[0].cert_pem
    "tls.key" = tls_private_key.search_api_dev[0].private_key_pem
  }
}
