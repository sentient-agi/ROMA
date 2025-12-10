"""Next.js MCP Server for ROMA.

Provides code generation tools for Next.js applications including:
- Page generation (App Router)
- API route generation
- Component scaffolding
- Layout generation
- Middleware generation
- Server actions
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from roma_dspy.tools.mcp.servers.base import BaseMCPServer, GenerationResult, TemplateResult


class PageConfig(BaseModel):
    """Configuration for Next.js page generation."""

    name: str = Field(..., description="Page name/route (e.g., 'dashboard', 'users/[id]')")
    use_client: bool = Field(False, description="Add 'use client' directive")
    with_loading: bool = Field(False, description="Include loading.tsx")
    with_error: bool = Field(False, description="Include error.tsx")
    with_layout: bool = Field(False, description="Include layout.tsx")


class NextJSMCPServer(BaseMCPServer):
    """MCP Server for Next.js code generation.

    Provides tools for generating Next.js pages, API routes, components,
    layouts, and middleware following Next.js 14+ App Router best practices.
    """

    name = "roma-nextjs-mcp"
    description = "Next.js code generation tools for ROMA"
    version = "1.0.0"

    def _register_tools(self) -> None:
        """Register Next.js generation tools."""
        self._register_tool("generate_page", self.generate_page)
        self._register_tool("generate_api_route", self.generate_api_route)
        self._register_tool("generate_component", self.generate_component)
        self._register_tool("generate_layout", self.generate_layout)
        self._register_tool("generate_middleware", self.generate_middleware)
        self._register_tool("generate_server_action", self.generate_server_action)
        self._register_tool("generate_loading", self.generate_loading)
        self._register_tool("generate_error", self.generate_error)
        self._register_tool("generate_crud_pages", self.generate_crud_pages)

    def generate_page(
        self,
        route: str,
        use_client: bool = False,
        with_params: bool = False,
        with_search_params: bool = False,
        fetch_data: bool = False,
    ) -> TemplateResult:
        """Generate a Next.js page file (App Router).

        Args:
            route: Route path (e.g., 'dashboard', 'users/[id]')
            use_client: Add 'use client' directive for client component
            with_params: Include params for dynamic routes
            with_search_params: Include searchParams
            fetch_data: Include data fetching example

        Returns:
            Generated page file
        """
        page_name = self._route_to_component_name(route)

        directives = "'use client';\n\n" if use_client else ""

        imports = []
        if not use_client:
            imports.append("import { Metadata } from 'next';")

        # Build props interface
        props_parts = []
        if with_params or "[" in route:
            props_parts.append("params: Promise<{ id: string }>")
        if with_search_params:
            props_parts.append("searchParams: Promise<{ [key: string]: string | string[] | undefined }>")

        props_interface = ""
        props_destructure = ""
        if props_parts:
            props_interface = f"""
interface {page_name}Props {{
  {'; '.join(props_parts)};
}}
"""
            props_destructure = f"{{ {', '.join(p.split(':')[0] for p in props_parts)} }}: {page_name}Props"
        else:
            props_destructure = ""

        # Build metadata export
        metadata = ""
        if not use_client:
            metadata = f"""
export const metadata: Metadata = {{
  title: '{page_name}',
  description: '{page_name} page',
}};
"""

        # Build async keyword and data fetching
        async_keyword = "async " if fetch_data and not use_client else ""

        data_fetch = ""
        if fetch_data and not use_client:
            data_fetch = """
  // Fetch data
  const data = await fetch('https://api.example.com/data', {
    cache: 'no-store', // or 'force-cache' for static
  }).then(res => res.json());
