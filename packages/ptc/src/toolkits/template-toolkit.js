/**
 * Template Toolkit - EJS rendering for MCP
 *
 * Provides template rendering with EJS
 */
import * as ejs from 'ejs';
import { join } from 'path';
import { BaseToolkit } from './base-toolkit.js';
export class TemplateToolkit extends BaseToolkit {
    name = 'template';
    description = 'Template rendering with EJS';
    workingDir;
    constructor(workingDir) {
        super();
        this.workingDir = workingDir;
    }
    getTools() {
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
    async executeTool(toolName, params) {
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
        }
        catch (error) {
            return {
                success: false,
                error: error.message,
            };
        }
    }
    async templateRender(params) {
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
    async templateRenderFile(params) {
        const fullPath = join(this.workingDir, params.templatePath);
        const rendered = await ejs.renderFile(fullPath, params.vars);
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
//# sourceMappingURL=template-toolkit.js.map