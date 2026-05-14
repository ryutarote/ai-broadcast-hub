output "alb_dns_name" {
  value = aws_lb.this.dns_name
}

output "alb_zone_id" {
  value = aws_lb.this.zone_id
}

output "alb_security_group_id" {
  value = aws_security_group.alb.id
}

output "litellm_target_group_arn" {
  value = aws_lb_target_group.litellm.arn
}

output "control_plane_target_group_arn" {
  value = aws_lb_target_group.control_plane.arn
}

output "acm_certificate_arn" {
  value = aws_acm_certificate.this.arn
}
