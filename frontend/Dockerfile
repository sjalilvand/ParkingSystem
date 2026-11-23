# ============================================================================
# فرانت‌اند production — دو تارگت بیلد:
#
#   dist-only : dist از قبل روی هاست با Node محلی ساخته شده (UPDATE-AND-RUN.ps1
#               این را خودکار می‌کند و FRONTEND_BUILD_TARGET=dist-only می‌گذارد)
#               → فقط nginx لازم است؛ هیچ تماسی با Docker Hub برای node نیست.
#               ریشهٔ ارور «403 Forbidden برای node:20-alpine» همین‌جا حل می‌شود.
#
#   with-node (پیش‌فرض): بیلد کامل داخل Docker — به node:20-alpine از Docker Hub
#               نیاز دارد. اگر Docker Hub به IP شما 403 بدهد این تارگت کار نمی‌کند.
#
#   ساخت دستی:  npm run build ; docker build -t ps-frontend --target dist-only .
# ============================================================================
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS nginx-base
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

# dist آمادهٔ روی هاست — سبک و بدون وابستگی به Docker Hub
FROM nginx-base AS dist-only
COPY dist /usr/share/nginx/html

# بیلد کامل داخل Docker — تارگت پیش‌فرض (آخرین مرحله)
FROM nginx-base AS with-node
COPY --from=build /app/dist /usr/share/nginx/html
