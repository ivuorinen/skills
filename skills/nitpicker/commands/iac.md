# /nitpicker iac — Infrastructure-as-Code Audit

Hostile audit of infrastructure-as-code — container images (Dockerfiles), orchestration (Kubernetes, Compose, Helm), and cloud provisioning (Terraform, CloudFormation, Pulumi): assume every image runs as root, every network is open to the world, every store is unencrypted, and every credential is committed, until each file proves otherwise.

## When to use

- Auditing Dockerfiles, `docker-compose*.yml`, Kubernetes manifests, Helm charts, Terraform, CloudFormation, or Pulumi for security and reliability defects
- A new service, container, or cloud resource was added and you need to confirm it is not world-exposed, root-privileged, or leaking secrets
- Before a deploy, to prove no resource ships public, unencrypted, or over-permissioned
- When asked to "audit the infra", "audit the Dockerfiles", "check Terraform security", "is this k8s manifest hardened", or "review the IaC"

Out of scope: CI/CD pipeline definitions (`.github/workflows/`, `.gitlab-ci.yml`) route to `/nitpicker ci`; application-source vulnerabilities and committed secrets in application code to `/nitpicker security`; runtime env-var documentation and config drift in the app layer to `/nitpicker config`; dependency CVEs to `/nitpicker deps`. A repo with no infrastructure-as-code files gets the explicit verdict "no IaC surface".

## Process

1. **Enumerate IaC files.** `Dockerfile`, `*.Dockerfile`, `Containerfile`; `docker-compose*.{yml,yaml}`, `compose*.{yml,yaml}`; Kubernetes manifests (`*.{yml,yaml}` carrying `apiVersion:` + `kind:`); Helm charts (`Chart.yaml`, `templates/**`, `values*.yaml`); Kustomize (`kustomization.yaml`); Terraform (`*.tf`, `*.tf.json`, `*.tfvars`); CloudFormation (`*.{yml,yaml,json}` with `AWSTemplateFormatVersion` or a top-level `Resources:`); Pulumi (`Pulumi.yaml`, `__main__.py`/`index.ts` in a Pulumi project). When unsure whether a YAML/JSON file provisions infrastructure, examine it — "unrecognized" is not "absent". Record the count. Every enumerated file is examined against every applicable defect class — never sample. A run with unexamined files has verdict INCOMPLETE.
2. **Run installed analyzers.** Probe with `command -v` for `hadolint` (Dockerfiles), `checkov`, `tfsec`, `trivy` (`trivy config`), `terrascan`, `kics`, `kube-score`, `kubesec`, `kubeconform`. Run each tool found against the matching files (`hadolint <file>`; `checkov -d . --compact`; `trivy config --format json .`); record a missing tool as "not available" and a crashed tool as "errored: <message>" — a tool failure never aborts the run. Never install a tool. Parse output into findings, deduplicating on file + line + class; list every source in Evidence. Tool output supplements the manual sweep in step 3 — it never replaces it: scanners miss cross-file exposure (a public LB in front of a no-authn service), intent, and drift from the running environment.
3. **Manual defect-class sweep.** Check every enumerated file against every applicable class in the defect classes table. Read each Dockerfile instruction, container `securityContext`, security-group/firewall rule, IAM policy document, and storage/database resource end-to-end — grep alone misses a `USER` reset by a later stage, an IAM `Action: "*"` split across a variable, and ingress opened in a separate rule block.
4. **Trace exposure end-to-end.** For each network-reachable resource, follow the path from the internet inward: an open security group (`0.0.0.0/0`) is Critical in front of an unauthenticated database, Advisory in front of a public CDN. A `LoadBalancer`/`Ingress` with no auth, a storage bucket with public-read ACL or policy, and a database with a public endpoint are each traced to what they expose. Missing exposure analysis is a coverage gap, not a pass.
5. **File findings** via the store protocol in `_conventions.md`, using `--auditor iac`. Each finding records the class, the tool sources (hadolint, checkov, manual), Evidence (file:line plus the concrete attack or blast radius), Impact (what an attacker reaches or what fails), and Fix (the exact remediation: the `securityContext` block, the CIDR to narrow to, the `encrypted = true` line, the base-image digest to pin). A committed secret is filed regardless and its rotation instructed.
6. **Summarize and fix.** The summary states the run verdict (COMPLETE only if every enumerated file was examined and every exposed resource traced), tool coverage, and counts by resource type. Fix application and the commit gate follow `_conventions.md`, with this override: the (s)afe option applies only additive hardening that cannot break a running deploy (pinning a base image digest, adding a `securityContext`, adding `encrypted = true` to a not-yet-created resource) — never a CIDR narrowing or a resource replacement that can sever live access. After each fix, re-check the cited location and re-run the analyzer on the changed file.

