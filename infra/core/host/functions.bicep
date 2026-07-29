metadata description = 'Creates a Flex Consumption Azure Functions app that reaches storage with its managed identity.'

// プランとサイトは標準リソースなので AVM を使う。バージョンは固定し、更新は明示的に行う。
// ストレージへのロール付与だけは、サイトのプリンシパル ID が要るため raw Bicep の glue として残す。

param name string
param planName string
param location string = resourceGroup().location
param tags object = {}

@description('Storage account used for host state and for the deployment package.')
param storageAccountName string

@description('Blob container that holds the deployment package.')
param deploymentContainerName string

param applicationInsightsName string

@description('Python version of the Functions worker. Flex Consumption supports 3.13 as GA.')
param runtimeVersion string = '3.13'

@secure()
param appSettings object = {}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: applicationInsightsName
}

module plan 'br/public:avm/res/web/serverfarm:0.7.0' = {
  name: 'functions-plan'
  params: {
    name: planName
    location: location
    tags: tags
    kind: 'functionapp'
    skuName: 'FC1'
    reserved: true
  }
}

module functionApp 'br/public:avm/res/web/site:0.24.0' = {
  name: 'functions-site'
  params: {
    name: name
    location: location
    tags: tags
    kind: 'functionapp,linux'
    serverFarmResourceId: plan.outputs.resourceId
    managedIdentities: {
      systemAssigned: true
    }
    httpsOnly: true
    // Key Vault 参照のアプリ設定を、システム割り当て ID で解決する。
    keyVaultAccessIdentityResourceId: 'SystemAssigned'
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
    configs: [
      {
        name: 'appsettings'
        properties: union(appSettings, {
          // Identity-based host storage: Flex Consumption needs no connection string.
          AzureWebJobsStorage__accountName: storage.name
          APPLICATIONINSIGHTS_CONNECTION_STRING: applicationInsights.properties.ConnectionString
        })
      }
    ]
  }
}

// Roles the Functions host needs on its own storage account once the connection is identity-based:
// blobs for host state and the deployment package, queues for the LINE message queue, tables for
// diagnostic events. See https://learn.microsoft.com/azure/azure-functions/manage-connections
// ストレージ側の AVM へロールを渡すとサイトとの間で循環参照になるため、ここで付ける。
var storageRoleIds = [
  'b7e6dc6d-f1e8-4753-8033-0f276bb0955b' // Storage Blob Data Owner
  '974c5e8b-45b9-4653-ba55-5f855dd0fb88' // Storage Queue Data Contributor
  '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3' // Storage Table Data Contributor
]

resource storageRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for roleId in storageRoleIds: {
    // ロール割り当て名はデプロイ開始時に確定する必要があるため、サイトの出力ではなく
    // 名前から導いたリソース ID を使う（値は functionApp のリソース ID と同じ）。
    name: guid(storage.id, resourceId('Microsoft.Web/sites', name), roleId)
    scope: storage
    properties: {
      principalId: functionApp.outputs.systemAssignedMIPrincipalId!
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleId)
      principalType: 'ServicePrincipal'
    }
  }
]

output name string = functionApp.outputs.name
output uri string = 'https://${functionApp.outputs.defaultHostname}'
output identityPrincipalId string = functionApp.outputs.systemAssignedMIPrincipalId!
