FROM golang:1.26-bookworm AS bridge
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
ARG CARBONATE_COMMIT=baa9818402e980208ac0041ea6544f3d4683d29d
WORKDIR /src
RUN git clone https://github.com/develonrails/carbonate.git . && git checkout "${CARBONATE_COMMIT}"
COPY carbonate-cli.patch /tmp/carbonate-cli.patch
RUN git apply /tmp/carbonate-cli.patch
RUN CGO_ENABLED=0 go build -trimpath -o /out/carbonate ./cmd/carbonate

FROM python:3.14-slim-bookworm
RUN groupadd -g 10001 calendar && useradd -u 10001 -g calendar -M calendar && mkdir /data /app && chown calendar:calendar /data
COPY --from=bridge /out/carbonate /usr/local/bin/carbonate
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py entrypoint.sh ./
RUN chmod 755 /app/entrypoint.sh
USER 10001:10001
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
