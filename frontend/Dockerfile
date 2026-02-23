FROM node:20-alpine AS build

WORKDIR /app

# Копируем package*.json (package.json и, при наличии, package-lock.json)
COPY package*.json ./

# Установка зависимостей
RUN npm install

# Копируем остальной исходный код
COPY . .

# Сборка фронтенда
RUN npm run build

FROM nginx:alpine

COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

