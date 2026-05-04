terraform {
  backend "gcs" {
    bucket = "mlops-dev-a-tfstate"
    prefix = "hybrid-search-cloud"
  }
}
