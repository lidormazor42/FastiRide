# Project Book — FastiRide

A DevOps capstone project: a working, containerized application deployed to a managed Kubernetes cluster (AWS EKS), with full CI/CD and GitOps, and real monitoring — everything defined as code.

---

## 1. Project Introduction

FastiRide is a ride-sharing platform for festivals — drivers post a ride, other attendees join it, and a private chat opens between the driver and approved passengers. The application itself is a vehicle for demonstrating a complete DevOps project — the emphasis is on **how** it's built, tested, deployed, and monitored, not just on what it does.

## 2. System Goal

To build and operate a real application in a full DevOps environment: from local code, through Docker and Kubernetes, with a fully automated pipeline (push → build → deploy), and infrastructure that is entirely defined as code (Terraform) — including the monitoring layer itself, not just the application.

## 3. Application Overview

- **Frontend:** Plain HTML/JS served through Nginx — no build step, to keep the container small.
- **Backend:** FastAPI (Python), with endpoints for events, rides, joining/approval, chat (WebSocket), and ticket validation (AWS Rekognition).
- **Database:** Amazon RDS for PostgreSQL (originally a StatefulSet inside the cluster — migrated for real, see section 13).
- **Auth:** Google OAuth, JWT-based session in a cookie (the signing key is stored in SSM Parameter Store, not in code).
- **Notifications:** Amazon SES for emails to drivers when someone joins/cancels — branded HTML templates matching the site's design.
- **Distributed chat:** chat messages flow through Redis pub/sub (a small per-environment deployment, no persistence — the messages themselves live in Postgres). This is what makes it possible to run multiple backend replicas: a message sent through one pod reaches users connected to a different pod. Verified live with two clients pinned to two different pods on two different nodes.
- **Load protection:** rate limiting (slowapi) backed by Redis — so the limit is enforced globally across all replicas, not per-pod. The most important limit: `/api/validate` (which triggers billed Rekognition calls) is capped at 10 requests/minute per IP. IP detection reads `X-Forwarded-For` (set by the ALB) — without it every request would appear to come from the ALB itself.
- **Ticket validation — a design decision:** the primary OCR engine is AWS Rekognition (managed, no native dependencies), but pytesseract deliberately remains as a local fallback — so the app still works in local docker compose without an AWS connection. This isn't leftover cruft but a deliberate graceful degradation: cloud first, local as backup.

## 4. System Architecture