### Defect classes

| Class | What to flag | Fix shape |
| --- | --- | --- |
| **root-container** | Container with no `USER` (runs as root); Dockerfile `USER root` at the final stage; k8s `securityContext.runAsNonRoot` absent/false, `runAsUser: 0`, or `privileged: true`; `allowPrivilegeEscalation` not false | Add a non-root `USER <uid>` in the final stage; k8s `runAsNonRoot: true`, `runAsUser: <non-zero>`, `allowPrivilegeEscalation: false`, drop `privileged` |
| **unpinned-base-image** | `FROM image:latest`, a mutable tag, or no tag; a base image with no `@sha256:` digest; a k8s/Compose `image:` on `:latest`, a mutable tag, or with no digest; `apt-get`/`apk`/`pip` install without a version | Pin `FROM image:tag@sha256:<digest>` and every `image:` reference; pin package versions; rebuild reproducibly |
| **committed-secret** | Hardcoded password/token/key/connection-string in a Dockerfile `ENV`/`ARG`, `*.tfvars`, a Compose `environment:`, a k8s `Secret` with inline plaintext `data`/`stringData`, or a CloudFormation parameter default | Move to a secrets manager / sealed secret / CI secret injected at deploy; rotate the exposed value; never bake secrets into an image layer |
| **open-ingress** | Security group / firewall / NSG / k8s `NetworkPolicy` allowing `0.0.0.0/0` (or `::/0`) inbound to SSH (22), RDP (3389), a database port, or an admin panel; a Service `LoadBalancer` with no source restriction | Narrow the CIDR to known ranges or a bastion; put admin behind a VPN/allowlist; scope the `NetworkPolicy` ingress |
| **public-data-store** | S3/GCS/Azure bucket with public-read/write ACL or a wildcard-principal policy; a database (RDS/CloudSQL) with `publicly_accessible = true`; a container registry set public; a snapshot shared with `all` | Remove public access; block-public-access at account+bucket; private subnet + no public endpoint for databases |
| **unencrypted-resource** | Storage bucket, EBS/PD volume, RDS/CloudSQL instance, or backup with encryption-at-rest disabled or absent; a load balancer/listener serving plaintext HTTP with no TLS; secrets store unencrypted | `encrypted = true` / KMS key; enforce TLS listeners and redirect HTTP→HTTPS; enable at-rest encryption on every store |
| **overbroad-iam** | IAM policy/role with `Action: "*"`, `Resource: "*"`, `Allow` on `*:*`, `iam:PassRole` unscoped, an admin managed-policy on a service role, or a k8s `ClusterRole` with `verbs: ["*"]` on `resources: ["*"]` | Scope actions and resources to exactly what the workload uses; replace `*` with concrete ARNs/verbs; no admin on service roles |
| **metadata-credential-exposure** | EC2 / launch template / instance without `http_tokens = "required"` — IMDSv1 lets an app-side SSRF steal the instance role's credentials; an over-high metadata hop limit | Require IMDSv2 (`http_tokens = "required"`, `http_put_response_hop_limit = 1`) |
| **missing-audit-logging** | CloudTrail disabled, single-region, or without log-file validation; VPC flow logs absent; S3 bucket with no server-access `logging`; ALB/ELB/CloudFront access logs off; RDS/EKS control-plane audit logs off; no k8s audit policy | Enable multi-region CloudTrail with log-file validation; turn on VPC flow logs; point S3/ALB access logs at a restricted log bucket; export audit logs |
| **missing-limits** | k8s container with no `resources.limits`/`requests` (a noisy neighbor or OOM starves the node); no `livenessProbe`/`readinessProbe`; a Compose service with no restart policy or resource cap | Set CPU/memory `requests` and `limits`; add liveness/readiness probes; set a bounded restart policy |
| **no-durability-control** | RDS/CloudSQL with `deletion_protection = false`, no `backup_retention_period`, or `skip_final_snapshot = true`; S3 bucket without versioning or MFA-delete; a stateful volume with no snapshot policy | Enable deletion protection and backup retention; disable final-snapshot skipping; turn on bucket versioning; define a snapshot policy |
| **host-namespace-mount** | `hostNetwork`/`hostPID`/`hostIPC: true`; a `hostPath` volume mounting `/`, `/var/run/docker.sock`, or a sensitive host path; a Compose service mounting the Docker socket or running `network_mode: host` / `privileged: true` | Remove host namespace sharing; drop the docker.sock mount; use a scoped volume, not a host bind mount |
| **excess-capabilities** | Container adding Linux capabilities (`SYS_ADMIN`, `NET_ADMIN`, `ALL`); `readOnlyRootFilesystem` absent/false where the workload does not write; default ServiceAccount token auto-mounted into a pod that never calls the API | Drop `ALL` and add back only required capabilities; `readOnlyRootFilesystem: true`; `automountServiceAccountToken: false` when unused |
| **no-drift-control** | Terraform/Pulumi state file committed to git; no remote state backend; no state locking; a provider or module referenced by a mutable/`latest`/floating version instead of a pinned constraint | Remote encrypted state backend with locking; gitignore state; pin provider and module versions |
| **dockerfile-hygiene** | Secret fetched then removed in a later layer (still present in the earlier layer); `ADD <url>` (unverified remote fetch) where `COPY` suffices; `curl \| sh` in a `RUN`; broad `COPY . .` pulling `.git`/secrets into the image | Multi-stage build so secrets never enter a persisted layer; `COPY` local files; verify checksums; a `.dockerignore` excluding `.git`/secrets |

