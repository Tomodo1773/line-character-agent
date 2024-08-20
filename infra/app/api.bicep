param name string
param location string = resourceGroup().location
param tags object = {}

param appCommandLine string = 'gunicorn --workers 1 --timeout 120 --access-logfile "-" --error-logfile "-" --bind=0.0.0.0:8000 -k uvicorn.workers.UvicornWorker line-ai-bot.main:app'
param appServicePlanId string
@secure()
param appSettings object = {}
param serviceName string = 'api'

param cosmosDbAccountName string
param cosmosDbResourceGroupName string

param alwaysOn bool
module api '../core/appservice.bicep' = {
  name: 'api'
  params: {
    name: name
    location: location
    tags: union(tags, { 'azd-service-name': serviceName })
    appCommandLine: appCommandLine
    appServicePlanId: appServicePlanId
    cosmosDbAccountName: cosmosDbAccountName
    cosmosDbResourceGroupName: cosmosDbResourceGroupName
    appSettings: appSettings
    runtimeName: 'python'
    runtimeVersion: '3.11'
    scmDoBuildDuringDeployment: true
    alwaysOn: alwaysOn
  }
}