The full diagram + environment table + FinOps decision log live in [README.md](README.md#architecture) (a Mermaid diagram rendered natively on GitHub). In short: a VPC across 2 Availability Zones, public subnets (ALB + NAT Instance) and private subnets (EKS nodes + RDS), one ALB shared between the application and Grafana, and Route 53 for `fastiride.app`.

## 5. Tools and Their Role

| Tool | Actual role in this project |
|---|---|
| **Docker** | Packages the backend and frontend into standalone images — the same image runs locally (docker compose) and in the cloud (EKS) |
| **Kubernetes (EKS)** | Runs the pods, keeps them alive (self-healing), routes traffic (Service/Ingress), and allows scaling (replicas) |
| **Helm** | One "template" for all Kubernetes manifests, with a different values file per environment (local dev vs. prod on AWS) |
| **Terraform** | Defines every AWS resource as code — VPC, EKS, RDS, S3, IAM, Route53 — so the infrastructure is rebuildable and reproducible, not clicked together in the console |
| **GitHub Actions** | CI: on every push — lint, run tests (pytest), build images, push to ECR |
| **ArgoCD** | CD: reads the desired state from Git and applies it to the cluster on its own — the CI doesn't "push" to the cluster, ArgoCD "pulls" from Git |
| **Prometheus** | Collects metrics — both for the cluster itself and for the backend (dedicated `/metrics` endpoint) |
| **Grafana** | Displays the metrics as dashboards — including a custom dashboard I built following the RED method (Rate/Errors/Duration) |
| **Loki** | Collects logs from all pods (a lighter alternative to Elasticsearch) |
| **Alertmanager** | Sends a **real email** when something's wrong — not just "a dashboard nobody looks at" |
| **Redis** | The chat's message bus (pub/sub between backend replicas) + the rate limiter's storage — transport only, no persistence |
| **metrics-server** | The cluster's Metrics API (`kubectl top`) — the prerequisite for HPA; installed through ArgoCD like everything else |
| **HPA** | Pod-level scaling: backend 2-6 replicas, frontend 2-4, based on 70% CPU — verified live under real load (2→6 and back) |
| **Karpenter** | Node-level scaling: when pods don't fit in existing capacity, a new node is provisioned within ~40 seconds and deleted automatically once it empties out (demonstrated live, on-demand only, no spot — a cost decision) |
| **Alembic** | Manages Postgres schema migrations — every schema change is a versioned migration file in Git (upgrade+downgrade), run automatically via an `initContainer` before the backend starts; replaced a manual `ALTER TABLE IF NOT EXISTS` mechanism |

## 6. Workflow

Work follows **GitHub Flow** (not GitFlow — no long-lived `develop` branch): a short-lived `feature/*` branch per change, a Pull Request straight into `main` (branch protection — PR required, lint+tests run). Every merge to `main` **deploys automatically to staging** (`staging.fastiride.app`). When ready to actually promote to production, push a git tag (`git tag v1.2.0 && git push origin v1.2.0`) — this runs a separate workflow that promotes the exact image already tested on staging to production (`fastiride.app`), **without rebuilding**. See section 4 for more detail.

## 7. Pipeline (CI/CD)

Two workflow files, responsible for two different deploy triggers:

**`.github/workflows/ci.yaml`** — runs on every push/PR to `main`, three jobs:
1. **Lint** — `ruff` over the Python code.
2. **Test** — `pytest` over a real test suite (`backend/tests/`) — runs against an in-memory sqlite, no dependency on any external service.
3. **Deploy to Staging** (only on push to `main`, and only if the two previous jobs passed) — builds the backend and frontend images (with GitHub Actions layer caching), pushes to ECR, scans both **built images** with Trivy (informational only for now — the first run against these images, not yet gated on a confirmed-clean baseline), then **updates the image tag in `values-staging.yaml` in Git itself** (never touches the cluster directly!) — this is the "trigger" ArgoCD detects and syncs to staging. A final step polls `staging.fastiride.app/api/health` for up to 200 seconds and fails the job if staging never comes back healthy — a real post-deploy smoke test, not just "the sync command didn't error."

**`.github/workflows/promote-to-production.yaml`** — runs **only** when a git tag matching `v*` is pushed. Builds no new image at all — reads the current tags from `values-staging.yaml` (what's already running and verified on staging) and writes them into `values-prod.yaml`. This way production always runs exactly what already "passed" on staging, not an independent build.

**`.github/workflows/iac-quality.yaml`** — CI for the infrastructure itself, not just the code: `terraform fmt -check` + `terraform validate` (runs with no credentials at all, using `-backend=false`), `helm lint` against both environments' values files, and a **Trivy** security scan — CRITICAL vulnerabilities in Python dependencies or Terraform/K8s misconfigurations fail the pipeline; HIGH findings are reported in the log for review.

**Pipeline hardening pass:** every job across both workflows now declares explicit least-privilege `permissions` instead of relying on the repo default; `deploy-staging` has a `concurrency` group so two fast pushes to `main` queue instead of racing on the same `values-staging.yaml` commit; `promote-to-production` targets a **GitHub Environment** (`production`) with a required-reviewer rule, so pushing a version tag is no longer the final approval by itself — it also requires an explicit human click in GitHub before anything reaches `values-prod.yaml`; and `.github/dependabot.yml` now opens automatic PRs for backend pip dependencies, both Dockerfiles' base images, and GitHub Actions versions — it found two real upgrades (Python and nginx base images) on its very first scan. **Honest limitation, found immediately when testing the new gate for real** (tagging `v0.3.1` to bring production back in sync with staging): the promotion ran straight through without ever pausing for approval. GitHub's environment protection rules let repository admins bypass required reviewers by default (`can_admins_bypass: true`), and on a personal (non-organization) repo there's no setting to turn that off — only an organization-owned repo can enforce protection rules against its own admins. So this gate is real protection against anyone without owner access (a compromised token, a future collaborator), but it does not add friction for the repo owner specifically — documenting that limitation is more honest than presenting it as a hard stop for everyone.

## 8. Kubernetes

Resources in use: `Deployment` (backend, frontend, redis — with real resource requests/limits and a full `securityContext`: `runAsNonRoot`, `readOnlyRootFilesystem`, `capabilities: drop: [ALL]`), `Service`, `Ingress` (via the AWS Load Balancer Controller, one ALB shared between the application and Grafana), `HPA` (**active** on both tiers — backend 2-6 replicas, frontend 2-4, at 70% CPU — verified live under real load), `PodDisruptionBudget` (minAvailable:1, so node maintenance doesn't take down all replicas at once), `NetworkPolicy` (default-deny-ingress per namespace + explicit allows for ALB/Prometheus/redis only — verified with real traffic-blocking tests, not just "it exists"), a `CronJob` (daily DB backup to S3), and an `initContainer` named `migrate` on the backend Deployment — runs to completion (`alembic upgrade head`) before the main container starts, so the DB schema is always up to date before any replica starts serving traffic. A **Pod** is the basic unit of execution (one or more containers, shared network/storage); a **Deployment** maintains a desired replica count and replaces pods that fail; a **Service** gives a stable DNS/IP to a group of pods even as they're replaced.

**Scaling at two levels — Pod and Node:** the HPA (Horizontal Pod Autoscaler) adds/removes **pods** based on CPU load within existing nodes. **Karpenter** (installed via ArgoCD, not manual helm) solves the layer beneath it: when the HPA already wants more pods than the existing nodes can fit (pods get stuck `Pending`), Karpenter provisions a new **node** (EC2, on-demand only — no spot, a cost decision) in under a minute, and removes it automatically once it empties out (`consolidationPolicy: WhenEmptyOrUnderutilized`). Demonstrated live: scaling the backend beyond existing physical capacity brought up two new nodes within ~40 seconds, and they were automatically deleted within ~90 seconds after emptying out — Karpenter even logs the exact cost savings in its own logs.

## 9. Docker

A dedicated Dockerfile for the backend and for the frontend. The backend requires system libraries (`libzbar0`, `tesseract-ocr`) before `pip install` — so the image is built in layers (system deps → python deps → code), so Docker can use its cache and skip unchanged steps. The exact same image runs both locally (docker compose) and in the cloud — that's the whole point of containers: "works on my machine" becomes "works everywhere."

**Hardening:** the backend runs as a non-root user (`USER appuser` in the Dockerfile) — if the application is ever compromised (e.g. via a malicious image file in a ticket upload), the attacker doesn't get root inside the container. Port 8000 is unprivileged, so no further change was needed.

## 10. Terraform

All infrastructure lives under `terraform/`, with remote state in S3 (not a local state file) **and state locking** (`use_lockfile = true` — native S3 locking since Terraform 1.10, no DynamoDB table needed) which prevents two parallel `apply` runs from corrupting the state. Modules: `vpc`, `ecr`, `eks`, `rds`, `uploads` (S3), `dns` (Route53), `github-oidc`. Each module owns exactly one AWS resource area — not one giant file with everything mixed together.

**Additional hardening during the extension week:** EKS's public API endpoint is restricted to a specific IP only (`eks_public_access_cidrs` — open by default, so a clean `apply` never accidentally locks anyone out; GitHub Actions doesn't need this access at all, it only talks to ECR). An IRSA role + a tightly scoped IAM policy were added for the Karpenter controller (based on AWS's official template, with `RequestTag`/`ResourceTag` conditions ensuring it can never touch an instance it didn't create itself).

**Secrets management — everything through SSM Parameter Store (SecureString):** the RDS password, the key that signs user sessions, the Grafana admin password, and Google OAuth client ID/secret — all in SSM. Most are generated directly by Terraform's `random_password`; the Google OAuth credentials are the exception (they come from the Google Cloud Console, so they can't be auto-generated) — they're injected via a local `secrets.auto.tfvars` (gitignored) and from there into SSM like everything else, instead of being read directly from `.env` as they were until the finishing stage. No secret appears in code or in Git; the bootstrap script reads them from SSM at setup time and builds Kubernetes Secrets from them. (Originally the Grafana password and session secret were hardcoded in the script — identified and fixed in a pre-submission security audit.)

**One deliberate exception, left as-is:** `ALERTMANAGER_SMTP_PASSWORD` is still read from `.env`, not SSM. Unlike the other secrets, it isn't a raw value that can simply be relayed into a `random_password`/SSM parameter — SES SMTP requires a password *derived* from the IAM access key's secret key via HMAC-SHA256 (`scripts/derive-ses-smtp-password.py`), and vanilla Terraform has no built-in `hmac` function to compute that derivation itself. Moving it into SSM properly would mean either an `external`/`terraform_data` provider shelling out to that script during `apply`, or deriving and uploading the value out-of-band — real, but meaningfully more work than the Google OAuth fix for a lower-stakes value (a derived SMTP credential, not a raw external one). Documented here as a conscious tradeoff, not an oversight.

## 11. Monitoring

Prometheus + Grafana + Loki + Alertmanager — **all deployed through ArgoCD themselves**, not manual helm, to keep GitOps consistency even for the infrastructure that monitors the application. A custom dashboard (`fastiride-backend`) is built on real backend metrics (not just a generic community dashboard). Alertmanager is actually wired to SES and sends a real email — not just "alert rules nobody sees."

## 12. Screenshots

See `docs/images/` (the required screenshot list is detailed in the [README](README.md#screenshots)) — the ride board, ArgoCD with all Applications Synced/Healthy, both Grafana dashboards, a green CI run, and the RDS console.

## 13. Problems and Solutions

This is the genuinely interesting part — not "everything worked on the first try," but a series of real incidents I ran into and resolved:

**Cost incident — an abandoned cluster in Frankfurt ($153).** A routine AWS billing check revealed a full EKS cluster running in `eu-central-1` for about a month, not managed by Terraform at all. Verified via Route53 that it served no real traffic, and deleted it. **Lesson:** cost checks must scan multiple regions, not just the one in active use.

**IRSA bug — AWS permissions never actually worked.** The backend IAM role's trust policy pointed at the wrong namespace (`fastiride` instead of `fastiride-prod`) — every Rekognition/S3 call failed silently and fell back to local OCR, with no visible error. Only discovered by checking logs during a live test on AWS — testing in local Docker alone isn't enough.

**ArgoCD selfHeal erases manual changes.** A fix applied directly via `helm upgrade` (without a git push) was deleted within a minute by ArgoCD's automatic sync, because it reads the desired state **from Git only**. This lesson repeated itself the same way more than once — Git is the single source of truth, there's no "quick side fix."

**Silent 404s on the ALB health check.** The Load Balancer checked the default path `/` on the backend by default — but the API doesn't define such a route at all. Every check failed with a 404 every 10-30 seconds, which polluted the error-rate metrics (a simulated 44% error rate!) with no real impact on users. Fixed with an annotation scoped only to the backend's Service.

**Helm merge bug in Alertmanager.** Helm merges dictionaries but **replaces arrays entirely**. A custom `receivers` definition accidentally erased a default receiver named `"null"` (which silences the Watchdog heartbeat alert) that a route still pointed to — Alertmanager simply wouldn't start, until a matching receiver was restored.

**Orphaned PVCs — three times.** `helm uninstall` doesn't delete PVCs created via a StatefulSet — happened with Postgres, then again with Prometheus/Loki after the move to ArgoCD. Lesson: any StatefulSet migration/uninstall requires a separate `kubectl get pvc` check, never rely on automatic cleanup.

**Grafana deployment deadlock.** A `ReadWriteOnce` volume + the default `RollingUpdate` strategy (with a single replica) create a genuine deadlock — the new pod can't claim the volume while the old one holds it, but the old one won't terminate until the new one is ready. Fix: `strategy.type: Recreate`.

**A node failed to join the cluster.** Attempting to raise the pods-per-node limit (from 17 to 110, via prefix delegation), `terraform apply` failed: `User data was not in the MIME multipart format`. EKS requires a specific MIME multipart wrapper around the NodeConfig definition, not raw YAML — even if the YAML itself is valid. Fixed, and verified: both nodes came up with a capacity of 110 pods instead of 17.

**Migration to RDS.** Postgres originally ran as a StatefulSet inside the cluster (to save cost during the fast-iteration development phase). Ahead of submission, a full migration to managed RDS was carried out: a new Terraform module, a randomly generated password stored in SSM Parameter Store, updated bootstrap/teardown scripts, and removal of the StatefulSet from the Helm chart. Verified end-to-end: all 7 tables were created correctly on RDS (initially via the internal `ALTER TABLE IF NOT EXISTS` mechanism, later replaced by Alembic — see the next item).

**From `ALTER TABLE IF NOT EXISTS` to real Alembic.** For most of the project, schema changes were made by a code block in `main.py` that ran `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` on every application startup — it worked, but with no version history, no rollback option, and no review step before a change hit a real database. When asked directly whether this was good enough for a DevOps project, the honest answer was no — this is a real weak point, not just polish. The fix: `backend/migrations/` with Alembic wired to the real models and `DATABASE_URL`; a baseline migration autogenerated against an empty DB and verified (`alembic check`) to be **an exact match** for what the old mechanism had already built in practice; a new `initContainer` named `migrate` on the backend Deployment that runs `alembic upgrade head` before the main container starts — using the same image, the same secrets, and the same hardened `securityContext` (readOnlyRootFilesystem, non-root). Verified for real in both directions: a new migration adding a column (`rides.notes`) was created, tested locally, and deployed to staging's real RDS (verified via `psql` that the column exists) — then a reverse migration removed it the same way. This isn't just theory: it's a mechanism proven to work end-to-end on real infrastructure, in both directions.

**GitOps skew — the third occurrence, and the most painful one (Alembic).** Right as the new `initContainer` joined the chart, a brand-new cluster was raised from scratch (Terraform + `bootstrap-prod.sh`) — and on ArgoCD's very first sync to prod, the Deployment picked up the new chart (with `migrate`) but the image tag stayed pinned to the old version, which doesn't have `alembic` at all (only installed in the new image). The result: **both backend replicas in prod got stuck in `Init:CrashLoopBackOff` with `exec: "alembic": executable file not found`** — this time with no healthy old pod to fall back on, since the whole Deployment was freshly created. This is exactly the same pattern that already happened twice (probe path, nginx port), but this time with zero working replicas instead of a gradual degradation. Fixed the same way as before: a version tag (`v0.3.0`) promoting the matching image from staging, plus a manual `argocd app sync` to avoid waiting out the ~3-minute poll interval while prod was down. **The reinforced conclusion:** any chart change that assumes a capability inside the image (a binary, an endpoint, a port) must be followed by a version promotion **before or immediately after** the first sync on a new cluster — not wait for a CrashLoopBackOff to find out.

**Driver emails failed silently — since day one.** The email-notification feature (ride join requests) appeared to "work" ever since it was built — but in practice no email was ever actually sent: the sender address `noreply@fastiride.app` was never verified in SES, and a `try/except` in the code silently swallowed the error and fell back to a console print. Only discovered when a real user (me) noticed an email never arrived. Diagnosis: running the send function directly inside the pod (`kubectl exec`) revealed `Email address is not verified`. Fix: verified the **entire domain** in SES via DKIM — three CNAME records in Route53, all in Terraform (`ses-domain.tf`), with no manual clicking. **Two lessons:** (1) an overly quiet fallback hides real failures — it was meant for local development but masked a real production failure; (2) a real functional check (did the email actually arrive?) is worth more than code that merely looks correct.

**Ownership conflict between Helm and ArgoCD.** The bootstrap script ran `helm upgrade --install` on a release that was actually fully managed by ArgoCD — resulting in `invalid ownership metadata: missing key "meta.helm.sh/release-name"`. Reason: a resource created by ArgoCD only gets ArgoCD's own tracking annotation, not Helm's ownership annotations — so Helm refuses to "adopt" it. Point fix: added the annotations manually. Structural fix: removed the manual helm commands from the script entirely — ArgoCD is the **sole** writer of these manifests, from first deploy to the end. Two tools managing the same resource is always a bug waiting to happen.

**CI couldn't push to the protected branch.** After enabling branch protection on `main` (PR required), the job that updates the image tag in Git failed with `GH006: Protected branch update failed` — Actions' built-in `GITHUB_TOKEN` is subject to the protection rules, and on a personal (non-organization) repo, GitHub doesn't support configuring an app bypass. The fix: using the repo owner's Personal Access Token (a secret named `GH_PAT`) at the checkout step — the owner's own token is exempt from the PR requirement (with `enforce_admins` off). Three `gh api` attempts failed before the exact semantics of this API on personal repos became clear.

**ArgoCD failed to sync Prometheus's CRDs.** During a full cluster bring-up, `monitoring-prometheus` got stuck `OutOfSync` with `metadata.annotations: Too long: may not be more than 262144 bytes`. Reason: kube-prometheus-stack's CRDs are large enough that the client-side-apply annotation (`last-applied-configuration`, which stores the entire previous config for a 3-way diff) exceeds Kubernetes' annotation size limit. The documented fix: `syncOptions: [ServerSideApply=true]`, which tracks ownership per-field instead of via a whole annotation. A second, more subtle problem surfaced right after: the Prometheus Operator itself **started before** the CRDs were successfully created, logged "resource not installed" at startup, and never checked again — a manual `kubectl rollout restart` was needed so it would rediscover the CRDs that already existed. Lesson: a race condition during bootstrap can "get stuck" in a component that's already up, not just in a resource that hasn't been created yet — a restart is a legitimate diagnostic tool, not just "turning it off and on again."

**Ticket validation was fully bypassable — fixed after a threat-model discussion.** The original check (`_ticket_matches`) only verified whether the event name's words appeared in the text detected in the image (OCR/barcode) — a trivial bypass: any image with the right text "written on it" in an image editor would pass. The fix went through several real rounds of thinking: first, connecting to the producer's own ticketing API was considered — rejected, because (a) it's not technically realistic across different ticketing platforms without a business agreement, and (b) **even if it were realistic, it wouldn't close the real risk** — a ticket is a product anyone can purchase, including a hostile actor; verifying "this is a genuine ticket" is not equivalent to identity verification. The key insight: in Israeli festival culture, producers actually perform selection on who receives a ticket — so verifying "is this a genuine ticket the producer issued" indirectly inherits the selection process the producer already carried out. The final, layered solution: (1) a readable barcode/QR became mandatory — closes "there's no real ticket at all"; (2) the producer can optionally upload (at event creation, addable at any time) samples of genuine tickets; (3) when samples exist, **visual similarity (average-hash, no new dependency) is the only signal that decides — text plays no part in the decision at all**, since text is exactly what an attacker controls; an initial attempt that fell back to text when visual similarity failed turned out to reopen the exact same hole (an attacker with an old ticket + faked text would have passed) and was fixed. Verified with synthetic ticket images: an old ticket with a pasted-on name (different design, real barcode) — blocked; a buyer from a second sales round (same template, different label) — still passes, since perceptual hashing tolerates small local edits and is strict only against a wholesale different design.

**GitOps skew — chart changes immediately, image tag doesn't (twice, same lesson).** The Helm chart (Deployment/Service/Probe specs) tracks `main` **in both environments simultaneously** via ArgoCD, regardless of version tagging — only `image.tag` stays frozen until an explicit promotion. Twice in the same week a chart change "ran ahead" of the old image still running in prod: first when `readinessProbe` moved to `/api/ready` (an endpoint that didn't exist in the old image — `fastiride.app` returned 503 on every request), second when nginx switched to listening on port 8080 (the Service routed everyone to that port immediately, but the old image still listened on 80 — 502 on every request, even from pods that "passed" their own old probe). Both cases were fixed the same way: an immediate version tag promoting the matching image. **Standing lesson:** any change to a container's port/probe/structure requires an immediate version promotion, not "at the end of the week" — otherwise prod breaks itself on its own.

**Karpenter — wrong API version, not a CRD problem.** The Helm chart's metadata claimed `v1beta1` for EC2NodeClass/NodePool, but the version actually installed by chart 1.14.0 is `v1` — only discovered by checking directly against the live CRD (`kubectl get crd ... -o jsonpath='{.spec.versions[*].name}'`), not the documentation. Also, `nodeClassRef` under v1 requires explicit `group`/`kind`, not just `name`. **Lesson:** chart metadata can be stale — the only reliable check is against the actual live CRD.

**VPC CNI addon schema — not every env var is real.** A first attempt to enable NetworkPolicy placed `ENABLE_NETWORK_POLICY` under `env` (next to two similar existing settings) — failed immediately in `terraform apply`'s own schema validation (without touching anything). The correct field is a top-level one, `enableNetworkPolicy` — discovered via `aws eks describe-addon-configuration`. **Lesson:** always check an addon's actual schema, don't assume every similar-looking env var goes in the same place.

**CI doesn't trigger from a change to itself.** `ci.yaml` is configured with a `paths:` filter on `backend/**`/`frontend/**`/`helm/**` — a change to the workflow file itself does **not** trigger it. Discovered when trying to test a CI change and `deploy-staging` simply didn't run. Testing a change to CI itself requires pairing it with a real change in one of those directories.

**SES sandbox — production access request denied.** Despite a detailed, professional answer to every question asked, AWS denied the request (most likely an automated review based on account age/history, not the content of the request). **Workaround chosen instead of waiting further:** manually verifying specific email addresses in SES (still sandbox mode, but ensures emails work for the demo). Documented as a deliberate decision, not a hidden gap — the sandbox is still active, and an unverified address simply won't receive any email.

## 14. Code Screenshots

Recommended representative code snippets to capture and add here:
- `backend/main.py` — the `/metrics` endpoint wiring (`Instrumentator().instrument(app).expose(app)`)
- `helm/fastiride/templates/postgres-backup-cronjob.yaml` — the full CronJob
- `terraform/modules/rds/main.tf` — the RDS definition
- `terraform/ses-alerting.tf` — the SES identity and IAM user for Alertmanager
- `.github/workflows/ci.yaml` — the full pipeline (lint → test → build → GitOps bump)
- `backend/tests/test_join_flow.py` — an example of a real unit test

## 15. Personal Summary

_(Draft below — read it, cut/rewrite anything that doesn't sound like you, add anything real that's missing. It's meant as a starting point, not a final answer.)_

Going into this project, I thought of DevOps mostly as "the thing that runs the app" — a supporting layer around the real work of building features. By the end, it had become the actual subject: the application itself was almost secondary to the question of how it gets built, tested, deployed, scaled, secured, and recovered without a person having to babysit any of those steps by hand. That shift in perspective is the main thing I take away from this project.

Concretely, that meant learning to distrust anything I hadn't verified live. It's one thing to write a NetworkPolicy or an HPA config and see it apply cleanly; it's another to actually try to break past it — hit a blocked namespace and confirm it times out, push load until pods visibly scale, kill a dependency and watch the system degrade the way it's supposed to instead of the way I assumed it would. Almost every real lesson in this project came from that gap between "the YAML looks right" and "I watched it behave correctly under real conditions."

The most challenging part was less about any single technology and more about the discipline of GitOps itself: once ArgoCD owns the cluster, every change has to go through Git, in the right order, or it gets silently overwritten or — worse — half-applied in a way that only breaks production once, later, when it's least convenient. I hit that lesson from a few different angles over the course of the project, and each time the fix was small but the failure mode was the same: assuming a manual shortcut was safe because it "worked" in the moment.

If I were starting over, I'd bring in the practices I only added under deadline pressure — real migrations instead of ad-hoc schema patches, a message bus instead of in-memory state, tighter security defaults — from day one, instead of treating them as upgrades to bolt on later. Building them in from the start would have meant fewer moments of finding out, live, that something I thought was solid actually wasn't.

---

## Appendix: Exam Prep

Answers tied directly to this project, not generic definitions from the internet:

**What does Docker do?**
Packages the application (code + dependencies + system libraries like `libzbar0`) into one self-contained image, which runs identically everywhere — locally and in the cloud it's the exact same `fastiride-backend` image.

**Why Kubernetes?**
Because a single EC2 instance doesn't bring itself back to life when it crashes. Kubernetes maintains a desired replica count (backend, frontend), routes traffic even as pods are replaced (Service), and allows zero-downtime deploys (rolling update).

**What happens on a Push?**
To `main` (after a PR merge): GitHub Actions runs lint, then pytest. If both pass — it builds images, pushes to ECR, and updates the tag in `values-staging.yaml` **in Git itself** (never touches the cluster directly). This deploys to **staging only**, automatically, on every merge.

**How does deployment happen?**
ArgoCD scans the repo roughly every ~3 minutes (its default reconciliation interval, never overridden in this project) and sees the values file changed — applies it to the cluster on its own. I never run `kubectl apply` or `helm upgrade` manually. **Production does not update on every merge** — only when a git tag in the format `vX.Y.Z` is pushed, which runs a separate workflow (`promote-to-production.yaml`) that copies the existing tags from `values-staging.yaml` (an image already built and tested) into `values-prod.yaml` — without rebuilding. This way production always runs exactly what already worked on staging.

**Why Terraform?**
Because otherwise the infrastructure only exists "in my head" and in the AWS console — impossible to reproduce, verify, or explain precisely what exists and why. With Terraform, `terraform destroy` followed by `terraform apply` rebuilds the exact same infrastructure.

**How does Grafana connect?**
Through two pre-configured datasources (Prometheus for metrics, Loki for logs) — their internal Service addresses within the cluster (`monitoring-prometheus-kube-prometheus.monitoring.svc.cluster.local:9090`, etc.).

**What does ArgoCD do?**
"Pulls" the desired state from Git and applies it — as opposed to CI, which "pushes." ArgoCD also detects drift between what's actually running and what's written in Git, and corrects it automatically (`selfHeal`) — I ran into this for real when a manual fix that never reached Git was erased within a minute.

**How does the system update itself?**
The GitOps loop: push → CI builds and updates the tag in Git → ArgoCD detects it and syncs. No person touches the cluster between these steps.

**Where are the system's secrets?**
In AWS SSM Parameter Store, as SecureString: the RDS password, the session-signing key, the Grafana password, and — since the finishing stage — the Google OAuth client ID/secret too. Most are generated directly by Terraform (`random_password`); the Google OAuth credentials are the exception — they can't be auto-generated since they come from the Google Cloud Console, so they're injected into Terraform via a local `secrets.auto.tfvars` (gitignored, never in Git) and from there into SSM like everything else. Until the finishing stage they were the real exception — still read directly from `.env` in `bootstrap-prod.sh`, a deviation from the architectural principle I'd stated. Fixed so every secret flows through the same, single path. Everything is read by the bootstrap script, which builds Kubernetes Secrets from them. No secret is in Git — the local `.env` is in `.gitignore`, and in-cluster permissions are IRSA-based (one IAM role per ServiceAccount) with no static keys.

**What happens if the DB is deleted?**
A daily CronJob runs `pg_dump`, compresses it, and uploads it to S3 (`db-backups/`), using the same IRSA role the backend already has (no new IAM needed). In addition, RDS is managed with AWS's automatic backups. Restore: `gunzip -c backup.sql.gz | psql $DATABASE_URL` — **not** `pg_restore` (that's for pg_dump's custom format; this is a plain text dump, `psql` is the right tool). The drill was tested for real: a real test row was seeded, a backup taken, restored into a separate scratch database (the real data was never touched), verified the exact row survived, and cleaned up.

**What's the difference between HPA and Karpenter?**
Two completely different scaling layers. HPA adds/removes **pods** within existing nodes, based on a metric (CPU/memory) — doesn't touch infrastructure. Karpenter solves what happens when HPA already wants more pods than the existing nodes can provide (pods get stuck `Pending`) — it provisions a real **node** (EC2) in under a minute, and removes it automatically once it's empty. Both work together: HPA detects load at the application level, Karpenter detects a lack of capacity at the infrastructure level.

**How does NetworkPolicy protect the cluster?**
Kubernetes' default: any pod can talk to any other pod in the cluster, including across namespaces (staging could talk to prod!). NetworkPolicy turns this into deny-by-default: block all incoming traffic, then explicitly allow only what's actually needed — the ALB (public subnet) to backend/frontend, Prometheus (a separate namespace) to backend:8000 only, and the backend only to redis. Tested for real with a temporary pod: an unauthorized namespace gets a genuine timeout (not a 403 — an actual network block), not just "the policy exists."

**How do you know the system is healthy right now?**
Three layers: Kubernetes probes (liveness/readiness on every pod), a RED dashboard in Grafana (Rate/Errors/Duration on the real API), and Alertmanager, which sends a real email via SES if an alert fires — including an alert for a backend that stops responding.

**How does a DB schema change reach production?**
Through Alembic, not manually. Every schema change (`models.py`) gets a versioned migration file (`alembic revision --autogenerate`), with an `upgrade()` and `downgrade()` function, tested locally, and goes through the exact same GitOps flow as any code change. In Kubernetes, an `initContainer` named `migrate` on the backend Deployment runs `alembic upgrade head` **before** the main container starts — so no replica ever starts serving traffic against an incompatible schema. This used to be done with a manual `ALTER TABLE IF NOT EXISTS` block in `main.py` — it worked, but with no version history and no rollback; replaced on my own initiative, after honestly assessing it as a real weak point for a DevOps project.

**Does the app's ticket validation actually prevent fraud?**
No, and it doesn't claim to. Even with the upgraded check (mandatory barcode + visual similarity to a genuine ticket) — someone who genuinely wants to get in can simply buy a legitimate ticket, since a ticket is a product anyone can purchase; this isn't identity verification. The point of the check is to filter out **casual, opportunistic** access to the ride-sharing group (someone copy-pasting text in an image editor), not to replace physical security at the event itself. It matters to me that this is written down clearly, not just "it works" — a solution that projects false confidence is worse than one that's honest about its limits.
