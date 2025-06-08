param keyVaultName string
param principalAssignments array

resource keyVault 'Microsoft.KeyVault/vaults@2022-07-01' existing = {
  name: keyVaultName
  scope: resourceGroup()
}

// principalAssignments: [
//   {
//     name: string // AppService.name など
//     principalId: string // AppService.outputs.identityPrincipalId など
//   }, ...
// ]

var roleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7')

// ループで各principalにroleAssignmentを作成
resource keyVaultRoleAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for assignment in principalAssignments: {
  name: guid(assignment.name, keyVault.id, 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7')
  scope: keyVault
  properties: {
    principalId: assignment.principalId
    roleDefinitionId: roleDefinitionId // Key Vault Secrets User
    principalType: 'ServicePrincipal'
  }
}]
