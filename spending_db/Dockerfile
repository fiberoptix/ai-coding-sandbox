# Use the official PostgreSQL image as the base
FROM postgres:15

# Set environment variables
ENV POSTGRES_USER=postgres
ENV POSTGRES_PASSWORD=postgres
ENV POSTGRES_DB=spending_db

# Copy CSV file to the container
COPY transactions.csv /transactions.csv

# Copy the initialization script
COPY init.sql /docker-entrypoint-initdb.d/

# Expose PostgreSQL port
EXPOSE 5432

# Keep the container running
CMD ["postgres"] 