"""

        # Build params handling
        params_handling = ""
        if with_params or "[" in route:
            if not use_client:
                params_handling = "\n  const { id } = await params;"

        content = f'''{directives}{chr(10).join(imports)}
{props_interface}{metadata}
export default {async_keyword}function {page_name}Page({props_destructure}) {{{params_handling}{data_fetch}
  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold mb-4">{page_name}</h1>
      <p>Welcome to the {page_name} page.</p>
    </div>
  );
}}
'''

        return TemplateResult(
            filename="page.tsx",
            content=content,
            language="typescript",
            path=f"app/{route}",
            dependencies=["next", "react"],
        )

    def generate_api_route(
        self,
        route: str,
        methods: Optional[List[str]] = None,
        with_validation: bool = False,
        with_auth: bool = False,
    ) -> TemplateResult:
        """Generate a Next.js API route (App Router).

        Args:
            route: API route path (e.g., 'users', 'users/[id]')
            methods: HTTP methods to include (GET, POST, PUT, PATCH, DELETE)
            with_validation: Include Zod validation
            with_auth: Include authentication check

        Returns:
            Generated API route file
        """
        methods = methods or ["GET", "POST"]

        imports = ["import { NextRequest, NextResponse } from 'next/server';"]

        if with_validation:
            imports.append("import { z } from 'zod';")

        validation_schema = ""
        if with_validation:
            validation_schema = """
const schema = z.object({
  name: z.string().min(1),
  email: z.string().email(),
});
"""

        auth_check = ""
        if with_auth:
            auth_check = """
  // Check authentication
  const authHeader = request.headers.get('authorization');
  if (!authHeader?.startsWith('Bearer ')) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
"""

        method_handlers = []
        for method in methods:
            method_handlers.append(self._generate_api_method(method, with_validation, auth_check))

        content = f'''{chr(10).join(imports)}
{validation_schema}
{chr(10).join(method_handlers)}
'''

        return TemplateResult(
            filename="route.ts",
            content=content,
            language="typescript",
            path=f"app/api/{route}",
            dependencies=["next"] + (["zod"] if with_validation else []),
        )

    def _generate_api_method(self, method: str, with_validation: bool, auth_check: str) -> str:
        """Generate an API method handler."""
        method_upper = method.upper()

        if method_upper == "GET":
            return f'''
export async function GET(request: NextRequest) {{{auth_check}
  try {{
    // TODO: Implement GET logic
    return NextResponse.json({{ data: [] }});
  }} catch (error) {{
    return NextResponse.json({{ error: 'Internal Server Error' }}, {{ status: 500 }});
  }}
}}
'''
        elif method_upper == "POST":
            validation = ""
            if with_validation:
                validation = """
    // Validate request body
    const validation = schema.safeParse(body);
    if (!validation.success) {
      return NextResponse.json({ error: validation.error.errors }, { status: 400 });
    }
"""
            return f'''
export async function POST(request: NextRequest) {{{auth_check}
  try {{
    const body = await request.json();
{validation}
    // TODO: Implement POST logic
    return NextResponse.json({{ data: body }}, {{ status: 201 }});
  }} catch (error) {{
    return NextResponse.json({{ error: 'Internal Server Error' }}, {{ status: 500 }});
  }}
}}
'''
        elif method_upper in ["PUT", "PATCH"]:
            return f'''
export async function {method_upper}(request: NextRequest) {{{auth_check}
  try {{
    const body = await request.json();
    // TODO: Implement {method_upper} logic
    return NextResponse.json({{ data: body }});
  }} catch (error) {{
    return NextResponse.json({{ error: 'Internal Server Error' }}, {{ status: 500 }});
  }}
}}
'''
        elif method_upper == "DELETE":
            return f'''
export async function DELETE(request: NextRequest) {{{auth_check}
  try {{
    // TODO: Implement DELETE logic
    return NextResponse.json({{ success: true }});
  }} catch (error) {{
    return NextResponse.json({{ error: 'Internal Server Error' }}, {{ status: 500 }});
  }}
}}
'''
        return ""

    def generate_component(
        self,
        name: str,
        use_client: bool = True,
        with_props: bool = True,
        with_state: bool = False,
        component_type: str = "functional",
    ) -> TemplateResult:
        """Generate a React component for Next.js.

        Args:
            name: Component name (PascalCase)
            use_client: Add 'use client' directive
            with_props: Include props interface
            with_state: Include useState hook
            component_type: 'functional' or 'arrow'

        Returns:
            Generated component file
        """
        class_name = self._to_pascal_case(name)

        directives = "'use client';\n\n" if use_client else ""

        imports = ["import React from 'react';"]
        if with_state:
            imports[0] = "import React, { useState } from 'react';"

        props_interface = ""
        props_param = ""
        if with_props:
            props_interface = f"""
