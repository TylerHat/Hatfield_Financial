# Dependency chain (no cycles):
#   certs  → (none)
#   efs    → networking
#   apigateway → networking, certs
#   cdn    → certs
#   ecs    → networking, ecr, iam, efs, apigateway, certs
#   dns    → cdn, apigateway

module "networking" {
  source   = "./modules/networking"
  app_name = var.app_name
}

module "ecr" {
  source   = "./modules/ecr"
  app_name = var.app_name
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

module "efs" {
  source                = "./modules/efs"
  app_name              = var.app_name
  vpc_id                = module.networking.vpc_id
  subnet_ids            = module.networking.public_subnet_ids
  ecs_security_group_id = module.networking.ecs_security_group_id
}

module "apigateway" {
  source                = "./modules/apigateway"
  app_name              = var.app_name
  vpc_id                = module.networking.vpc_id
  subnet_ids            = module.networking.public_subnet_ids
  ecs_security_group_id = module.networking.ecs_security_group_id
  acm_certificate_arn   = module.certs.api_cert_arn
  domain_name           = var.domain_name
}

module "cdn" {
  source              = "./modules/cdn"
  app_name            = var.app_name
  domain_name         = var.domain_name
  acm_certificate_arn = module.certs.frontend_cert_arn
}

module "ecs" {
  source                        = "./modules/ecs"
  app_name                      = var.app_name
  aws_region                    = var.aws_region
  ecr_repository_url            = module.ecr.repository_url
  vpc_id                        = module.networking.vpc_id
  public_subnet_ids             = module.networking.public_subnet_ids
  ecs_security_group_id         = module.networking.ecs_security_group_id
  ecs_task_execution_role_arn   = module.iam.ecs_task_execution_role_arn
  secret_key                    = var.secret_key
  allowed_origin                = "https://${var.domain_name}"
  efs_file_system_id            = module.efs.file_system_id
  efs_access_point_id           = module.efs.access_point_id
  service_discovery_service_arn = module.apigateway.service_discovery_service_arn
  s3_cache_bucket_name          = module.lambda.s3_cache_bucket_name
}

module "lambda" {
  source     = "./modules/lambda"
  app_name   = var.app_name
  aws_region = var.aws_region
}

module "dns" {
  source                     = "./modules/dns"
  app_name                   = var.app_name
  domain_name                = var.domain_name
  cloudfront_domain_name     = module.cdn.cloudfront_domain
  cloudfront_hosted_zone_id  = module.cdn.cloudfront_hosted_zone_id
  api_gateway_domain_target  = module.apigateway.api_gateway_domain_target
  api_gateway_hosted_zone_id = module.apigateway.api_gateway_hosted_zone_id
}
