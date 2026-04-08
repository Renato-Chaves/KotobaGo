FROM node:24-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

# Source code is volume-mounted in dev, so no COPY needed here.
# In production you'd add: COPY . .

CMD ["npm", "run", "dev"]
