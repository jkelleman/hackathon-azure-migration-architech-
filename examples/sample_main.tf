# examples/sample_main.tf
# ─────────────────────────────────────────────────────────────
# A generic Terraform configuration the agent would receive
# as input when a developer pushes to the repo.
# ─────────────────────────────────────────────────────────────

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# ── Web Application ────────────────────────────────────────────
resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.medium"

  tags = {
    Name        = "webapp-server"
    Environment = "production"
    Team        = "platform"
  }
}

# ── Database ────────────────────────────────────────────────────
resource "aws_db_instance" "postgres" {
  allocated_storage    = 20
  engine               = "postgres"
  engine_version       = "15.4"
  instance_class       = "db.t3.micro"
  db_name              = "appdb"
  username             = "admin"
  password             = "changeme123"     # bad practice — agent should flag
  skip_final_snapshot  = true

  tags = {
    Name        = "webapp-db"
    Environment = "production"
  }
}

# ── Object Storage ──────────────────────────────────────────────
resource "aws_s3_bucket" "assets" {
  bucket = "webapp-static-assets"

  tags = {
    Name        = "webapp-assets"
    Environment = "production"
  }
}

resource "aws_s3_bucket_versioning" "assets" {
  bucket = aws_s3_bucket.assets.id
  versioning_configuration {
    status = "Enabled"
  }
}
