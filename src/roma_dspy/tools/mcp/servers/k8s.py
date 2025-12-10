"""Kubernetes MCP Server for ROMA.

Provides code generation tools for Kubernetes manifests including:
- Deployment generation
- Service generation
- ConfigMap and Secret generation
- Ingress generation
- HPA (Horizontal Pod Autoscaler) generation
- Complete application manifests
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from roma_dspy.tools.mcp.servers.base import BaseMCPServer, GenerationResult, TemplateResult


class K8sConfig(BaseModel):
    """Configuration for Kubernetes generation."""

    app_name: str = Field(..., description="Application name")
    namespace: str = Field("default", description="Kubernetes namespace")
    replicas: int = Field(2, description="Number of replicas")
    port: int = Field(3000, description="Container port")


class K8sMCPServer(BaseMCPServer):
    """MCP Server for Kubernetes manifest generation.

    Provides tools for generating Kubernetes deployment manifests,
    services, configmaps, secrets, ingress, and HPA configurations
    following Kubernetes best practices.
    """

    name = "roma-k8s-mcp"
    description = "Kubernetes manifest generation tools for ROMA"
    version = "1.0.0"

    def _register_tools(self) -> None:
        """Register Kubernetes generation tools."""
        self._register_tool("generate_deployment", self.generate_deployment)
        self._register_tool("generate_service", self.generate_service)
        self._register_tool("generate_configmap", self.generate_configmap)
        self._register_tool("generate_secret", self.generate_secret)
        self._register_tool("generate_ingress", self.generate_ingress)
        self._register_tool("generate_hpa", self.generate_hpa)
        self._register_tool("generate_namespace", self.generate_namespace)
        self._register_tool("generate_pvc", self.generate_pvc)
        self._register_tool("generate_full_app", self.generate_full_app)

    def generate_deployment(
        self,
        app_name: str,
        image: str,
        namespace: str = "default",
        replicas: int = 2,
        port: int = 3000,
        env_vars: Optional[Dict[str, str]] = None,
        env_from_configmap: Optional[str] = None,
        env_from_secret: Optional[str] = None,
        resources: Optional[Dict[str, Any]] = None,
        with_probes: bool = True,
        with_security_context: bool = True,
        labels: Optional[Dict[str, str]] = None,
    ) -> TemplateResult:
        """Generate a Kubernetes Deployment manifest.

        Args:
            app_name: Application name
            image: Container image
            namespace: Kubernetes namespace
            replicas: Number of replicas
            port: Container port
            env_vars: Environment variables
            env_from_configmap: ConfigMap name for env vars
            env_from_secret: Secret name for env vars
            resources: Resource requests/limits
            with_probes: Include liveness/readiness probes
            with_security_context: Include security context
            labels: Additional labels

        Returns:
            Generated Deployment manifest
        """
        labels = labels or {}
        labels.update({
            "app": app_name,
            "app.kubernetes.io/name": app_name,
            "app.kubernetes.io/instance": app_name,
        })

        label_str = "\n".join([f"    {k}: {v}" for k, v in labels.items()])
        selector_labels = f"app: {app_name}"

        # Environment section
        env_section = ""
        if env_vars or env_from_configmap or env_from_secret:
            env_items = []

            if env_vars:
                for key, value in env_vars.items():
                    env_items.append(f'''          - name: {key}
            value: "{value}"''')

            if env_from_configmap:
                env_items.append(f'''          envFrom:
          - configMapRef:
              name: {env_from_configmap}''')

            if env_from_secret:
                env_items.append(f'''          - secretRef:
              name: {env_from_secret}''')

            env_section = f'''
          env:
{chr(10).join(env_items)}'''

        # Resources section
        resources = resources or {
            "requests": {"cpu": "100m", "memory": "128Mi"},
            "limits": {"cpu": "500m", "memory": "512Mi"},
        }
        resources_section = f'''
          resources:
            requests:
              cpu: "{resources['requests']['cpu']}"
              memory: "{resources['requests']['memory']}"
            limits:
              cpu: "{resources['limits']['cpu']}"
              memory: "{resources['limits']['memory']}"'''

        # Probes section
        probes_section = ""
        if with_probes:
            probes_section = f'''
          livenessProbe:
            httpGet:
              path: /health
              port: {port}
            initialDelaySeconds: 30
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health
              port: {port}
            initialDelaySeconds: 5
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 3'''

        # Security context section
        security_section = ""
        if with_security_context:
            security_section = '''
          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL'''

        content = f'''apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_name}
  namespace: {namespace}
  labels:
{label_str}
spec:
  replicas: {replicas}
  selector:
    matchLabels:
      {selector_labels}
  template:
    metadata:
      labels:
{label_str}
    spec:
      containers:
        - name: {app_name}
          image: {image}
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: {port}
              protocol: TCP{env_section}{resources_section}{probes_section}{security_section}
      restartPolicy: Always
'''

        return TemplateResult(
            filename=f"{app_name}-deployment.yaml",
            content=content,
            language="yaml",
            path="k8s",
            dependencies=[],
        )

    def generate_service(
        self,
        app_name: str,
        namespace: str = "default",
        port: int = 3000,
        target_port: Optional[int] = None,
        service_type: str = "ClusterIP",
        labels: Optional[Dict[str, str]] = None,
    ) -> TemplateResult:
        """Generate a Kubernetes Service manifest.

        Args:
            app_name: Application name
            namespace: Kubernetes namespace
            port: Service port
            target_port: Target port (defaults to port)
            service_type: Service type (ClusterIP, NodePort, LoadBalancer)
            labels: Additional labels

        Returns:
            Generated Service manifest
        """
        target_port = target_port or port
        labels = labels or {}
        labels.update({
            "app": app_name,
            "app.kubernetes.io/name": app_name,
        })

        label_str = "\n".join([f"    {k}: {v}" for k, v in labels.items()])

        content = f'''apiVersion: v1
kind: Service
metadata:
  name: {app_name}
  namespace: {namespace}
  labels:
{label_str}
spec:
  type: {service_type}
  ports:
    - port: {port}
      targetPort: {target_port}
      protocol: TCP
      name: http
  selector:
    app: {app_name}
'''

        return TemplateResult(
            filename=f"{app_name}-service.yaml",
            content=content,
            language="yaml",
            path="k8s",
            dependencies=[],
        )

    def generate_configmap(
        self,
        name: str,
        namespace: str = "default",
        data: Optional[Dict[str, str]] = None,
        from_file: Optional[Dict[str, str]] = None,
    ) -> TemplateResult:
        """Generate a Kubernetes ConfigMap manifest.

        Args:
            name: ConfigMap name
            namespace: Kubernetes namespace
            data: Key-value pairs for the ConfigMap
            from_file: Files to include (key: filename, value: content)

        Returns:
            Generated ConfigMap manifest
        """
        data = data or {
            "NODE_ENV": "production",
            "LOG_LEVEL": "info",
        }

        data_section = "\n".join([f"  {k}: \"{v}\"" for k, v in data.items()])

        content = f'''apiVersion: v1
kind: ConfigMap
metadata:
  name: {name}
  namespace: {namespace}
data:
{data_section}
'''

        return TemplateResult(
            filename=f"{name}-configmap.yaml",
            content=content,
            language="yaml",
            path="k8s",
            dependencies=[],
        )

    def generate_secret(
        self,
        name: str,
        namespace: str = "default",
        data: Optional[Dict[str, str]] = None,
        string_data: Optional[Dict[str, str]] = None,
        secret_type: str = "Opaque",
    ) -> TemplateResult:
        """Generate a Kubernetes Secret manifest.

        Args:
            name: Secret name
            namespace: Kubernetes namespace
            data: Base64 encoded data
            string_data: Plain text data (will be base64 encoded by k8s)
            secret_type: Secret type

        Returns:
            Generated Secret manifest
        """
        data_section = ""
        if data:
            data_section = "data:\n" + "\n".join([f"  {k}: {v}" for k, v in data.items()])
        elif string_data:
            string_data = string_data or {
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "API_KEY": "your-api-key-here",
            }
            data_section = "stringData:\n" + "\n".join([f"  {k}: \"{v}\"" for k, v in string_data.items()])
        else:
            data_section = '''stringData:
  DATABASE_URL: "postgresql://user:pass@host:5432/db"
  API_KEY: "your-api-key-here"'''

        content = f'''apiVersion: v1
kind: Secret
metadata:
  name: {name}
  namespace: {namespace}
type: {secret_type}
{data_section}
'''

        return TemplateResult(
            filename=f"{name}-secret.yaml",
            content=content,
            language="yaml",
            path="k8s",
            dependencies=[],
        )

    def generate_ingress(
        self,
        app_name: str,
        namespace: str = "default",
        host: str = "app.example.com",
        service_port: int = 80,
        path: str = "/",
        tls_enabled: bool = True,
        tls_secret_name: Optional[str] = None,
        ingress_class: str = "nginx",
        annotations: Optional[Dict[str, str]] = None,
    ) -> TemplateResult:
        """Generate a Kubernetes Ingress manifest.

        Args:
            app_name: Application name
            namespace: Kubernetes namespace
            host: Ingress hostname
            service_port: Backend service port
            path: URL path
            tls_enabled: Enable TLS
            tls_secret_name: TLS secret name
            ingress_class: Ingress class
            annotations: Additional annotations

        Returns:
            Generated Ingress manifest
        """
        annotations = annotations or {}
        annotations.update({
            "kubernetes.io/ingress.class": ingress_class,
        })

        if tls_enabled:
            annotations["cert-manager.io/cluster-issuer"] = "letsencrypt-prod"

        annotations_str = "\n".join([f"    {k}: \"{v}\"" for k, v in annotations.items()])

        tls_section = ""
        if tls_enabled:
            secret_name = tls_secret_name or f"{app_name}-tls"
            tls_section = f'''
  tls:
    - hosts:
        - {host}
      secretName: {secret_name}'''

        content = f'''apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {app_name}
  namespace: {namespace}
  annotations:
{annotations_str}
spec:
  ingressClassName: {ingress_class}{tls_section}
  rules:
    - host: {host}
      http:
        paths:
          - path: {path}
            pathType: Prefix
            backend:
              service:
                name: {app_name}
                port:
                  number: {service_port}
'''

        return TemplateResult(
            filename=f"{app_name}-ingress.yaml",
            content=content,
            language="yaml",
            path="k8s",
            dependencies=[],
        )

    def generate_hpa(
        self,
        app_name: str,
        namespace: str = "default",
        min_replicas: int = 2,
        max_replicas: int = 10,
        target_cpu: int = 80,
        target_memory: Optional[int] = None,
    ) -> TemplateResult:
        """Generate a Kubernetes HorizontalPodAutoscaler manifest.

        Args:
            app_name: Application name
            namespace: Kubernetes namespace
            min_replicas: Minimum replicas
            max_replicas: Maximum replicas
            target_cpu: Target CPU utilization percentage
            target_memory: Target memory utilization percentage

        Returns:
            Generated HPA manifest
        """
        metrics = [f'''    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {target_cpu}''']

        if target_memory:
            metrics.append(f'''    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: {target_memory}''')

        content = f'''apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {app_name}
  namespace: {namespace}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {app_name}
  minReplicas: {min_replicas}
  maxReplicas: {max_replicas}
  metrics:
{chr(10).join(metrics)}
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 15
        - type: Pods
          value: 4
          periodSeconds: 15
      selectPolicy: Max
'''

        return TemplateResult(
            filename=f"{app_name}-hpa.yaml",
            content=content,
            language="yaml",
            path="k8s",
            dependencies=[],
        )

    def generate_namespace(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> TemplateResult:
        """Generate a Kubernetes Namespace manifest.

        Args:
            name: Namespace name
            labels: Additional labels

        Returns:
            Generated Namespace manifest
        """
        labels = labels or {}
        labels["name"] = name

        label_str = "\n".join([f"    {k}: {v}" for k, v in labels.items()])

        content = f'''apiVersion: v1
kind: Namespace
metadata:
  name: {name}
  labels:
{label_str}
'''

        return TemplateResult(
            filename=f"{name}-namespace.yaml",
            content=content,
            language="yaml",
            path="k8s",
            dependencies=[],
        )

    def generate_pvc(
        self,
        name: str,
        namespace: str = "default",
        storage: str = "10Gi",
        access_modes: Optional[List[str]] = None,
        storage_class: Optional[str] = None,
    ) -> TemplateResult:
        """Generate a Kubernetes PersistentVolumeClaim manifest.

        Args:
            name: PVC name
            namespace: Kubernetes namespace
            storage: Storage size
            access_modes: Access modes
            storage_class: Storage class name

        Returns:
            Generated PVC manifest
        """
        access_modes = access_modes or ["ReadWriteOnce"]
        access_modes_str = "\n".join([f"    - {mode}" for mode in access_modes])

        storage_class_section = ""
        if storage_class:
            storage_class_section = f"\n  storageClassName: {storage_class}"

        content = f'''apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {name}
  namespace: {namespace}
spec:
  accessModes:
{access_modes_str}{storage_class_section}
  resources:
    requests:
      storage: {storage}
'''

        return TemplateResult(
            filename=f"{name}-pvc.yaml",
            content=content,
            language="yaml",
            path="k8s",
            dependencies=[],
        )

    def generate_full_app(
        self,
        app_name: str,
        image: str,
        namespace: str = "default",
        port: int = 3000,
        host: Optional[str] = None,
        replicas: int = 2,
        with_hpa: bool = True,
        with_ingress: bool = True,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> GenerationResult:
        """Generate complete Kubernetes manifests for an application.

        Args:
            app_name: Application name
            image: Container image
            namespace: Kubernetes namespace
            port: Application port
            host: Ingress hostname
            replicas: Number of replicas
            with_hpa: Include HPA
            with_ingress: Include Ingress
            env_vars: Environment variables

        Returns:
            All Kubernetes manifests for the application
        """
        files = []

        # Namespace
        ns = self.generate_namespace(namespace)
        files.append(ns)

        # ConfigMap
        configmap = self.generate_configmap(
            f"{app_name}-config",
            namespace=namespace,
            data=env_vars or {"NODE_ENV": "production"},
        )
        files.append(configmap)

        # Secret
        secret = self.generate_secret(
            f"{app_name}-secret",
            namespace=namespace,
        )
        files.append(secret)

        # Deployment
        deployment = self.generate_deployment(
            app_name=app_name,
            image=image,
            namespace=namespace,
            replicas=replicas,
            port=port,
            env_from_configmap=f"{app_name}-config",
            env_from_secret=f"{app_name}-secret",
            with_probes=True,
            with_security_context=True,
        )
        files.append(deployment)

        # Service
        service = self.generate_service(
            app_name=app_name,
            namespace=namespace,
            port=port,
        )
        files.append(service)

        # HPA
        if with_hpa:
            hpa = self.generate_hpa(
                app_name=app_name,
                namespace=namespace,
                min_replicas=replicas,
                max_replicas=replicas * 5,
            )
            files.append(hpa)

        # Ingress
        if with_ingress and host:
            ingress = self.generate_ingress(
                app_name=app_name,
                namespace=namespace,
                host=host,
                service_port=port,
            )
            files.append(ingress)

        # Generate kustomization.yaml
        kustomization = self._generate_kustomization(
            app_name=app_name,
            files=[f.filename for f in files],
            namespace=namespace,
        )
        files.append(kustomization)

        instructions = f"""
