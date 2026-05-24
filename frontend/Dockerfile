FROM node:20-alpine
WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
EXPOSE 3000

# The Magic Fix: Run npm install AT RUNTIME before booting Vite, 
# ensuring volume mounts cannot hide the dependencies.
CMD sh -c "npm install && npm run dev"
