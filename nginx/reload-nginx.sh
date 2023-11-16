#!/bin/sh
echo "Testing Nginx configuration"
docker-compose exec -T nginx nginx -t
echo "Reloading Nginx"
docker-compose exec -T -u root nginx nginx -s reload
echo "Nginx reloaded"
