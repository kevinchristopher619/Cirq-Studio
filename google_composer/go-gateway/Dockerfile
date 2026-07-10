FROM golang:1.26 AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . ./
RUN CGO_ENABLED=0 GOOS=linux go build -o quantum-gateway .

FROM alpine:3.18
RUN apk --no-cache add ca-certificates
WORKDIR /app
COPY --from=builder /app/quantum-gateway /app/quantum-gateway
COPY firebase-service-account.json /app/firebase-service-account.json
ENV FIREBASE_CREDENTIALS=/app/firebase-service-account.json
EXPOSE 8080
CMD ["/app/quantum-gateway"]
