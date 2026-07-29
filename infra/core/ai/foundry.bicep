metadata description = 'Creates a Microsoft Foundry account, a project, and the model deployments the agent uses.'

@description('Publisher, catalog model and deployment settings for one model deployment.')
type modelDeployment = {
  @description('Deployment name. This is what the agent passes as the `model` parameter.')
  name: string

  @description('Catalog model name, for example `Kimi-K2.6`.')
  modelName: string

  @description('Publisher as reported by `az cognitiveservices account list-models`, for example `Moonshot AI` or `OpenAI`.')
  format: string

  @description('Model version, for example `2026-04-20`.')
  version: string

  @description('Deployment type, for example `GlobalStandard`.')
  skuName: string

  @description('Capacity in units of 1,000 tokens per minute.')
  capacity: int
}

@description('Foundry account name. Doubles as the custom subdomain, so it must be globally unique.')
param accountName string

@description('Foundry project name. The project endpoint is derived from this.')
param projectName string

param location string
param tags object = {}

@description('Model deployments to create on the account.')
param modelDeployments modelDeployment[]

@description('Application Insights resource that receives the project and hosted agent traces.')
param applicationInsightsName string

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: applicationInsightsName
}

// アカウントとモデルデプロイは AVM を使う。バージョンは固定し、更新は明示的に行う。
// AVM はデプロイを直列に作るため、Foundry が同時書き込みを拒む問題は起きない。
module accountModule 'br/public:avm/res/cognitive-services/account:0.17.0' = {
  name: 'foundry-account'
  params: {
    name: accountName
    location: location
    tags: tags
    kind: 'AIServices'
    sku: 'S0'
    managedIdentities: {
      systemAssigned: true
    }
    // Required to host Foundry projects under this account.
    allowProjectManagement: true
    customSubDomainName: accountName
    // ADR-0001: model calls authenticate with Entra ID, so API keys stay disabled.
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    deployments: map(modelDeployments, deployment => {
      name: deployment.name
      sku: {
        name: deployment.skuName
        capacity: deployment.capacity
      }
      model: {
        format: deployment.format
        name: deployment.modelName
        version: deployment.version
      }
    })
  }
}

// Project と Connection は AVM が未対応なので raw Bicep を維持する。
resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
  dependsOn: [
    accountModule
  ]
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
}

// Foundry Observability. Connecting Application Insights turns on server-side tracing for
// every agent in the project, so hosted agents emit OpenTelemetry traces without any code change.
resource applicationInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: applicationInsightsName
  properties: {
    category: 'AppInsights'
    target: applicationInsights.id
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: applicationInsights.properties.ConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: applicationInsights.id
    }
  }
}

output accountName string = account.name
output projectName string = project.name
output projectEndpoint string = 'https://${accountName}.services.ai.azure.com/api/projects/${projectName}'
