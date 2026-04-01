# AWS Migration Plan — Hatfield Financial

## Overview

Migrate Hatfield Financial from a local dev setup (Flask on port 5000 + React on port 3000) to a production AWS environment with GitHub Actions CI/CD. The app has a Flask REST API backend, React SPA frontend, SQLite database, and in-memory caching.

**Current blockers for cloud deployment:**
- Hardcoded `localhost` URLs in both frontend and backend
- SQLite (not suitable for cloud/multi-instance)
- In-memory rate limiter (lost on restart)
- No WSGI server (Flask dev server only)
- No Docker containers
- No CI/CD pipeline

---

## Recommended AWS Architecture

```
GitHub (source)
  └─ GitHub Actions CI/CD
       ├─ Frontend build → S3 bucket → CloudFront CDN (HTTPS)
       └─ Backend build → ECR (Docker image) → ECS Fargate (container)
                                                    └─ ALB (HTTPS load balancer)
                                                         └─ RDS PostgreSQL (database)
                                                         └─ Secrets Manager (secrets)
```

### Services Used

| Service | Purpose |
|---------|---------|
| **S3** | Host React static build |
| **CloudFront** | CDN + HTTPS for frontend |
| **ECR** | Docker image registry |
| **ECS Fargate** | Run Flask + Gunicorn container (no EC2 management) |
| **ALB** | HTTPS load balancer → ECS |
| **RDS PostgreSQL** | Replace SQLite (db.t3.micro) |
| **Secrets Manager** | Store SECRET_KEY, DB credentials |
| **ACM** | Free SSL/TLS certificates |
| **GitHub Actions** | CI/CD: build, push image, deploy |
| **Route 53** | (Optional) Custom domain |

---

## Monthly Cost Estimate

| Service | Config | Est. Cost/mo |
|---------|--------|-------------|
| ECS Fargate | 0.5 vCPU, 1 GB RAM, 24/7 | ~$18 |
| RDS PostgreSQL | db.t3.micro, 20 GB SSD | ~$15 |
| Application Load Balancer | 1 ALB, low traffic | ~$16 |
| S3 | Static hosting, ~1 GB | < $1 |
| CloudFront | HTTPS CDN, low traffic | ~$1–2 |
| ECR | ~2 GB image storage | ~$0.20 |
| Secrets Manager | 3 secrets | ~$1.20 |
| Data Transfer | Low traffic | ~$1–2 |
| **Total** | | **~$53–55/month** |

> **Year 1 discount:** RDS db.t3.micro is free-tier eligible — drops to ~$35–38/month for the first 12 months.

> **Optional:** Route 53 hosted zone +$0.50/mo; domain registration ~$12–15/year.

---

## Phase 1: Code Changes (Before Any AWS Setup)

### 1.1 `Backend/app.py`

```python
# CORS — read from env var
CORS(app, origins=[os.environ.get('ALLOWED_ORIGIN', 'http://localhost:3000')])

# Database — use PostgreSQL in cloud, SQLite locally
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///hatfield.db')

# Remove debug=True from app.run()
app.run(port=int(os.environ.get('PORT', 5000)), debug=False)
```

### 1.2 `Backend/requirements.txt`

Add:
```
gunicorn          # production WSGI server
psycopg2-binary   # PostgreSQL driver
python-dotenv     # local .env loading
```

### 1.3 `Frontend/src/api.js`

```js
// Before:
const API_BASE = 'http://localhost:5000';

// After:
const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:5000';
```

### 1.4 New Files to Create

**`Backend/Dockerfile`**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "app:app"]
```

**`.env.example`** (root — commit this, never the real `.env`)
```
# Backend
SECRET_KEY=change-me-in-production
DATABASE_URL=postgresql://user:pass@host:5432/hatfield
ALLOWED_ORIGIN=https://your-cloudfront-domain.cloudfront.net
DEBUG=False

