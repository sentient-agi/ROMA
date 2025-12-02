/**
 * Code Generator - Converts ScaffoldingSpec to executable Node.js code
 *
 * Generates programmatic tool-calling code that uses MCP toolkits
 */
import type { ScaffoldingSpec } from '@roma/schemas';

export class CodeGenerator {
  /**
   * Generate executable Node.js code from ScaffoldingSpec
   */
  generateExecutionCode(spec: ScaffoldingSpec): string {
    const code: string[] = [];

    // Header
    code.push('// Auto-generated execution code');
    code.push('// Feature: ' + spec.metadata.featureName);
    code.push('');

    // Import toolkits
    code.push('import { executeToolByName } from "../mcp-toolkits/index.js";');
    code.push('');

    // Main execution function
    code.push('export async function execute(toolkits) {');
    code.push('  const results = [];');
    code.push('  let stepIndex = 0;');
    code.push('');

    // Generate code for each step
    for (let i = 0; i < spec.steps.length; i++) {
      const step = spec.steps[i];
      code.push(`  // Step ${i + 1}: ${step.description}`);
      code.push(`  stepIndex = ${i};`);

      code.push(...this.generateStepCode(step, i));

      code.push('');
    }

    // Return results
    code.push('  return { success: true, results };');
    code.push('}');

    return code.join('\n');
  }

  /**
   * Generate code for a single step
   */
  private generateStepCode(step: any, index: number): string[] {
    const code: string[] = [];

    switch (step.type) {
      case 'file':
        code.push(...this.generateFileStepCode(step, index));
        break;
      case 'template':
        code.push(...this.generateTemplateStepCode(step, index));
        break;
      case 'command':
        code.push(...this.generateCommandStepCode(step, index));
        break;
      case 'api_call':
        code.push(...this.generateApiCallStepCode(step, index));
        break;
      case 'test':
        code.push(...this.generateTestStepCode(step, index));
        break;
      default:
        code.push(`  // Unknown step type: ${step.type}`);
    }

    return code;
  }

  /**
   * Generate code for file operation step
   */
  private generateFileStepCode(step: any, index: number): string[] {
    const code: string[] = [];
    const op = step.operation;

    if (op.type === 'create' || op.type === 'update') {
      code.push('  {');
      code.push(`    const result = await executeToolByName('file_write', {`);
      code.push(`      path: ${JSON.stringify(op.path)},`);
      code.push(`      content: ${JSON.stringify(op.content || '')}`);
      code.push('    }, toolkits);');
      code.push(`    results.push({ step: ${index}, success: result.success });`);
      code.push('  }');
    } else if (op.type === 'delete') {
      code.push('  {');
      code.push(`    const result = await executeToolByName('file_delete', {`);
      code.push(`      path: ${JSON.stringify(op.path)},`);
      code.push('      recursive: true');
      code.push('    }, toolkits);');
      code.push(`    results.push({ step: ${index}, success: result.success });`);
      code.push('  }');
    }

    return code;
  }

  /**
   * Generate code for template step
   */
  private generateTemplateStepCode(step: any, index: number): string[] {
    const code: string[] = [];

    code.push('  {');
    code.push('    // Render template');
    code.push(`    const renderResult = await executeToolByName('template_render', {`);
    code.push(`      template: ${JSON.stringify(step.templateContent || '')},`);
    code.push(`      vars: ${JSON.stringify(step.templateVars || {})}`);
    code.push('    }, toolkits);');
    code.push('');
    code.push('    // Write rendered output');
    code.push('    if (renderResult.success) {');
    code.push(`      const writeResult = await executeToolByName('file_write', {`);
    code.push(`        path: ${JSON.stringify(step.outputPath)},`);
    code.push('        content: renderResult.output');
    code.push('      }, toolkits);');
    code.push(`      results.push({ step: ${index}, success: writeResult.success });`);
    code.push('    } else {');
    code.push(`      results.push({ step: ${index}, success: false, error: renderResult.error });`);
    code.push('    }');
    code.push('  }');

    return code;
  }

  /**
   * Generate code for command execution step
   */
  private generateCommandStepCode(step: any, index: number): string[] {
    const code: string[] = [];

    // Check if it's an npm command
    if (step.command.startsWith('npm ')) {
      const npmCmd = step.command.replace('npm ', '');
      if (npmCmd === 'install' || npmCmd.startsWith('install ')) {
        code.push('  {');
        code.push(`    const result = await executeToolByName('npm_install', {}, toolkits);`);
        code.push(`    results.push({ step: ${index}, success: result.success });`);
        code.push('  }');
      } else if (npmCmd.startsWith('run ')) {
        const script = npmCmd.replace('run ', '');
        code.push('  {');
        code.push(`    const result = await executeToolByName('npm_run', {`);
        code.push(`      script: ${JSON.stringify(script)}`);
        code.push('    }, toolkits);');
        code.push(`    results.push({ step: ${index}, success: result.success });`);
        code.push('  }');
      }
    } else {
      // Generic command execution
      const [cmd, ...args] = step.command.split(' ');
      code.push('  {');
      code.push(`    const result = await executeToolByName('exec', {`);
      code.push(`      command: ${JSON.stringify(cmd)},`);
      code.push(`      args: ${JSON.stringify(args)}`);
      code.push('    }, toolkits);');
      code.push(`    results.push({ step: ${index}, success: result.success });`);
      code.push('  }');
    }

    return code;
  }

  /**
   * Generate code for API call step
   */
  private generateApiCallStepCode(step: any, index: number): string[] {
    const code: string[] = [];

    code.push('  {');
    code.push(`    // API call to ${step.url}`);
    code.push(`    // Note: Using exec to call curl as placeholder`);
    code.push(`    const result = await executeToolByName('exec', {`);
    code.push(`      command: 'curl',`);
    code.push(`      args: ['-X', ${JSON.stringify(step.method)}, ${JSON.stringify(step.url)}]`);
    code.push('    }, toolkits);');
    code.push(`    results.push({ step: ${index}, success: result.success });`);
    code.push('  }');

    return code;
  }

  /**
   * Generate code for test execution step
   */
  private generateTestStepCode(step: any, index: number): string[] {
    const code: string[] = [];

    code.push('  {');
    code.push(`    const result = await executeToolByName('test_run', {`);
    code.push(`      coverage: false`);
    code.push('    }, toolkits);');
    code.push(`    results.push({ step: ${index}, success: result.success });`);
    code.push('  }');

    return code;
  }
}
