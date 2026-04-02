# Dependency chain (no cycles):
#   certs  → (none)
#   cdn    → certs
#   ecs    → networking, ecr, iam, rds, certs
#   dns    → cdn, ecs

module "networking" {
  source   = "./modules/networking"
  app_name = var.app_name
}

module "ecr" {
  source   = "./modules/ecr"
  app_name = var.app_name
}

module "rds" {
  source               = "./modules/rds"
  app_name             = var.app_name
  db_username          = var.db_username
  db_password          = var.db_password
  private_subnet_ids   = module.networking.private_subnet_ids
  db_security_group_id = module.networking.db_security_group_id
}

module "iam" {
  source   = "./modules/iam"
  app_name = var.app_name
}

module "certs" {
  source      = "./modules/certs"
  app_name    = var.app_name
  domain_name = var.domain_name
}

module "cdn" {
  source              = "./modules/cdn"
  app_name            = var.app_name
  domain_name         = var.domain_name
  acm_certificate_arn = module.certs.frontend_cert_arn
}

module "ecs" {
  source                      = "./modules/ecs"
  app_name                    = var.app_name
  aws_region                  = var.aws_region
  ecr_repository_url          = module.ecr.repository_url
  vpc_id                      = module.networking.vpc_id
  public_subnet_ids           = module.networking.public_subnet_ids
  ecs_security_group_id       = module.networking.ecs_security_group_id
  alb_security_group_id       = module.networking.alb_security_group_id
  ecs_task_execution_role_arn = module.iam.ecs_task_execution_role_arn
  acm_certificate_arn         = module.certs.api_cert_arn
  secret_key                  = var.secret_key
  database_url                = "postgresql://${var.db_username}:${var.db_password}@${module.rds.db_endpoint}/hatfield"
  allowed_origin              = "https://${var.domain_name}"
}

module "dns" {
  source                    = "./modules/dns"
  app_name                  = var.app_name
  domain_name               = var.domain_name
  cloudfront_domain_name    = module.cdn.cloudfront_domain
  cloudfront_hosted_zone_id = module.cdn.cloudfront_hosted_zone_id
  alb_dns_name              = module.ecs.alb_dns_name
  alb_hosted_zone_id        = module.ecs.alb_hosted_zone_id
}
