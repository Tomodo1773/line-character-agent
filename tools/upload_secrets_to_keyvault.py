#!/usr/bin/env python3
"""
Upload secrets from .env file to Azure Key Vault

This script reads a .env file and uploads each key-value pair as a secret to Azure Key Vault.

Requirements:
    - Azure CLI authenticated or environment variables set for authentication
    - azure-keyvault-secrets package: `uv add azure-keyvault-secrets`

Usage:
    uv run upload_secrets_to_keyvault.py --keyvault-name <vault_name> --env-file <path_to_env_file>

Example:
    uv run upload_secrets_to_keyvault.py --keyvault-name my-keyvault --env-file .env
"""

import argparse
import os
import sys
from typing import Dict

try:
    from azure.core.exceptions import AzureError
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Please install: uv add azure-keyvault-secrets")
    sys.exit(1)

from dotenv import dotenv_values


def load_env_file(env_file_path: str) -> Dict[str, str]:
    """Load environment variables from .env file"""
    if not os.path.exists(env_file_path):
        raise FileNotFoundError(f"Environment file not found: {env_file_path}")

    env_vars = dotenv_values(env_file_path)
    # Filter out empty values
    return {k: v for k, v in env_vars.items() if v}


def get_keyvault_client(vault_name: str) -> SecretClient:
    """Create Azure Key Vault client"""
    vault_url = f"https://{vault_name}.vault.azure.net/"
    credential = DefaultAzureCredential()
    return SecretClient(vault_url=vault_url, credential=credential)


def convert_key_to_secret_name(key: str) -> str:
    """
    Convert environment variable key to Key Vault secret name format.

    Key Vault secret names must match: ^[0-9a-zA-Z-]+$
    Replace underscores with hyphens and ensure uppercase.
    """
    return key.replace("_", "-").upper()


def upload_secrets(client: SecretClient, env_vars: Dict[str, str], dry_run: bool = False) -> None:
    """Upload secrets to Key Vault"""
    print(f"{'[DRY RUN] ' if dry_run else ''}Uploading {len(env_vars)} secrets to Key Vault...")

    success_count = 0
    error_count = 0

    for key, value in env_vars.items():
        secret_name = convert_key_to_secret_name(key)

        try:
            if dry_run:
                print(f"[DRY RUN] Would upload: {key} -> {secret_name}")
            else:
                client.set_secret(secret_name, value)
                print(f"✓ Uploaded: {key} -> {secret_name}")
            success_count += 1

        except AzureError as e:
            print(f"✗ Failed to upload {key} -> {secret_name}: {e}")
            error_count += 1
        except Exception as e:
            print(f"✗ Unexpected error uploading {key} -> {secret_name}: {e}")
            error_count += 1

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Summary:")
    print(f"  Successful: {success_count}")
    print(f"  Failed: {error_count}")

    if error_count > 0 and not dry_run:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Upload secrets from .env file to Azure Key Vault")
    parser.add_argument("--keyvault-name", required=True, help="Azure Key Vault name (without .vault.azure.net suffix)")
    parser.add_argument("--env-file", default=".env", help="Path to .env file (default: .env)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be uploaded without actually uploading")

    args = parser.parse_args()

    try:
        # Load environment variables
        env_vars = load_env_file(args.env_file)
        if not env_vars:
            print(f"No environment variables found in {args.env_file}")
            return

        print(f"Loaded {len(env_vars)} environment variables from {args.env_file}")

        # Create Key Vault client
        client = get_keyvault_client(args.keyvault_name)

        # Upload secrets
        upload_secrets(client, env_vars, args.dry_run)

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except AzureError as e:
        print(f"Azure error: {e}")
        print("Make sure you're authenticated with Azure CLI: az login")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
