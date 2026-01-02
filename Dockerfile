FROM node:18-alpine

WORKDIR /app

# Set permissions for /app directory
RUN chown -R node:node /app

# Switch to non-root user 'node'
USER node

# Copy package.json with correct ownership and install dependencies
COPY --chown=node:node package.json .
RUN npm install

# Copy the rest of the application files with correct ownership
COPY --chown=node:node . .

# Expose Vite default port
EXPOSE 5173

# Start development server
CMD ["npm", "run", "dev", "--", "--host"]