FROM 192.168.55.148:5000/mirror/docker.io/library/golang:1.24-alpine AS builder

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY *.go ./
COPY web/ ./web/
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/marketflow-retireops .

FROM 192.168.55.148:5000/mirror/docker.io/library/alpine:3.21

RUN apk add --no-cache ca-certificates tzdata
COPY --from=builder /out/marketflow-retireops /usr/local/bin/marketflow-retireops

EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/marketflow-retireops"]
