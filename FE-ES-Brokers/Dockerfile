FROM node:20-slim

WORKDIR /app

# Copy package list and lockfile
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy application files
COPY . .

# Set the Nitro preset to node-server
ENV NITRO_PRESET=node-server

# Build the project
# RUN npm run build

# Expose port 3000
EXPOSE 3000

# Run the server
CMD ["npm", "run", "dev"]
