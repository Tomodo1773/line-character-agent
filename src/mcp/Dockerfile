FROM mcr.microsoft.com/azure-functions/python:4-python3.11

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true

WORKDIR /home/site/wwwroot

# Install uv for dependency management
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
# Use --no-cache to reduce image size
RUN uv sync --frozen --no-dev --no-cache

# Copy the rest of the application code
COPY . .

# The base image already has the entrypoint configured to run func host start
