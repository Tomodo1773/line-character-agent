using './main.bicep'

param environmentName = readEnvironmentVariable('AZURE_ENV_NAME', 'default-env')

param location = readEnvironmentVariable('AZURE_LOCATION', 'westus')

param appSettings = {
  LANGCHAIN_API_KEY: readEnvironmentVariable('LANGCHAIN_API_KEY', 'default-langchain-key')
  LINE_CHANNEL_ACCESS_TOKEN: readEnvironmentVariable('LINE_CHANNEL_ACCESS_TOKEN', 'default-access-token')
  LINE_CHANNEL_SECRET: readEnvironmentVariable('LINE_CHANNEL_SECRET', 'default-channel-secret')
  GOOGLE_API_KEY: readEnvironmentVariable('GOOGLE_API_KEY', 'default-google-api-key')
  TAVILY_API_KEY: readEnvironmentVariable('TAVILY_API_KEY', 'default-tavily-api-key')
  OPENAI_API_KEY: readEnvironmentVariable('OPENAI_API_KEY', 'default-openai-api-key')
  OPENAI_COMPATIBLE_API_KEY: readEnvironmentVariable('OPENAI_COMPATIBLE_API_KEY', 'default-openai-compatible-api-key')
  GROQ_API_KEY: readEnvironmentVariable('GROQ_API_KEY', 'default-groq-api-key')
  COSMOS_DB_DATABASE_NAME: readEnvironmentVariable('COSMOS_DB_DATABASE_NAME', 'DEMO')
  ANTHROPIC_API_KEY: readEnvironmentVariable('ANTHROPIC_API_KEY', 'default-anthropic-api-key')
  AZURE_AI_SEARCH_SERVICE_NAME: readEnvironmentVariable('AZURE_AI_SEARCH_SERVICE_NAME', 'default-azure-search-service-name')
  AZURE_AI_SEARCH_API_KEY: readEnvironmentVariable('AZURE_AI_SEARCH_API_KEY', 'default-azure-search-admin-key')
  NIJIVOICE_API_KEY: readEnvironmentVariable('NIJIVOICE_API_KEY', 'default-nijivoice-api-key')
  DRIVE_FOLDER_ID: readEnvironmentVariable('DRIVE_FOLDER_ID', 'default-drive-folder-id')
  APPLICATIONINSIGHTS_CONNECTION_STRING: readEnvironmentVariable('APPLICATIONINSIGHTS_CONNECTION_STRING', 'default-appinsights-connection-string')
}

param funcappSettings = {
  DRIVE_FOLDER_ID: readEnvironmentVariable('DRIVE_FOLDER_ID', 'default-drive-folder-id')
}

param cosmosDbAccountName = readEnvironmentVariable('AZURE_COSMOSDB_NAME', '')
param cosmosDbResourceGroupName = readEnvironmentVariable('AZURE_COSMOSDB_RG', '')
param appServicePlanName = readEnvironmentVariable('AZURE_APPSERVICEPLAN_NAME', '')
param appServicePlanResourceGroupName  = readEnvironmentVariable('AZURE_APPSERVICEPLAN_RG', '')
