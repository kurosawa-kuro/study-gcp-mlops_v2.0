terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source = "hashicorp/google"
    }
    # google_dataflow_flex_template_job lives in google-beta as of 5.40;
    # SA + IAM resources stay in the stable google provider.
    google-beta = {
      source = "hashicorp/google-beta"
    }
  }
}
