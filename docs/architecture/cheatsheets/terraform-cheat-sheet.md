# Cheat Sheet — Terraform

> Terraform declares infrastructure as code and reconciles real resources toward it
> through a state file. The core loop is write, then init, plan, apply.

## Core workflow

```bash
terraform init            # download providers/modules, configure the backend
terraform fmt -recursive  # canonical formatting
terraform validate        # static validation
terraform plan -out=tfplan
terraform apply tfplan
terraform destroy
```

## State commands

```bash
terraform state list
terraform state show aws_s3_bucket.data
terraform state mv aws_s3_bucket.a aws_s3_bucket.b
terraform state rm aws_s3_bucket.gone        # forget without destroying
terraform import aws_s3_bucket.data my-bucket
terraform output -json
terraform refresh                            # reconcile state with real world
```

- Never hand-edit `terraform.tfstate`. State can hold secrets, so store it remotely,
  encrypted, and with locking enabled.

## Variables, outputs, locals

```hcl
variable "region" {
  type    = string
  default = "eu-west-1"
}

locals {
  name = "platform-${var.environment}"
}

output "bucket_arn" {
  value = aws_s3_bucket.data.arn
}
```

```bash
terraform apply -var 'region=us-east-1'
terraform apply -var-file=prod.tfvars
# precedence: -var/-var-file > TF_VAR_* env > *.auto.tfvars > terraform.tfvars > default
```

## Modules

```hcl
module "network" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"
  name    = local.name
  cidr    = "10.0.0.0/16"
}
```

- Pin module and provider versions. Reference outputs as `module.network.vpc_id`.

## Backends (remote state)

```hcl
terraform {
  backend "s3" {
    bucket         = "tfstate-platform"
    key            = "prod/network.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "tf-locks"
    encrypt        = true
  }
}
```

## Workspaces

```bash
terraform workspace new staging
terraform workspace select prod
terraform workspace list
# reference the active workspace as terraform.workspace in config
```

- Workspaces suit lightweight variants of one config; prefer separate state keys or
  directories for strong environment isolation.

## Meta-arguments

| Meta-argument | Purpose |
|---------------|---------|
| `count` | N copies; index with `count.index` |
| `for_each` | One per map/set key (stable addressing) |
| `depends_on` | Explicit ordering when implicit refs are not enough |
| `lifecycle` | `create_before_destroy`, `prevent_destroy`, `ignore_changes` |
| `provider` | Pick an aliased provider instance |

## Providers & versions

```hcl
terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}
```

- Commit `.terraform.lock.hcl` so every run uses identical provider versions.
- In CI, gate on `terraform plan -detailed-exitcode` (0 = no changes, 2 = changes).
- Handy functions: `coalesce`, `try`, `lookup`, `merge`, `templatefile`,
  `jsonencode`, `cidrsubnet`.

## Testing & quality

```bash
terraform fmt -check -recursive
terraform validate
tflint                                  # lint and provider-specific rules
tfsec .                                 # security static analysis
checkov -d .                            # policy / misconfiguration scanning
terraform test                          # native test framework (1.6+)
```

- **Terratest** (Go) runs `apply` against real or ephemeral infra, asserts on
  outputs, then runs `destroy` in a deferred cleanup.

## See also

- [`../05-infrastructure-as-code/`](../05-infrastructure-as-code/) - Terraform
  fundamentals, state, modules, testing, and Crossplane.
