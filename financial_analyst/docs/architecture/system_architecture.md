# System Architecture

## Overview

The Financial Analyst application is built using a containerized architecture with three main components:
1. Flask Web Application
2. PostgreSQL Database
3. Docker Container Environment

## Component Details

### 1. Flask Web Application (full-app.py)

#### Core Components
- **Web Server**: Flask development server (port 5002)
- **Template Engine**: Jinja2 for HTML rendering
- **Static Assets**: CSS, JavaScript, and images
- **Session Management**: Flask sessions

#### Key Routes
- `/` → Historical Analysis (main dashboard)
- `/data_import_tagging` → Data import and categorization
- `/monthly_summary` → Monthly financial reports
- `/transaction_summary` → Transaction listing and analysis
- `/historical_analysis` → Historical trends and patterns
- `/budgets` → Budget management interface

#### Application Structure
```
financial_analyst/
├── full-app.py         # Main application code
├── templates/          # HTML templates
│   ├── index.html     # Main template
│   └── confirm_tag_all.html
├── requirements.txt    # Python dependencies
└── init.sql           # Database initialization
```

### 2. PostgreSQL Database

#### Configuration
- Host: localhost
- Port: 5432
- User: postgres
- Password: postgres
- Database: financial_analyst

#### Tables
1. **records_history**
   ```sql
   CREATE TABLE records_history (
       id SERIAL PRIMARY KEY,
       date TEXT,
       description TEXT,
       vendor TEXT,
       amount TEXT,
       tag TEXT,
       imported_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   )
   ```

2. **tags**
   ```sql
   CREATE TABLE tags (
       id SERIAL PRIMARY KEY,
       description TEXT UNIQUE,
       tag TEXT
   )
   ```

3. **records_imported**
   ```sql
   CREATE TABLE records_imported (
       id SERIAL PRIMARY KEY,
       date TEXT,
       description TEXT,
       vendor TEXT,
       amount TEXT
   )
   ```

4. **budgets**
   ```sql
   CREATE TABLE budgets (
       id SERIAL PRIMARY KEY,
       tag TEXT UNIQUE,
       monthly_amount NUMERIC(10,2),
       created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   )
   ```

### 3. Docker Container Environment

#### Container Configuration
- Base Image: python:3.9-slim
- Exposed Ports: 5002 (app), 5432 (database)
- Working Directory: /app
- Environment Variables:
  - POSTGRES_USER=postgres
  - POSTGRES_PASSWORD=postgres
  - POSTGRES_DB=financial_analyst
  - PGDATA=/var/lib/postgresql/data
  - PYTHONUNBUFFERED=1

#### Container Services
1. **PostgreSQL Service**
   - Initialization script: init.sql
   - Data persistence: Docker volume
   - Automatic startup and initialization

2. **Application Service**
   - Python dependencies installation
   - Application startup script
   - Database connection management
   - Error handling and logging

## Build System

### Build Process
1. Container stops and cleanup
2. Build number increment
3. Docker image build
4. Container startup
5. Database initialization
6. Application startup

### Build Scripts
- `run-docker.sh`: Main build and deployment script
- Commands:
  - `start`: Start existing container
  - `stop`: Stop running container
  - `rebuild`: Full rebuild
  - `bb`: Stop, build, and start (with build increment)

## Deployment

### Local Deployment
```bash
./run-docker.sh bb
```

### Remote Deployment
```bash
cd deploy && ./deploy.sh
```

## Quality Assurance

### QA Process
1. Automated testing via qa_test.sh
2. HTTP endpoint validation
3. Database connectivity checks
4. Data integrity verification
5. Performance monitoring

### Monitoring
- Container health checks
- Database connection status
- Response time measurements
- Error log analysis

## Security

### Data Protection
- Containerized environment
- Database password protection
- Input validation
- Error handling

### Access Control
- Local network access only
- Database port restrictions
- Container isolation
- Secure configuration defaults

## Error Handling

### Application Errors
- Exception catching and logging
- User-friendly error messages
- Database connection retry logic
- Transaction rollback on failure

### System Errors
- Container health monitoring
- Database connection validation
- Resource usage tracking
- Log rotation and management

## Performance

### Optimization
- Database connection pooling
- Query optimization
- Caching where appropriate
- Resource management

### Monitoring
- Response time tracking
- Database query performance
- Container resource usage
- Error rate monitoring

## Dependencies

### Python Packages
- Flask
- psycopg2
- psycopg2-binary
- Other requirements in requirements.txt

### System Requirements
- Docker
- Docker Compose
- Python 3.9+
- PostgreSQL 12+

## Future Architecture Considerations

### Scalability
- Load balancing capability
- Database replication
- Caching layer
- API rate limiting

### Security Enhancements
- SSL/TLS implementation
- Authentication system
- Role-based access control
- Enhanced data encryption

### Performance Improvements
- Query optimization
- Connection pooling
- Asset optimization
- Caching strategy

### Monitoring Enhancements
- Metrics collection
- Performance tracking
- Error reporting
- Usage analytics 