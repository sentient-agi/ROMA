/**
 * Base MCP Toolkit Interface
 *
 * All toolkits must implement this interface to be MCP-compatible
 */
export class BaseToolkit {
    /**
     * Initialize the toolkit (optional)
     */
    async initialize() {
        // Default: no-op
    }
    /**
     * Cleanup resources (optional)
     */
    async cleanup() {
        // Default: no-op
    }
}
//# sourceMappingURL=base-toolkit.js.map