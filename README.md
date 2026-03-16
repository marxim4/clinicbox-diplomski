## Requirements

Before running the project make sure the following software is installed:

- Python 3.12 or newer
- Docker
- Docker Compose
- Git


## Project Structure


````
backend/
├ app
│   ├ blueprints
│   ├ services
│   ├ models
│   ├ schemas
│   ├ data_layer
│   ├ enums
│   └ utils
│
├ migrations
├ tests
├ requirements.txt
└ wsgi.py

````


## Running the Project

### 1. Clone the repository

```bash
git clone <repo-url>
cd clinicBox
````

### 2. Start PostgreSQL with Docker

```bash
docker compose up -d db
```

### 3. Create Python virtual environment

```bash
python -m venv .venv
```

Activate the environment.

Windows:

```bash
.venv\Scripts\activate
```

Mac/Linux:

```bash
source .venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r backend/requirements.txt
```

### 5. Configure environment variables

Copy the example environment file:

```bash
cp backend/.env.example backend/.env
```

Adjust values if necessary.

### 6. Run database migrations

```bash
flask --app backend/app db upgrade
```

### 7. Start the API server

```bash
python backend/wsgi.py
```

The API will be available at:

```
http://localhost:5000
```

## API Documentation

Swagger documentation is available at:

```
http://localhost:5000/apidocs
```

## Running Tests

```bash
pytest
```