## Kubernetes Deployment for {app_name}

### Prerequisites
- kubectl configured with cluster access
- Namespace: {namespace}
- Container image: {image}

### Deploy
```bash
# Apply all manifests
kubectl apply -f k8s/

# Or use kustomize
kubectl apply -k k8s/
```

### Verify
```bash
# Check deployment status
kubectl get deployments -n {namespace}

# Check pods
kubectl get pods -n {namespace}

# Check services
kubectl get services -n {namespace}

# View logs
kubectl logs -f deployment/{app_name} -n {namespace}
```

### Scale
```bash
# Manual scaling
kubectl scale deployment {app_name} --replicas=5 -n {namespace}

# HPA will auto-scale based on CPU/memory
kubectl get hpa -n {namespace}
```

### Secrets
Update the secret values before deploying:
```bash
# Edit secret
kubectl edit secret {app_name}-secret -n {namespace}

# Or create from literal
kubectl create secret generic {app_name}-secret \\
  --from-literal=DATABASE_URL='your-db-url' \\
  --from-literal=API_KEY='your-api-key' \\
  -n {namespace} --dry-run=client -o yaml | kubectl apply -f -
```
"""

        return GenerationResult(
            files=files,
            instructions=instructions,
            dependencies={},
        )

    def _generate_kustomization(
        self,
        app_name: str,
        files: List[str],
        namespace: str,
    ) -> TemplateResult:
        """Generate kustomization.yaml."""
        resources_str = "\n".join([f"  - {f}" for f in files if f != "kustomization.yaml"])

        content = f'''apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: {namespace}

commonLabels:
  app: {app_name}
  managed-by: kustomize

resources:
{resources_str}
'''

        return TemplateResult(
            filename="kustomization.yaml",
            content=content,
            language="yaml",
            path="k8s",
            dependencies=[],
        )
