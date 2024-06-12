targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the the environment which is used to generate a short unique hash used in all resources.')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

param resourceGroupName string = ''

param env object
var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = { 'azd-env-name': environmentName }

// Organize resources in a resource group
resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: !empty(resourceGroupName) ? resourceGroupName : '${abbrs.resourcesResourceGroups}${environmentName}'
  location: location
  tags: tags
}

module CosmosDB 'core/cosmos.bicep' = {
  name: 'CosmosDB'
  scope: rg
  params: {
    name: '${abbrs.documentDBDatabaseAccounts}${resourceToken}'
    location: 'Japan West'
    tags: {
      defaultExperience: 'Core (SQL)'
      'hidden-cosmos-mmspecial': ''
      'azd-env-name': environmentName
    }
    enableFreeTier: false
    totalThroughputLimit: 1000
  }
}

module AppServicePlan 'core/appserviceplan.bicep' = {
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

// module AppService 'core/appservice.bicep' = {
//   name: 'AppService'
//   scope: rg
//   params: {
//     name: '${abbrs.webSitesAppService}${resourceToken}'
//     location: location
//     tags: { 
//       'azd-env-name': environmentName
//       'azd-service-name': 'api'
//     }
//     AppServicePlanName: AppServicePlan.outputs.name
//     linuxFxVersion: 'PYTHON|3.11'
//     cosmosDbAccountName: CosmosDB.outputs.name
//     env: env
//   }
//   dependsOn:[
//     AppServicePlan
//     CosmosDB
//   ]
// }

// The application backend
module AppService './app/api.bicep' = {
  name: 'AppService'
  scope: rg
  params: {
    name: '${abbrs.webSitesAppService}${resourceToken}'
    location: location
    tags: tags
    // applicationInsightsName: monitoring.outputs.applicationInsightsName
    appServicePlanId: AppServicePlan.outputs.name
    cosmosDbAccountName: CosmosDB.outputs.name
    // keyVaultName: keyVault.outputs.name
    // allowedOrigins: [ web.outputs.SERVICE_WEB_URI ]
    appSettings: {
      LANGCHAIN_API_KEY: env.LANGCHAIN_API_KEY
      LINE_USER_ID: env.LINE_USER_ID
      LINE_CHANNEL_ACCESS_TOKEN: env.LINE_CHANNEL_ACCESS_TOKEN
      LINE_CHANNEL_SECRET: env.LINE_CHANNEL_SECRET
      GOOGLE_API_KEY: env.GOOGLE_API_KEY
    }
  }
  dependsOn:[
    AppServicePlan
    CosmosDB
  ]
}


// App outputs
