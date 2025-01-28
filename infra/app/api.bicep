param name string
param location string = resourceGroup().location
param tags object = {}

param appCommandLine string = 'python -m gunicorn --workers 1 --timeout 120 --access-logfile "-" --error-logfile "-" --bind=0.0.0.0:8000 -k uvicorn.workers.UvicornWorker chatbot.main:app'
param appServicePlanId string
@secure()
param appSettings object = {}
param serviceName string = 'api'

param cosmosDbAccountName string
param cosmosDbResourceGroupName string

param alwaysOn bool
module api '../core/host/appservice.bicep' = {
  name: 'api'
  params: {
    name: name
    location: location
    tags: union(tags, { 'azd-service-name': serviceName })
    appCommandLine: appCommandLine
    appServicePlanId: appServicePlanId
    appSettings: union(appSettings,
      {
        COSMOS_DB_ACCOUNT_KEY: CosmosAccounts.listKeys().primaryMasterKey
        COSMOS_DB_ACCOUNT_URL: CosmosAccounts.properties.documentEndpoint
      })
    runtimeName: 'python'
    runtimeVersion: '3.11'
    alwaysOn: alwaysOn
  }
}

resource CosmosAccounts 'Microsoft.DocumentDB/databaseAccounts@2024-02-15-preview' existing = {
  name: cosmosDbAccountName
  scope: resourceGroup(cosmosDbResourceGroupName)
}
