# Hatfield Financial — Infrastructure

AWS-hosted. Terraform-managed. CI/CD via GitHub Actions.

---

## Architecture

```
                                                  EventBridge (cron)
                                                      │
                                  ┌───────────────────┼──────────────────────┐
                                  │                                          │
                                  ▼                                          ▼
User → CloudFront → S3 (React)                  Lambda (precompute)    Lambda (rebalance)
              ↘                                       ↓                   ↓ HTTPS
                Route 53 (hatfield-financial.com)    S3 cache         POST /api/custom-etf/
                ↗                                       ↑              auto-rebalance-all
              ↘                                         │ (X-Internal-Secret)
                Route 53 (api.hatfield-financial.com)   │
                       ↓                                │
                 API Gateway (HTTP API + VPC Link)      │
                       ↓                                │
                 Cloud Map service ─→ ECS Fargate (Flask + gunicorn) ──┘
                                            │
                                            ├──→ EFS (SQLite at /mnt/efs/hatfield.db)
                                            └──→ S3 cache (read latest.json)
```

- **Frontend:** S3 static site behind CloudFront (PriceClass_100), domain via Route 53, ACM cert (us-east-1).
- **Backend:** Docker container on ECS Fargate (`desired_count = 1`), fronted by API Gateway HTTP API + VPC Link via Cloud Map service discovery. ACM cert for `api.hatfield-financial.com`.
- **Storage:** EFS (`/mnt/efs/hatfield.db`) for the SQLite file. RDS module exists in Terraform but is **not** instantiated.
- **Database:** SQLite via SQLAlchemy in both local and prod. Local file lives in `Backend/instance/`. Prod file lives on EFS.
- **Async work:** Two scheduled Lambdas — recommendations precompute (every 20 min, writes to S3) and Custom ETF auto-rebalance (9:30 ET MON-FRI, calls into the backend).
- **Domain:** hatfield-financial.com (apex + `api` subdomain).

---

## Terraform (`infra/`)

State: S3 bucket `hatfield-financial-tfstate` + DynamoDB lock table `hatfield-financial-tfstate-lock`. Region: us-east-1.

| Module | Purpose | Key Resources |
|--------|---------|---------------|
| `networking` | VPC, public + (unused) private subnets, security groups | VPC, subnets, SGs for ECS + API GW VPC link |
| `ecr` | Container registries | ECR repositories for backend image and Lambda image |
| `iam` | Permissions | ECS task execution role, Lambda exec roles, **long-lived GitHub Actions IAM user + access key** (output to GH Secrets) |
| `certs` | TLS | ACM certs for frontend + API subdomains |
| `cdn` | Frontend hosting | CloudFront distribution + S3 origin (bucket versioning on, no lifecycle rule) |
| `dns` | Routing | Route 53 records: apex → CloudFront, `api` → API Gateway |
| `apigateway` | API routing | HTTP API + VPC Link + Cloud Map namespace + custom domain |
| `ecs` | Compute | ECS cluster, service, task def (image:latest with `ignore_changes`), EFS mount |
| `efs` | Storage | EFS file system + access point for the SQLite mount |
| `lambda` | Async jobs | Two Lambda functions (precompute, rebalance), S3 cache bucket, EventBridge rule + scheduler |
| `rds` | Database (UNUSED) | PostgreSQL instance code — present in `infra/modules/rds/` but not wired into `main.tf`. Keep or delete. |

**Dependency chain (actual):**
`networking → efs / apigateway / certs → ecs`
`ecr + iam → ecs`
`lambda (S3 cache bucket) → ecs (env var)`
`certs + cdn → dns`
`apigateway → dns`

The `rds` module and the **private subnets** (declared in `networking` but with no route table or NAT attached) are orphans. Either remove them or wire them up.

### Variables (`infra/variables.tf`)
- `aws_region` (default: us-east-1)
- `app_name` (default: hatfield-financial)
- `domain_name` (default: hatfield-financial.com)
- `secret_key` (sensitive, via tfvars or CI secret)
- `internal_api_secret` (sensitive, shared secret used by the rebalance Lambda to call the backend)

> Note: `db_username` / `db_password` exist only inside the unused RDS module. The root-level Terraform does NOT declare them, even though `infra/terraform.tfvars.example` and `.github/workflows/infra.yml` still pass them as `TF_VAR_*`. Those are no-ops today.

---

## CI/CD (`.github/workflows/`)

### `deploy.yml` — Push to main

**Three** parallel jobs (no `needs:` ordering — there is a race risk between frontend and backend rollout):

