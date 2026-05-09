FROM golang:1.26-bookworm AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY main.go ./

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/app ./main.go

FROM debian:bookworm-slim

WORKDIR /app

COPY --from=builder /out/app /app/app

CMD ["/app/app"]
