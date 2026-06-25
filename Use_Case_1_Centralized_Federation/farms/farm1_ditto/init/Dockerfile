# Dockerfile for the Ditto initialisation container
# Runs a bash script once (set -e) to create the policy + digital-twin thing
# on the Eclipse Ditto Gateway via its REST API.
FROM alpine:3.18
RUN apk add --no-cache curl bash
WORKDIR /app
CMD ["bash", "/app/init.sh"]