1. **deploy-frontend:** `npm ci` → `npm run build` → `aws s3 sync` (with `index.html` cached `no-cache`) → CloudFront invalidation.
2. **deploy-backend:** Docker build → ECR push (`:SHA` and `:latest`) → fetch current task def, strip read-only fields, upsert `ALLOWED_ORIGIN` + `ADMIN_USERNAME` env vars → register new revision → `aws ecs update-service` (no `wait services-stable`).
3. **deploy-lambda:** Build `Backend/Dockerfile.lambda` → push to a separate ECR repo → `aws lambda update-function-code` for the precompute function. (The rebalance Lambda is not updated by CI; it's currently deployed via Terraform only.)

### `infra.yml` — PR touching `infra/**`
Runs `terraform fmt -check`, `terraform validate`, `terraform plan`, posts the plan as a PR comment (truncated to 60K chars). Passes `TF_VAR_secret_key` from a GH secret; does **not** pass `TF_VAR_internal_api_secret`, which is currently a required root variable — plan will fail until added. Manual `terraform apply` from a workstation.

---

## Environment Variables

| Variable | Where Set | Purpose |
|----------|-----------|---------|
| `SECRET_KEY` | Terraform (from `var.secret_key`) → ECS task env | Flask session/JWT signing |
| `INTERNAL_API_SECRET` | Terraform (from `var.internal_api_secret`) → ECS task env + Lambda env | Shared secret authenticating the rebalance Lambda → backend call (`X-Internal-Secret` header) |
| `DATABASE_URL` | Hardcoded in `infra/modules/ecs/main.tf` to `sqlite:////mnt/efs/hatfield.db` | DB connection string |
| `ALLOWED_ORIGIN` | `deploy.yml` upserts at deploy time using `DOMAIN_NAME` secret | CORS origin (`https://hatfield-financial.com`). The backend always *also* allows `https://hatfield-financial.com` via set-union, so this is mostly redundant. |
| `ADMIN_USERNAME` | `deploy.yml` upserts at deploy time | Username to promote to admin on startup |
| `ADMIN_PASSWORD` | NOT set anywhere in CI today | Optional one-shot password reset for the admin user. If you add it to the task def, **remove it after the reset** — it lives in the task definition JSON otherwise. |
| `S3_CACHE_BUCKET` | Terraform output from `lambda` module → ECS task env | Bucket Flask reads the recommendations `latest.json` from |
| `S3_BUCKET` / `S3_KEY` | Lambda env (Terraform) | Where the precompute Lambda writes the recommendations JSON |
| `BACKEND_URL` | Lambda env (Terraform) | URL the rebalance Lambda POSTs to (`https://api.<domain>`) |
| `REACT_APP_API_URL` | GitHub Secrets → frontend build time | Backend API base URL (`https://api.hatfield-financial.com`) — points at API Gateway, NOT an ALB |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | GitHub Secrets | Long-lived static credentials for the deploy IAM user. Move to OIDC. |

Local dev defaults: SQLite at `Backend/instance/hatfield.db` when `DATABASE_URL` is unset, `ALLOWED_ORIGIN=http://localhost:3000` when unset.

---

## Docker

### `Backend/Dockerfile` — ECS Fargate API

Single-stage Python image. Runs gunicorn on `:8000`. Actual CMD:

```
gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 120 app:app
```

Notes:
- **No `--preload`** flag (despite previous documentation claims). If you re-add `--preload`, audit the data_fetcher singleton + prewarm thread — they assume single-fork behavior.
- **Container runs as root** — no `USER` directive.
- **No `.dockerignore`** in `Backend/` — image build can pick up `instance/`, local `.env`, venv dirs, and `*.db` files if they are present.

### `Backend/Dockerfile.lambda` — Lambda container

Image used by both the precompute and rebalance Lambdas. Built and pushed by `deploy-lambda` CI job.

---

## Cost-relevant defaults

- ECS Fargate task: 512 CPU / 1024 MB. Likely oversized for `desired_count = 1` low-traffic.
- EFS: bursting throughput (cheapest tier), no IA transition policy.
- CloudFront: PriceClass_100 (cheapest geographic tier).
- Lambda (precompute): 2048 MB / 600 s timeout / scheduled every 20 min (24/7). Reserved concurrency 1.
- Lambda (rebalance): runs only on weekday-morning schedule. Negligible cost.
- CloudWatch log retention: 30 days on ECS log group, **none configured on Lambda log groups** (default = infinite retention).
- No NAT Gateway — ECS tasks are in public subnets with `assign_public_ip = true` and an SG ingress restricted to the VPC CIDR on port 8000. Saves ~$32/mo at the cost of pinning ECS to public subnets.

---

## Maintenance Note

**Update this file when:**
- Terraform modules are added, renamed, removed (and update the dependency chain)
- CI/CD workflows change (new jobs, new secrets, new env vars)
- New environment variables are introduced
- The infrastructure topology changes (e.g. RDS finally gets wired in, NAT added, OIDC replaces static keys, ECS sizing changes)
- The Docker CMD changes
