#!/usr/bin/env python3
"""
Converts an IAM secret access key into an SES SMTP password.

Why this exists: SES SMTP auth does NOT accept your raw IAM secret key — it
needs a password derived from it via a fixed AWS algorithm (documented at
https://docs.aws.amazon.com/ses/latest/dg/smtp-credentials.html). There's no
Terraform built-in for this, so it's a separate manual step.

Usage:
    python3 scripts/derive-ses-smtp-password.py <iam-secret-access-key> [region]

Run this once, right after `terraform apply` (it prints the new IAM user's
secret key as an output). Put the result in .env as ALERTMANAGER_SMTP_PASSWORD.
"""
import sys
import hmac
import hashlib
import base64

SES_VERSION = b"\x04"


def derive_smtp_password(secret_access_key: str, region: str) -> str:
    def sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    signature = sign(f"AWS4{secret_access_key}".encode("utf-8"), "11111111")
    signature = sign(signature, region)
    signature = sign(signature, "ses")
    signature = sign(signature, "aws4_request")
    signature = sign(signature, "SendRawEmail")
    return base64.b64encode(SES_VERSION + signature).decode("utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    secret_key = sys.argv[1]
    region = sys.argv[2] if len(sys.argv) > 2 else "us-east-1"
    print(derive_smtp_password(secret_key, region))
