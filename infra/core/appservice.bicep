param name string
param location string
param tags object
param linuxFxVersion string

param AppServicePlanName string

param cosmosDbAccountName string

param env object

resource AppServicePlan 'Microsoft.Web/serverfarms@2023-12-01' existing = {
  name: AppServicePlanName
}

resource CosmosAccounts 'Microsoft.DocumentDB/databaseAccounts@2024-02-15-preview' existing = {
  name: cosmosDbAccountName
}


resource AppService 'Microsoft.Web/sites@2023-12-01' = {
  name: name
  location: location
  kind: 'app,linux'
  tags: tags
  properties: {
    enabled: true
    hostNameSslStates: [
      {
        name: '${name}.azurewebsites.net'
        sslState: 'Disabled'
        hostType: 'Standard'
      }
      {
        name: '${name}.scm.azurewebsites.net'
        sslState: 'Disabled'
        hostType: 'Repository'
      }
    ]
    serverFarmId: AppServicePlan.id
    reserved: true
    siteConfig: {
      linuxFxVersion: linuxFxVersion
      appSettings: [
        {
          name: 'COSMOS_DB_ACCOUNT_KEY'
          value: CosmosAccounts.listKeys().primaryMasterKey
        }
        {
          name: 'COSMOS_DB_ACCOUNT_URL'
          value: CosmosAccounts.properties.documentEndpoint
        }
        {
          name: 'COSMOS_DB_DATABASE_NAME'
          value: 'DEMO'
        }
        {
          name: 'LANGCHAIN_API_KEY'
          value: env.LANGCHAIN_API_KEY
        }
        {
          name: 'LINE_USER_ID'
          value: env.LINE_USER_ID
        }
        {
          name: 'LINE_CHANNEL_ACCESS_TOKEN'
          value: env.LINE_CHANNEL_ACCESS_TOKEN
        }
        {
          name: 'LINE_CHANNEL_SECRET'
          value: env.LINE_CHANNEL_SECRET
        }
        {
          name: 'GOOGLE_API_KEY'
          value: env.GOOGLE_API_KEY
        }
      ]
    }
    httpsOnly: true
    keyVaultReferenceIdentity: 'SystemAssigned'
  }
}

resource credentials_ftp 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2023-12-01' = {
  parent: AppService
  name: 'ftp'
  properties: {
    allow: false
  }
}

resource credential_scm 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2023-12-01' = {
  parent: AppService
  name: 'scm'
  properties: {
    allow: false
  }
}

resource AppService_config 'Microsoft.Web/sites/config@2023-12-01' = {
  parent: AppService
  name: 'web'
  properties: {
    linuxFxVersion: linuxFxVersion
    publishingUsername: name
    scmType: 'None'
    use32BitWorkerProcess: true
    ipSecurityRestrictions: [
      {
        ipAddress: 'Any'
        action: 'Allow'
        priority: 2147483647
        name: 'Allow all'
        description: 'Allow all access'
      }
    ]
    scmIpSecurityRestrictions: [
      { 
        ipAddress: 'Any'
        action: 'Allow'
        priority: 2147483647
        name: 'Allow all'
        description: 'Allow all access'
      }
    ]
    minTlsVersion: '1.2'
    scmMinTlsVersion: '1.2'
    ftpsState: 'FtpsOnly'
    appCommandLine: 'startup.txt'
  }
}

resource AppService_hostnamaBindings 'Microsoft.Web/sites/hostNameBindings@2023-12-01' = {
  parent: AppService
  name: '${name}.azurewebsites.net'
  properties: {
    siteName: name
    hostNameType: 'Verified'
  }
}
