FROM node:latest
WORKDIR /app
COPY . .
RUN npm install
ENV JWT_SECRET=orders-jwt-signing-key-9f8e7d6c
RUN npm run build
EXPOSE 3000
CMD ["node", "dist/main"]
