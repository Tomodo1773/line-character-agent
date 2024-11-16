targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the the environment which is used to generate a short unique hash used in all resources.')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Location for azure functions')
param locationFunc string ='Australia East'

param resourceGroupName string = ''

param cosmosDbAccountName string = ''
param cosmosDbResourceGroupName string = ''
param appServicePlanName string = ''
param appServicePlanResourceGroupName string = ''

param appSettings object

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

module CosmosDB 'core/cosmos.bicep' = if (empty(cosmosDbAccountName)) {
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

module AppServicePlan 'core/appserviceplan.bicep' = if (empty(appServicePlanName)) {
  name: 'AppServicePlan'
  scope: rg
  params: {
    name: '${abbrs.webServerFarms}${resourceToken}'
    location: location
    tags: tags
    skuName: 'F1'
    skuTier: 'Free'
    skuSize: 'F1'
    skuFamily: 'F'
    skuCapacity: 1
    kind: 'linux'
  }
}

// ****************************************************************
// AppService
// ****************************************************************

// The application backend
module AppService './app/api.bicep' = {
  name: 'AppService'
  scope: rg
  params: {
    name: '${abbrs.webSitesAppService}${resourceToken}'
    location: location
    tags: tags
    appServicePlanId: empty(appServicePlanName) ? AppServicePlan.outputs.id : existingAppServicePlan.id
    cosmosDbAccountName: empty(cosmosDbAccountName) ? CosmosDB.outputs.name : existingCosmosDB.name
    cosmosDbResourceGroupName: empty(cosmosDbResourceGroupName) ? rg.name : cosmosDbResourceGroupName
    alwaysOn: true
    appSettings: {
      LANGCHAIN_API_KEY: appSettings.LANGCHAIN_API_KEY
      LINE_CHANNEL_ACCESS_TOKEN: appSettings.LINE_CHANNEL_ACCESS_TOKEN
      LINE_CHANNEL_SECRET: appSettings.LINE_CHANNEL_SECRET
      GOOGLE_API_KEY: appSettings.GOOGLE_API_KEY
      TAVILY_API_KEY: appSettings.TAVILY_API_KEY
      OPENAI_API_KEY: appSettings.OPENAI_API_KEY
      GROQ_API_KEY: appSettings.GROQ_API_KEY
      FIRECRAWL_API_KEY:appSettings.FIRECRAWL_API_KEY
      COSMOS_DB_DATABASE_NAME: appSettings.COSMOS_DB_DATABASE_NAME
      ANTHROPIC_API_KEY:appSettings.ANTHROPIC_API_KEY
      AZURE_AI_SEARCH_SERVICE_NAME:appSettings.AZURE_AI_SEARCH_SERVICE_NAME
      AZURE_AI_SEARCH_API_KEY:appSettings.AZURE_AI_SEARCH_API_KEY
    }
  }
  dependsOn:[
    AppServicePlan
    CosmosDB
  ]
}


// ****************************************************************
// Functions
// ****************************************************************

module storageAccount 'core/storage/storage-account.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    name: '${abbrs.storageStorageAccounts}${resourceToken}'
    location: locationFunc
    tags: tags
  }
}

module appServicePlan './core/host/appserviceplan.bicep' = {
  name: 'func-appserviceplan'
  scope: rg
  params: {
    name: '${abbrs.webServerFarms}func-${resourceToken}'
    location: locationFunc
    tags: tags
    sku: {
      name: 'FC1'
      tier: 'FlexConsumption'
    }
  }
}

module functionApp 'core/host/functions.bicep' = {
  name: 'function'
  scope: rg
  params: {
    name: '${abbrs.webSitesFunctions}${resourceToken}'
    location: locationFunc
    tags: union(tags, { 'azd-service-name': 'func' })
    alwaysOn: false
    appSettings: {
      AzureWebJobsFeatureFlags: 'EnableWorkerIndexing'
    }
    appServicePlanId: appServicePlan.outputs.id
    runtimeName: 'python'
    runtimeVersion: '3.11'
    storageAccountName: storageAccount.outputs.name
    functionAppScaleLimit: 100
    minimumElasticInstanceCount: 0
  }
}
