metadata description = 'Creates an Azure App Service plan.'
param name string
param location string = resourceGroup().location
param kind string = ''
param tags object = {}

param maximumElasticWorkerCount int =0
param sku object

resource AppServicePlan 'Microsoft.Web/serverfarms@2022-03-01' = {
  name: name
  location: location
  tags: tags
  sku: sku
  kind: kind
  properties: {    
    perSiteScaling: false
    elasticScaleEnabled: false
    maximumElasticWorkerCount: maximumElasticWorkerCount
    isSpot: false
    reserved: true
    isXenon: false
    hyperV: false
    targetWorkerCount: 0
    targetWorkerSizeId: 0
    zoneRedundant: false
    }
}

output id string = AppServicePlan.id
output name string = AppServicePlan.name
