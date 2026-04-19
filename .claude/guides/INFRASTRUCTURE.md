# Hatfield Financial — Infrastructure

AWS-hosted. Terraform-managed. CI/CD via GitHub Actions.

---

## Architecture

```
User → CloudFront (CDN) → S3 (React build)
                        ↘ API Gateway → ECS Fargate (Flask API) → S3 (recommendations cache)
                                                    ↕
                                                   EFS
                        Lambda (scheduled) ──────────↗
```

- **Frontend:** S3 static site behind CloudFront, domain via Route 53
- **Backend:** Docker container on ECS Fargate, behind API Gateway with HTTPS
- **Lambda:** Separate Docker container (`Dockerfile.lambda`) that pre-computes S&P 500 recommendations on a schedule and writes to S3. ECS reads from this S3 bucket (`S3_CACHE_BUCKET`) to serve `/api/recommendations` without blocking.
- **Storage:** EFS for persistent file storage across containers; S3 bucket for Lambda → ECS recommendations cache
- **Database:** SQLite (local dev); no RDS module is currently wired in `main.tf` (the `modules/rds/` directory exists but is not called)
- **Domain:** hatfield-financial.com, ACM certs for both frontend and API

---

## Terraform (`infra/`)

State: S3 bucket `hatfield-financial-tfstate` + DynamoDB lock table. Region: us-east-1.

| Module | Purpose | Key Resources |
|--------|---------|---------------|
| `networking` | VPC, subnets, security groups | VPC, public/private subnets, SGs for ECS/API GW |
| `ecr` | Container registry | ECR repository (backend image) |
| `ecs` | Compute | ECS cluster, service, task def, target group |
| `lambda` | Recommendations pre-compute | Lambda function + S3 cache bucket |
| `iam` | Permissions | ECS task execution role |
| `certs` | TLS | ACM certificates for frontend + API domains |
| `cdn` | Frontend hosting | CloudFront distribution + S3 origin |
| `dns` | Routing | Route 53 records for domain → CloudFront/API GW |
| `apigateway` | API routing | API Gateway for backend HTTPS routing |
| `efs` | Storage | Elastic File System for persistent container storage |

> **RDS module**: `modules/rds/` exists in the repo but is **not called** from `main.tf`. The application uses SQLite locally and does not currently wire a managed PostgreSQL instance in the Terraform deployment.

**Dependency chain** (from `main.tf` comments):
- `certs` → (none)
- `efs` → `networking`
- `apigateway` → `networking`, `certs`
- `cdn` → `certs`
- `ecs` → `networking`, `ecr`, `iam`, `efs`, `apigateway`, `certs`, **`lambda`** (reads `s3_cache_bucket_name`)
- `dns` → `cdn`, `apigateway`

### Variables (`variables.tf`)

Root-level variables only:
- `aws_region` (default: us-east-1)
- `app_name` (default: hatfield-financial)
- `domain_name` (default: hatfield-financial.com)
- `secret_key` (sensitive, via tfvars or CI secrets)

> `db_username` and `db_password` are defined in `modules/rds/variables.tf`, not at the root level.

---

## CI/CD (`.github/workflows/`)

### `deploy.yml` — Push to main
Three parallel jobs:
1. **deploy-frontend:** `npm ci` → `npm run build` → S3 sync → CloudFront invalidation
2. **deploy-backend:** Docker build (`Dockerfile`) → ECR push (tagged by SHA + latest) → ECS rolling update. Also upserts `ALLOWED_ORIGIN` and `ADMIN_USERNAME` into the ECS task definition environment.
3. **deploy-lambda:** Docker build (`Dockerfile.lambda`) → Lambda ECR push → `aws lambda update-function-code`

### `infra.yml` — PR touching `infra/**`
Runs `terraform plan` and posts output as a PR comment. Manual `terraform apply` required.

---

## Environment Variables

| Variable | Where Set | Purpose |
|----------|-----------|---------|
| `SECRET_KEY` | GitHub Secrets / tfvars | Flask JWT signing key |
| `DATABASE_URL` | ECS task env (from Terraform) | PostgreSQL connection string (unset → SQLite) |
| `ALLOWED_ORIGIN` | ECS task env (upserted by deploy.yml) | CORS origin — comma-separated list, always also allows `https://hatfield-financial.com` |
| `ADMIN_USERNAME` | ECS task env (upserted by deploy.yml) | Username to seed as admin on startup |
| `ADMIN_PASSWORD` | ECS task env (remove after use) | Resets the admin user's password on startup |
| `S3_CACHE_BUCKET` | ECS task env (from Terraform via lambda module) | S3 bucket name for recommendations pre-compute cache |
| `REACT_APP_API_URL` | GitHub Secrets → build-time | Backend API URL for frontend |
| `AWS_ACCESS_KEY_ID/SECRET` | GitHub Secrets | AWS auth for deploy |
| `LAMBDA_ECR_REPOSITORY` | GitHub Secrets | ECR repo URL for Lambda image |
| `LAMBDA_FUNCTION_NAME` | GitHub Secrets | Lambda function name to update |

Local dev uses SQLite automatically when `DATABASE_URL` is unset. See `.env.example`.

---

## Docker

**`Backend/Dockerfile`** — ECS Fargate image. Single-stage Python 3.11-slim build. Runs:
```
gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 120 app:app
```

**`Backend/Dockerfile.lambda`** — Lambda image. Uses `lambda_handler.py` as the entry point for scheduled S&P 500 recommendations pre-compute.

---

## Maintenance Note

**Update this file when:**
- Terraform modules are added, renamed, or restructured
- CI/CD workflows change (new jobs, new secrets)
- New environment variables are introduced
- Infrastructure architecture changes (new AWS services, regions, etc.)
