#!/usr/bin/env python3
"""
Download secrets from Azure Key Vault and output in .env format

This script retrieves secrets from Azure Key Vault and outputs them in .env format.
Can optionally filter to only the secrets used by this project.

Requirements:
    - Azure CLI authenticated or environment variables set for authentication
    - azure-keyvault-secrets package: `uv add azure-keyvault-secrets`

Usage:
    uv run download_secrets_from_keyvault.py --keyvault-name <vault_name> [options]

Example:
    # Download all secrets to .env file
    uv run download_secrets_from_keyvault.py --keyvault-name my-keyvault --output .env

    # Download only project secrets to stdout
    uv run download_secrets_from_keyvault.py --keyvault-name my-keyvault --project-only

    # Show all available secrets (dry run)
    uv run download_secrets_from_keyvault.py --keyvault-name my-keyvault --list-only
"""

import argparse
import sys
from typing import Dict, List

try:
    from azure.core.exceptions import AzureError
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient
except ImportError as e:
    print(f"Error: Missing required package: {e}")
    print("Please install: uv add azure-keyvault-secrets")
    sys.exit(1)


# Project-specific secret names (based on bicep templates)
PROJECT_SECRETS = {
    "LANGCHAIN-API-KEY",
    "LINE-CHANNEL-ACCESS-TOKEN",
    "LINE-CHANNEL-SECRET",
    "OPENAI-API-KEY",
    "OPENAI-COMPATIBLE-API-KEY",
    "GROQ-API-KEY",
    "AZURE-AI-SEARCH-API-KEY",
    "NIJIVOICE-API-KEY",
    "DRIVE-FOLDER-ID",
    "SPOTIFY-CLIENT-ID",
    "SPOTIFY-CLIENT-SECRET",
    "SPOTIFY-REFRESH-TOKEN",
    "PERPLEXITY-API-KEY",
}


def get_keyvault_client(vault_name: str) -> SecretClient:
    """Create Azure Key Vault client"""
    vault_url = f"https://{vault_name}.vault.azure.net/"
    credential = DefaultAzureCredential()
    return SecretClient(vault_url=vault_url, credential=credential)


def convert_secret_name_to_env_key(secret_name: str) -> str:
    """
    Convert Key Vault secret name to environment variable key format.

    Convert hyphens to underscores and keep uppercase.
    """
    return secret_name.replace("-", "_")


def list_secrets(client: SecretClient, project_only: bool = False) -> List[str]:
    """List all secret names in the Key Vault"""
    secret_names = []

    try:
        secret_properties = client.list_properties_of_secrets()
        for secret_property in secret_properties:
            secret_name = secret_property.name

            if project_only and secret_name not in PROJECT_SECRETS:
                continue

            secret_names.append(secret_name)

    except AzureError as e:
        print(f"Error listing secrets: {e}")
        sys.exit(1)

    return sorted(secret_names)


def download_secrets(client: SecretClient, secret_names: List[str]) -> Dict[str, str]:
    """Download secret values from Key Vault"""
    secrets = {}

    print(f"Downloading {len(secret_names)} secrets from Key Vault...", file=sys.stderr)

    success_count = 0
    error_count = 0

    for secret_name in secret_names:
        try:
            secret = client.get_secret(secret_name)
            env_key = convert_secret_name_to_env_key(secret_name)
            secrets[env_key] = secret.value
            print(f"✓ Downloaded: {secret_name} -> {env_key}", file=sys.stderr)
            success_count += 1

        except AzureError as e:
            print(f"✗ Failed to download {secret_name}: {e}", file=sys.stderr)
            error_count += 1
        except Exception as e:
            print(f"✗ Unexpected error downloading {secret_name}: {e}", file=sys.stderr)
            error_count += 1

    print("\nSummary:", file=sys.stderr)
    print(f"  Successful: {success_count}", file=sys.stderr)
    print(f"  Failed: {error_count}", file=sys.stderr)

    if error_count > 0:
        print(f"\nWarning: {error_count} secrets failed to download", file=sys.stderr)

    return secrets


def format_as_env(secrets: Dict[str, str]) -> str:
    """Format secrets as .env file content"""
    lines = []
    lines.append("# Generated from Azure Key Vault")
    lines.append("# WARNING: Keep this file secure and do not commit to version control")
    lines.append("")

    for key in sorted(secrets.keys()):
        value = secrets[key]
        # Escape quotes in values
        escaped_value = value.replace('"', '\\"')
        lines.append(f'{key}="{escaped_value}"')

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Download secrets from Azure Key Vault and output in .env format")
    parser.add_argument("--keyvault-name", required=True, help="Azure Key Vault name (without .vault.azure.net suffix)")
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)")
    parser.add_argument("--project-only", action="store_true", help="Only download secrets used by this project")
    parser.add_argument("--list-only", action="store_true", help="Only list available secrets without downloading values")

    args = parser.parse_args()

    try:
        # Create Key Vault client
        client = get_keyvault_client(args.keyvault_name)

        # List secrets
        secret_names = list_secrets(client, args.project_only)

        if not secret_names:
            print("No secrets found in Key Vault", file=sys.stderr)
            if args.project_only:
                print("Project secrets expected:", file=sys.stderr)
                for secret in sorted(PROJECT_SECRETS):
                    print(f"  - {secret}", file=sys.stderr)
            return

        if args.list_only:
            print(f"Available secrets ({len(secret_names)}):", file=sys.stderr)
            for secret_name in secret_names:
                env_key = convert_secret_name_to_env_key(secret_name)
                print(f"  {secret_name} -> {env_key}", file=sys.stderr)
            return

        # Download secrets
        secrets = download_secrets(client, secret_names)

        if not secrets:
            print("No secrets were successfully downloaded", file=sys.stderr)
            sys.exit(1)

        # Format as .env content
        env_content = format_as_env(secrets)

        # Output to file or stdout
        if args.output:
            with open(args.output, "w") as f:
                f.write(env_content)
            print(f"\n✓ Wrote {len(secrets)} secrets to {args.output}", file=sys.stderr)
        else:
            print(env_content, end="")

    except AzureError as e:
        print(f"Azure error: {e}", file=sys.stderr)
        print("Make sure you're authenticated with Azure CLI: az login", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
