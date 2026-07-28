targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment, used to derive a short unique hash for resource names.')
param environmentName string

@minLength(1)
@description('Primary location for all resources. Must offer Foundry Agent Service and the chosen models.')
param location string

param resourceGroupName string = ''

@minLength(3)
@description('Existing Cosmos DB account holding the users and diary containers.')
param cosmosDbAccountName string

@minLength(1)
@description('Resource group of the existing Cosmos DB account.')
param cosmosDbResourceGroupName string

@minLength(3)
@description('Existing Key Vault holding the LINE channel secret and access token.')
param keyVaultName string

@minLength(1)
@description('Resource group of the existing Key Vault.')
param keyVaultResourceGroupName string

// ---------------------------------------------------------------------------
// Models. ADR-0001 treats the default model as a setting to be swapped, not a
// fixed asset: change it here (or via the matching AZURE_AI_* environment
// variable) and nothing else in the repository needs to move.
// Confirm `format` and `version` against `az cognitiveservices account list-models`
// before switching models; the publisher string differs per catalog collection.
// ---------------------------------------------------------------------------

@description('Deployment name the agent passes as the `model` parameter.')
param chatDeploymentName string = 'Kimi-K2.6'

@description('Catalog model name of the chat model.')
param chatModelName string = 'Kimi-K2.6'

@description('Publisher of the chat model as reported by the model catalog.')
param chatModelFormat string = 'Moonshot AI'

param chatModelVersion string = '2026-04-20'
param chatModelSkuName string = 'GlobalStandard'
param chatModelCapacity int = 1

@description('Deployment name used for diary embeddings.')
param embeddingDeploymentName string = 'text-embedding-3-small'

param embeddingModelName string = 'text-embedding-3-small'
param embeddingModelFormat string = 'OpenAI'
param embeddingModelVersion string = '1'
param embeddingModelSkuName string = 'Standard'
param embeddingModelCapacity int = 30

@description('Principal ID of the hosted agent Entra agent identity. Empty until the agent is deployed in Phase 3; set it afterwards to grant the agent access to Cosmos DB.')
param agentPrincipalId string = ''

var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = { 'azd-env-name': environmentName }

var deploymentContainerName = 'deployments'
var diaryBackupContainerName = 'diary-backup'
var lineMessageQueueName = 'line-messages'

resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: !empty(resourceGroupName) ? resourceGroupName : '${abbrs.resourcesResourceGroups}${environmentName}'
  location: location
  tags: tags
}

// Existing resources kept outside the azd-managed resource group.
resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' existing = {
  name: cosmosDbAccountName
  scope: resourceGroup(cosmosDbResourceGroupName)
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
  scope: resourceGroup(keyVaultResourceGroupName)
}

module monitoring 'core/monitor/monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: {
    location: location
    tags: tags
    logAnalyticsName: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    applicationInsightsName: '${abbrs.insightsComponents}${resourceToken}'
  }
}

module storage 'core/storage/storage-account.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    name: '${abbrs.storageStorageAccounts}${resourceToken}'
    location: location
    tags: tags
    containers: [
      deploymentContainerName
      diaryBackupContainerName
    ]
    queues: [
      lineMessageQueueName
    ]
  }
}

module foundry 'core/ai/foundry.bicep' = {
  name: 'foundry'
  scope: rg
  params: {
    accountName: '${abbrs.cognitiveServicesAccounts}${resourceToken}'
    projectName: 'proj-${resourceToken}'
    location: location
    tags: tags
    applicationInsightsName: monitoring.outputs.applicationInsightsName
    modelDeployments: [
      {
        name: chatDeploymentName
        modelName: chatModelName
        format: chatModelFormat
        version: chatModelVersion
        skuName: chatModelSkuName
        capacity: chatModelCapacity
      }
      {
        name: embeddingDeploymentName
        modelName: embeddingModelName
        format: embeddingModelFormat
        version: embeddingModelVersion
        skuName: embeddingModelSkuName
        capacity: embeddingModelCapacity
      }
    ]
  }
}

// LINE gateway and queue worker. The functions themselves arrive in Phase 4.
module functions 'core/host/functions.bicep' = {
  name: 'functions'
  scope: rg
  params: {
    name: '${abbrs.webSitesFunctions}${resourceToken}'
    planName: '${abbrs.webServerFarms}func-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'func' })
    storageAccountName: storage.outputs.name
    deploymentContainerName: deploymentContainerName
    applicationInsightsName: monitoring.outputs.applicationInsightsName
    appSettings: {
      FOUNDRY_PROJECT_ENDPOINT: foundry.outputs.projectEndpoint
      AZURE_AI_MODEL_DEPLOYMENT_NAME: chatDeploymentName
      COSMOS_DB_ACCOUNT_URL: cosmosDb.properties.documentEndpoint
      STORAGE_ACCOUNT_NAME: storage.outputs.name
      LINE_MESSAGE_QUEUE_NAME: lineMessageQueueName
      DIARY_BACKUP_CONTAINER_NAME: diaryBackupContainerName
      LINE_CHANNEL_SECRET: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/LINE-CHANNEL-SECRET)'
      LINE_CHANNEL_ACCESS_TOKEN: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/LINE-CHANNEL-ACCESS-TOKEN)'
    }
  }
}

// ADR-0001: reach Cosmos DB by RBAC, never by account key. The hosted agent identity
// only exists once the agent is deployed, so it joins the list on a later provision.
module cosmosDataAccess 'core/db/cosmos-data-access.bicep' = {
  name: 'cosmos-data-access'
  scope: resourceGroup(cosmosDbResourceGroupName)
  params: {
    accountName: cosmosDbAccountName
    contributorPrincipalIds: concat(
      [functions.outputs.identityPrincipalId],
      empty(agentPrincipalId) ? [] : [agentPrincipalId]
    )
  }
}

module keyVaultAccess 'core/security/keyvault-secrets-user.bicep' = {
  name: 'keyvault-access'
  scope: resourceGroup(keyVaultResourceGroupName)
  params: {
    keyVaultName: keyVaultName
    principalId: functions.outputs.identityPrincipalId
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_TENANT_ID string = tenant().tenantId

output FOUNDRY_ACCOUNT_NAME string = foundry.outputs.accountName
output FOUNDRY_PROJECT_NAME string = foundry.outputs.projectName
output FOUNDRY_PROJECT_ENDPOINT string = foundry.outputs.projectEndpoint
output AZURE_AI_MODEL_DEPLOYMENT_NAME string = chatDeploymentName
output AZURE_AI_EMBEDDING_DEPLOYMENT_NAME string = embeddingDeploymentName

output APPLICATIONINSIGHTS_CONNECTION_STRING string = monitoring.outputs.applicationInsightsConnectionString

output STORAGE_ACCOUNT_NAME string = storage.outputs.name
output LINE_MESSAGE_QUEUE_NAME string = lineMessageQueueName
output DIARY_BACKUP_CONTAINER_NAME string = diaryBackupContainerName

output COSMOS_DB_ACCOUNT_URL string = cosmosDb.properties.documentEndpoint
output AZURE_COSMOSDB_NAME string = cosmosDbAccountName
output AZURE_COSMOSDB_RG string = cosmosDbResourceGroupName
output AZURE_KEYVAULT_NAME string = keyVaultName
output AZURE_KEYVAULT_RG string = keyVaultResourceGroupName
