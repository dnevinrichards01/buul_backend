#!/bin/bash

# Configuration Variables
DOMAIN="accumate-backend.link"
CERTBOT_MANUAL_AUTH_HOOK="./get_cert.sh"  # Path to your DNS auth hook script
SECRET_NAME="letsencrypt-certificate"             # AWS Secrets Manager secret name
CERTBOT_DIR="/etc/letsencrypt/live/${DOMAIN}"

# 1. Renew Certificate with DNS-01 Challenge
echo "Starting Certbot renewal with DNS-01 challenge..."
certbot certonly \
    --manual \
    --preferred-challenges dns \
    --manual-auth-hook "${CERTBOT_MANUAL_AUTH_HOOK}" \
    --manual-cleanup-hook "${CERTBOT_MANUAL_AUTH_HOOK}" \
    --manual-public-ip-logging-ok \
    --non-interactive \
    --agree-tos \
    --renew-by-default 

if [ $? -ne 0 ]; then
    echo "Certbot renewal failed!"
    exit 1
fi
echo "Certificate renewal successful."

# 2. Bundle Certificate Files for AWS Secrets Manager
CERT_PEM=$(cat "${CERTBOT_DIR}/cert.pem")
CHAIN_PEM=$(cat "${CERTBOT_DIR}/chain.pem")
FULLCHAIN_PEM=$(cat "${CERTBOT_DIR}/fullchain.pem")
PRIVKEY_PEM=$(cat "${CERTBOT_DIR}/privkey.pem")

echo "Bundling certificate files for AWS Secrets Manager..."

# Create a JSON payload for Secrets Manager
SECRET_PAYLOAD=$(jq -n \
  --arg cert "$FULLCHAIN_PEM" \
  --arg pkey "$PRIVKEY_PEM" \
  '{
    "cert": $cert,
    "pkey": $pkey
  }')

# 3. Push Certificates to AWS Secrets Manager
echo "Pushing certificates to AWS Secrets Manager..."
aws secretsmanager put-secret-value \
    --secret-id "${SECRET_NAME}" \
    --secret-string "${SECRET_PAYLOAD}" \
    --region "us-west-1"

if [ $? -ne 0 ]; then
    echo "Failed to push certificates to AWS Secrets Manager."
    exit 1
fi
echo "Certificates successfully pushed to AWS Secrets Manager."

rm -f "${CERT_PEM}" "${CHAIN_PEM}" "${FULLCHAIN_PEM}" "${CERTPRIVKEY_PEM_PEM}"
echo "deleted the ceritificates" 

exit 0