interface {class_name}Props {{
  title?: string;
  children?: React.ReactNode;
}}
"""
            props_param = f"{{ title, children }}: {class_name}Props"

        state_hook = ""
        if with_state:
            state_hook = "\n  const [count, setCount] = useState(0);\n"

        if component_type == "arrow":
            content = f'''{directives}{chr(10).join(imports)}
{props_interface}
const {class_name}: React.FC<{class_name}Props> = ({props_param}) => {{{state_hook}
  return (
    <div className="p-4">
      <h2 className="text-xl font-semibold">{{title || '{class_name}'}}</h2>
      {{children}}
    </div>
  );
}};

export default {class_name};
'''
        else:
            content = f'''{directives}{chr(10).join(imports)}
{props_interface}
export default function {class_name}({props_param}) {{{state_hook}
  return (
    <div className="p-4">
      <h2 className="text-xl font-semibold">{{title || '{class_name}'}}</h2>
      {{children}}
    </div>
  );
}}
'''

        return TemplateResult(
            filename=f"{class_name}.tsx",
            content=content,
            language="typescript",
            path="components",
            dependencies=["react"],
        )

    def generate_layout(
        self,
        route: str = "",
        with_metadata: bool = True,
        with_nav: bool = False,
        with_footer: bool = False,
    ) -> TemplateResult:
        """Generate a Next.js layout file.

        Args:
            route: Route path (empty for root layout)
            with_metadata: Include metadata export
            with_nav: Include navigation component
            with_footer: Include footer component

        Returns:
            Generated layout file
        """
        is_root = route == "" or route == "/"

        imports = ["import type { Metadata } from 'next';"]
        if is_root:
            imports.append("import './globals.css';")
        if with_nav:
            imports.append("import { Navigation } from '@/components/Navigation';")
        if with_footer:
            imports.append("import { Footer } from '@/components/Footer';")

        metadata = ""
        if with_metadata:
            metadata = """
export const metadata: Metadata = {
  title: {
    template: '%s | My App',
    default: 'My App',
  },
  description: 'My Next.js application',
};
"""

        body_content = "{children}"
        if with_nav or with_footer:
            nav = "<Navigation />" if with_nav else ""
            footer = "<Footer />" if with_footer else ""
            body_content = f"""
        {nav}
        <main className="flex-1">{{children}}</main>
        {footer}
"""

        if is_root:
            content = f'''{chr(10).join(imports)}
{metadata}
export default function RootLayout({{
  children,
}}: {{
  children: React.ReactNode;
}}) {{
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col">
        {body_content}
      </body>
    </html>
  );
}}
'''
        else:
            content = f'''{chr(10).join(imports)}
{metadata}
export default function Layout({{
  children,
}}: {{
  children: React.ReactNode;
}}) {{
  return (
    <div className="min-h-screen flex flex-col">
      {body_content}
    </div>
  );
}}
'''

        path = "app" if is_root else f"app/{route}"
        return TemplateResult(
            filename="layout.tsx",
            content=content,
            language="typescript",
            path=path,
            dependencies=["next", "react"],
        )

    def generate_middleware(
        self,
        protected_routes: Optional[List[str]] = None,
        redirect_to: str = "/login",
    ) -> TemplateResult:
        """Generate Next.js middleware for route protection.

        Args:
            protected_routes: Routes that require authentication
            redirect_to: Redirect path for unauthenticated users

        Returns:
            Generated middleware file
        """
        protected_routes = protected_routes or ["/dashboard", "/profile", "/settings"]

        route_checks = " ||\n    ".join([f"pathname.startsWith('{route}')" for route in protected_routes])

        content = f'''import {{ NextResponse }} from 'next/server';
import type {{ NextRequest }} from 'next/server';

export function middleware(request: NextRequest) {{
  const {{ pathname }} = request.nextUrl;

  // Check if route requires authentication
  const isProtectedRoute =
    {route_checks};

  if (isProtectedRoute) {{
    // Check for auth token
    const token = request.cookies.get('auth-token')?.value;

    if (!token) {{
      const url = new URL('{redirect_to}', request.url);
      url.searchParams.set('callbackUrl', pathname);
      return NextResponse.redirect(url);
    }}

    // TODO: Validate token if needed
  }}

  return NextResponse.next();
}}

export const config = {{
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public files (public directory)
     */
    '/((?!_next/static|_next/image|favicon.ico|public).*)',
  ],
}};
'''

        return TemplateResult(
            filename="middleware.ts",
            content=content,
            language="typescript",
            path="",  # Root of project
            dependencies=["next"],
        )

    def generate_server_action(
        self,
        name: str,
        with_validation: bool = True,
        with_revalidation: bool = True,
    ) -> TemplateResult:
        """Generate a Next.js server action.

        Args:
            name: Action name (e.g., 'createUser', 'updatePost')
            with_validation: Include Zod validation
            with_revalidation: Include revalidatePath

        Returns:
            Generated server action file
        """
        action_name = self._to_camel_case(name)

        imports = ["'use server';", ""]
        if with_validation:
            imports.append("import { z } from 'zod';")
        if with_revalidation:
            imports.append("import { revalidatePath } from 'next/cache';")

        validation_schema = ""
        if with_validation:
            validation_schema = f"""
