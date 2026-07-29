metadata description = 'Creates a storage account with the blob containers and queues the app needs.'

// 標準リソースなので AVM を使う。バージョンは固定し、更新は明示的に行う。

param name string
param location string = resourceGroup().location
param tags object = {}

@description('Blob container names.')
param containers string[] = []

@description('Queue names.')
param queues string[] = []

module storage 'br/public:avm/res/storage/storage-account:0.33.0' = {
  name: 'storage-account'
  params: {
    name: name
    location: location
    tags: tags
    kind: 'StorageV2'
    skuName: 'Standard_LRS'
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    // Every caller (Functions host, Timer backup) authenticates with a managed identity.
    allowSharedKeyAccess: false
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
    blobServices: {
      containers: map(containers, containerName => {
        name: containerName
      })
    }
    queueServices: {
      queues: map(queues, queueName => {
        name: queueName
      })
    }
  }
}

output name string = storage.outputs.name
output blobEndpoint string = storage.outputs.serviceEndpoints.blob
output queueEndpoint string = storage.outputs.serviceEndpoints.queue
