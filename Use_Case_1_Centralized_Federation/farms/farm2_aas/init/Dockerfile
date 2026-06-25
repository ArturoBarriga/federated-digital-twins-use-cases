# Dockerfile for the AAS initialisation container
FROM alpine:3.18
RUN apk add --no-cache curl bash
WORKDIR /app
CMD ["bash", "/app/init.sh"]