const {action_name}Schema = z.object({{
  name: z.string().min(1, 'Name is required'),
  email: z.string().email('Invalid email'),
}});

type {self._to_pascal_case(name)}Input = z.infer<typeof {action_name}Schema>;
"""

        validation_code = ""
        if with_validation:
            validation_code = f"""
  // Validate input
  const validation = {action_name}Schema.safeParse(data);
  if (!validation.success) {{
    return {{
      success: false,
      errors: validation.error.flatten().fieldErrors,
    }};
  }}
"""

        revalidation_code = ""
        if with_revalidation:
            revalidation_code = """
  // Revalidate the path
  revalidatePath('/');
"""

        content = f'''{chr(10).join(imports)}
{validation_schema}
export async function {action_name}(data: {'FormData | ' + self._to_pascal_case(name) + 'Input' if with_validation else 'FormData'}) {{
  try {{{validation_code}
    // TODO: Implement action logic
    // Example: await db.insert(data);
{revalidation_code}
    return {{ success: true, data: {{'validated' if with_validation else 'data'}} }};
  }} catch (error) {{
    console.error('{action_name} error:', error);
    return {{
      success: false,
      error: 'An unexpected error occurred',
    }};
  }}
}}
'''

        return TemplateResult(
            filename=f"{name}.ts",
            content=content,
            language="typescript",
            path="actions",
            dependencies=["next"] + (["zod"] if with_validation else []),
        )

    def generate_loading(self, route: str = "") -> TemplateResult:
        """Generate a Next.js loading file.

        Args:
            route: Route path

        Returns:
            Generated loading file
        """
        content = '''export default function Loading() {
  return (
    <div className="flex items-center justify-center min-h-[400px]">
      <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary"></div>
    </div>
  );
}
'''

        path = "app" if not route else f"app/{route}"
        return TemplateResult(
            filename="loading.tsx",
            content=content,
            language="typescript",
            path=path,
            dependencies=["react"],
        )

    def generate_error(self, route: str = "", with_reset: bool = True) -> TemplateResult:
        """Generate a Next.js error file.

        Args:
            route: Route path
            with_reset: Include reset button

        Returns:
            Generated error file
        """
        reset_button = ""
        if with_reset:
            reset_button = """
        <button
          onClick={() => reset()}
          className="px-4 py-2 bg-primary text-white rounded hover:bg-primary/90"
        >
          Try again
        </button>"""

        content = f''''use client';

import {{ useEffect }} from 'react';

export default function Error({{
  error,
  reset,
}}: {{
  error: Error & {{ digest?: string }};
  reset: () => void;
}}) {{
  useEffect(() => {{
    console.error(error);
  }}, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
      <h2 className="text-xl font-semibold">Something went wrong!</h2>
      <p className="text-muted-foreground">{{error.message}}</p>{reset_button}
    </div>
  );
}}
'''

        path = "app" if not route else f"app/{route}"
        return TemplateResult(
            filename="error.tsx",
            content=content,
            language="typescript",
            path=path,
            dependencies=["react"],
        )

    def generate_crud_pages(
        self,
        resource: str,
        with_api: bool = True,
        with_actions: bool = True,
    ) -> GenerationResult:
        """Generate complete CRUD pages for a resource.

        Args:
            resource: Resource name (e.g., 'users', 'posts')
            with_api: Include API routes
            with_actions: Include server actions

        Returns:
            All generated files for CRUD operations
        """
        files = []
        all_deps = set()
        singular = resource.rstrip("s")

        # List page
        list_page = self.generate_page(resource, fetch_data=True)
        files.append(list_page)
        all_deps.update(list_page.dependencies)

        # Detail page
        detail_page = self.generate_page(f"{resource}/[id]", with_params=True, fetch_data=True)
        files.append(detail_page)
        all_deps.update(detail_page.dependencies)

        # Create page
        create_page = self.generate_page(f"{resource}/new", use_client=True)
        files.append(create_page)
        all_deps.update(create_page.dependencies)

        # Edit page
        edit_page = self.generate_page(f"{resource}/[id]/edit", use_client=True, with_params=True)
        files.append(edit_page)
        all_deps.update(edit_page.dependencies)

        # Loading states
        loading = self.generate_loading(resource)
        files.append(loading)

        # Error boundary
        error = self.generate_error(resource)
        files.append(error)

        # API routes
        if with_api:
            list_api = self.generate_api_route(resource, methods=["GET", "POST"], with_validation=True)
            files.append(list_api)
            all_deps.update(list_api.dependencies)

            detail_api = self.generate_api_route(
                f"{resource}/[id]", methods=["GET", "PUT", "DELETE"], with_validation=True
            )
            files.append(detail_api)
            all_deps.update(detail_api.dependencies)

        # Server actions
        if with_actions:
            create_action = self.generate_server_action(f"create{self._to_pascal_case(singular)}")
            files.append(create_action)
            all_deps.update(create_action.dependencies)

            update_action = self.generate_server_action(f"update{self._to_pascal_case(singular)}")
            files.append(update_action)
            all_deps.update(update_action.dependencies)

            delete_action = self.generate_server_action(f"delete{self._to_pascal_case(singular)}")
            files.append(delete_action)
            all_deps.update(delete_action.dependencies)

        deps_with_versions = {
            "next": "^14.0.0",
            "react": "^18.0.0",
            "react-dom": "^18.0.0",
            "zod": "^3.22.0",
        }

        instructions = f"""
