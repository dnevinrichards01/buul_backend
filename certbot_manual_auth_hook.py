#!/usr/bin/env python3
import os
import boto3
import time
import sys
import dns.resolver

# AWS Route 53 Configuration
HOSTED_ZONE_ID = "us-west-1"
TTL = 60
RESOLVERS = ['8.8.8.8', '1.1.1.1', '9.9.9.9']  # Google, Cloudflare, Quad9


def check_dns_propagation(record_name, record_type, expected_value, resolvers):
    """
    Check DNS record propagation against a list of DNS resolvers.
    """
    for resolver_ip in resolvers:
        try:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = [resolver_ip]
            answers = resolver.resolve(record_name, record_type)
            
            print(f"\nChecking with resolver {resolver_ip}:")
            for rdata in answers:
                print(f"Found: {rdata.to_text()}")
                if expected_value in rdata.to_text():
                    print("Record has propagated.")
                    return True
            print("Record not yet propagated.")
        except Exception as e:
            print(f"Error querying {resolver_ip}: {e}")
    return False


def create_txt_record(domain, validation):
    """Create the TXT record for DNS-01 challenge in Route 53."""
    print(f"Creating TXT record for domain: _acme-challenge.{domain}")
    try:
        client = boto3.client("route53")
        response = client.change_resource_record_sets(
            HostedZoneId=HOSTED_ZONE_ID,
            ChangeBatch={
                "Comment": "Certbot DNS-01 challenge TXT record",
                "Changes": [
                    {
                        "Action": "UPSERT",
                        "ResourceRecordSet": {
                            "Name": f"_acme-challenge.{domain}",
                            "Type": "TXT",
                            "TTL": TTL,
                            "ResourceRecords": [{"Value": f'"{validation}"'}],
                        },
                    }
                ],
            },
        )
        print("Waiting for DNS propagation...")
        while not check_dns_propagation(f"_acme-challenge.{domain}", 'TXT', validation, RESOLVERS):
            time.sleep(15)
            print("Waiting for DNS propagation...")
        print("TXT record created successfully.")
    except Exception as e:
        print(f"Error creating TXT record: {e}")
        sys.exit(1)

def main():
    """Main function to handle Certbot DNS-01 challenge hooks."""
    # Certbot environment variables
    domain = os.environ.get("CERTBOT_DOMAIN")
    validation = os.environ.get("CERTBOT_VALIDATION")

    if not domain or not validation:
        print("CERTBOT_DOMAIN and CERTBOT_VALIDATION are required environment variables.")
        sys.exit(1)

    create_txt_record(domain, validation)

if __name__ == "__main__":
    main()
