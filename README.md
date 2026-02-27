# Azure Migration Architect — GitLab Duo Agent

> **GitLab AI Hackathon Submission**
> Automatically converts Terraform & Docker infrastructure code into Azure-native Bicep templates, then opens a Merge Request — all orchestrated by GitLab Duo.

---

## Problem

Migrating infrastructure to Azure is a manual, error-prone process.  Developers push generic Terraform or Docker configs, then an engineer must:

1. Translate each resource to its Azure equivalent
2. Write valid Bicep / ARM templates
3. Estimate monthly costs
4. Open a review branch with all the changes

**This agent automates the entire flow.**

---

## How It Works

```
┌──────────────┐     ┌─────────────────────────┐     ┌──────────────────┐
│  git push     │────▶│  GitLab Duo Agent        │────▶│  Merge Request   │
│  (.tf / Docker)│     │  "Azure Migration        │     │  • Bicep files   │
│               │     │   Architect" prompt       │     │  • Cost estimate │
└──────────────┘     └─────────────────────────┘     └──────────────────┘
        │                        │                            │
   Webhook /               AI generates                GitLab API:
   CI trigger              valid .bicep              create branch →
                           + cost table              commit → open MR
```

### Trigger
A push containing `.tf` or `Dockerfile` changes fires the CI pipeline (or a webhook configured in `agent-config.yml`).

### Generate
The **Azure Migration Architect** prompt template (`prompts/azure_migration_architect.md`) instructs GitLab Duo to:
- Analyze the original code and identify Compute, Storage, Networking, and Database resources
- Map each to the Azure-native equivalent (e.g., AWS RDS → Azure Database for PostgreSQL)
- Output production-ready `.bicep` with best-practice patterns (managed identities, Key Vault, diagnostic settings)
- Include a monthly cost estimate table

### Publish
The automation script (`scripts/open_migration_mr.py`) uses the **GitLab REST API** to:
1. Create a `migrate-to-azure` branch
2. Commit the generated `.bicep` files
3. Open a Merge Request with the migration summary, resource mapping, and cost estimate

---

## Repository Structure

```
.
├── LICENSE                              # MIT (required by hackathon rules)
├── README.md                            # ← you are here
├── agent-config.yml                     # GitLab Duo Agent Platform config
├── gitlab-ci.yml                        # CI/CD pipeline definition
├── prompts/
│   └── azure_migration_architect.md     # AI prompt template
├── scripts/
│   └── open_migration_mr.py            # GitLab API automation (Python 3.12, stdlib only)
└── examples/
    ├── sample_main.tf                   # Example Terraform input
    ├── sample_Dockerfile                # Example Dockerfile input
    └── generated_main.bicep             # Example Bicep output
```

---

## Quick Start

### Prerequisites
| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.10+ | Runs the automation script |
| GitLab Account | Free+ | Hosts the repo & agent |
| GitLab API Token | Project or Group | Creates branches & MRs |
| Azure Service Principal | *(optional for demo)* | Validates Bicep deployments |

### 1. Clone & configure

```bash
git clone https://gitlab.com/<your-namespace>/hackathon-azure-migration-architech-.git
cd hackathon-azure-migration-architech-
```

### 2. Set CI/CD variables

In **Settings → CI/CD → Variables**, add:

| Variable | Description |
|----------|-------------|
| `GITLAB_API_TOKEN` | Project access token with `api` scope |
| `AZURE_SUBSCRIPTION_ID` | *(optional)* Your Azure subscription |
| `AZURE_TENANT_ID` | *(optional)* Azure AD tenant |
| `AZURE_CLIENT_ID` | *(optional)* Service Principal app ID |
| `AZURE_CLIENT_SECRET` | *(optional)* Service Principal secret |

### 3. Push infrastructure code

```bash
cp examples/sample_main.tf main.tf
git add main.tf && git commit -s -m "feat: add sample Terraform config"
git push origin main
```

The pipeline detects the `.tf` change, invokes the agent prompt, and opens a Merge Request with Azure Bicep templates.

### 4. Review the MR

Open the auto-generated MR labeled `azure-migration, automated, duo-agent`. It contains:
- **Migration Summary** — what was detected and converted
- **Resource Mapping** table — AWS → Azure service mapping
- **Cost Estimate** table — monthly Pay-As-You-Go pricing
- **Bicep files** ready to deploy with `az deployment group create`

---

## Example: AWS → Azure Migration

### Input (`sample_main.tf`)

| AWS Resource | Type |
|---|---|
| `aws_instance.web` | EC2 t3.medium |
| `aws_db_instance.postgres` | RDS PostgreSQL 15 |
| `aws_s3_bucket.assets` | S3 with versioning |

### Output (`generated_main.bicep`)

| Azure Resource | SKU | Est. Monthly Cost |
|---|---|---|
| Container App (`ca-webapp-server`) | 1 vCPU / 2 GiB | ~$36 |
| PostgreSQL Flexible Server (`psql-webapp-db`) | Standard_B1ms | ~$25 |
| Storage Account (`stwebappassets`) | Standard_LRS | ~$2 |
| Log Analytics Workspace | PerGB2018 | ~$5 |
| **Total** | | **~$68** |

---

## SDLC Impact

- **Accelerates cloud migration** — from days of manual refactoring to a single `git push`
- **Enforces Azure best practices** — managed identities, Key Vault, private endpoints
- **Cost transparency** — developers see the bill *before* they deploy
- **Full GitLab integration** — branches, commits, MRs, and labels are automated end-to-end

---

## Demo Video Outline (3 min)

| Timestamp | Content |
|-----------|---------|
| 0:00–0:45 | Push a "messy" Terraform file to GitLab |
| 0:45–2:00 | Show the CI pipeline / Duo Agent generating Bicep |
| 2:00–3:00 | Review the auto-created MR with cost estimate |

---

## Licensing & DCO

- **License:** MIT — see [LICENSE](LICENSE)
- **Developer Certificate of Origin:** All commits are signed (`git commit -s`) per GitLab's DCO requirement.

---

## Built With

- [GitLab Duo Agent Platform](https://docs.gitlab.com/ee/user/duo_workflow/)
- [Azure Bicep](https://learn.microsoft.com/azure/azure-resource-manager/bicep/)
- [GitLab REST API](https://docs.gitlab.com/ee/api/)
- Python 3.12 (stdlib only — zero external dependencies)