# Use Python as base image
FROM python:3.9-slim

# Install PostgreSQL and locales
RUN apt-get update && apt-get install -y \
    postgresql \
    postgresql-contrib \
    libpq-dev \
    gcc \
    sudo

# Set locale
RUN localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8
ENV LANG en_US.utf8

# Add PostgreSQL bin to path for convenience
RUN export PGBIN=$(find /usr/lib/postgresql -name bin -type d | head -n 1) && \
    echo "export PATH=$PGBIN:\$PATH" >> /etc/bash.bashrc

# Create PostgreSQL directories
RUN mkdir -p /var/lib/postgresql/data && \
    mkdir -p /var/run/postgresql && \
    mkdir -p /var/log/postgresql && \
    chown -R postgres:postgres /var/lib/postgresql && \
    chown -R postgres:postgres /var/run/postgresql && \
    chown -R postgres:postgres /var/log/postgresql 

# Set working directory
WORKDIR /app

# Create sample data directory
RUN mkdir -p /app/sample_data

# Copy application files
COPY full-app.py /app/
COPY init.sql /app/
COPY templates/ /app/templates/
COPY requirements.txt /app/

# Install dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Set environment variables
ENV POSTGRES_USER=postgres
ENV POSTGRES_PASSWORD=postgres
ENV POSTGRES_DB=financial_analyst
ENV PGDATA=/var/lib/postgresql/data
ENV PYTHONUNBUFFERED=1

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
PGBIN=$(find /usr/lib/postgresql -name bin -type d | head -n 1)\n\
export PATH="$PGBIN:$PATH"\n\
\n\
echo "Starting PostgreSQL..."\n\
if [ -f "$PGDATA/PG_VERSION" ]; then\n\
    # Database is already initialized, just start it\n\
    su postgres -c "pg_ctl -D $PGDATA -l /var/log/postgresql/server.log start"\n\
else\n\
    # Need to initialize database\n\
    mkdir -p $PGDATA && chown postgres:postgres $PGDATA && chmod 700 $PGDATA\n\
    su postgres -c "pg_ctl -D $PGDATA initdb && pg_ctl -D $PGDATA -l /var/log/postgresql/server.log start"\n\
fi\n\
\n\
echo "Checking if database exists..."\n\
su postgres -c "psql -c \\"SELECT 1 FROM pg_database WHERE datname = '"'"'financial_analyst'"'"';\\" | grep -q 1 || \\\n\
               psql -c \\"CREATE DATABASE financial_analyst;\\""\n\
\n\
echo "Initializing database..."\n\
python /app/full-app.py' > /app/start.sh

RUN chmod +x /app/start.sh

# Expose port 5002
EXPOSE 5002

# Command to start the application
CMD ["/app/start.sh"] 