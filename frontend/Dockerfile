FROM nginx:1.31-alpine

# Replace the default Nginx config with ours.
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the static HTML pages into Nginx's serving directory.
COPY html/ /usr/share/nginx/html/

EXPOSE 80
