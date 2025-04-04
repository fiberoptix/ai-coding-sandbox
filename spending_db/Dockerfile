# Use Python as base image
FROM python:3.9-slim

# Install PostgreSQL and required packages
RUN apt-get update && apt-get install -y \
    postgresql \
    postgresql-contrib \
    libpq-dev \
    gcc \
    sudo \
    locales \
    && rm -rf /var/lib/apt/lists/*

# Set up the locale
RUN localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8

# Set environment variables
ENV POSTGRES_USER=postgres
ENV POSTGRES_PASSWORD=postgres
ENV POSTGRES_DB=spending_db

# Find and set the PostgreSQL binary path
RUN export PGBIN=$(find /usr/lib/postgresql -name bin -type d | head -n 1) && \
    echo "export PATH=$PGBIN:\$PATH" >> /etc/profile && \
    echo "PostgreSQL binaries: $PGBIN" && \
    echo "export PATH=$PGBIN:\$PATH" >> /root/.bashrc && \
    echo "export PATH=$PGBIN:\$PATH" >> /etc/bash.bashrc

# Set PATH for the current build
ENV PATH="/usr/lib/postgresql/15/bin:${PATH}"

# Set very permissive permissions on PostgreSQL directories
RUN mkdir -p /var/lib/postgresql/data && \
    mkdir -p /var/run/postgresql && \
    mkdir -p /var/log/postgresql && \
    chmod -R 0750 /var/lib/postgresql && \
    chmod -R 0750 /var/run/postgresql && \
    chmod -R 0750 /var/log/postgresql && \
    chown -R postgres:postgres /var/lib/postgresql && \
    chown -R postgres:postgres /var/run/postgresql && \
    chown -R postgres:postgres /var/log/postgresql

# Create app directory
WORKDIR /app

# Create sample data directory
RUN mkdir -p /app/sample_data

# Copy application files
COPY full-app.py /app/
COPY init.sql /app/
COPY templates/ /app/templates/
COPY requirements.txt /app/

# Move transaction.csv to sample_data directory (instead of root)
COPY transactions.csv /app/sample_data/

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Create a startup script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Find PostgreSQL binaries\n\
PGBIN=$(find /usr/lib/postgresql -name bin -type d | head -n 1)\n\
export PATH="$PGBIN:$PATH"\n\
echo "PostgreSQL binaries: $PGBIN"\n\
\n\
# Set correct PostgreSQL permissions\n\
chmod -R 0750 /var/lib/postgresql/data\n\
chmod -R 0750 /var/run/postgresql\n\
chmod -R 0750 /var/log/postgresql\n\
chown -R postgres:postgres /var/lib/postgresql\n\
chown -R postgres:postgres /var/run/postgresql\n\
chown -R postgres:postgres /var/log/postgresql\n\
\n\
# Check for version mismatch and cleanup if needed\n\
if [ -f /var/lib/postgresql/data/PG_VERSION ]; then\n\
    PG_VERSION=$(cat /var/lib/postgresql/data/PG_VERSION)\n\
    INSTALLED_VERSION=$(pg_config --version | grep -oE "[0-9]+" | head -1)\n\
    echo "Data directory PostgreSQL version: $PG_VERSION"\n\
    echo "Installed PostgreSQL version: $INSTALLED_VERSION"\n\
    if [ "$PG_VERSION" != "$INSTALLED_VERSION" ]; then\n\
        echo "PostgreSQL version mismatch. Cleaning data directory..."\n\
        rm -rf /var/lib/postgresql/data/*\n\
    fi\n\
fi\n\
\n\
# Initialize PostgreSQL if needed\n\
if [ ! -s /var/lib/postgresql/data/PG_VERSION ]; then\n\
    echo "Initializing PostgreSQL database..."\n\
    su postgres -c "initdb --locale=en_US.UTF-8 -D /var/lib/postgresql/data"\n\
    echo "listen_addresses = '"'"'*'"'"'" >> /var/lib/postgresql/data/postgresql.conf\n\
    echo "host all all 0.0.0.0/0 md5" >> /var/lib/postgresql/data/pg_hba.conf\n\
fi\n\
\n\
# Start PostgreSQL\n\
echo "Starting PostgreSQL..."\n\
su postgres -c "pg_ctl -D /var/lib/postgresql/data -l /var/log/postgresql/postgresql.log start || true"\n\
\n\
# Wait for PostgreSQL to start\n\
echo "Waiting for PostgreSQL to be ready..."\n\
until su postgres -c "pg_isready -h localhost"; do\n\
    echo "Waiting for PostgreSQL..."\n\
    sleep 1\n\
done\n\
\n\
# Create database and user if they don'"'"'t exist\n\
su postgres -c "psql -c \\"SELECT 1 FROM pg_database WHERE datname = '"'"'spending_db'"'"';\\" | grep -q 1 || \\\n\
               psql -c \\"CREATE DATABASE spending_db;\\""\n\
su postgres -c "psql -c \\"ALTER USER postgres WITH PASSWORD '"'"'postgres'"'"';\\""\n\
\n\
# We no longer automatically import transactions.csv\n\
# Users will need to use the web UI to import data\n\
\n\
# Start the web application\n\
echo "Starting web application..."\n\
cd /app\n\
python full-app.py\n\
' > /app/start.sh

# Make the startup script executable
RUN chmod +x /app/start.sh

# Expose ports
EXPOSE 5001 5432

# Run the startup script
CMD ["/app/start.sh"] 