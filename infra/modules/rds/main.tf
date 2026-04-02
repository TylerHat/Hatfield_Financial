resource "aws_db_subnet_group" "main" {
  name       = "${var.app_name}-db-subnet-group"
  subnet_ids = var.private_subnet_ids

  tags = { Name = "${var.app_name}-db-subnet-group" }
}

resource "aws_db_instance" "postgres" {
  identifier        = "${var.app_name}-db"
  engine            = "postgres"
  engine_version    = "15"
  instance_class    = "db.t3.micro"
  allocated_storage = 20
  storage_type      = "gp2"
  storage_encrypted = true

  db_name  = "hatfield"
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.db_security_group_id]

  backup_retention_period = 7
  skip_final_snapshot     = false
  final_snapshot_identifier = "${var.app_name}-db-final-snapshot"

  deletion_protection = false

  tags = { Name = "${var.app_name}-db" }
}
