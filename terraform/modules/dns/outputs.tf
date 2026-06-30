output "zone_id" {
  description = "Route 53 hosted zone ID — used by the bootstrap script to update the A record"
  value       = aws_route53_zone.main.zone_id
}

output "name_servers" {
  description = "Paste these 4 nameservers into Name.com to delegate DNS to Route 53"
  value       = aws_route53_zone.main.name_servers
}
