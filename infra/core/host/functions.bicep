metadata description = 'Creates a Flex Consumption Azure Functions app that reaches storage with its managed identity.'

param name string
param planName string
param location string = resourceGroup().location
param tags object = {}

@description('Storage account used for host state and for the deployment package.')
param storageAccountName string

@description('Blob container that holds the deployment package.')
param deploymentContainerName string

param applicationInsightsName string

@description('Python version of the Functions worker.')
param runtimeVersion string = '3.11'

@secure()
param appSettings object = {}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: applicationInsightsName
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  tags: tags
  kind: 'functionapp'
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: name
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    keyVaultReferenceIdentity: 'SystemAssigned'
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${deploymentContainerName}'
          authentication: {
            type: 'SystemAssignedIdentity'
          }
        }
      }
      runtime: {
        name: 'python'
        version: runtimeVersion
      }
      scaleAndConcurrency: {
        // 個人専用エージェントの会話を単一Workerで順番に処理する。
        maximumInstanceCount: 1
        instanceMemoryMB: 512
      }
    }
  }
}

resource configAppSettings 'Microsoft.Web/sites/config@2023-12-01' = {
  parent: functionApp
  name: 'appsettings'
  properties: union(appSettings, {
    // Identity-based host storage: Flex Consumption needs no connection string.
    AzureWebJobsStorage__accountName: storage.name
    APPLICATIONINSIGHTS_CONNECTION_STRING: applicationInsights.properties.ConnectionString
  })
}

// Roles the Functions host needs on its own storage account once the connection is identity-based:
// blobs for host state and the deployment package, queues for the LINE message queue, tables for
// diagnostic events. See https://learn.microsoft.com/azure/azure-functions/manage-connections
var storageRoleIds = [
  'b7e6dc6d-f1e8-4753-8033-0f276bb0955b' // Storage Blob Data Owner
  '974c5e8b-45b9-4653-ba55-5f855dd0fb88' // Storage Queue Data Contributor
  '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3' // Storage Table Data Contributor
]

resource storageRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for roleId in storageRoleIds: {
    name: guid(storage.id, functionApp.id, roleId)
    scope: storage
    properties: {
      principalId: functionApp.identity.principalId
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleId)
      principalType: 'ServicePrincipal'
    }
  }
]

output name string = functionApp.name
output uri string = 'https://${functionApp.properties.defaultHostName}'
output identityPrincipalId string = functionApp.identity.principalId
