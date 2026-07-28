metadata description = 'Creates a storage account with the blob containers and queues the app needs.'

param name string
param location string = resourceGroup().location
param tags object = {}

@description('Blob container names.')
param containers string[] = []

@description('Queue names.')
param queues string[] = []

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    // Every caller (Functions host, Timer backup) authenticates with a managed identity.
    allowSharedKeyAccess: false
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }

  resource blobServices 'blobServices' = {
    name: 'default'

    resource container 'containers' = [
      for containerName in containers: {
        name: containerName
      }
    ]
  }

  resource queueServices 'queueServices' = {
    name: 'default'

    resource queue 'queues' = [
      for queueName in queues: {
        name: queueName
      }
    ]
  }
}

output name string = storage.name
output blobEndpoint string = storage.properties.primaryEndpoints.blob
output queueEndpoint string = storage.properties.primaryEndpoints.queue
