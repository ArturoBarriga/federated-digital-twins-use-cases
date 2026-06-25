FROM alpine:3.19
RUN apk add --no-cache curl bash
COPY init.sh /app/init.sh
RUN chmod +x /app/init.sh
CMD ["bash", "/app/init.sh"]
