terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    bucket         = "ai-tpm-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "ai-tpm-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  default = "us-east-1"
}

variable "environment" {
  default = "production"
}

# VPC & Subnets
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "ai-tpm-vpc-${var.environment}"
    Environment = var.environment
  }
}

# PostgreSQL RDS Instance with Read Replica
resource "aws_db_subnet_group" "rds" {
  name       = "ai-tpm-rds-subnet-group"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

resource "aws_db_instance" "postgres_primary" {
  identifier             = "ai-tpm-postgres-primary"
  allocated_storage      = 100
  max_allocated_storage  = 500
  engine                 = "postgres"
  engine_version         = "16.1"
  instance_class         = "db.r6g.xlarge"
  db_name                = "aitpm"
  username               = "dbadmin"
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.rds.name
  skip_final_snapshot    = false
  deletion_protection    = true
  storage_encrypted      = true
  multi_az               = true
}

resource "aws_db_instance" "postgres_replica" {
  identifier             = "ai-tpm-postgres-replica"
  replicate_source_db    = aws_db_instance.postgres_primary.identifier
  instance_class         = "db.r6g.large"
  skip_final_snapshot    = true
  auto_minor_version_upgrade = true
}

# Redis ElastiCache Cluster
resource "aws_elasticache_subnet_group" "redis" {
  name       = "ai-tpm-redis-subnet-group"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id          = "ai-tpm-redis-cluster"
  replication_group_description = "Redis cluster for rate limiting, session cache, and event streams"
  node_type                     = "cache.r6g.large"
  num_cache_clusters            = 2
  parameter_group_name          = "default.redis7"
  port                          = 6379
  subnet_group_name             = aws_elasticache_subnet_group.redis.name
  automatic_failover_enabled    = true
  at_rest_encryption_enabled    = true
  transit_encryption_enabled    = true
}

# Cold Storage S3 Archive Bucket for Memory Rotator & Vector GC
resource "aws_s3_bucket" "cold_storage" {
  bucket = "ai-tpm-cold-storage-archive-${var.environment}"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cold_storage" {
  bucket = aws_s3_bucket.cold_storage.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

variable "db_password" {
  type      = string
  sensitive = true
}
