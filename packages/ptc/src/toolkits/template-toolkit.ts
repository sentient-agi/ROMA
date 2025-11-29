/**
 * Template Toolkit - EJS rendering for MCP
 *
 * Provides template rendering with EJS
 */
import * as ejs from 'ejs';
import { join } from 'path';
import { BaseToolkit, ToolDefinition, ToolResult } from './base-toolkit.js';

export class TemplateToolkit extends BaseToolkit {
  readonly name = 'template';
  readonly description = 'Template rendering with EJS';

  private workingDir: string;

  constructor(workingDir: string) {
    super();
    this.workingDir = workingDir;
  }

  getTools(): ToolDefinition[] {
    return [
      {
        name: 'template_render',
        description: 'Render an EJS template with variables',
        inputSchema: {
          type: 'object',
          properties: {
            template: {
              type: 'string',
              description: 'EJS template string',
              required: true,
            },
            vars: {
              type: 'object',
              description: 'Variables to inject into template',
              required: true,
            },
          },
          required: ['template', 'vars'],
        },
      },
      {
        name: 'template_render_file',
        description: 'Render an EJS template file',
        inputSchema: {
          type: 'object',
          properties: {
            templatePath: {
              type: 'string',
              description: 'Path to EJS template file',
              required: true,
            },
            vars: {
              type: 'object',
              description: 'Variables to inject into template',
              required: true,
            },
          },
          required: ['templatePath', 'vars'],
        },
      },
    ];
  }

  async executeTool(toolName: string, params: any): Promise<ToolResult> {
    try {
      switch (toolName) {
        case 'template_render':
          return await this.templateRender(params);
        case 'template_render_file':
          return await this.templateRenderFile(params);
        default:
          return {
            success: false,
            error: `Unknown tool: ${toolName}`,
          };
      }
    } catch (error: any) {
      return {
        success: false,
        error: error.message,
      };
    }
  }

  private async templateRender(params: any): Promise<ToolResult> {
    const rendered = ejs.render(params.template, params.vars);

    return {
      success: true,
      output: rendered,
      metadata: {
        templateLength: params.template.length,
        outputLength: rendered.length,
        varsCount: Object.keys(params.vars).length,
      },
    };
  }

  private async templateRenderFile(params: any): Promise<ToolResult> {
    const fullPath = join(this.workingDir, params.templatePath);
    const rendered = (await ejs.renderFile(fullPath, params.vars)) as string;

    return {
      success: true,
      output: rendered,
      metadata: {
        templatePath: params.templatePath,
        outputLength: rendered.length,
        varsCount: Object.keys(params.vars).length,
      },
    };
  }
}
