/**
 * MCP Toolkits - Exports all available toolkits
 */

export { BaseToolkit, type ToolDefinition, type ToolResult } from './base-toolkit.js';
export { FileToolkit } from './file-toolkit.js';
export { GitToolkit } from './git-toolkit.js';
export { BuildToolkit } from './build-toolkit.js';
export { TestToolkit } from './test-toolkit.js';
export { TemplateToolkit } from './template-toolkit.js';
export { LintToolkit } from './lint-toolkit.js';
export { SecretToolkit } from './secret-toolkit.js';

import { BaseToolkit } from './base-toolkit.js';
import { FileToolkit } from './file-toolkit.js';
import { GitToolkit } from './git-toolkit.js';
import { BuildToolkit } from './build-toolkit.js';
import { TestToolkit } from './test-toolkit.js';
import { TemplateToolkit } from './template-toolkit.js';
import { LintToolkit } from './lint-toolkit.js';
import { SecretToolkit } from './secret-toolkit.js';
import { SecretProvider } from '../src/interfaces.js';

/**
 * Create all standard toolkits for a workspace
 */
export function createStandardToolkits(
  workingDir: string,
  secretProvider: SecretProvider
): BaseToolkit[] {
  return [
    new FileToolkit(workingDir),
    new TemplateToolkit(workingDir),
    new GitToolkit(workingDir),
    new BuildToolkit(workingDir),
    new TestToolkit(workingDir),
    new LintToolkit(workingDir),
    new SecretToolkit(secretProvider),
  ];
}

/**
 * Get all available tools from toolkits
 */
export function getAllToolDefinitions(toolkits: BaseToolkit[]) {
  const tools: any[] = [];

  for (const toolkit of toolkits) {
    const toolkitTools = toolkit.getTools();
    tools.push(...toolkitTools);
  }

  return tools;
}

/**
 * Execute a tool by name across all toolkits
 */
export async function executeToolByName(
  toolName: string,
  params: any,
  toolkits: BaseToolkit[]
) {
  for (const toolkit of toolkits) {
    const tools = toolkit.getTools();
    const tool = tools.find((t) => t.name === toolName);

    if (tool) {
      return await toolkit.executeTool(toolName, params);
    }
  }

  return {
    success: false,
    error: `Tool not found: ${toolName}`,
  };
}
