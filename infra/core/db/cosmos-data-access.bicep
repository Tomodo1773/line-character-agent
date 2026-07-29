metadata description = 'Grants the Cosmos DB built-in data plane roles on an existing account, so callers never need an account key.'

// 割り当てそのものは AVM の子モジュールを使う。バージョンは固定し、更新は明示的に行う。

@description('Existing Cosmos DB account. This module must be deployed into that account\'s resource group.')
param accountName string

@description('Principal IDs that read and write application data (Gateway/Worker Functions, hosted agent).')
param contributorPrincipalIds string[]

// Cosmos DB Built-in Data Contributor. The ID is fixed for every account.
var dataContributorRoleId = '00000000-0000-0000-0000-000000000002'

resource account 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' existing = {
  name: accountName
}

module contributorAssignments 'br/public:avm/res/document-db/database-account/sql-role-assignment:0.2.1' = [
  for principalId in contributorPrincipalIds: {
    name: 'cosmos-data-contributor-${uniqueString(principalId)}'
    params: {
      databaseAccountName: accountName
      principalId: principalId
      roleDefinitionIdOrName: dataContributorRoleId
      // アカウント全体を対象にする（従来の scope: account.id と同じ）。
      scope: account.id
      // 既存の割り当てと同じ名前を保ち、置き換えで権限が一度落ちるのを避ける。
      name: guid(account.id, principalId, dataContributorRoleId)
    }
  }
]
