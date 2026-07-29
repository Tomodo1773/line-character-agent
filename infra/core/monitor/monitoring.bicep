metadata description = 'Creates the Application Insights component and the Log Analytics workspace behind it.'

// 標準リソースなので AVM を使う。バージョンは固定し、更新は明示的に行う。

param logAnalyticsName string
param applicationInsightsName string
param location string = resourceGroup().location
param tags object = {}

module logAnalytics 'br/public:avm/res/operational-insights/workspace:0.16.0' = {
  name: 'log-analytics'
  params: {
    name: logAnalyticsName
    location: location
    tags: tags
    dataRetention: 30
    skuName: 'PerGB2018'
  }
}

module applicationInsights 'br/public:avm/res/insights/component:0.8.0' = {
  name: 'application-insights'
  params: {
    name: applicationInsightsName
    location: location
    tags: tags
    kind: 'web'
    applicationType: 'web'
    workspaceResourceId: logAnalytics.outputs.resourceId
  }
}

output applicationInsightsName string = applicationInsights.outputs.name
output applicationInsightsConnectionString string = applicationInsights.outputs.connectionString
