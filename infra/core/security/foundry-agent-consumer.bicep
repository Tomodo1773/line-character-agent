metadata description = 'Grants Foundry Agent Consumer on a Foundry project, so a caller can invoke hosted agent endpoints without any developer permission.'

@description('Foundry account that owns the project.')
param foundryAccountName string

@description('Foundry project the hosted agent lives in.')
param foundryProjectName string

@description('Principal that calls the hosted agent (the Functions managed identity).')
param principalId string

// Foundry Agent Consumer. Least-privilege role for principals that only interact with
// agent endpoints. The GUID is stable across the Foundry role rename.
// https://learn.microsoft.com/azure/foundry/concepts/rbac-foundry
var agentConsumerRoleId = 'eed3b665-ab3a-47b6-8f48-c9382fb1dad6'

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: account
  name: foundryProjectName
}

resource agentConsumerAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(project.id, principalId, agentConsumerRoleId)
  scope: project
  properties: {
    principalId: principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', agentConsumerRoleId)
    principalType: 'ServicePrincipal'
  }
}
