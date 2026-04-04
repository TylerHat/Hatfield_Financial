# ── EFS File System ───────────────────────────────────────────────────────────
resource "aws_efs_file_system" "main" {
  encrypted        = true
  performance_mode = "generalPurpose"
  throughput_mode  = "bursting"

  tags = { Name = "${var.app_name}-efs" }
}

# ── EFS Mount Targets (one per subnet where ECS tasks run) ───────────────────
resource "aws_efs_mount_target" "main" {
  count           = length(var.subnet_ids)
  file_system_id  = aws_efs_file_system.main.id
  subnet_id       = var.subnet_ids[count.index]
  security_groups = [aws_security_group.efs.id]
}

# ── EFS Access Point ─────────────────────────────────────────────────────────
resource "aws_efs_access_point" "data" {
  file_system_id = aws_efs_file_system.main.id

  root_directory {
    path = "/data"
    creation_info {
      owner_gid   = 0
      owner_uid   = 0
      permissions = "0755"
    }
  }

  tags = { Name = "${var.app_name}-efs-ap" }
}

# ── Security Group: EFS ──────────────────────────────────────────────────────
resource "aws_security_group" "efs" {
  name        = "${var.app_name}-efs-sg"
  description = "Allow NFS from ECS tasks"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 2049
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [var.ecs_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.app_name}-efs-sg" }
}
