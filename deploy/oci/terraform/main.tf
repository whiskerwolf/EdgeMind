# Availability Domain lookup
data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

# Image lookup: Ubuntu 24.04 LTS aarch64
data "oci_core_images" "ubuntu_arm" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "24.04"
  shape                    = var.instance_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

locals {
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[var.availability_domain_number - 1].name
  image_id            = length(data.oci_core_images.ubuntu_arm.images) > 0 ? data.oci_core_images.ubuntu_arm.images[0].id : null
}

# Virtual Cloud Network (VCN)
resource "oci_core_vcn" "edgemind_vcn" {
  cidr_block     = "10.0.0.0/16"
  compartment_id = var.compartment_ocid
  display_name   = "edgemind-vcn"
  dns_label      = "edgemindvcn"
}

# Internet Gateway
resource "oci_core_internet_gateway" "edgemind_igw" {
  compartment_id = var.compartment_ocid
  display_name   = "edgemind-internet-gateway"
  enabled        = true
  vcn_id         = oci_core_vcn.edgemind_vcn.id
}

# Route Table for Internet Access
resource "oci_core_route_table" "edgemind_route_table" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.edgemind_vcn.id
  display_name   = "edgemind-public-route-table"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.edgemind_igw.id
  }
}

# Security List: Exposes ONLY SSH (22), HTTP (80), and HTTPS (443)
# PostgreSQL (5432), Redis (6379/6380), and Ollama (11434) are strictly restricted from public ingress.
resource "oci_core_security_list" "edgemind_security_list" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.edgemind_vcn.id
  display_name   = "edgemind-security-list"

  # Outbound rules: Allow all egress traffic
  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
    stateless   = false
  }

  # Inbound rules: SSH (port 22) restricted to admin CIDR
  ingress_security_rules {
    protocol    = "6" # TCP
    source      = var.admin_ip_cidr
    stateless   = false
    description = "Restricted SSH administration"

    tcp_options {
      min = 22
      max = 22
    }
  }

  # Inbound rules: HTTP (port 80) for ACME challenge & HTTP to HTTPS redirect
  ingress_security_rules {
    protocol    = "6" # TCP
    source      = "0.0.0.0/0"
    stateless   = false
    description = "Public HTTP for Caddy Let's Encrypt TLS challenge and redirection"

    tcp_options {
      min = 80
      max = 80
    }
  }

  # Inbound rules: HTTPS (port 443) for secure API traffic
  ingress_security_rules {
    protocol    = "6" # TCP
    source      = "0.0.0.0/0"
    stateless   = false
    description = "Public HTTPS for EdgeMind API traffic"

    tcp_options {
      min = 443
      max = 443
    }
  }
}

# Public Regional Subnet
resource "oci_core_subnet" "edgemind_subnet" {
  cidr_block        = "10.0.1.0/24"
  display_name      = "edgemind-public-subnet"
  dns_label         = "edgemindsub"
  compartment_id    = var.compartment_ocid
  vcn_id            = oci_core_vcn.edgemind_vcn.id
  route_table_id    = oci_core_route_table.edgemind_route_table.id
  security_list_ids = [oci_core_security_list.edgemind_security_list.id]
}

# Compute Instance: Ampere A1 ARM64 Flex VM (Always Free)
resource "oci_core_instance" "edgemind_vm" {
  availability_domain = local.availability_domain
  compartment_id      = var.compartment_ocid
  display_name        = "edgemind-production-vm"
  shape               = var.instance_shape

  shape_config {
    ocpus         = var.ocpus
    memory_in_gbs = var.memory_in_gbs
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.edgemind_subnet.id
    display_name     = "edgemind-primary-vnic"
    assign_public_ip = true
    hostname_label   = "edgemind"
  }

  source_details {
    source_type             = "image"
    source_id               = local.image_id
    boot_volume_size_in_gbs = var.boot_volume_size_in_gbs
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data           = filebase64("${path.module}/../cloud-init.yaml")
  }

  lifecycle {
    ignore_changes = [
      source_details[0].source_id,
    ]
  }
}