## Severity guide

Absent explicit evidence a workload is non-production — a `dev`/`staging` namespace, path, or variable in the file itself — rate it as production. Unproven environment is never a down-severity reason.

| Severity | Condition |
| --- | --- |
| Critical | Data or credential exposed to the internet or a live secret committed: a public-read data store or `0.0.0.0/0` ingress to an unauthenticated database/admin port; a plaintext secret in a committed IaC file; a `privileged`/docker.sock container reachable from untrusted input |
| High | Root/privileged container in a deployed workload; overbroad-IAM (`*:*` reachable) on an assumable role; IMDSv1 on an instance running attacker-reachable code; unencrypted-at-rest data store holding sensitive data; host-namespace mount; committed Terraform state exposing secrets |
| Medium | Unpinned/`:latest` base image in a deployed service; missing resource limits or probes on a production workload; excess capabilities; open ingress to a non-sensitive port; audit/access logging disabled on an account or store holding sensitive data; no durability control on a stateful store; no state locking |
| Low | Missing `.dockerignore`; `ADD <url>` where `COPY` suffices; mutable provider/module version with a lockfile present; missing readiness probe on a non-critical job |
| Advisory | Hardening with no current blast radius (e.g. `readOnlyRootFilesystem` on a workload that writes nothing sensitive); first-party-registry base image unpinned in a dev-only image |

