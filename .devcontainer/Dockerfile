FROM mcr.microsoft.com/devcontainers/base:bookworm

# The installer requires curl (and certificates) to download the release archive.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download the pinned installer and run it as the non-root devcontainer user so the
# binaries land in /home/vscode/.local/bin (which is accessible to post-create hooks).
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN chmod 755 /uv-installer.sh \
    && chown vscode:vscode /uv-installer.sh \
    && su - vscode -c "sh /uv-installer.sh" \
    && rm /uv-installer.sh

# Install act for running GitHub Actions locally via Docker-in-Docker.
RUN curl -sSL https://raw.githubusercontent.com/nektos/act/master/install.sh | bash -s -- -b /usr/local/bin

# Ensure the installed binary is discoverable in the PATH for all subsequent users.
ENV PATH="/home/vscode/.local/bin:${PATH}"
