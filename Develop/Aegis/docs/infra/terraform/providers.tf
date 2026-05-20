provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project    = "aegis"
      ManagedBy  = "terraform"
      Repository = "ai-broadcast-hub"
    }
  }
}

# CloudFront/ACM 用（バージニア固定）
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project    = "aegis"
      ManagedBy  = "terraform"
      Repository = "ai-broadcast-hub"
    }
  }
}
