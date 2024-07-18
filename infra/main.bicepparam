using './main.bicep'

param environmentName = readEnvironmentVariable('AZURE_ENV_NAME', 'default-env')

param location = readEnvironmentVariable('AZURE_LOCATION', 'westus')

param appSettings = {
  LANGCHAIN_API_KEY: readEnvironmentVariable('LANGCHAIN_API_KEY', 'default-langchain-key')
  LINE_USER_ID: readEnvironmentVariable('LINE_USER_ID', 'default-line-user-id')
  LINE_CHANNEL_ACCESS_TOKEN: readEnvironmentVariable('LINE_CHANNEL_ACCESS_TOKEN', 'default-access-token')
  LINE_CHANNEL_SECRET: readEnvironmentVariable('LINE_CHANNEL_SECRET', 'default-channel-secret')
  GOOGLE_API_KEY: readEnvironmentVariable('GOOGLE_API_KEY', 'default-google-api-key')
}

param cosmosDbAccountName = readEnvironmentVariable('AZURE_COSMOSDB_NAME', '')
param cosmosDbResourceGroupName = readEnvironmentVariable('AZURE_COSMOSDB_RG', '')
param appServicePlanName = readEnvironmentVariable('AZURE_APPSERVICEPLAN_NAME', '')
param appServicePlanResourceGroupName  = readEnvironmentVariable('AZURE_APPSERVICEPLAN_RG', '')
