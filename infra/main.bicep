targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the the environment which is used to generate a short unique hash used in all resources.')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string


param resourceGroupName string = ''

param cosmosDbAccountName string = ''
param cosmosDbResourceGroupName string = ''
param appServicePlanName string = ''
param appServicePlanResourceGroupName string = ''

param keyVaultName string
param keyVaultResourceGroupName string


var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = { 'azd-env-name': environmentName }

// Organize resources in a resource group
resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: !empty(resourceGroupName) ? resourceGroupName : '${abbrs.resourcesResourceGroups}${environmentName}'
  location: location
  tags: tags
}


// ****************************************************************
// CosmosDB
// ****************************************************************

resource existingCosmosDB 'Microsoft.DocumentDB/databaseAccounts@2021-04-15' existing = if (!empty(cosmosDbAccountName)) {
  name: cosmosDbAccountName
  scope: resourceGroup(cosmosDbResourceGroupName)
}

module CosmosDB 'core/db/cosmos.bicep' = if (empty(cosmosDbAccountName)) {
  name: 'CosmosDB'
  scope: rg
  params: {
    name: '${abbrs.documentDBDatabaseAccounts}${resourceToken}'
    location: location
    tags: {
      defaultExperience: 'Core (SQL)'
      'hidden-cosmos-mmspecial': ''
      'azd-env-name': environmentName
    }
    enableFreeTier: true
    totalThroughputLimit: 1000
  }
}

// ****************************************************************
// AppServicePlan
// ****************************************************************

resource existingAppServicePlan 'Microsoft.Web/serverfarms@2021-02-01' existing = {
  name: appServicePlanName
  scope: resourceGroup(appServicePlanResourceGroupName)
}

module AppServicePlan 'core/host/appserviceplan.bicep' = if (empty(appServicePlanName)) {
  name: 'AppServicePlan'
  scope: rg
  params: {
    name: '${abbrs.webServerFarms}${resourceToken}'
    location: location
    tags: tags
    sku: {
      name: 'F1'
      tier: 'Free'
    }
    kind: 'linux'
  }
}

// ****************************************************************
// Key Vault (existing)
// ****************************************************************

resource keyVault 'Microsoft.KeyVault/vaults@2022-07-01' existing = {
  name: keyVaultName
  scope: resourceGroup(!empty(keyVaultResourceGroupName) ? keyVaultResourceGroupName : resourceGroupName)
}

// ****************************************************************
// AppService
// ****************************************************************

// The application backend
var appServiceName = '${abbrs.webSitesAppService}${resourceToken}'
var appServiceUri = 'https://${appServiceName}.azurewebsites.net'
var googleOAuthRedirectUri = '${appServiceUri}/auth/google/callback'

module AppService './app/api.bicep' = {
  name: 'AppService'
  scope: rg
  params: {
    name: appServiceName
    location: location
    tags: tags
    appServicePlanId: empty(appServicePlanName) ? AppServicePlan.outputs.id : existingAppServicePlan.id
    cosmosDbAccountName: empty(cosmosDbAccountName) ? CosmosDB.outputs.name : existingCosmosDB.name
    cosmosDbResourceGroupName: empty(cosmosDbResourceGroupName) ? rg.name : cosmosDbResourceGroupName
    keyVaultName: keyVaultName
    alwaysOn: true
    appSettings: {
      LANGSMITH_API_KEY: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/LANGSMITH-API-KEY)'
      LINE_CHANNEL_ACCESS_TOKEN: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/LINE-CHANNEL-ACCESS-TOKEN)'
      LINE_CHANNEL_SECRET: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/LINE-CHANNEL-SECRET)'
      OPENAI_API_KEY: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/OPENAI-API-KEY)'
      OPENAI_COMPATIBLE_API_KEY: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/OPENAI-COMPATIBLE-API-KEY)'
      MCP_FUNCTION_URL: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/MCP-FUNCTION-URL)'
      GOOGLE_CLIENT_ID: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/GOOGLE-CLIENT-ID)'
      GOOGLE_CLIENT_SECRET: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/GOOGLE-CLIENT-SECRET)'
      GOOGLE_OAUTH_REDIRECT_URI: googleOAuthRedirectUri
      GOOGLE_TOKEN_ENC_KEY: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/GOOGLE-TOKEN-ENC-KEY)'
      POSTGRES_CHECKPOINT_URL: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/POSTGRES-CHECKPOINT-URL)'
      COSMOS_DB_CONNECTION_VERIFY: 'true'
      APPLICATIONINSIGHTS_CONNECTION_STRING: monitoring.outputs.applicationInsightsConnectionString
    }
  }
}


// ****************************************************************
// Functions
// ****************************************************************

module monitoring './core/monitor/monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: {
    location: location
    tags: tags
    logAnalyticsName: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    applicationInsightsName: '${abbrs.insightsComponents}${resourceToken}'
    applicationInsightsDashboardName: '${abbrs.insightsComponents}${resourceToken}-dashboard'
  }
}

