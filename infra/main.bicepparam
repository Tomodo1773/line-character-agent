using './main.bicep'

param environmentName = readEnvironmentVariable('AZURE_ENV_NAME', 'default-env')

// Japan East offers Foundry Agent Service, the Responses API, Kimi-K2.6 (Global Standard)
// and text-embedding-3-small (Standard).
param location = readEnvironmentVariable('AZURE_LOCATION', 'japaneast')

param cosmosDbAccountName = readEnvironmentVariable('AZURE_COSMOSDB_NAME', '')
param cosmosDbResourceGroupName = readEnvironmentVariable('AZURE_COSMOSDB_RG', '')

param keyVaultName = readEnvironmentVariable('AZURE_KEYVAULT_NAME', '')
param keyVaultResourceGroupName = readEnvironmentVariable('AZURE_KEYVAULT_RG', '')

// Swap the default model here. The remaining model parameters live in main.bicep.
param chatDeploymentName = readEnvironmentVariable('AZURE_AI_MODEL_DEPLOYMENT_NAME', 'Kimi-K2.6')
param chatModelName = readEnvironmentVariable('AZURE_AI_MODEL_NAME', 'Kimi-K2.6')
param chatModelFormat = readEnvironmentVariable('AZURE_AI_MODEL_FORMAT', 'Moonshot AI')
param chatModelVersion = readEnvironmentVariable('AZURE_AI_MODEL_VERSION', '2026-04-20')

// Owner of the diary, also the recipient of backup failure notices. Same value the agent gets.
param diaryUserId = readEnvironmentVariable('DIARY_USER_ID', '')

// Set after the hosted agent is deployed (Phase 3) to grant it Cosmos DB data access.
param agentPrincipalId = readEnvironmentVariable('AZURE_AI_AGENT_PRINCIPAL_ID', '')
