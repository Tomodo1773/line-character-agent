metadata description = 'Creates an Azure Function for MCP Spotify in an existing Azure App Service plan.'
param name string
param location string = resourceGroup().location
param tags object = {}

// Reference Properties
param applicationInsightsName string = ''
param appServicePlanId string
param keyVaultName string = ''
param managedIdentity bool = !empty(keyVaultName)
param storageAccountName string

// Runtime Properties
@allowed([
  'dotnet', 'dotnetcore', 'dotnet-isolated', 'node', 'python', 'java', 'powershell', 'custom'
])
param runtimeName string
param runtimeVersion string

// Function Settings
@allowed([
  '~4', '~3', '~2', '~1'
])
param extensionVersion string = '~4'

// Microsoft.Web/sites Properties
param kind string = 'functionapp,linux'

// Microsoft.Web/sites/config
param allowedOrigins array = []
param alwaysOn bool = false
param appCommandLine string = ''
@secure()
param appSettings object = {}
param clientAffinityEnabled bool = false
param functionAppScaleLimit int = -1
param minimumElasticInstanceCount int = -1
param numberOfWorkers int = -1
param use32BitWorkerProcess bool = false
param healthCheckPath string = ''

param functionAppContainer string = ''

param serviceName string = 'mcp-spotify'

module functions '../core/host/function.bicep' = {
  name: '${name}-functions'
  params: {
    name: name
    location: location
    tags: union(tags, { 'azd-service-name': serviceName })
    allowedOrigins: allowedOrigins
    alwaysOn: alwaysOn
    appCommandLine: appCommandLine
    applicationInsightsName: applicationInsightsName
    appServicePlanId: appServicePlanId
    appSettings: union(appSettings, {
        AzureWebJobsStorage: 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
        DEPLOYMENT_STORAGE_CONNECTION_STRING: 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'
        FUNCTIONS_EXTENSION_VERSION: extensionVersion
      })
    clientAffinityEnabled: clientAffinityEnabled
    functionAppScaleLimit: functionAppScaleLimit
    healthCheckPath: healthCheckPath
    keyVaultName: keyVaultName
    kind: kind
    managedIdentity: managedIdentity
    minimumElasticInstanceCount: minimumElasticInstanceCount
    numberOfWorkers: numberOfWorkers
    runtimeName: runtimeName
    runtimeVersion: runtimeVersion
    use32BitWorkerProcess: use32BitWorkerProcess
    functionAppContainer: functionAppContainer
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2021-09-01' existing = {
  name: storageAccountName
}

output identityPrincipalId string = managedIdentity ? functions.outputs.identityPrincipalId : ''
output name string = functions.outputs.name
output uri string = functions.outputs.uri