output "instance_public_ip" {
  description = "Public IP address of the EdgeMind OCI VM"
  value       = oci_core_instance.edgemind_vm.public_ip
}

output "instance_ocid" {
  description = "OCID of the EdgeMind production instance"
  value       = oci_core_instance.edgemind_vm.id
}

output "ssh_connection_command" {
  description = "SSH command to connect to the instance"
  value       = "ssh ubuntu@${oci_core_instance.edgemind_vm.public_ip}"
}

output "https_api_url" {
  description = "Public HTTPS endpoint URL for EdgeMind API"
  value       = var.domain_name != "" ? "https://${var.domain_name}" : "https://${oci_core_instance.edgemind_vm.public_ip}"
}