module storageAccount 'core/storage/storage-account.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    name: '${abbrs.storageStorageAccounts}${resourceToken}'
    location: location
    tags: tags
    containers: [
      {
        name: 'app-package-${resourceToken}'
        publicAccess: 'None'
      }
      {
        name: 'app-package-mcp-${resourceToken}'
        publicAccess: 'None'
      }
      {
        name: 'azure-webjobs-hosts'
        publicAccess: 'None'
      }
      {
        name: 'azure-webjobs'
        publicAccess: 'None'
      }
    ]
  }
}

module appServicePlan './core/host/appserviceplan.bicep' = {
  name: 'func-appserviceplan'
  scope: rg
  params: {
    name: '${abbrs.webServerFarms}func-${resourceToken}'
    location: location
    tags: tags
    sku: {
      name: 'FC1'
      tier: 'FlexConsumption'
    }
  }
}

module functionApp 'app/func.bicep' = {
  name: 'function'
  scope: rg
  params: {
    name: '${abbrs.webSitesFunctions}${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'func' })
    alwaysOn: false
    keyVaultName: keyVaultName
    cosmosDbAccountName: empty(cosmosDbAccountName) ? CosmosDB.outputs.name : existingCosmosDB.name
    cosmosDbResourceGroupName: empty(cosmosDbResourceGroupName) ? rg.name : cosmosDbResourceGroupName
    appSettings: {
      AzureWebJobsFeatureFlags: 'EnableWorkerIndexing'
      OPENAI_API_KEY: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/OPENAI-API-KEY)'
      LANGSMITH_API_KEY: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/LANGSMITH-API-KEY)'
      LANGCHAIN_PROJECT: 'diary-rag'
      SPAN_DAYS: 5
      GOOGLE_CLIENT_ID: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/GOOGLE-CLIENT-ID)'
      GOOGLE_CLIENT_SECRET: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/GOOGLE-CLIENT-SECRET)'
      GOOGLE_TOKEN_ENC_KEY: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/GOOGLE-TOKEN-ENC-KEY)'
      COSMOS_DB_CONNECTION_VERIFY: 'true'
    }
    applicationInsightsName: monitoring.outputs.applicationInsightsName
    appServicePlanId: appServicePlan.outputs.id
    runtimeName: 'python'
    runtimeVersion: '3.11'
    storageAccountName: storageAccount.outputs.name
    functionAppContainer: 'https://${storageAccount.outputs.name}.blob.${environment().suffixes.storage}/app-package-${resourceToken}'
    functionAppScaleLimit: 100
    minimumElasticInstanceCount: 0
  }
}

module mcpFunctionApp 'app/mcp.bicep' = {
  name: 'mcp'
  scope: rg
  params: {
    name: '${abbrs.webSitesFunctions}mcp-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'mcp' })
    alwaysOn: false
    keyVaultName: keyVaultName
    appSettings: {
      AzureWebJobsFeatureFlags: 'EnableWorkerIndexing'
      SPOTIFY_CLIENT_ID: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/SPOTIFY-CLIENT-ID)'
      SPOTIFY_CLIENT_SECRET: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/SPOTIFY-CLIENT-SECRET)'
      SPOTIFY_REFRESH_TOKEN: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/SPOTIFY-REFRESH-TOKEN)'
      OPENAI_API_KEY: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/OPENAI-API-KEY)'
    }
    applicationInsightsName: monitoring.outputs.applicationInsightsName
    appServicePlanId: appServicePlan.outputs.id
    runtimeName: 'python'
    runtimeVersion: '3.11'
    storageAccountName: storageAccount.outputs.name
    functionAppContainer: 'https://${storageAccount.outputs.name}.blob.${environment().suffixes.storage}/app-package-mcp-${resourceToken}'
    functionAppScaleLimit: 100
    minimumElasticInstanceCount: 0
  }
}

module diagnostics 'core/host/app-diagnostics.bicep' = {
  name: 'functions-diagnostics'
  scope: rg
  params: {
    appName: functionApp.outputs.name
    kind: 'functionapp'
    diagnosticWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
  }
}

module mcpDiagnostics 'core/host/app-diagnostics.bicep' = {
  name: 'mcp-diagnostics'
  scope: rg
  params: {
    appName: mcpFunctionApp.outputs.name
    kind: 'functionapp'
    diagnosticWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
  }
}

// ****************************************************************
// RBAC Role Assignments for Key Vault
// ****************************************************************

module assignKeyVaultRoles 'core/host/assign-keyvault-roles.bicep' = {
  name: 'assignKeyVaultRoles'
  scope: resourceGroup(!empty(keyVaultResourceGroupName) ? keyVaultResourceGroupName : resourceGroupName)
  params: {
    keyVaultName: keyVaultName
    principalAssignments: [
      {
        name: AppService.name
        principalId: AppService.outputs.identityPrincipalId
      }
      {
        name: functionApp.name
        principalId: functionApp.outputs.identityPrincipalId
      }
      {
        name: mcpFunctionApp.name
        principalId: mcpFunctionApp.outputs.identityPrincipalId
      }
    ]
  }
}
