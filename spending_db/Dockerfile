# Use a base image with both PostgreSQL and Python
FROM postgres:15

# Set environment variables for PostgreSQL
ENV POSTGRES_USER=postgres
ENV POSTGRES_PASSWORD=postgres
ENV POSTGRES_DB=spending_db

# Install Python and required packages
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Flask and psycopg2
RUN pip3 install flask psycopg2-binary

# Create app directory
WORKDIR /app

# Copy files to the container
COPY transactions.csv /transactions.csv
COPY init.sql /docker-entrypoint-initdb.d/
COPY web_service.py /app/
COPY templates/ /app/templates/
COPY start-web.sh /start-web.sh

# Make startup script executable
RUN chmod +x /start-web.sh

# Expose PostgreSQL and web service ports
EXPOSE 5432 5000

# Override the default command to use our custom startup script
CMD ["/start-web.sh"] 