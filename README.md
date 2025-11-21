# README – Environment Setup for Full-Stack ClinicBox Project

This document lists **all software installations** needed to set up the development environment on any machine.

Use this when preparing a new laptop/PC or reinstalling your environment.

---

#  Development Tools

## IDEs
- **PyCharm Professional** — Python backend development  
- **WebStorm** — React + TypeScript frontend

---

# Backend Requirements

## Python
- **Python 3.14**
- `pip` (included with Python)
- Virtual environment (PyCharm `.venv` is fine)

## Python Packages (via `requirements.txt`)
Backend is built with Flask and SQLAlchemy. Ensure the following are installed:

### Flask ecosystem
- `flask`
- `flask-cors`
- `flask-jwt-extended`

### Database / ORM
- `flask-sqlalchemy`
- `sqlalchemy`
- `flask-migrate`
- `psycopg2-binary` (Postgres driver)

### Utilities
- `python-dotenv`
- `pydantic` (optional but recommended)

---

# Frontend Requirements

## Node.js
- **Node 24**
- `npm` (included)

## Frontend dependencies (installed inside `frontend/`)
- React + TypeScript (Vite template)
- Tailwind CSS
- shadcn/ui
- react-hook-form
- zod
- @tanstack/react-query

---

#  Database & Containers

## Docker
- **Docker Desktop** — must be installed and running

## PostgreSQL
Runs **inside Docker**, not installed on the host:

- Docker image: `postgres:16`
- Run via `docker-compose.yml`:

```bash
docker compose up -d db
```

## DB Client
- **DBeaver** — GUI for inspecting tables, running queries, managing schemas

---

# API Testing
- **Postman** — to test API endpoints manually

---

# Git & Repo Tools
- **Git** (system installation)
- **SourceTree** — Git GUI client

---

# Summary Table

| Category | Tools |
|---------|-------|
| Backend | Python 3.14, Flask, SQLAlchemy, psycopg2-binary |
| Frontend | Node 24, React, Vite, Tailwind, shadcn/ui |
| Containers | Docker Desktop, Postgres 16 (Docker) |
| Database Tools | DBeaver |
| API Testing | Postman |
| IDEs | PyCharm, WebStorm |
| Version Control | Git, SourceTree |

---

#  You're ready to develop on any machine

Just install everything above, clone your repo, create a venv, run:

```bash
docker compose up -d db
```

…and your environment is identical to your main machine.
