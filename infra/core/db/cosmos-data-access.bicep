metadata description = 'Grants the Cosmos DB built-in data plane roles on an existing account, so callers never need an account key.'

@description('Existing Cosmos DB account. This module must be deployed into that account\'s resource group.')
param accountName string

@description('Principal IDs that read and write application data (Gateway/Worker Functions, hosted agent).')
param contributorPrincipalIds string[]

// Cosmos DB Built-in Data Contributor. The ID is fixed for every account.
var dataContributorRoleId = '00000000-0000-0000-0000-000000000002'

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' existing = {
  name: accountName
}

resource contributorAssignments 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = [
  for principalId in contributorPrincipalIds: {
    parent: account
    name: guid(account.id, principalId, dataContributorRoleId)
    properties: {
      principalId: principalId
      roleDefinitionId: '${account.id}/sqlRoleDefinitions/${dataContributorRoleId}'
      scope: account.id
    }
  }
]
