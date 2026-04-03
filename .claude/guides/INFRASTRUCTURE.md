# Hatfield Financial — Infrastructure

AWS-hosted. Terraform-managed. CI/CD via GitHub Actions.

---

## Architecture

```
User → CloudFront (CDN) → S3 (React build)
                        ↘ ALB → ECS Fargate (Flask API) → RDS PostgreSQL
```

- **Frontend:** S3 static site behind CloudFront, domain via Route 53
- **Backend:** Docker container on ECS Fargate, behind ALB with HTTPS
- **Database:** RDS PostgreSQL (prod), SQLite (local dev)
- **Domain:** hatfield-financial.com, ACM certs for both frontend and API

---

## Terraform (`infra/`)

State: S3 bucket `hatfield-financial-tfstate` + DynamoDB lock table. Region: us-east-1.

| Module | Purpose | Key Resources |
|--------|---------|---------------|
| `networking` | VPC, subnets, security groups | VPC, public/private subnets, SGs for ECS/ALB/RDS |
| `ecr` | Container registry | ECR repository |
| `ecs` | Compute | ECS cluster, service, task def, ALB, target group |
| `rds` | Database | PostgreSQL instance in private subnets |
| `iam` | Permissions | ECS task execution role |
| `certs` | TLS | ACM certificates for frontend + API domains |
| `cdn` | Frontend hosting | CloudFront distribution + S3 origin |
| `dns` | Routing | Route 53 records for domain → CloudFront/ALB |

**Dependency chain:** certs → cdn → dns; networking + ecr + iam + rds + certs → ecs → dns

### Variables (`variables.tf`)
- `aws_region` (default: us-east-1)
- `app_name` (default: hatfield-financial)
- `domain_name` (default: hatfield-financial.com)
- `db_username`, `db_password`, `secret_key` (sensitive, via tfvars or CI secrets)

---

## CI/CD (`.github/workflows/`)

### `deploy.yml` — Push to main
Two parallel jobs:
1. **deploy-frontend:** `npm ci` → `npm run build` → S3 sync → CloudFront invalidation
2. **deploy-backend:** Docker build → ECR push (tagged by SHA + latest) → ECS rolling update (new task def revision)

### `infra.yml` — PR touching `infra/**`
Runs `terraform plan` and posts output as a PR comment. Manual `terraform apply` required.

---

## Environment Variables

| Variable | Where Set | Purpose |
|----------|-----------|---------|
| `SECRET_KEY` | GitHub Secrets / tfvars | Flask session signing |
| `DATABASE_URL` | ECS task env (from Terraform) | PostgreSQL connection string |
| `ALLOWED_ORIGIN` | ECS task env (from deploy.yml) | CORS origin (CloudFront domain) |
| `REACT_APP_API_URL` | GitHub Secrets → build-time | Backend ALB URL for frontend |
| `AWS_ACCESS_KEY_ID/SECRET` | GitHub Secrets | AWS auth for deploy |

Local dev uses SQLite automatically when `DATABASE_URL` is unset. See `.env.example`.

---

## Docker (`Backend/Dockerfile`)

Single-stage build for the Flask API. Runs on port 5000 inside the container.

---

## Maintenance Note

**Update this file when:**
- Terraform modules are added, renamed, or restructured
- CI/CD workflows change (new jobs, new secrets)
- New environment variables are introduced
- Infrastructure architecture changes (new AWS services, regions, etc.)