# Frontend (set in GitHub Actions secrets)
REACT_APP_API_URL=https://your-alb-domain.us-east-1.elb.amazonaws.com
```

**`.github/workflows/deploy.yml`**
Two jobs triggered on push to `main`:
1. `deploy-frontend` — `npm run build` → `aws s3 sync` → CloudFront cache invalidation
2. `deploy-backend` — `docker build` → `docker push` to ECR → `aws ecs update-service`

PRs only run lint/tests — no deploy until merged to `main`.

---

## Phase 2: AWS Infrastructure Setup (One-Time, Done in Console or Terraform)

Perform in this order:

1. **VPC** — use default VPC for simplicity, or create one with public + private subnets
2. **RDS PostgreSQL** — db.t3.micro, place in private subnet
3. **ECR repository** — name it `hatfield-financial-backend`
4. **ECS Cluster** — Fargate launch type
5. **ECS Task Definition** — reference ECR image, inject secrets from Secrets Manager as env vars
6. **ACM Certificate** — request a cert for your domain (or ALB default domain)
7. **ALB** — HTTPS listener on 443, forward to ECS target group
8. **ECS Service** — attach to ALB target group, 1 desired task
9. **S3 Bucket** — block public access; bucket policy allows CloudFront only
10. **CloudFront Distribution** — origin: S3 bucket, HTTPS only
11. **Secrets Manager** — store `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_ORIGIN`
12. **IAM Roles**:
    - ECS task execution role → can read Secrets Manager
    - GitHub Actions deploy user → ECR push, ECS update-service, S3 sync, CloudFront invalidate

### GitHub Actions Secrets Required

```
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_REGION
ECR_REPOSITORY
ECS_CLUSTER
ECS_SERVICE
S3_BUCKET_NAME
CLOUDFRONT_DISTRIBUTION_ID
REACT_APP_API_URL
```

---

## Phase 3: Database Migration

1. Add `Flask-Migrate` to requirements.txt
2. Run `flask db init` + `flask db migrate` to generate Alembic migrations
3. On first deploy, run `flask db upgrade` against RDS PostgreSQL
4. No data migration needed (SQLite has no production data)

---

## Deployment Workflow (After Setup)

```
Developer opens PR
  └─ GitHub Actions: lint + tests only (no deploy)

Developer merges PR to main
  └─ GitHub Actions triggers two parallel jobs:
       ├─ Frontend:
       │    ├─ npm ci
       │    ├─ npm run build  (REACT_APP_API_URL injected from secrets)
       │    ├─ aws s3 sync build/ s3://{bucket} --delete
       │    └─ aws cloudfront create-invalidation --paths "/*"
       └─ Backend:
            ├─ docker build -t {ecr-url}:{git-sha} .
            ├─ docker push {ecr-url}:{git-sha}
            └─ aws ecs update-service --force-new-deployment
                   (ECS pulls new image, rolling deploy, zero downtime)
```

---

## Files Modified / Created Summary

| File | Action | Change |
|------|--------|--------|
| `Backend/app.py` | Modify | CORS env var, DATABASE_URL, remove debug=True |
| `Backend/requirements.txt` | Modify | Add gunicorn, psycopg2-binary, python-dotenv |
| `Frontend/src/api.js` | Modify | Use `process.env.REACT_APP_API_URL` |
| `Backend/Dockerfile` | Create | Gunicorn-based container |
| `.env.example` | Create | Template for local dev |
| `.github/workflows/deploy.yml` | Create | Full CI/CD pipeline |

---

## Verification Checklist

- [ ] `docker build` and `docker run` backend locally — API responds on port 8000
- [ ] `npm run build` with `REACT_APP_API_URL` set — build succeeds, no localhost references
- [ ] ECS task starts healthy, ALB health check passes
- [ ] Frontend loads from CloudFront URL, API calls reach ECS via ALB
- [ ] Push to `main` triggers GitHub Actions, both jobs pass, live app updates
- [ ] PR to `main` does NOT trigger a deploy (tests only)
