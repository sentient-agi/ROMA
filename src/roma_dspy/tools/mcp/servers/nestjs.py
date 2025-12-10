"""NestJS MCP Server for ROMA.

Provides code generation tools for NestJS applications including:
- Module scaffolding
- Service generation
- Controller generation
- DTO generation
- Entity/Model generation
- Guard and interceptor templates
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from roma_dspy.tools.mcp.servers.base import BaseMCPServer, GenerationResult, TemplateResult


class ModuleConfig(BaseModel):
    """Configuration for NestJS module generation."""

    name: str = Field(..., description="Module name (e.g., 'users', 'products')")
    include_service: bool = Field(True, description="Include service file")
    include_controller: bool = Field(True, description="Include controller file")
    include_dto: bool = Field(True, description="Include DTO files")
    include_entity: bool = Field(False, description="Include entity file for TypeORM")
    crud_operations: List[str] = Field(
        default_factory=lambda: ["create", "findAll", "findOne", "update", "remove"],
        description="CRUD operations to include",
    )


class NestJSMCPServer(BaseMCPServer):
    """MCP Server for NestJS code generation.

    Provides tools for generating NestJS modules, services, controllers,
    DTOs, entities, guards, and interceptors following NestJS best practices.
    """

    name = "roma-nestjs-mcp"
    description = "NestJS code generation tools for ROMA"
    version = "1.0.0"

    def _register_tools(self) -> None:
        """Register NestJS generation tools."""
        self._register_tool("generate_module", self.generate_module)
        self._register_tool("generate_service", self.generate_service)
        self._register_tool("generate_controller", self.generate_controller)
        self._register_tool("generate_dto", self.generate_dto)
        self._register_tool("generate_entity", self.generate_entity)
        self._register_tool("generate_guard", self.generate_guard)
        self._register_tool("generate_interceptor", self.generate_interceptor)
        self._register_tool("generate_crud_module", self.generate_crud_module)

    def generate_module(
        self,
        name: str,
        imports: Optional[List[str]] = None,
        providers: Optional[List[str]] = None,
        controllers: Optional[List[str]] = None,
        exports: Optional[List[str]] = None,
    ) -> TemplateResult:
        """Generate a NestJS module file.

        Args:
            name: Module name (e.g., 'users')
            imports: Modules to import
            providers: Service providers
            controllers: Controllers to register
            exports: Providers to export

        Returns:
            Generated module file
        """
        class_name = self._to_pascal_case(name)
        imports = imports or []
        providers = providers or [f"{class_name}Service"]
        controllers = controllers or [f"{class_name}Controller"]
        exports = exports or [f"{class_name}Service"]

        import_statements = ["import { Module } from '@nestjs/common';"]

        if providers:
            import_statements.append(
                f"import {{ {', '.join(providers)} }} from './{name}.service';"
            )
        if controllers:
            import_statements.append(
                f"import {{ {', '.join(controllers)} }} from './{name}.controller';"
            )

        imports_section = ""
        if imports:
            imports_section = f"\n  imports: [{', '.join(imports)}],"

        content = f'''{chr(10).join(import_statements)}

@Module({{
  {imports_section}
  controllers: [{', '.join(controllers)}],
  providers: [{', '.join(providers)}],
  exports: [{', '.join(exports)}],
}})
export class {class_name}Module {{}}
'''

        return TemplateResult(
            filename=f"{name}.module.ts",
            content=content,
            language="typescript",
            path=f"src/{name}",
            dependencies=["@nestjs/common"],
        )

    def generate_service(
        self,
        name: str,
        methods: Optional[List[str]] = None,
        inject_repository: bool = False,
        entity_name: Optional[str] = None,
    ) -> TemplateResult:
        """Generate a NestJS service file.

        Args:
            name: Service name (e.g., 'users')
            methods: Method names to include
            inject_repository: Whether to inject a TypeORM repository
            entity_name: Entity name if using repository

        Returns:
            Generated service file
        """
        class_name = self._to_pascal_case(name)
        methods = methods or ["create", "findAll", "findOne", "update", "remove"]
        entity_class = self._to_pascal_case(entity_name or name)

        imports = ["import { Injectable } from '@nestjs/common';"]
        constructor_params = ""
        constructor_body = ""

        if inject_repository:
            imports.append("import { InjectRepository } from '@nestjs/typeorm';")
            imports.append("import { Repository } from 'typeorm';")
            imports.append(f"import {{ {entity_class} }} from './{name}.entity';")
            constructor_params = f"\n    @InjectRepository({entity_class})\n    private readonly {name}Repository: Repository<{entity_class}>,"

        method_implementations = []
        for method in methods:
            method_implementations.append(self._generate_service_method(method, name, inject_repository))

        content = f'''{chr(10).join(imports)}

@Injectable()
export class {class_name}Service {{
  constructor({constructor_params}) {{}}

{chr(10).join(method_implementations)}
}}
'''

        deps = ["@nestjs/common"]
        if inject_repository:
            deps.extend(["@nestjs/typeorm", "typeorm"])

        return TemplateResult(
            filename=f"{name}.service.ts",
            content=content,
            language="typescript",
            path=f"src/{name}",
            dependencies=deps,
        )

    def _generate_service_method(self, method: str, name: str, use_repo: bool) -> str:
        """Generate a service method implementation."""
        class_name = self._to_pascal_case(name)
        singular = name.rstrip("s")

        if method == "create":
            if use_repo:
                return f'''  async create(create{class_name}Dto: Create{class_name}Dto): Promise<{class_name}> {{
    const {singular} = this.{name}Repository.create(create{class_name}Dto);
    return this.{name}Repository.save({singular});
  }}'''
            return f'''  create(create{class_name}Dto: Create{class_name}Dto) {{
    // TODO: Implement create logic
    return 'This action adds a new {singular}';
  }}'''

        elif method == "findAll":
            if use_repo:
                return f'''  async findAll(): Promise<{class_name}[]> {{
    return this.{name}Repository.find();
  }}'''
            return f'''  findAll() {{
    // TODO: Implement findAll logic
    return `This action returns all {name}`;
  }}'''

        elif method == "findOne":
            if use_repo:
                return f'''  async findOne(id: number): Promise<{class_name} | null> {{
    return this.{name}Repository.findOneBy({{ id }});
  }}'''
            return f'''  findOne(id: number) {{
    // TODO: Implement findOne logic
    return `This action returns a #{singular} with id ${{id}}`;
  }}'''

        elif method == "update":
            if use_repo:
                return f'''  async update(id: number, update{class_name}Dto: Update{class_name}Dto): Promise<{class_name} | null> {{
    await this.{name}Repository.update(id, update{class_name}Dto);
    return this.findOne(id);
  }}'''
            return f'''  update(id: number, update{class_name}Dto: Update{class_name}Dto) {{
    // TODO: Implement update logic
    return `This action updates a #{singular} with id ${{id}}`;
  }}'''

        elif method == "remove":
            if use_repo:
                return f'''  async remove(id: number): Promise<void> {{
    await this.{name}Repository.delete(id);
  }}'''
            return f'''  remove(id: number) {{
    // TODO: Implement remove logic
    return `This action removes a #{singular} with id ${{id}}`;
  }}'''

        return f'''  {method}() {{
    // TODO: Implement {method} logic
  }}'''

    def generate_controller(
        self,
        name: str,
        methods: Optional[List[str]] = None,
        api_prefix: Optional[str] = None,
    ) -> TemplateResult:
        """Generate a NestJS controller file.

        Args:
            name: Controller name (e.g., 'users')
            methods: HTTP methods to include
            api_prefix: API route prefix

        Returns:
            Generated controller file
        """
        class_name = self._to_pascal_case(name)
        methods = methods or ["create", "findAll", "findOne", "update", "remove"]
        prefix = api_prefix or name

        imports = [
            "import { Controller, Get, Post, Body, Patch, Param, Delete } from '@nestjs/common';",
            f"import {{ {class_name}Service }} from './{name}.service';",
            f"import {{ Create{class_name}Dto }} from './dto/create-{name}.dto';",
            f"import {{ Update{class_name}Dto }} from './dto/update-{name}.dto';",
        ]

        method_implementations = []
        for method in methods:
            method_implementations.append(self._generate_controller_method(method, name))

        content = f'''{chr(10).join(imports)}

@Controller('{prefix}')
export class {class_name}Controller {{
  constructor(private readonly {name}Service: {class_name}Service) {{}}

{chr(10).join(method_implementations)}
}}
'''

        return TemplateResult(
            filename=f"{name}.controller.ts",
            content=content,
            language="typescript",
            path=f"src/{name}",
            dependencies=["@nestjs/common"],
        )

    def _generate_controller_method(self, method: str, name: str) -> str:
        """Generate a controller method implementation."""
        class_name = self._to_pascal_case(name)

        if method == "create":
            return f'''  @Post()
  create(@Body() create{class_name}Dto: Create{class_name}Dto) {{
    return this.{name}Service.create(create{class_name}Dto);
  }}'''

        elif method == "findAll":
            return f'''  @Get()
  findAll() {{
    return this.{name}Service.findAll();
  }}'''

        elif method == "findOne":
            return f'''  @Get(':id')
  findOne(@Param('id') id: string) {{
    return this.{name}Service.findOne(+id);
  }}'''

        elif method == "update":
            return f'''  @Patch(':id')
  update(@Param('id') id: string, @Body() update{class_name}Dto: Update{class_name}Dto) {{
    return this.{name}Service.update(+id, update{class_name}Dto);
  }}'''

        elif method == "remove":
            return f'''  @Delete(':id')
  remove(@Param('id') id: string) {{
    return this.{name}Service.remove(+id);
  }}'''

        return ""

    def generate_dto(
        self,
        name: str,
        dto_type: str = "create",
        fields: Optional[List[Dict[str, Any]]] = None,
    ) -> TemplateResult:
        """Generate a NestJS DTO file.

        Args:
            name: Entity name (e.g., 'user')
            dto_type: Type of DTO ('create' or 'update')
            fields: List of field definitions

        Returns:
            Generated DTO file
        """
        class_name = self._to_pascal_case(name)
        dto_class = f"{dto_type.capitalize()}{class_name}Dto"

        fields = fields or [
            {"name": "name", "type": "string", "required": True},
            {"name": "email", "type": "string", "required": True},
        ]

        imports = ["import { IsString, IsOptional, IsEmail, IsNotEmpty } from 'class-validator';"]

        field_definitions = []
        for field in fields:
            decorators = []
            if field.get("required", True) and dto_type == "create":
                decorators.append("@IsNotEmpty()")
            else:
                decorators.append("@IsOptional()")

            if field["type"] == "string":
                if "email" in field["name"].lower():
                    decorators.append("@IsEmail()")
                else:
                    decorators.append("@IsString()")

            decorator_str = "\n  ".join(decorators)
            optional = "?" if dto_type == "update" or not field.get("required", True) else ""
            field_definitions.append(
                f"  {decorator_str}\n  {field['name']}{optional}: {field['type']};"
            )

        content = f'''{chr(10).join(imports)}

export class {dto_class} {{
{chr(10).join(field_definitions)}
}}
'''

        filename = f"{dto_type}-{name}.dto.ts"
        return TemplateResult(
            filename=filename,
            content=content,
            language="typescript",
            path=f"src/{name}/dto",
            dependencies=["class-validator", "class-transformer"],
        )

    def generate_entity(
        self,
        name: str,
        fields: Optional[List[Dict[str, Any]]] = None,
        table_name: Optional[str] = None,
    ) -> TemplateResult:
        """Generate a TypeORM entity file.

        Args:
            name: Entity name (e.g., 'user')
            fields: List of field definitions
            table_name: Database table name

        Returns:
            Generated entity file
        """
        class_name = self._to_pascal_case(name)
        table = table_name or f"{name}s"

        fields = fields or [
            {"name": "id", "type": "number", "primary": True},
            {"name": "name", "type": "string"},
            {"name": "email", "type": "string", "unique": True},
            {"name": "createdAt", "type": "Date"},
            {"name": "updatedAt", "type": "Date"},
        ]

        imports = [
            "import { Entity, Column, PrimaryGeneratedColumn, CreateDateColumn, UpdateDateColumn } from 'typeorm';",
        ]

        field_definitions = []
        for field in fields:
            if field.get("primary"):
                field_definitions.append(
                    f"  @PrimaryGeneratedColumn()\n  {field['name']}: {field['type']};"
                )
            elif field["name"] == "createdAt":
                field_definitions.append(
                    f"  @CreateDateColumn()\n  {field['name']}: {field['type']};"
                )
            elif field["name"] == "updatedAt":
                field_definitions.append(
                    f"  @UpdateDateColumn()\n  {field['name']}: {field['type']};"
                )
            else:
                unique = ", { unique: true }" if field.get("unique") else ""
                field_definitions.append(
                    f"  @Column({unique})\n  {field['name']}: {field['type']};"
                )

        content = f'''{chr(10).join(imports)}

@Entity('{table}')
export class {class_name} {{
{chr(10).join(field_definitions)}
}}
'''

        return TemplateResult(
            filename=f"{name}.entity.ts",
            content=content,
            language="typescript",
            path=f"src/{name}",
            dependencies=["typeorm", "@nestjs/typeorm"],
        )

    def generate_guard(
        self,
        name: str,
        guard_type: str = "auth",
    ) -> TemplateResult:
        """Generate a NestJS guard file.

        Args:
            name: Guard name (e.g., 'jwt', 'roles')
            guard_type: Type of guard ('auth', 'roles', 'custom')

        Returns:
            Generated guard file
        """
        class_name = self._to_pascal_case(name)

        if guard_type == "auth":
            content = f'''import {{ Injectable, CanActivate, ExecutionContext, UnauthorizedException }} from '@nestjs/common';
import {{ Observable }} from 'rxjs';

@Injectable()
export class {class_name}Guard implements CanActivate {{
  canActivate(
    context: ExecutionContext,
  ): boolean | Promise<boolean> | Observable<boolean> {{
    const request = context.switchToHttp().getRequest();
    const token = this.extractTokenFromHeader(request);

    if (!token) {{
      throw new UnauthorizedException();
    }}

    // TODO: Implement token validation
    return true;
  }}

  private extractTokenFromHeader(request: any): string | undefined {{
    const [type, token] = request.headers.authorization?.split(' ') ?? [];
    return type === 'Bearer' ? token : undefined;
  }}
}}
'''
        elif guard_type == "roles":
            content = f'''import {{ Injectable, CanActivate, ExecutionContext }} from '@nestjs/common';
import {{ Reflector }} from '@nestjs/core';
import {{ Observable }} from 'rxjs';

@Injectable()
export class {class_name}Guard implements CanActivate {{
  constructor(private reflector: Reflector) {{}}

  canActivate(
    context: ExecutionContext,
  ): boolean | Promise<boolean> | Observable<boolean> {{
    const requiredRoles = this.reflector.getAllAndOverride<string[]>('roles', [
      context.getHandler(),
      context.getClass(),
    ]);

    if (!requiredRoles) {{
      return true;
    }}

    const {{ user }} = context.switchToHttp().getRequest();
    return requiredRoles.some((role) => user.roles?.includes(role));
  }}
}}
'''
        else:
            content = f'''import {{ Injectable, CanActivate, ExecutionContext }} from '@nestjs/common';
import {{ Observable }} from 'rxjs';

@Injectable()
export class {class_name}Guard implements CanActivate {{
  canActivate(
    context: ExecutionContext,
  ): boolean | Promise<boolean> | Observable<boolean> {{
    // TODO: Implement custom guard logic
    return true;
  }}
}}
'''

        return TemplateResult(
            filename=f"{name}.guard.ts",
            content=content,
            language="typescript",
            path="src/common/guards",
            dependencies=["@nestjs/common"],
        )

    def generate_interceptor(
        self,
        name: str,
        interceptor_type: str = "logging",
    ) -> TemplateResult:
        """Generate a NestJS interceptor file.

        Args:
            name: Interceptor name
            interceptor_type: Type of interceptor ('logging', 'transform', 'cache', 'custom')

        Returns:
            Generated interceptor file
        """
        class_name = self._to_pascal_case(name)

        if interceptor_type == "logging":
            content = f'''import {{
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
  Logger,
}} from '@nestjs/common';
import {{ Observable }} from 'rxjs';
import {{ tap }} from 'rxjs/operators';

@Injectable()
export class {class_name}Interceptor implements NestInterceptor {{
  private readonly logger = new Logger({class_name}Interceptor.name);

  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {{
    const request = context.switchToHttp().getRequest();
    const {{ method, url }} = request;
    const now = Date.now();

    this.logger.log(`${{method}} ${{url}} - Request started`);

    return next.handle().pipe(
      tap(() => {{
        this.logger.log(`${{method}} ${{url}} - ${{Date.now() - now}}ms`);
      }}),
    );
  }}
}}
'''
        elif interceptor_type == "transform":
            content = f'''import {{
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
}} from '@nestjs/common';
import {{ Observable }} from 'rxjs';
import {{ map }} from 'rxjs/operators';

export interface Response<T> {{
  data: T;
  statusCode: number;
  timestamp: string;
}}

@Injectable()
export class {class_name}Interceptor<T> implements NestInterceptor<T, Response<T>> {{
  intercept(context: ExecutionContext, next: CallHandler): Observable<Response<T>> {{
    return next.handle().pipe(
      map((data) => ({{
        data,
        statusCode: context.switchToHttp().getResponse().statusCode,
        timestamp: new Date().toISOString(),
      }})),
    );
  }}
}}
'''
        else:
            content = f'''import {{
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
}} from '@nestjs/common';
import {{ Observable }} from 'rxjs';

@Injectable()
export class {class_name}Interceptor implements NestInterceptor {{
  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {{
    // TODO: Implement custom interceptor logic
    return next.handle();
  }}
}}
'''

        return TemplateResult(
            filename=f"{name}.interceptor.ts",
            content=content,
            language="typescript",
            path="src/common/interceptors",
            dependencies=["@nestjs/common", "rxjs"],
        )

    def generate_crud_module(
        self,
        name: str,
        with_entity: bool = True,
        fields: Optional[List[Dict[str, Any]]] = None,
    ) -> GenerationResult:
        """Generate a complete CRUD module with all files.

        Args:
            name: Module name (e.g., 'users')
            with_entity: Include TypeORM entity
            fields: Entity field definitions

        Returns:
            All generated files for the CRUD module
        """
        files = []
        all_deps = set()

        # Generate module
        module = self.generate_module(name)
        files.append(module)
        all_deps.update(module.dependencies)

        # Generate service
        service = self.generate_service(name, inject_repository=with_entity)
        files.append(service)
        all_deps.update(service.dependencies)

        # Generate controller
        controller = self.generate_controller(name)
        files.append(controller)
        all_deps.update(controller.dependencies)

        # Generate DTOs
        create_dto = self.generate_dto(name, "create", fields)
        files.append(create_dto)
        all_deps.update(create_dto.dependencies)

        update_dto = self.generate_dto(name, "update", fields)
        files.append(update_dto)
        all_deps.update(update_dto.dependencies)

        # Generate entity if requested
        if with_entity:
            entity = self.generate_entity(name, fields)
            files.append(entity)
            all_deps.update(entity.dependencies)

        # Build dependency dict with versions
        deps_with_versions = {
            "@nestjs/common": "^10.0.0",
            "@nestjs/core": "^10.0.0",
            "class-validator": "^0.14.0",
            "class-transformer": "^0.5.1",
        }
        if with_entity:
            deps_with_versions.update({
                "@nestjs/typeorm": "^10.0.0",
                "typeorm": "^0.3.17",
            })

        instructions = f"""
## {self._to_pascal_case(name)} Module Setup

1. Import the module in your app.module.ts:
   ```typescript
   import {{ {self._to_pascal_case(name)}Module }} from './{name}/{name}.module';

   @Module({{
     imports: [{self._to_pascal_case(name)}Module],
   }})
   export class AppModule {{}}
   ```

2. If using TypeORM, configure your database connection in app.module.ts

3. Install dependencies:
   ```bash
   npm install {' '.join(deps_with_versions.keys())}
   ```

4. API Endpoints:
   - POST   /{name}      - Create new {name}
   - GET    /{name}      - Get all {name}
   - GET    /{name}/:id  - Get {name} by ID
   - PATCH  /{name}/:id  - Update {name}
   - DELETE /{name}/:id  - Delete {name}
"""

        return GenerationResult(
            files=files,
            instructions=instructions,
            dependencies=deps_with_versions,
        )

    def _to_pascal_case(self, name: str) -> str:
        """Convert name to PascalCase."""
        return "".join(word.capitalize() for word in name.replace("-", "_").split("_"))
