# SaaS Automation Builder

**Interactive CLI tool that generates complete, deployable SaaS applications from simple questionnaires.**

Transform your SaaS idea into production-ready code in minutes, not weeks.

## 🚀 What It Does

The SaaS Automation Builder creates full-stack applications by:

1. **Asking you questions** about your SaaS idea interactively
2. **Analyzing your answers** and asking clarifying follow-ups
3. **Generating complete codebases** with:
   - ✅ Backend API (Node.js/TypeScript with Express)
   - ✅ React frontend (TypeScript + Vite)
   - ✅ PostgreSQL/MongoDB database setup
   - ✅ JWT authentication system
   - ✅ Docker configuration with health checks
   - ✅ Complete documentation

## ⚡ Quick Start

### Installation

```bash
cd saas-automation-builder
npm install
npm run build
```

### Create Your First SaaS

**Interactive Mode** (Recommended):

```bash
npm run dev -- init my-saas.json
```

You'll be asked questions like:
- What is the name of your product?
- What does your product do?
- Who is your target user?
- What are your core features?
- What tech stack do you prefer?
- What database do you need?

The builder validates your answers and asks clarifying questions automatically.

### Build Your Project

```bash
npm run dev -- build my-saas.json
cd output/my-saas
docker-compose up
```

Your SaaS is now running at http://localhost! 🎉

## 📖 Commands

| Command | Description |
|---------|-------------|
| `npm run dev -- init [file]` | Start interactive questionnaire (creates intake form) |
| `npm run dev -- init --manual [file]` | Create blank template instead of interactive mode |
| `npm run dev -- build <file>` | Generate SaaS project from intake form |
| `npm run dev -- list` | List all generated projects |

## 🎯 Generated Project Structure

```
my-saas/
├── backend/               # Node.js/TypeScript API
│   ├── src/
│   │   ├── index.ts      # Express server
│   │   ├── database.ts   # Database connection
│   │   └── routes/       # API endpoints
│   ├── Dockerfile
│   └── package.json
├── frontend/              # React application
│   ├── src/
│   │   ├── App.tsx       # Main component
│   │   └── components/   # UI components
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml     # Docker orchestration
├── package.json           # Workspace config
└── README.md             # Project documentation
```

## ⚙️ What Gets Generated

### Backend Features
- ✅ Express server with TypeScript
- ✅ Database connection (PostgreSQL/MongoDB)
- ✅ Authentication endpoints (`/api/auth/login`, `/api/auth/register`)
- ✅ Feature-specific API routes
- ✅ CORS configuration
- ✅ Environment variable setup
- ✅ Health check endpoint

### Frontend Features
- ✅ React 18 with TypeScript
- ✅ Vite build system
- ✅ React Router setup
- ✅ Login/Home components
- ✅ Nginx production server
- ✅ API proxy configuration

### Docker Setup
- ✅ Multi-service docker-compose
- ✅ Database health checks
- ✅ Hot reload in development
- ✅ Environment variables configured
- ✅ Persistent database volumes

## 📝 Important Notes

### Generated Code is a Starter Template

The builder generates **skeleton code** with TODO comments for you to implement:

```typescript
// Example: Generated auth route
router.post('/register', async (req, res) => {
  const { email, password } = req.body;
  const hashedPassword = await bcrypt.hash(password, 10);
  // TODO: Save user to database  ← You implement this
  res.json({ message: 'User registered successfully' });
});
```

**What's Included:**
- ✅ Project structure
- ✅ Dependencies installed
- ✅ Database connections
- ✅ Route definitions
- ✅ Docker configuration

**What You Need to Add:**
- 📝 Database schemas/models
- 📝 Business logic implementation
- 📝 UI components and styling
- 📝 Error handling
- 📝 Tests

Think of it as a **production-ready scaffold**, not a finished product.

## 🔧 Supported Technologies

### Tech Stacks
- ✅ **Node.js + React** (fully supported, tested)
- ⚠️ **Python + React** (code exists, needs testing)

### Databases
- ✅ **PostgreSQL** (fully supported, tested)
- ⚠️ **MongoDB** (code exists, needs testing)
- 📝 **SQLite** (planned)
- ❌ **MySQL** (not yet supported)

### Authentication
- ✅ **email/password** (JWT-based)
- 📝 **OAuth** (planned)
- 📝 **Magic link** (planned)

### Deployment
- ✅ **Docker/Docker Compose** (fully supported)
- 📝 **Vercel/Netlify** (planned)
- 📝 **Kubernetes** (planned)

## 🐛 Troubleshooting

### Docker Issues

**Database won't connect:**
```bash
# Check if database is healthy
docker ps

# View backend logs
docker logs <container-name>-backend-1

# Restart services
docker-compose down
docker-compose up
```

**Port conflicts:**
```bash
# Change ports in docker-compose.yml
ports:
  - 8080:80     # Frontend (was 80:80)
  - 3001:3000   # Backend (was 3000:3000)
```

### Build Issues

**TypeScript errors:**
```bash
# Rebuild after changes
npm run build
```

**Missing dependencies:**
```bash
# Reinstall
rm -rf node_modules package-lock.json
npm install
```

## 🤝 Contributing

Issues and pull requests are welcome! Please report bugs at:
https://github.com/Mtolivepickle/SaaSideas/issues

## 📄 License

MIT License - See LICENSE file for details

## 🎯 Example Projects

The builder has successfully generated:
- **TaskFlow Pro** - Task management for small teams
- **FitTrack Hub** - Fitness tracking and workout planning

See `test-saas.json` for a complete example intake form.

## 🔗 Links

- **Repository**: https://github.com/Mtolivepickle/SaaSideas
- **Issues**: https://github.com/Mtolivepickle/SaaSideas/issues
- **Documentation**: See this README

---

**Built with ❤️ to help you ship SaaS faster**
