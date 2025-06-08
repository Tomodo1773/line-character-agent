using './main.bicep'

param environmentName = readEnvironmentVariable('AZURE_ENV_NAME', 'default-env')

param location = readEnvironmentVariable('AZURE_LOCATION', 'westus')


param cosmosDbAccountName = readEnvironmentVariable('AZURE_COSMOSDB_NAME', '')
param cosmosDbResourceGroupName = readEnvironmentVariable('AZURE_COSMOSDB_RG', '')
param cosmosDbDatabaseName = readEnvironmentVariable('COSMOS_DB_DATABASE_NAME', '')
param azureAiSearchServiceName = readEnvironmentVariable('AZURE_AI_SEARCH_SERVICE_NAME', '')
param appServicePlanName = readEnvironmentVariable('AZURE_APPSERVICEPLAN_NAME', '')
param appServicePlanResourceGroupName  = readEnvironmentVariable('AZURE_APPSERVICEPLAN_RG', '')

param keyVaultName = readEnvironmentVariable('AZURE_KEYVAULT_NAME', '')
param keyVaultResourceGroupName = readEnvironmentVariable('AZURE_KEYVAULT_RG', '')