## {self._to_pascal_case(resource)} CRUD Pages Setup

### Generated Pages:
- `/{resource}` - List all {resource}
- `/{resource}/new` - Create new {singular}
- `/{resource}/[id]` - View {singular} details
- `/{resource}/[id]/edit` - Edit {singular}

### Generated API Routes:
- `GET /api/{resource}` - List all {resource}
- `POST /api/{resource}` - Create new {singular}
- `GET /api/{resource}/[id]` - Get {singular} by ID
- `PUT /api/{resource}/[id]` - Update {singular}
- `DELETE /api/{resource}/[id]` - Delete {singular}

### Server Actions:
- `create{self._to_pascal_case(singular)}` - Create action with validation
- `update{self._to_pascal_case(singular)}` - Update action with validation
- `delete{self._to_pascal_case(singular)}` - Delete action

### Install Dependencies:
```bash
npm install {' '.join(deps_with_versions.keys())}
```
"""

        return GenerationResult(
            files=files,
            instructions=instructions,
            dependencies=deps_with_versions,
        )

    def _to_pascal_case(self, name: str) -> str:
        """Convert name to PascalCase."""
        return "".join(word.capitalize() for word in name.replace("-", "_").split("_"))

    def _to_camel_case(self, name: str) -> str:
        """Convert name to camelCase."""
        pascal = self._to_pascal_case(name)
        return pascal[0].lower() + pascal[1:] if pascal else ""

    def _route_to_component_name(self, route: str) -> str:
        """Convert route to component name."""
        # Remove dynamic segments notation and convert to PascalCase
        clean = route.replace("[", "").replace("]", "").replace("/", "_")
        return self._to_pascal_case(clean)