## Fix strategy

**Auto-applicable:**

- Add a non-root `USER`/`securityContext` (`runAsNonRoot`, `allowPrivilegeEscalation: false`, drop `ALL` capabilities)
- Pin a base image to `tag@sha256:<digest>`
- Add `encrypted = true` / a KMS key to a not-yet-created resource
- Require IMDSv2 (`http_tokens = "required"`) and enable audit logging on a not-yet-created resource
- Add `resources.limits`/`requests` and liveness/readiness probes
- Add a `.dockerignore` excluding `.git` and secret paths

**Requires explicit approval per change:**

- Narrowing a security-group CIDR or `NetworkPolicy` (can sever live access)
- Removing `publicly_accessible`/public ACL on an existing resource (can break current consumers)
- Scoping an IAM policy (can break a workload silently relying on the breadth)
- Moving state to a remote backend, or enabling deletion protection on a live resource (a migration, not an edit)

**Never auto-apply:**

- Secret rotation — name the exposed secret (redacted) and instruct rotation; rotation is the user's action
- Deleting or replacing a live resource to fix a finding
- Weakening any existing control (widening a CIDR, removing encryption) to make a plan apply

## Common mistakes

These are the rationalizations this command exists to defeat. Each one is forbidden.

**"There's no Terraform here, just a Dockerfile, so IaC is N/A."** A Dockerfile is IaC; so is one Compose file, one k8s manifest, or one Helm chart. The "no IaC surface" verdict applies only when the repo has zero infrastructure files of any kind. One Dockerfile earns a full audit against every applicable class.

**"It's behind a VPC/firewall, so the container running as root is fine."** Defense in depth is the point: the firewall is one layer, and a root container turns any app-level RCE into host compromise. Root + a reachable app bug is privilege escalation, not a non-issue. Flag the root container at the severity its reachability earns.

**"`:latest` is convenient and it's just the base image."** `latest` is a mutable pointer: the image that builds today is not the image that redeploys next month, and a compromised or yanked tag ships silently. Pin the digest; the tag stays readable in the comment.

**"That `0.0.0.0/0` is temporary / it's only the staging security group."** Staging holds real data and real credentials, "temporary" rules outlive the person who added them, and an open database port is scanned within minutes of going live. Trace what the CIDR exposes and file it at that severity.

**"The secret is only in a `.tfvars` / it's a low-value token."** A credential committed to git is exposed to everyone with repo access and to every fork and mirror forever, and git history keeps it after deletion. Every committed secret is a finding, redacted in Evidence, with rotation instructed — there is no low-value committed credential.

**"checkov/tfsec passed, so the infra is secure."** Scanners check per-resource rules against a policy set; they do not trace that a public load balancer sits in front of an unauthenticated service, that an IAM role's breadth matches an assumable principal, or that the manifest matches what is actually running. Tool output feeds the manual sweep; it never replaces it.

**"The Dockerfile deletes the secret in the next `RUN`, so it's gone."** Each instruction is a layer; a secret added in one layer and removed in a later one is still recoverable from the earlier layer in the pushed image. Only a multi-stage build where the secret never enters the final stage removes it. Flag it.

**"There are forty manifests; I'll check the ones that run in prod."** The manifest nobody reads is where the privileged container and the wildcard IAM role live, and "dev-only" resources share accounts, networks, and secrets with prod. Every enumerated file is examined; a run that samples has verdict INCOMPLETE and says so.

**"It's a managed service, so encryption/limits/logging are the provider's job."** The provider offers the control; leaving it off is your configuration choice, and the default is frequently unencrypted, unbounded, or un-logged. An absent `encrypted`/`limits`/audit-log setting is your finding, not the provider's.

**"I described the hardening, so the finding is handled."** A described fix is an open finding. A finding is resolved only after the change is applied, the cited location re-checked, and the analyzer re-run on the changed file.
