variable "tenancy_ocid" {
  description = "OCID of the OCI tenancy"
  type        = string
}

variable "user_ocid" {
  description = "OCID of the OCI user with permissions to manage compute and network resources"
  type        = string
}

variable "fingerprint" {
  description = "Fingerprint for the OCI API signing key"
  type        = string
}

variable "private_key_path" {
  description = "Local path to the OCI API private key file"
  type        = string
}

variable "region" {
  description = "OCI region identifier (e.g., us-ashburn-1, us-phoenix-1, eu-frankfurt-1)"
  type        = string
  default     = "us-ashburn-1"
}

variable "compartment_ocid" {
  description = "OCID of the compartment where resources will be provisioned (defaults to tenancy root)"
  type        = string
}

variable "availability_domain_number" {
  description = "Availability domain index (1, 2, or 3) within the region"
  type        = number
  default     = 1
}

variable "instance_shape" {
  description = "Compute instance shape for the OCI Always Free ARM64 Ampere A1 VM"
  type        = string
  default     = "VM.Standard.A1.Flex"
}

variable "ocpus" {
  description = "Number of OCPUs for the Ampere A1 VM (Always Free allows up to 4 total across tenancy)"
  type        = number
  default     = 2
}

variable "memory_in_gbs" {
  description = "Memory in gigabytes for the Ampere A1 VM (Always Free allows up to 24 GB total across tenancy)"
  type        = number
  default     = 12
}

variable "boot_volume_size_in_gbs" {
  description = "Boot volume storage in GB (Always Free allows up to 200 GB total)"
  type        = number
  default     = 100
}

variable "ssh_public_key" {
  description = "SSH public key string for remote administration"
  type        = string
}

variable "admin_ip_cidr" {
  description = "Allowed CIDR block for SSH administration (port 22). Restrict to your IP for enhanced security."
  type        = string
  default     = "0.0.0.0/0"
}

variable "domain_name" {
  description = "Optional custom domain name for automatic Let's Encrypt TLS in Caddy (e.g., edgemind.example.com)"
  type        = string
  default     = ""
}
